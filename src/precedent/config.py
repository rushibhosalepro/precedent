"""`precedent.config.yaml`: who may approve, and the fields each case type has."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from precedent.errors import SchemaError

FIELD_TYPES = ("string", "number", "integer", "enum", "boolean")


@dataclass(frozen=True)
class Approver:
    id: str  # the Switch sender id, which Switch writes and an agent cannot set
    name: str


@dataclass(frozen=True)
class FieldSpec:
    type: str
    required: bool
    values: tuple[str, ...] = ()

    def accepts(self, value: Any) -> bool:
        if self.type == "string":
            return isinstance(value, str)
        if self.type == "boolean":
            return isinstance(value, bool)
        if self.type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if self.type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        return isinstance(value, str) and value in self.values


@dataclass(frozen=True)
class CaseType:
    name: str
    fields: dict[str, FieldSpec]


@dataclass(frozen=True)
class Agents:
    """Which Switch agent plays each role, by agent name."""

    clerk: str
    judge: str
    auditor: str

    def role_of(self, agent_name: str) -> str | None:
        for role in ("clerk", "judge", "auditor"):
            if getattr(self, role) == agent_name:
                return role
        return None


@dataclass(frozen=True)
class Config:
    approvers: tuple[Approver, ...]
    currency: str
    types: dict[str, CaseType]
    agents: Agents | None
    switch_room: str | None
    switch_credentials: str | None
    offline_approvals: bool
    agent_reported_approvals: bool

    def approver(self, sender_id: str) -> Approver | None:
        for approver in self.approvers:
            if approver.id == sender_id:
                return approver
        return None

    def case_type(self, name: str) -> CaseType:
        try:
            return self.types[name]
        except KeyError:
            raise SchemaError(
                f"Unknown case type {name!r}; known: {', '.join(sorted(self.types))}"
            ) from None


def _require_keys(where: str, data: dict[str, Any], allowed: set[str], required: set[str]) -> None:
    if not isinstance(data, dict):
        raise SchemaError(f"{where} must be a mapping")
    unknown = set(data) - allowed
    if unknown:
        raise SchemaError(f"{where} has unknown keys: {', '.join(sorted(unknown))}")
    missing = required - set(data)
    if missing:
        raise SchemaError(f"{where} is missing: {', '.join(sorted(missing))}")


def parse_config(data: Any) -> Config:
    _require_keys(
        "config",
        data,
        {"approvers", "currency", "types", "agents", "switch", "offline_approvals", "agent_reported_approvals"},
        {"approvers", "currency", "types"},
    )
    approvers = []
    for index, raw in enumerate(data["approvers"] or []):
        _require_keys(f"approvers[{index}]", raw, {"id", "name"}, {"id", "name"})
        approvers.append(Approver(id=str(raw["id"]), name=str(raw["name"])))
    if not approvers:
        raise SchemaError("config needs at least one approver")

    types: dict[str, CaseType] = {}
    for type_name, raw_type in (data["types"] or {}).items():
        _require_keys(f"types.{type_name}", raw_type, {"fields"}, {"fields"})
        fields: dict[str, FieldSpec] = {}
        for field_name, raw_field in raw_type["fields"].items():
            where = f"types.{type_name}.fields.{field_name}"
            _require_keys(where, raw_field, {"type", "required", "values"}, {"type"})
            if raw_field["type"] not in FIELD_TYPES:
                raise SchemaError(f"{where}.type must be one of {', '.join(FIELD_TYPES)}")
            values = tuple(raw_field.get("values") or ())
            if raw_field["type"] == "enum" and not values:
                raise SchemaError(f"{where} is an enum with no values")
            fields[field_name] = FieldSpec(
                type=raw_field["type"],
                required=bool(raw_field.get("required", False)),
                values=values,
            )
        types[type_name] = CaseType(name=type_name, fields=fields)
    if not types:
        raise SchemaError("config needs at least one case type")

    agents = None
    if data.get("agents") is not None:
        _require_keys("agents", data["agents"], {"clerk", "judge", "auditor"}, {"clerk", "judge", "auditor"})
        agents = Agents(**{k: str(v) for k, v in data["agents"].items()})

    switch_room = None
    switch_credentials = None
    if data.get("switch") is not None:
        _require_keys("switch", data["switch"], {"room_id", "credentials"}, {"room_id"})
        switch_room = str(data["switch"]["room_id"])
        if data["switch"].get("credentials") is not None:
            switch_credentials = str(data["switch"]["credentials"])

    return Config(
        approvers=tuple(approvers),
        currency=str(data["currency"]),
        types=types,
        agents=agents,
        switch_room=switch_room,
        switch_credentials=switch_credentials,
        offline_approvals=bool(data.get("offline_approvals", False)),
        agent_reported_approvals=bool(data.get("agent_reported_approvals", False)),
    )


def load_config(path: Path) -> Config:
    if not path.exists():
        raise SchemaError(f"No config at {path}; run `precedent init` first")
    return parse_config(yaml.safe_load(path.read_text(encoding="utf-8")))
