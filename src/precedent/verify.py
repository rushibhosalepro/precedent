"""Approvals: what a person must type, and the checks the engine makes on it.

Every proposal carries a reference: a short hash of exactly what is being
approved (the case version and outcome, or the rule content and the policy it
was backtested against). The approver quotes it, and the engine recomputes it
from current state, so an approval can never be replayed onto a different
version, outcome or rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from precedent.config import Config
from precedent.errors import Refused
from precedent.models import Case, Rule, short_hash

_APPROVAL = re.compile(
    r"(?<![\w-])(approve|deny|adopt|retire)\s+([CP]-\d{3,})\s+#([0-9a-f]{6})(?![0-9a-f])",
    re.IGNORECASE,
)


def decision_ref(case: Case, outcome: str, under: str) -> str:
    return short_hash({"action": "decide", "case": case.id, "version": case.version, "outcome": outcome, "under": under})


def adopt_ref(rule: Rule, policy: str) -> str:
    return short_hash({"action": "adopt", "rule": rule.content(), "policy": policy})


def retire_ref(rule: Rule) -> str:
    return short_hash({"action": "retire", "rule": rule.content()})


def reply_line(verb: str, object_id: str, ref: str) -> str:
    return f"{verb} {object_id} #{ref}"


@dataclass(frozen=True)
class Approval:
    message_id: str
    sender_id: str
    sender_name: str
    timestamp_ms: int


def verify_approval(
    entry: dict[str, Any],
    *,
    config: Config,
    message_id: str,
    verb: str,
    object_id: str,
    ref: str,
    not_before_ms: int | None,
    used: dict[str, Any],
) -> Approval:
    """Accept `entry` as a person's approval of `verb object_id #ref`, or refuse.

    `entry` is the message as Switch returned it, never as an agent described it.
    """
    if entry.get("id") != message_id:
        raise Refused("The message Switch returned is not the one named")
    if message_id in used:
        raise Refused(f"Approval message {message_id} was already used for {used[message_id].get('action')}")
    if entry.get("kind") != "message":
        raise Refused("An approval must be a chat message")
    if entry.get("sender_kind") in ("agent", "platform") or entry.get("on_behalf_of"):
        raise Refused("An approval must come from a person, not an agent or Switch itself")

    sender_id = str(entry.get("sender") or "")
    approver = config.approver(sender_id)
    if approver is None:
        name = entry.get("sender_name") or sender_id
        raise Refused(f"{name} is not an approver; approvers: {', '.join(a.name for a in config.approvers)}")

    found = [m for m in _APPROVAL.finditer(str(entry.get("body") or ""))]
    if len(found) != 1:
        raise Refused(
            f"The message must contain exactly one approval line like `{reply_line(verb, object_id, ref)}`"
        )
    said_verb, said_object, said_ref = (g.lower() if i != 1 else g.upper() for i, g in enumerate(found[0].groups()))
    if said_verb != verb or said_object != object_id:
        raise Refused(f"The message says `{said_verb} {said_object}`, not `{verb} {object_id}`")
    if said_ref != ref:
        raise Refused(
            f"The reference #{said_ref} does not match what is being approved now (#{ref}); "
            "the proposal changed since it was shown. Ask again with the current reference."
        )

    timestamp = int(entry.get("timestamp") or 0)
    if not_before_ms is not None and timestamp < not_before_ms:
        raise Refused("The approval was sent before the proposal it refers to")
    return Approval(message_id=message_id, sender_id=sender_id, sender_name=approver.name, timestamp_ms=timestamp)
