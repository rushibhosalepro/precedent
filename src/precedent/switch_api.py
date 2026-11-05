"""Read one room message from Switch, as Switch recorded it.

This is what makes an approval trustworthy: the agent hands the engine only a
message id, and the engine asks Switch who sent it. Uses the agent HTTP API's
front door, `POST /agents/{agent_id}/ops/read_context`, with the credentials
Switch Console writes to `<working dir>/.switch/agents/<slug>.json`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

import httpx

from precedent.errors import NotFound, SchemaError, SwitchUnavailable

READ_LIMIT = 200


class MessageSource(Protocol):
    #: How the message was obtained, recorded with every approval it backs:
    #: "switch" (read from the server), "agent_reported" or "offline".
    mode: str

    def fetch(self, room_id: str, message_id: str) -> dict[str, Any]: ...


def _entries(context: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for thread in context.get("threads") or []:
        root = thread.get("root")
        if root:
            yield root
        yield from thread.get("replies") or []


class SwitchMessages:
    mode = "switch"

    def __init__(self, endpoint: str, agent_id: str, token: str, *, timeout: float = 15.0) -> None:
        self._url = f"{endpoint.rstrip('/')}/agents/{agent_id}/ops/read_context"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._timeout = timeout

    @classmethod
    def from_credentials(cls, path: Path) -> SwitchMessages:
        try:
            env = json.loads(path.read_text(encoding="utf-8"))["env"]
            return cls(env["SWITCH_API_ENDPOINT"], env["SWITCH_AGENT_ID"], env["SWITCH_API_TOKEN"])
        except FileNotFoundError:
            raise SchemaError(f"No Switch credentials at {path}") from None
        except (KeyError, json.JSONDecodeError) as exc:
            raise SchemaError(f"Switch credentials at {path} are not in the expected shape: {exc}") from exc

    def recent(self, room_id: str) -> list[dict[str, Any]]:
        """The room's recent messages as Switch records them, for setup."""
        return list(_entries(self._read(room_id)))

    def fetch(self, room_id: str, message_id: str) -> dict[str, Any]:
        for entry in _entries(self._read(room_id)):
            if entry.get("id") == message_id:
                return entry
        raise NotFound(f"Message {message_id} is not in the last {READ_LIMIT} messages of room {room_id}")

    def _read(self, room_id: str) -> dict[str, Any]:
        try:
            response = httpx.post(
                self._url,
                headers=self._headers,
                json={"room_id": room_id, "limit": READ_LIMIT},
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise SwitchUnavailable(f"Could not reach Switch to verify the approval: {exc}") from exc
        if response.status_code != 200:
            raise SwitchUnavailable(
                f"Switch refused read_context ({response.status_code}): {response.text[:300]}"
            )
        body = response.json()
        context = body if "threads" in body else body.get("result", body)
        if not isinstance(context, dict) or "threads" not in context:
            raise SwitchUnavailable(f"Unexpected read_context response shape: {str(body)[:300]}")
        return context


class OfflineMessages:
    """Messages from a JSON file shaped like a `read_context` response.

    Only for tests and rehearsals: the config must say `offline_approvals: true`,
    and every report the engine prints then says so.
    """

    mode = "offline"

    def __init__(self, path: Path) -> None:
        self._path = path

    def fetch(self, room_id: str, message_id: str) -> dict[str, Any]:
        try:
            context = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SchemaError(f"No offline messages file at {self._path}") from None
        for entry in _entries(context):
            if entry.get("id") == message_id:
                return entry
        raise NotFound(f"Message {message_id} is not in {self._path.name}")


class AgentReported:
    """The fallback for a server that won't serve `read_context` to the
    engine: the agent passes the entry its own `read_context` tool returned.

    Weaker than `SwitchMessages`, because the engine must trust the agent's copy.
    It is allowed only when the config says `agent_reported_approvals: true`,
    and every approval it backs is recorded as `verified_via: agent_reported`.
    """

    mode = "agent_reported"

    def __init__(self, entry: dict[str, Any]) -> None:
        if not isinstance(entry, dict):
            raise SchemaError("--approval-entry must be a JSON object from read_context")
        self._entry = entry

    def fetch(self, room_id: str, message_id: str) -> dict[str, Any]:
        if self._entry.get("id") != message_id:
            raise NotFound(f"--approval-entry is message {self._entry.get('id')}, not {message_id}")
        return self._entry
