"""Generate the historical refund cases the demo starts from.

The manager decided these by hand, from a policy that lived only in her head
and was applied a little inconsistently, which is the problem Precedent solves:
  damaged            approve up to 60 days
  unopened           approve up to 30 days (but 3 late ones were denied)
  opened             approve up to 14 days, deny after
Two old cases were logged before item_state was recorded, so a backtest has
something honest to report as unresolved.

Run: uv run python scripts/make_seed.py
"""

from __future__ import annotations

import random
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent.parent / "seed" / "cases"
REASONS = ["changed mind", "wrong size", "arrived late", "not as described", "gift duplicate", None]
PEOPLE = ["sam", "ana", "lee", "ravi"]


def decide(state: str | None, days: int, index: int) -> str:
    if state == "damaged":
        return "approve" if days <= 60 else "deny"
    if state == "unopened":
        if days <= 14:
            return "approve"
        if days <= 30:
            return "deny" if index in (4, 11, 19) else "approve"
        return "deny"
    if state == "opened":
        return "approve" if days <= 14 else "deny"
    return "approve" if days <= 7 else "deny"


def main() -> None:
    rng = random.Random(7)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("C-*.yaml"):
        old.unlink()
    for index in range(1, 43):
        state = None if index in (2, 27) else rng.choice(["unopened", "unopened", "opened", "damaged"])
        days = rng.randint(1, 45)
        if index in (4, 11, 19):
            state, days = "unopened", rng.randint(15, 30)
        fields = {
            "order_id": str(4000 + index * 17),
            "amount": rng.choice([19, 24, 31, 45, 64, 89, 120, 199, 249]),
            "days_since_purchase": days,
        }
        if state is not None:
            fields["item_state"] = state
        reason = rng.choice(REASONS)
        if reason:
            fields["reason"] = reason
        day = 1 + index % 28
        case = {
            "id": f"C-{index:03d}",
            "type": "refund",
            "version": 2,
            "source_msg": None,
            "requested_by": {"id": "seed", "name": rng.choice(PEOPLE)},
            "created_at": f"2026-09-{day:02d}T10:00:00Z",
            "fields": fields,
            "history": [
                {"at": f"2026-09-{day:02d}T10:00:00Z", "event": "created"},
                {
                    "at": f"2026-09-{day:02d}T11:00:00Z",
                    "event": "decided",
                    "outcome": decide(state, days, index),
                    "under": "manual",
                    "by": "seed",
                    "by_name": "priya",
                    "approval_msg": None,
                },
            ],
        }
        (OUT / f"{case['id']}.yaml").write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
    print(f"wrote 42 cases to {OUT}")


if __name__ == "__main__":
    main()
