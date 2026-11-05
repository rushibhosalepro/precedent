"""Rehearse the demo's three flows without Switch.

Builds a throwaway state repository with offline approvals, then plays the
Clerk, the Judge, the Auditor and Priya through the real CLI, printing what
each would say in the room. Use it to check the engine end to end, and as the
fallback for the demo video if the live room misbehaves.

Run: uv run python scripts/rehearse.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRIYA = "@rehearsal_priya:switch.local"
SAM = "@rehearsal_sam:switch.local"


class Room:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: list[dict] = []
        self.clock = 4_102_444_800_000  # far future, after every proposal
        self._save()

    def say(self, who: str, sender: str, body: str) -> str:
        self.clock += 1000
        message_id = f"$msg{len(self.entries) + 1}"
        self.entries.append({"id": message_id, "kind": "message", "sender": sender, "sender_name": who, "body": body, "timestamp": self.clock})
        self._save()
        print(f"\n  {who:>8} │ {body}")
        return message_id

    def _save(self) -> None:
        self.path.write_text(json.dumps({"threads": [{"root": e, "replies": []} for e in self.entries]}), encoding="utf-8")


def engine(home: Path, env: dict, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "precedent.cli", "--home", str(home), *args],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT,
    )
    try:
        out = json.loads(result.stdout)
    except json.JSONDecodeError:
        out = {"text": result.stdout}
    if result.returncode != 0:
        print(f"           engine refused ({result.returncode}): {out.get('message', result.stderr)}")
    out["_code"] = result.returncode
    return out


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="precedent-rehearsal-"))
    home = work / "state"
    room = Room(work / "room.json")
    config = yaml.safe_load((ROOT / "precedent.config.yaml").read_text(encoding="utf-8"))
    config["approvers"] = [{"id": PRIYA, "name": "priya"}]
    config["switch"] = {"room_id": "!rehearsal"}
    config["offline_approvals"] = True
    (work / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    env = {**os.environ, "PRECEDENT_OFFLINE_MESSAGES": str(room.path)}

    init = engine(home, env, "init", "--config", str(work / "config.yaml"), "--seed", str(ROOT / "seed" / "cases"))
    print(f"State: {home} ({init['imported_cases']} historical cases)")

    def clerk(text: str, fields: dict) -> str:
        msg = room.say("sam", SAM, text)
        case = engine(home, env, "--as", "clerk", "case", "new", "--type", "refund", "--source-msg", msg,
                      "--requested-by-id", SAM, "--requested-by-name", "sam", "--fields", json.dumps(fields))["case"]
        f = case["fields"]
        room.say("Clerk", "@clerk", f"{case['id']} · refund · INR {f['amount']} · {f['days_since_purchase']} days · {f['item_state']}. Sent to the Judge.")
        return case["id"]

    def judge(case_id: str) -> dict:
        m = engine(home, env, "--as", "judge", "match", case_id)
        lines = {
            "match": f"{m['cited']} applies: {m['outcome']}.",
            "near_miss": "No rule applies. Nearly: " + "; ".join(f"{n['rule']} ({n['title']}) fails on {', '.join(n['failed'])}" for n in m["near_misses"]) + ".",
            "none": "No rule covers this yet.",
            "conflict": f"Rules disagree: {', '.join(m['matching'])}.",
            "missing_information": f"Need: {', '.join(m['missing_fields'])}.",
        }
        replies = " or ".join(f"`{o['reply']}`" for o in m["options"])
        room.say("Judge", "@judge", f"@priya {lines[m['result']]} Reply {replies}.")
        return m

    def decide(case_id: str, option: dict, extra: str = "") -> None:
        msg = room.say("priya", PRIYA, option["reply"] + extra)
        d = engine(home, env, "--as", "judge", "decide", case_id, "--outcome", option["outcome"], "--under", option["under"], "--approval-msg", msg)
        if d["_code"] == 0:
            room.say("Judge", "@judge", f"{case_id} {d['outcome']}d by {d['by']} under {d['under']}.")

    print("\n── Flow 1: no precedent, so the room is taught ─────────────────────")
    c1 = clerk("@clerk refund for order 4821, INR 64, unopened, bought 17 days ago", {"order_id": "4821", "amount": 64, "days_since_purchase": 17, "item_state": "unopened"})
    m1 = judge(c1)
    decide(c1, next(o for o in m1["options"] if o["outcome"] == "approve"), " and make it a rule: unopened items up to 30 days")
    draft = engine(home, env, "--as", "auditor", "rule", "draft", "--from", c1, "--title", "Refund unopened items up to 30 days",
                   "--outcome", "approve", "--conditions", json.dumps({"item_state": {"eq": "unopened"}, "days_since_purchase": {"max": 30}}))
    rule_id = draft["rule"]["id"]
    bt = engine(home, env, "--as", "auditor", "rule", "backtest", rule_id)
    report = bt["report"]
    disagree = [c["case"] for c in report["newly_covered"] if not c["agrees"]]
    room.say("Auditor", "@auditor", f"Draft {rule_id}: item_state is unopened, and days_since_purchase at most 30 → approve.\n"
             f"           {report['summary']}\n"
             f"           Past decisions it would have made differently: {', '.join(disagree) or 'none'}. Applies to new cases only.\n"
             f"           @priya reply `{bt['adopt_reply']}` to adopt.")
    adopt_msg = room.say("priya", PRIYA, bt["adopt_reply"])
    if engine(home, env, "--as", "auditor", "rule", "adopt", rule_id, "--approval-msg", adopt_msg)["_code"] == 0:
        room.say("Auditor", "@auditor", f"{rule_id}@1 is active. Ledger updated.")

    print("\n── Flow 2: a similar case, decided under the new rule ─────────────")
    c2 = clerk("@clerk order 5102, INR 31, still sealed, 22 days", {"order_id": "5102", "amount": 31, "days_since_purchase": 22, "item_state": "unopened"})
    m2 = judge(c2)
    decide(c2, m2["options"][0])

    print("\n── Flow 3: a near miss is never stretched to fit ───────────────────")
    c3 = clerk("@clerk order 5110, INR 64, opened, 22 days", {"order_id": "5110", "amount": 64, "days_since_purchase": 22, "item_state": "opened"})
    judge(c3)

    print("\n── And one attempt that must fail: Sam approving his own request ──")
    m3_option = engine(home, env, "--as", "judge", "match", c3)["options"][0]
    msg = room.say("sam", SAM, m3_option["reply"])
    engine(home, env, "--as", "judge", "decide", c3, "--outcome", m3_option["outcome"], "--under", m3_option["under"], "--approval-msg", msg)

    print("\n── Ledger ──────────────────────────────────────────────────────────")
    print(engine(home, env, "--as", "auditor", "ledger")["text"])
    print("── Stats ───────────────────────────────────────────────────────────")
    stats = engine(home, env, "--as", "judge", "stats")
    print(json.dumps({k: v for k, v in stats.items() if k != "_code"}, indent=2))
    log = subprocess.run(["git", "-C", str(home), "log", "--oneline"], capture_output=True, text=True, encoding="utf-8").stdout
    print("── Audit trail (git log) ───────────────────────────────────────────")
    print(log)


if __name__ == "__main__":
    main()
