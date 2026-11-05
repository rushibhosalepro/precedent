"""The demo's three flows, end to end through the CLI, plus every refusal
that keeps them honest."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from precedent.cli import main
from tests.conftest import TEAMMATE

SEED = Path(__file__).resolve().parent.parent / "seed" / "cases"


def cli(capsys, *args):
    code = main([str(a) for a in args])
    out = capsys.readouterr().out
    try:
        return code, json.loads(out)
    except json.JSONDecodeError:
        return code, out


@pytest.fixture
def engine(workspace, capsys):
    code, out = cli(capsys, "init", "--config", workspace["config"], "--seed", SEED)
    assert code == 0, out
    assert out["imported_cases"] == 42
    return workspace


def new_case(capsys, msg, **fields):
    base = {"order_id": "4821", "amount": 64, "days_since_purchase": 17, "item_state": "unopened"}
    return cli(
        capsys, "--as", "clerk", "case", "new", "--type", "refund", "--source-msg", msg,
        "--requested-by-id", TEAMMATE, "--requested-by-name", "sam", "--fields", json.dumps({**base, **fields}),
    )


def teach_p001(capsys, msgs):
    """Flow 1: no precedent → manager decides → rule drafted, backtested, adopted."""
    _, case = new_case(capsys, "$req1")
    case_id = case["case"]["id"]
    _, matched = cli(capsys, "--as", "judge", "match", case_id)
    assert matched["result"] == "none"
    approve = next(o for o in matched["options"] if o["outcome"] == "approve")
    msgs.say("$ok1", f"{approve['reply']} and make it a rule: unopened up to 30 days")
    code, decided = cli(capsys, "--as", "judge", "decide", case_id, "--outcome", "approve", "--under", "manual", "--approval-msg", "$ok1")
    assert code == 0, decided

    code, draft = cli(
        capsys, "--as", "auditor", "rule", "draft", "--from", case_id, "--title", "Refund unopened items up to 30 days",
        "--outcome", "approve", "--conditions", json.dumps({"item_state": {"eq": "unopened"}, "days_since_purchase": {"max": 30}}),
    )
    assert code == 0, draft
    rule_id = draft["rule"]["id"]
    code, backtest = cli(capsys, "--as", "auditor", "rule", "backtest", rule_id)
    assert code == 0, backtest
    msgs.say("$adopt1", backtest["adopt_reply"])
    code, adopted = cli(capsys, "--as", "auditor", "rule", "adopt", rule_id, "--approval-msg", "$adopt1")
    assert code == 0, adopted
    return case_id, rule_id, backtest["report"]


def test_three_demo_flows(engine, capsys):
    msgs = engine["messages"]
    _, rule_id, report = teach_p001(capsys, msgs)
    assert report["total"] == 43  # 42 seeded + the case just decided
    assert len(report["unresolved"]) == 2
    assert sum(not c["agrees"] for c in report["newly_covered"]) == 3  # the three late denials

    # Flow 2: a similar case is proposed under the new rule.
    _, case = new_case(capsys, "$req2", days_since_purchase=22, order_id="5102")
    _, matched = cli(capsys, "--as", "judge", "match", case["case"]["id"])
    assert matched["result"] == "match" and matched["cited"] == f"{rule_id}@1"
    msgs.say("$ok2", matched["options"][0]["reply"])
    code, decided = cli(capsys, "--as", "judge", "decide", case["case"]["id"], "--outcome", "approve", "--under", f"{rule_id}@1", "--approval-msg", "$ok2")
    assert code == 0 and decided["under"] == f"{rule_id}@1"

    # Flow 3: opened item: a near miss, never stretched to fit.
    _, case = new_case(capsys, "$req3", item_state="opened", days_since_purchase=22, order_id="5110")
    _, matched = cli(capsys, "--as", "judge", "match", case["case"]["id"])
    assert matched["result"] == "near_miss"
    assert matched["near_misses"][0]["failed"] == ["item_state"]

    _, stats = cli(capsys, "--as", "judge", "stats")
    assert stats["live_decided_under_a_rule"] == 1
    code, ledger = cli(capsys, "--as", "auditor", "ledger")
    assert f"**{rule_id}@1**" in ledger


def test_approval_refusals(engine, capsys):
    msgs = engine["messages"]
    _, case = new_case(capsys, "$req1")
    case_id = case["case"]["id"]
    _, matched = cli(capsys, "--as", "judge", "match", case_id)
    reply = next(o for o in matched["options"] if o["outcome"] == "approve")["reply"]

    def decide(msg):
        return cli(capsys, "--as", "judge", "decide", case_id, "--outcome", "approve", "--under", "manual", "--approval-msg", msg)

    msgs.say("$sam", reply, sender=TEAMMATE)
    assert decide("$sam")[0] == 3  # not an approver

    msgs.say("$agent", reply, sender_kind="agent")
    assert decide("$agent")[0] == 3  # agents cannot approve

    msgs.say("$wrongref", reply[:-6] + "000000")
    code, out = decide("$wrongref")
    assert code == 3 and "does not match" in out["message"]

    msgs.say("$deny", reply.replace("approve", "deny"))
    assert decide("$deny")[0] == 3  # says deny, command says approve

    msgs.say("$early", reply, timestamp_ms=1)
    assert decide("$early")[0] == 3  # sent before the proposal

    msgs.say("$ok", reply)
    assert decide("$ok")[0] == 0
    assert decide("$ok")[0] == 3  # already decided, and already spent


def test_a_stale_reference_is_refused_after_the_case_changes(engine, capsys):
    msgs = engine["messages"]
    _, case = new_case(capsys, "$req1")
    case_id = case["case"]["id"]
    _, first = cli(capsys, "--as", "judge", "match", case_id)
    old_reply = next(o for o in first["options"] if o["outcome"] == "approve")["reply"]
    cli(capsys, "--as", "judge", "match", case_id)  # proposed again: version moves on
    msgs.say("$old", old_reply)
    code, out = cli(capsys, "--as", "judge", "decide", case_id, "--outcome", "approve", "--under", "manual", "--approval-msg", "$old")
    assert code == 3 and "changed since it was shown" in out["message"]


def test_adoption_is_refused_when_the_policy_moved_after_the_backtest(engine, capsys):
    msgs = engine["messages"]
    case_id, _, _ = teach_p001(capsys, msgs)
    code, draft = cli(
        capsys, "--as", "auditor", "rule", "draft", "--from", case_id, "--title", "Damaged up to 60",
        "--outcome", "approve", "--conditions", json.dumps({"item_state": {"eq": "damaged"}, "days_since_purchase": {"max": 60}}),
    )
    _, backtest = cli(capsys, "--as", "auditor", "rule", "backtest", draft["rule"]["id"])
    # Another rule is adopted first.
    code, other = cli(
        capsys, "--as", "auditor", "rule", "draft", "--from", case_id, "--title", "Opened up to 14",
        "--outcome", "approve", "--conditions", json.dumps({"item_state": {"eq": "opened"}, "days_since_purchase": {"max": 14}}),
    )
    _, other_bt = cli(capsys, "--as", "auditor", "rule", "backtest", other["rule"]["id"])
    msgs.say("$a", other_bt["adopt_reply"])
    assert cli(capsys, "--as", "auditor", "rule", "adopt", other["rule"]["id"], "--approval-msg", "$a")[0] == 0
    msgs.say("$b", backtest["adopt_reply"])
    code, out = cli(capsys, "--as", "auditor", "rule", "adopt", draft["rule"]["id"], "--approval-msg", "$b")
    assert code == 3 and "backtest" in out["message"]


def test_agent_reported_approvals_are_refused_unless_the_config_allows_them(engine, capsys):
    _, case = new_case(capsys, "$req1")
    case_id = case["case"]["id"]
    _, matched = cli(capsys, "--as", "judge", "match", case_id)
    reply = next(o for o in matched["options"] if o["outcome"] == "approve")["reply"]
    entry = {"id": "$agentcopy", "kind": "message", "sender": "@slack_priya:switch.test", "body": reply, "timestamp": 4_102_444_800_000}
    args = ("--as", "judge", "decide", case_id, "--outcome", "approve", "--under", "manual", "--approval-msg", "$agentcopy", "--approval-entry", json.dumps(entry))
    code, out = cli(capsys, *args)
    assert code == 3 and "does not allow" in out["message"]

    config_path = engine["home"] / "precedent.config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["agent_reported_approvals"] = True
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    subprocess.run(["git", "-C", str(engine["home"]), "commit", "-qam", "allow agent-reported approvals"], check=True)
    assert cli(capsys, *args)[0] == 0
    _, shown = cli(capsys, "--as", "judge", "case", "show", case_id)
    assert shown["history"][-1]["verified_via"] == "agent_reported"


def test_types_lists_the_fields_the_clerk_needs(engine, capsys):
    code, out = cli(capsys, "--as", "clerk", "types")
    assert code == 0
    assert out["refund"]["item_state"]["values"] == ["unopened", "opened", "damaged"]


def test_roles_are_enforced(engine, capsys):
    _, case = new_case(capsys, "$req1")
    code, out = cli(capsys, "--as", "clerk", "match", case["case"]["id"])
    assert code == 3 and "judge" in out["message"]
    code, _ = cli(capsys, "match", case["case"]["id"])
    assert code == 3


def test_duplicate_request_messages_make_one_case(engine, capsys):
    _, first = new_case(capsys, "$req1")
    _, again = new_case(capsys, "$req1")
    assert again["duplicate"] and again["case"]["id"] == first["case"]["id"]


def test_missing_required_fields_are_reported(engine, capsys):
    code, out = cli(
        capsys, "--as", "clerk", "case", "new", "--type", "refund", "--source-msg", "$x",
        "--requested-by-id", TEAMMATE, "--requested-by-name", "sam", "--fields", json.dumps({"order_id": "1", "amount": 5}),
    )
    assert code == 2 and "days_since_purchase" in out["message"]


def test_invented_operators_are_rejected(engine, capsys):
    msgs = engine["messages"]
    case_id, _, _ = teach_p001(capsys, msgs)
    code, out = cli(
        capsys, "--as", "auditor", "rule", "draft", "--from", case_id, "--title", "x", "--outcome", "approve",
        "--conditions", json.dumps({"amount": {"roughly": 50}}),
    )
    assert code == 2 and "unknown operator" in out["message"]


def test_a_hand_edited_rule_stops_everything(engine, capsys):
    msgs = engine["messages"]
    _, rule_id, _ = teach_p001(capsys, msgs)
    path = engine["home"] / "precedents" / f"{rule_id}.v1.yaml"
    rule = yaml.safe_load(path.read_text(encoding="utf-8"))
    rule["conditions"]["days_since_purchase"]["max"] = 365
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    code, out = cli(capsys, "--as", "judge", "stats")
    assert code == 4 and "outside the engine" in out["message"]


def test_every_transition_is_a_commit(engine, capsys):
    teach_p001(capsys, engine["messages"])
    log = subprocess.run(["git", "-C", str(engine["home"]), "log", "--format=%s"], capture_output=True, text=True).stdout
    assert "adopted by" in log and "via msg $adopt1" in log
