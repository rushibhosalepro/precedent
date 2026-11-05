"""`precedent`: the command-line face of the engine, for the room's agents.

Output is always JSON on stdout (the ledger is Markdown). Exit codes:
0 ok · 2 bad input or not found · 3 refused · 4 state tampered · 5 Switch
unreachable. Agents treat any non-zero exit as "escalate to a person and stop".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from precedent.errors import PrecedentError, Refused, SchemaError
from precedent.service import Engine
from precedent.store import Store
from precedent.switch_api import AgentReported, MessageSource, OfflineMessages, SwitchMessages

ROLES = ("clerk", "judge", "auditor")

# Which role may run which command. Not a security boundary (the agents share
# an OS user); it keeps each agent inside its job, and makes a slip loud.
ALLOWED: dict[str, set[str]] = {
    "case new": {"clerk"},
    "case show": {"clerk", "judge", "auditor"},
    "match": {"judge"},
    "decide": {"judge"},
    "rule draft": {"auditor"},
    "rule backtest": {"auditor"},
    "rule adopt": {"auditor"},
    "rule retire-reply": {"auditor"},
    "rule retire": {"auditor"},
    "types": set(ROLES),
    "ledger": set(ROLES),
    "stats": set(ROLES),
    "validate": set(ROLES),
}


def _json_arg(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"Not valid JSON: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="precedent", description=__doc__.splitlines()[0])
    parser.add_argument("--home", type=Path, help="State directory (default: $PRECEDENT_HOME or ./state)")
    parser.add_argument("--as", dest="role", choices=ROLES, help="The role of the agent calling")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create the state repository")
    init.add_argument("--config", type=Path, required=True)
    init.add_argument("--seed", type=Path, help="Directory of historical C-*.yaml cases to import")

    case = sub.add_parser("case").add_subparsers(dest="case_command", required=True)
    new = case.add_parser("new", help="Create a case from a request")
    new.add_argument("--type", required=True)
    new.add_argument("--source-msg", required=True, help="Switch message id of the request")
    new.add_argument("--requested-by-id", required=True)
    new.add_argument("--requested-by-name", required=True)
    new.add_argument("--fields", required=True, type=_json_arg, help="JSON object of field values")
    show = case.add_parser("show")
    show.add_argument("case_id")

    m = sub.add_parser("match", help="Match a case against the active rules")
    m.add_argument("case_id")

    d = sub.add_parser("decide", help="Record a person's verified decision")
    d.add_argument("case_id")
    d.add_argument("--outcome", required=True, choices=("approve", "deny"))
    d.add_argument("--under", required=True, help="P-007@1, or manual")
    _approval_args(d)

    rule = sub.add_parser("rule").add_subparsers(dest="rule_command", required=True)
    draft = rule.add_parser("draft", help="Draft a rule from a decided case")
    draft.add_argument("--from", dest="from_case", required=True)
    draft.add_argument("--title", required=True)
    draft.add_argument("--outcome", required=True, choices=("approve", "deny"))
    draft.add_argument("--conditions", required=True, type=_json_arg)
    draft.add_argument("--supersedes", help="P-007 to draft its next version")
    bt = rule.add_parser("backtest")
    bt.add_argument("rule")
    adopt = rule.add_parser("adopt")
    adopt.add_argument("rule")
    _approval_args(adopt)
    rr = rule.add_parser("retire-reply", help="The line an approver types to retire a rule")
    rr.add_argument("rule")
    retire = rule.add_parser("retire")
    retire.add_argument("rule")
    _approval_args(retire)

    inspect = sub.add_parser(
        "inspect",
        help="Setup: list a room's recent messages with Switch's sender ids, to fill in approvers",
    )
    inspect.add_argument("--room", required=True)
    inspect.add_argument("--credentials", type=Path, help="Switch credentials file (default: the only .switch/agents/*.json here)")
    inspect.add_argument("--limit", type=int, default=10)

    sub.add_parser("types", help="The case types and the fields each one needs")
    sub.add_parser("ledger", help="Markdown table of active rules")
    sub.add_parser("stats")
    sub.add_parser("validate")
    return parser


def _approval_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--approval-msg", required=True, help="Switch message id of the person's reply")
    parser.add_argument("--room", help="Switch room id (default: the config's switch.room_id)")
    parser.add_argument("--credentials", type=Path, help="Switch credentials file (default: the only .switch/agents/*.json here)")
    parser.add_argument(
        "--approval-entry",
        type=_json_arg,
        help="Fallback only (config agent_reported_approvals: true): the message JSON from your read_context tool",
    )


def _command_name(args: argparse.Namespace) -> str:
    if args.command == "case":
        return f"case {args.case_command}"
    if args.command == "rule":
        return f"rule {args.rule_command}"
    return args.command


def _credentials(args: argparse.Namespace, configured: str | None) -> Path:
    """The flag, the environment, then the config. A managed agent's credentials
    live in its controller's folder, which the config names; an agent Console
    runs itself keeps them in its working directory."""
    if args.credentials:
        return args.credentials
    if os.environ.get("PRECEDENT_SWITCH_CREDENTIALS"):
        return Path(os.environ["PRECEDENT_SWITCH_CREDENTIALS"])
    if configured:
        return Path(configured)
    found = sorted(Path.cwd().glob(".switch/agents/*.json"))
    if len(found) != 1:
        raise SchemaError(
            "No Switch credentials: pass --credentials, set switch.credentials in the config, "
            "or run from a directory with exactly one .switch/agents/*.json"
        )
    return found[0]


def _inspect(args: argparse.Namespace) -> list[dict[str, Any]]:
    entries = SwitchMessages.from_credentials(_credentials(args, None)).recent(args.room)
    entries.sort(key=lambda e: e.get("timestamp") or 0)
    return [
        {
            "id": e.get("id"),
            "sender": e.get("sender"),
            "sender_name": e.get("sender_name"),
            "sender_kind": e.get("sender_kind"),
            "kind": e.get("kind"),
            "body": str(e.get("body") or "")[:80],
        }
        for e in entries[-args.limit :]
    ]


def _messages(args: argparse.Namespace, store: Store) -> tuple[MessageSource, str]:
    config = store.config
    room = args.room or config.switch_room
    if not room:
        raise SchemaError("No room id: pass --room or set switch.room_id in the config")
    if args.approval_entry is not None:
        if not config.agent_reported_approvals:
            raise Refused("--approval-entry is a fallback the config does not allow; the engine reads approvals from Switch")
        return AgentReported(args.approval_entry), room
    offline = os.environ.get("PRECEDENT_OFFLINE_MESSAGES")
    if offline:
        if not config.offline_approvals:
            raise Refused("PRECEDENT_OFFLINE_MESSAGES is set but the config does not allow offline approvals")
        return OfflineMessages(Path(offline)), room
    return SwitchMessages.from_credentials(_credentials(args, config.switch_credentials)), room


def run(argv: list[str]) -> tuple[int, str]:
    args = build_parser().parse_args(argv)
    home = args.home or Path(os.environ.get("PRECEDENT_HOME", "state"))
    store = Store(home.resolve())
    engine = Engine(store)
    name = _command_name(args)

    if name == "inspect":
        return 0, json.dumps(_inspect(args), indent=2, default=str)
    if name != "init":
        allowed = ALLOWED[name]
        if args.role is None:
            raise Refused(f"`{name}` needs --as <role> (one of: {', '.join(sorted(allowed))})")
        if args.role not in allowed:
            raise Refused(f"The {args.role} may not run `{name}`; that is for: {', '.join(sorted(allowed))}")

    if name == "init":
        out: Any = engine.init(args.config, args.seed)
    elif name == "case new":
        out = engine.case_new(
            args.type,
            args.fields,
            source_msg=args.source_msg,
            requested_by={"id": args.requested_by_id, "name": args.requested_by_name},
        )
    elif name == "case show":
        out = engine.case_show(args.case_id)
    elif name == "match":
        out = engine.match(args.case_id)
    elif name == "decide":
        messages, room = _messages(args, store)
        out = engine.decide(args.case_id, args.outcome, args.under, approval_msg=args.approval_msg, room_id=room, messages=messages)
    elif name == "rule draft":
        out = engine.rule_draft(
            from_case=args.from_case, title=args.title, outcome=args.outcome,
            conditions=args.conditions, supersedes=args.supersedes,
        )
    elif name == "rule backtest":
        out = engine.backtest(args.rule)
    elif name == "rule adopt":
        messages, room = _messages(args, store)
        out = engine.adopt(args.rule, approval_msg=args.approval_msg, room_id=room, messages=messages)
    elif name == "rule retire-reply":
        out = engine.retire_reply(args.rule)
    elif name == "rule retire":
        messages, room = _messages(args, store)
        out = engine.retire(args.rule, approval_msg=args.approval_msg, room_id=room, messages=messages)
    elif name == "types":
        out = engine.types()
    elif name == "ledger":
        return 0, engine.ledger()
    elif name == "stats":
        out = engine.stats()
    else:
        out = engine.validate()
    return 0, json.dumps(out, indent=2, default=str)


def main(argv: list[str] | None = None) -> int:
    try:
        code, text = run(sys.argv[1:] if argv is None else argv)
    except PrecedentError as exc:
        print(json.dumps({"ok": False, "error": exc.kind, "message": str(exc), "next": "escalate to a person"}, indent=2))
        return exc.exit_code
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
