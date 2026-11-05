"""Cases and rules, parsed strictly: an unknown key or operator is an error,
so a model drafting a rule cannot invent semantics the matcher does not have."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from precedent.config import CaseType, Config
from precedent.errors import SchemaError

OPERATORS = ("eq", "in", "min", "max")
OUTCOMES = ("approve", "deny")
RULE_STATUSES = ("draft", "active", "retired")

CASE_ID = re.compile(r"^C-\d{3,}$")
RULE_ID = re.compile(r"^P-\d{3,}$")


def canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def short_hash(data: Any, length: int = 6) -> str:
    return hashlib.sha256(canonical(data).encode()).hexdigest()[:length]


def _check_keys(where: str, data: Any, allowed: set[str], required: set[str]) -> None:
    if not isinstance(data, dict):
        raise SchemaError(f"{where} must be a mapping")
    unknown = set(data) - allowed
    if unknown:
        raise SchemaError(f"{where} has unknown keys: {', '.join(sorted(unknown))}")
    missing = required - set(data)
    if missing:
        raise SchemaError(f"{where} is missing: {', '.join(sorted(missing))}")


# ── conditions ────────────────────────────────────────────────────────────────


def validate_conditions(conditions: Any, case_type: CaseType) -> dict[str, dict[str, Any]]:
    """Check a rule's conditions against the case type's fields.

    Each condition is `{field: {op: value, ...}}` with ops from OPERATORS;
    `min`/`max` only on numbers, `eq`/`in` values must be values the field can
    hold. Returns a normalised copy (`in` lists sorted, so hashes are stable).
    """
    if not isinstance(conditions, dict) or not conditions:
        raise SchemaError("conditions must be a non-empty mapping of field to operators")
    normalised: dict[str, dict[str, Any]] = {}
    for field_name, ops in conditions.items():
        spec = case_type.fields.get(field_name)
        if spec is None:
            raise SchemaError(
                f"condition on unknown field {field_name!r}; "
                f"{case_type.name} has: {', '.join(case_type.fields)}"
            )
        if not isinstance(ops, dict) or not ops:
            raise SchemaError(f"condition {field_name!r} must map operators to values")
        out: dict[str, Any] = {}
        for op, value in ops.items():
            if op not in OPERATORS:
                raise SchemaError(f"unknown operator {op!r} on {field_name!r}; allowed: {', '.join(OPERATORS)}")
            if op in ("min", "max"):
                if spec.type not in ("number", "integer"):
                    raise SchemaError(f"{op!r} only applies to numbers, not {field_name!r}")
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise SchemaError(f"{field_name}.{op} must be a number")
                out[op] = value
            elif op == "eq":
                if not spec.accepts(value):
                    raise SchemaError(f"{field_name}.eq = {value!r} is not a valid {spec.type}")
                out[op] = value
            else:
                if not isinstance(value, list) or not value:
                    raise SchemaError(f"{field_name}.in must be a non-empty list")
                for item in value:
                    if not spec.accepts(item):
                        raise SchemaError(f"{field_name}.in has {item!r}, not a valid {spec.type}")
                out[op] = sorted(value, key=canonical)
        if "min" in out and "max" in out and out["min"] > out["max"]:
            raise SchemaError(f"{field_name}: min is greater than max")
        normalised[field_name] = out
    return normalised


def evaluate_condition(ops: dict[str, Any], value: Any) -> bool | None:
    """True, False, or None when the value is unknown. Unknown is never False."""
    if value is None:
        return None
    for op, expected in ops.items():
        if op == "eq" and value != expected:
            return False
        if op == "in" and value not in expected:
            return False
        if op == "min" and value < expected:
            return False
        if op == "max" and value > expected:
            return False
    return True


# ── rules ─────────────────────────────────────────────────────────────────────


@dataclass
class Rule:
    id: str
    version: int
    status: str
    title: str
    applies_to: str
    conditions: dict[str, dict[str, Any]]
    outcome: str
    source_case: str | None
    supersedes: str | None = None  # "P-007@1" when this version replaces another
    auto: bool = False
    backtest: dict[str, Any] | None = None
    adopted: dict[str, Any] | None = None
    retired: dict[str, Any] | None = None
    drafted: dict[str, Any] | None = None

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def content(self) -> dict[str, Any]:
        """What the rule says, without its lifecycle. Approvals bind to this."""
        return {
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "applies_to": self.applies_to,
            "conditions": self.conditions,
            "outcome": self.outcome,
            "supersedes": self.supersedes,
        }

    def to_dict(self) -> dict[str, Any]:
        data = {
            **self.content(),
            "status": self.status,
            "source_case": self.source_case,
            "auto": self.auto,
            "drafted": self.drafted,
            "backtest": self.backtest,
            "adopted": self.adopted,
            "retired": self.retired,
        }
        return {k: v for k, v in data.items() if v is not None}


_RULE_KEYS = {
    "id", "version", "status", "title", "applies_to", "conditions", "outcome",
    "source_case", "supersedes", "auto", "backtest", "adopted", "retired", "drafted",
}


def parse_rule(data: Any, config: Config) -> Rule:
    _check_keys("rule", data, _RULE_KEYS, {"id", "version", "status", "title", "applies_to", "conditions", "outcome"})
    if not RULE_ID.match(str(data["id"])):
        raise SchemaError(f"rule id {data['id']!r} must look like P-007")
    if not isinstance(data["version"], int) or data["version"] < 1:
        raise SchemaError("rule version must be a positive integer")
    if data["status"] not in RULE_STATUSES:
        raise SchemaError(f"rule status must be one of {', '.join(RULE_STATUSES)}")
    if data["outcome"] not in OUTCOMES:
        raise SchemaError(f"rule outcome must be one of {', '.join(OUTCOMES)}")
    if data.get("auto"):
        raise SchemaError("auto-apply is not supported in this version; set auto: false")
    case_type = config.case_type(data["applies_to"])
    return Rule(
        id=data["id"],
        version=data["version"],
        status=data["status"],
        title=str(data["title"]),
        applies_to=data["applies_to"],
        conditions=validate_conditions(data["conditions"], case_type),
        outcome=data["outcome"],
        source_case=data.get("source_case"),
        supersedes=data.get("supersedes"),
        auto=False,
        backtest=data.get("backtest"),
        adopted=data.get("adopted"),
        retired=data.get("retired"),
        drafted=data.get("drafted"),
    )


# ── cases ─────────────────────────────────────────────────────────────────────


def validate_fields(fields: Any, case_type: CaseType, *, require_all: bool) -> dict[str, Any]:
    """Check case fields against the type. `require_all=False` is for history
    imported from before the schema, where a missing field is data, not error."""
    if not isinstance(fields, dict):
        raise SchemaError("fields must be a mapping")
    unknown = set(fields) - set(case_type.fields)
    if unknown:
        raise SchemaError(f"unknown fields for {case_type.name}: {', '.join(sorted(unknown))}")
    missing = [
        name for name, spec in case_type.fields.items()
        if spec.required and fields.get(name) is None
    ]
    if missing and require_all:
        raise SchemaError(f"missing required fields: {', '.join(missing)}")
    for name, value in fields.items():
        if value is not None and not case_type.fields[name].accepts(value):
            spec = case_type.fields[name]
            allowed = f" ({', '.join(spec.values)})" if spec.values else ""
            raise SchemaError(f"field {name!r} = {value!r} is not a valid {spec.type}{allowed}")
    return {k: v for k, v in fields.items() if v is not None}


@dataclass
class Case:
    id: str
    type: str
    version: int
    source_msg: str | None
    requested_by: dict[str, str]
    created_at: str
    fields: dict[str, Any]
    history: list[dict[str, Any]] = field(default_factory=list)

    def decision(self) -> dict[str, Any] | None:
        """The latest decision event, if any. History is append-only, so an
        override is a later event, never an edit."""
        for event in reversed(self.history):
            if event.get("event") == "decided":
                return event
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "version": self.version,
            "source_msg": self.source_msg,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "fields": self.fields,
            "history": self.history,
        }


_CASE_KEYS = {"id", "type", "version", "source_msg", "requested_by", "created_at", "fields", "history"}


def parse_case(data: Any, config: Config) -> Case:
    _check_keys("case", data, _CASE_KEYS, {"id", "type", "version", "requested_by", "created_at", "fields"})
    if not CASE_ID.match(str(data["id"])):
        raise SchemaError(f"case id {data['id']!r} must look like C-031")
    case_type = config.case_type(data["type"])
    history = data.get("history") or []
    if not isinstance(history, list):
        raise SchemaError("case history must be a list")
    return Case(
        id=data["id"],
        type=data["type"],
        version=int(data["version"]),
        source_msg=data.get("source_msg"),
        requested_by=dict(data["requested_by"]),
        created_at=str(data["created_at"]),
        fields=validate_fields(data["fields"], case_type, require_all=False),
        history=list(history),
    )
