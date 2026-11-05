"""Replay history under today's policy (A) and today's policy plus a draft (B).

Adoption applies to new cases only. A past decision that the draft would have
decided differently is reported as information, never as a mistake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from precedent.matcher import CONFLICT, MATCH, MISSING, evaluate, match
from precedent.models import Case, Rule, short_hash

LOW_COVERAGE = 0.8


def policy_hash(rules: list[Rule]) -> str:
    """Identifies an active rule set. A backtest is only valid for the set it ran on."""
    return short_hash(sorted((r.content() for r in rules), key=lambda c: (c["id"], c["version"])), 12)


@dataclass
class Backtest:
    rule: str
    policy_hash: str
    total: int
    unresolved: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    newly_covered: list[dict[str, Any]] = field(default_factory=list)
    changed: list[dict[str, Any]] = field(default_factory=list)
    new_conflicts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def evaluated(self) -> int:
        return self.total - len(self.unresolved)

    @property
    def coverage(self) -> float:
        return self.evaluated / self.total if self.total else 0.0

    @property
    def blocks_adoption(self) -> bool:
        return bool(self.new_conflicts)

    def summary(self) -> str:
        line = (
            f"Historical cases {self.total} · evaluated {self.evaluated} ({self.coverage:.0%}) · "
            f"unresolved {len(self.unresolved)} · newly covered {len(self.newly_covered)} · "
            f"changed {len(self.changed)} · new conflicts {len(self.new_conflicts)}"
        )
        if self.total and self.coverage < LOW_COVERAGE:
            line = f"WARNING: only {self.coverage:.0%} of history could be evaluated. " + line
        return line

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "policy_hash": self.policy_hash,
            "total": self.total,
            "evaluated": self.evaluated,
            "coverage": round(self.coverage, 3),
            "unresolved": self.unresolved,
            "unchanged": len(self.unchanged),
            "newly_covered": self.newly_covered,
            "changed": self.changed,
            "new_conflicts": self.new_conflicts,
            "blocks_adoption": self.blocks_adoption,
            "summary": self.summary(),
            "note": "Adoption applies to new cases only; past decisions are not changed.",
        }


def run_backtest(draft: Rule, active: list[Rule], cases: list[Case]) -> Backtest:
    # A new version replaces the one it supersedes, in B only.
    replaced = draft.supersedes
    base = [r for r in active if r.applies_to == draft.applies_to]
    proposed = [r for r in base if r.ref != replaced] + [draft]
    report = Backtest(rule=draft.ref, policy_hash=policy_hash(active), total=0)

    for case in cases:
        if case.type != draft.applies_to:
            continue
        decision = case.decision()
        if decision is None:
            continue
        report.total += 1
        if evaluate(draft, case.fields).unknown:
            report.unresolved.append(case.id)
            continue
        before, after = match(case.fields, base), match(case.fields, proposed)
        human = decision.get("outcome")
        if after.result == CONFLICT and before.result != CONFLICT:
            report.new_conflicts.append({"case": case.id, "rules": [r.ref for r in after.matching]})
        elif after.result == MATCH and before.result != MATCH:
            report.newly_covered.append(
                {"case": case.id, "would_be": after.outcome, "human_decided": human, "agrees": after.outcome == human}
            )
        elif after.result == MATCH and before.result == MATCH and after.outcome != before.outcome:
            report.changed.append({"case": case.id, "was": before.outcome, "would_be": after.outcome})
        elif after.result == MISSING and before.result != MISSING:
            report.unresolved.append(case.id)
        else:
            report.unchanged.append(case.id)
    return report
