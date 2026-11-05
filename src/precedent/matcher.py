"""Which precedent, if any, decides a case. Deterministic and order-independent.

Every condition is true, false or unknown. Unknown is never treated as false:
a rule that could match once a missing field is known asks for that field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from precedent.models import Rule, evaluate_condition

MATCH = "match"
CONFLICT = "conflict"
MISSING = "missing_information"
NEAR_MISS = "near_miss"
NONE = "none"


@dataclass
class RuleEvaluation:
    rule: Rule
    conditions: dict[str, bool | None]

    @property
    def failed(self) -> list[str]:
        return [f for f, ok in self.conditions.items() if ok is False]

    @property
    def unknown(self) -> list[str]:
        return [f for f, ok in self.conditions.items() if ok is None]


@dataclass
class MatchResult:
    result: str
    outcome: str | None = None
    cited: Rule | None = None
    matching: list[Rule] = field(default_factory=list)
    near_misses: list[RuleEvaluation] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    could_match: list[Rule] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "outcome": self.outcome,
            "cited": self.cited.ref if self.cited else None,
            "matching": [r.ref for r in self.matching],
            "near_misses": [
                {"rule": e.rule.ref, "title": e.rule.title, "outcome": e.rule.outcome, "failed": e.failed}
                for e in self.near_misses
            ],
            "missing_fields": self.missing_fields,
            "could_match": [r.ref for r in self.could_match],
        }


def _specificity(rule: Rule) -> tuple[int, int, int]:
    # Most conditions first; ties go to the lowest id, then the latest version.
    return (-len(rule.conditions), int(rule.id.split("-")[1]), -rule.version)


def evaluate(rule: Rule, fields: dict[str, Any]) -> RuleEvaluation:
    return RuleEvaluation(
        rule=rule,
        conditions={name: evaluate_condition(ops, fields.get(name)) for name, ops in rule.conditions.items()},
    )


def match(fields: dict[str, Any], rules: list[Rule]) -> MatchResult:
    evaluations = [evaluate(rule, fields) for rule in rules]
    matching = sorted((e.rule for e in evaluations if all(e.conditions.values())), key=_specificity)
    could_match = sorted(
        (e.rule for e in evaluations if not e.failed and e.unknown),
        key=_specificity,
    )
    near = sorted(
        (e for e in evaluations if len(e.failed) == 1 and not e.unknown),
        key=lambda e: _specificity(e.rule),
    )

    if matching:
        outcomes = {r.outcome for r in matching}
        # A rule that might also apply once a field is known, with a different
        # outcome, would turn this into a conflict: ask instead of guessing.
        disagreeing = [r for r in could_match if r.outcome not in outcomes]
        if len(outcomes) > 1:
            return MatchResult(CONFLICT, matching=matching, near_misses=near)
        if disagreeing:
            missing = sorted({f for r in disagreeing for f in evaluate(r, fields).unknown})
            return MatchResult(MISSING, matching=matching, could_match=disagreeing, missing_fields=missing)
        return MatchResult(MATCH, outcome=matching[0].outcome, cited=matching[0], matching=matching)

    if could_match:
        missing = sorted({f for r in could_match for f in evaluate(r, fields).unknown})
        return MatchResult(MISSING, could_match=could_match, missing_fields=missing, near_misses=near)
    if near:
        return MatchResult(NEAR_MISS, near_misses=near)
    return MatchResult(NONE)
