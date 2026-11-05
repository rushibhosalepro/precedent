from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from precedent.config import parse_config
from precedent.models import Rule

APPROVER = "@slack_priya:switch.test"
TEAMMATE = "@slack_sam:switch.test"

CONFIG: dict[str, Any] = {
    "approvers": [{"id": APPROVER, "name": "priya"}],
    "currency": "INR",
    "switch": {"room_id": "!room:switch.test"},
    "offline_approvals": True,
    "types": {
        "refund": {
            "fields": {
                "order_id": {"type": "string", "required": True},
                "amount": {"type": "number", "required": True},
                "days_since_purchase": {"type": "integer", "required": True},
                "item_state": {"type": "enum", "values": ["unopened", "opened", "damaged"], "required": True},
                "reason": {"type": "string", "required": False},
            }
        }
    },
}


@pytest.fixture
def config():
    return parse_config(CONFIG)


def make_rule(rule_id: str, conditions: dict[str, Any], outcome: str = "approve", *, version: int = 1, status: str = "active") -> Rule:
    return Rule(
        id=rule_id, version=version, status=status, title=rule_id, applies_to="refund",
        conditions=conditions, outcome=outcome, source_case=None,
    )


class Messages:
    """A fake room: what `read_context` would return, written to a JSON file
    the engine reads with offline approvals on."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: list[dict[str, Any]] = []
        self._save()

    def say(self, message_id: str, body: str, *, sender: str = APPROVER, kind: str = "message", timestamp_ms: int = 4_102_444_800_000, **extra: Any) -> str:
        self.entries.append({"id": message_id, "kind": kind, "sender": sender, "sender_name": sender, "body": body, "timestamp": timestamp_ms, **extra})
        self._save()
        return message_id

    def _save(self) -> None:
        self.path.write_text(json.dumps({"threads": [{"root": e, "replies": []} for e in self.entries]}), encoding="utf-8")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    config_path = tmp_path / "precedent.config.yaml"
    config_path.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    messages = Messages(tmp_path / "messages.json")
    monkeypatch.setenv("PRECEDENT_OFFLINE_MESSAGES", str(messages.path))
    monkeypatch.setenv("PRECEDENT_HOME", str(tmp_path / "state"))
    return {"config": config_path, "messages": messages, "home": tmp_path / "state", "root": tmp_path}
