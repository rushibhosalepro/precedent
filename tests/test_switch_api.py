import json

import httpx
import pytest

from precedent.config import parse_config
from precedent.errors import NotFound, Refused, SwitchUnavailable
from precedent.models import Case
from precedent.switch_api import SwitchMessages
from precedent.verify import decision_ref, verify_approval
from tests.conftest import CONFIG

CONTEXT = {
    "threads": [
        {"root": {"id": "$root", "kind": "message", "sender": "@a:x", "body": "refund pls"},
         "replies": [{"id": "$reply", "kind": "message", "sender": "@priya:x", "body": "approve C-001 #abcdef"}]},
    ],
    "truncated": False,
}


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def post(url, **kwargs):
        seen.append({"url": url, **kwargs})
        return seen_response[0]

    seen_response = [httpx.Response(200, json=CONTEXT)]
    monkeypatch.setattr(httpx, "post", post)
    return seen, seen_response


def test_reads_a_reply_from_switch_with_the_agents_token(tmp_path, calls):
    seen, _ = calls
    creds = tmp_path / "judge.json"
    creds.write_text(json.dumps({"env": {"SWITCH_API_ENDPOINT": "http://switch.test/", "SWITCH_AGENT_ID": "ag1", "SWITCH_API_TOKEN": "t0k"}}))
    entry = SwitchMessages.from_credentials(creds).fetch("!room", "$reply")
    assert entry["sender"] == "@priya:x"
    assert seen[0]["url"] == "http://switch.test/agents/ag1/ops/read_context"
    assert seen[0]["headers"] == {"Authorization": "Bearer t0k"}
    assert seen[0]["json"]["room_id"] == "!room"
    assert seen[0]["follow_redirects"] is False


def test_the_real_shape_of_a_room_entry_verifies(config, calls):
    """Shapes taken from a live server: a person's sender id, a kickoff posted by
    Switch on someone's behalf, and an agent."""
    person = "@switch-slack-00000000-0000-0000-0000-000000000000-priya:localhost"
    live = parse_config({**CONFIG, "approvers": [{"id": person, "name": "priya"}]})
    case = Case(id="C-001", type="refund", version=2, source_msg=None, requested_by={"id": "x", "name": "x"}, created_at="2026-11-05T00:00:00Z", fields={})
    ref = decision_ref(case, "approve", "manual")
    base = {"id": "sw_abc", "kind": "message", "timestamp": 1793859065919, "body": f"approve C-001 #{ref}"}
    args = dict(config=live, message_id="sw_abc", verb="approve", object_id="C-001", ref=ref, not_before_ms=None, used={})
    assert verify_approval({**base, "sender": person, "sender_name": "priya"}, **args).sender_name == "priya"
    with pytest.raises(Refused):
        verify_approval({**base, "sender": "@switch-admin:localhost", "sender_kind": "platform", "on_behalf_of": "priya"}, **args)
    with pytest.raises(Refused):
        verify_approval({**base, "sender": "@switch-agent-a618bbe0:localhost"}, **args)


def test_an_operation_result_envelope_is_unwrapped(calls):
    _, response = calls
    response[0] = httpx.Response(200, json={"result": CONTEXT})
    assert SwitchMessages("http://s", "a", "t").fetch("!r", "$root")["body"] == "refund pls"


def test_missing_message_and_errors_are_loud(calls):
    _, response = calls
    client = SwitchMessages("http://s", "a", "t")
    with pytest.raises(NotFound):
        client.fetch("!r", "$nope")
    response[0] = httpx.Response(403, text="not a member")
    with pytest.raises(SwitchUnavailable, match="403"):
        client.fetch("!r", "$root")
    response[0] = httpx.Response(200, json={"weird": True})
    with pytest.raises(SwitchUnavailable, match="shape"):
        client.fetch("!r", "$root")
