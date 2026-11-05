"""The engine's operations. Each one is a single locked, validated, committed
state transition, so the CLI stays a thin layer of argument parsing."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from precedent.backtest import policy_hash, run_backtest
from precedent.errors import Refused, SchemaError
from precedent.matcher import MATCH, match
from precedent.models import Case, Rule, parse_case, validate_conditions, validate_fields
from precedent.store import APPROVALS_FILE, CONFIG_FILE, Store, now_iso
from precedent.switch_api import MessageSource
from precedent.verify import (
    adopt_ref,
    decision_ref,
    reply_line,
    retire_ref,
    verify_approval,
)

# Tolerated clock difference between this machine and the Switch server.
CLOCK_SKEW_MS = 60_000


def iso_to_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _last_event(case: Case, name: str) -> dict[str, Any] | None:
    for event in reversed(case.history):
        if event.get("event") == name:
            return event
    return None


class Engine:
    def __init__(self, store: Store) -> None:
        self.store = store

    # ── setup ─────────────────────────────────────────────────────────────

    def init(self, config_src: Path, seed_dir: Path | None) -> dict[str, Any]:
        store = self.store
        if (store.home / CONFIG_FILE).exists():
            raise Refused(f"{store.home} is already initialised")
        store.init_repo()
        shutil.copyfile(config_src, store.home / CONFIG_FILE)
        config = store.config  # validates
        written = [store.home / CONFIG_FILE, store.home / ".gitignore"]
        imported = 0
        if seed_dir is not None:
            for path in sorted(seed_dir.glob("C-*.yaml")):
                case = parse_case(yaml.safe_load(path.read_text(encoding="utf-8")), config)
                written.append(store.save_case(case))
                imported += 1
        (store.home / APPROVALS_FILE).write_text("{}\n", encoding="utf-8")
        written.append(store.home / APPROVALS_FILE)
        commit = store.commit(written, f"init: config and {imported} historical cases")
        return {"home": str(store.home), "imported_cases": imported, "commit": commit}

    # ── cases ─────────────────────────────────────────────────────────────

    def case_new(self, case_type: str, fields: dict[str, Any], *, source_msg: str, requested_by: dict[str, str]) -> dict[str, Any]:
        store = self.store
        with store.locked():
            for existing in store.cases():
                if existing.source_msg == source_msg:
                    return {"duplicate": True, "case": existing.to_dict()}
            spec = store.config.case_type(case_type)
            case = Case(
                id=store.next_case_id(),
                type=case_type,
                version=1,
                source_msg=source_msg,
                requested_by=requested_by,
                created_at=now_iso(),
                fields=validate_fields(fields, spec, require_all=True),
                history=[{"at": now_iso(), "event": "created"}],
            )
            commit = store.commit([store.save_case(case)], f"case {case.id}: created from msg {source_msg}")
        return {"duplicate": False, "case": case.to_dict(), "commit": commit}

    def case_show(self, case_id: str) -> dict[str, Any]:
        self.store.check_untampered()
        return self.store.case(case_id).to_dict()

    def match(self, case_id: str) -> dict[str, Any]:
        store = self.store
        with store.locked():
            case = store.case(case_id)
            if case.decision() is not None:
                raise Refused(f"{case_id} is already decided")
            result = match(case.fields, store.active_rules(case.type))
            case.version += 1
            case.history.append({
                "at": now_iso(),
                "event": "proposed",
                "result": result.result,
                "outcome": result.outcome,
                "cited": result.cited.ref if result.cited else None,
            })
            commit = store.commit([store.save_case(case)], f"case {case.id}: proposed ({result.result})")

        options = []
        if result.result == MATCH and result.cited is not None:
            under = result.cited.ref
            verb = result.outcome
            options.append({"outcome": verb, "under": under, "reply": reply_line(verb, case.id, decision_ref(case, verb, under))})
            other = "deny" if verb == "approve" else "approve"
            options.append({"outcome": other, "under": "manual", "reply": reply_line(other, case.id, decision_ref(case, other, "manual"))})
        elif result.result != "missing_information":
            for verb in ("approve", "deny"):
                options.append({"outcome": verb, "under": "manual", "reply": reply_line(verb, case.id, decision_ref(case, verb, "manual"))})
        return {"case": case.id, "version": case.version, **result.to_dict(), "options": options, "commit": commit}

    def decide(self, case_id: str, outcome: str, under: str, *, approval_msg: str, room_id: str, messages: MessageSource) -> dict[str, Any]:
        if outcome not in ("approve", "deny"):
            raise SchemaError("outcome must be approve or deny")
        store = self.store
        with store.locked():
            case = store.case(case_id)
            if case.decision() is not None:
                raise Refused(f"{case_id} is already decided")
            proposed = _last_event(case, "proposed")
            if proposed is None:
                raise Refused(f"{case_id} has not been matched yet; run `match` first")
            if under != "manual":
                result = match(case.fields, store.active_rules(case.type))
                if result.result != MATCH or under not in [r.ref for r in result.matching] or result.outcome != outcome:
                    raise Refused(f"{under} does not decide {case_id} as {outcome} under the active rules")
            entry = messages.fetch(room_id, approval_msg)
            approval = verify_approval(
                entry,
                config=store.config,
                message_id=approval_msg,
                verb=outcome,
                object_id=case.id,
                ref=decision_ref(case, outcome, under),
                not_before_ms=iso_to_ms(proposed["at"]) - CLOCK_SKEW_MS,
                used=store.used_approvals(),
            )
            case.version += 1
            case.history.append({
                "at": now_iso(),
                "event": "decided",
                "outcome": outcome,
                "under": under,
                "by": approval.sender_id,
                "by_name": approval.sender_name,
                "approval_msg": approval.message_id,
                "verified_via": messages.mode,
            })
            paths = [
                store.save_case(case),
                store.spend_approval(approval_msg, {"action": f"decide {case.id}", "at": now_iso()}),
            ]
            commit = store.commit(paths, f"case {case.id}: {outcome} under {under} by {approval.sender_id} via msg {approval_msg}")
        return {"case": case.id, "outcome": outcome, "under": under, "by": approval.sender_name, "commit": commit}

    # ── rules ─────────────────────────────────────────────────────────────

    def rule_draft(self, *, from_case: str, title: str, outcome: str, conditions: dict[str, Any], supersedes: str | None) -> dict[str, Any]:
        if outcome not in ("approve", "deny"):
            raise SchemaError("outcome must be approve or deny")
        store = self.store
        with store.locked():
            source = store.case(from_case)
            spec = store.config.case_type(source.type)
            normalised = validate_conditions(conditions, spec)
            if supersedes:
                old = store.rule(supersedes)
                if old.status != "active":
                    raise Refused(f"{old.ref} is not active, so it cannot be superseded")
                rule_id, version, replaces = old.id, old.version + 1, old.ref
                if any(r.id == rule_id and r.version == version for r in store.rules()):
                    raise Refused(f"{rule_id}@{version} already exists")
            else:
                rule_id, version, replaces = store.next_rule_id(), 1, None
            rule = Rule(
                id=rule_id,
                version=version,
                status="draft",
                title=title,
                applies_to=source.type,
                conditions=normalised,
                outcome=outcome,
                source_case=source.id,
                supersedes=replaces,
                drafted={"at": now_iso(), "from_case": source.id},
            )
            commit = store.commit([store.save_rule(rule)], f"rule {rule.ref}: drafted from {source.id}")
        return {"rule": rule.to_dict(), "commit": commit}

    def backtest(self, rule_ref: str) -> dict[str, Any]:
        store = self.store
        with store.locked():
            draft = store.rule(rule_ref)
            if draft.status != "draft":
                raise Refused(f"{draft.ref} is {draft.status}; only drafts are backtested")
            active = store.active_rules()
            report = run_backtest(draft, active, store.cases())
            draft.backtest = {"at": now_iso(), **report.to_dict()}
            commit = store.commit([store.save_rule(draft)], f"rule {draft.ref}: backtested ({report.summary()})")
        result = {"report": report.to_dict(), "commit": commit}
        if not report.blocks_adoption:
            result["adopt_reply"] = reply_line("adopt", draft.id, adopt_ref(draft, report.policy_hash))
        return result

    def adopt(self, rule_ref: str, *, approval_msg: str, room_id: str, messages: MessageSource) -> dict[str, Any]:
        store = self.store
        with store.locked():
            draft = store.rule(rule_ref)
            if draft.status != "draft":
                raise Refused(f"{draft.ref} is {draft.status}; only drafts can be adopted")
            if not draft.backtest:
                raise Refused(f"{draft.ref} has no backtest; run `backtest` first")
            if draft.backtest.get("blocks_adoption"):
                raise Refused(f"{draft.ref} would add conflicts; resolve them before adopting")
            active = store.active_rules()
            current = policy_hash(active)
            if draft.backtest.get("policy_hash") != current:
                raise Refused(f"The active rules changed since {draft.ref} was backtested; run `backtest` again")
            entry = messages.fetch(room_id, approval_msg)
            approval = verify_approval(
                entry,
                config=store.config,
                message_id=approval_msg,
                verb="adopt",
                object_id=draft.id,
                ref=adopt_ref(draft, current),
                not_before_ms=iso_to_ms(draft.backtest["at"]) - CLOCK_SKEW_MS,
                used=store.used_approvals(),
            )
            stamp = {
                "by": approval.sender_id,
                "by_name": approval.sender_name,
                "approval_msg": approval_msg,
                "verified_via": messages.mode,
                "at": now_iso(),
            }
            draft.status = "active"
            draft.adopted = stamp
            paths = [store.save_rule(draft)]
            if draft.supersedes:
                old = store.rule(draft.supersedes)
                old.status = "retired"
                old.retired = {**stamp, "replaced_by": draft.ref}
                paths.append(store.save_rule(old))
            paths.append(store.spend_approval(approval_msg, {"action": f"adopt {draft.ref}", "at": now_iso()}))
            commit = store.commit(paths, f"rule {draft.ref}: adopted by {approval.sender_id} via msg {approval_msg}")
        return {"rule": draft.ref, "status": "active", "by": approval.sender_name, "commit": commit}

    def retire_reply(self, rule_ref: str) -> dict[str, Any]:
        self.store.check_untampered()
        rule = self.store.rule(rule_ref)
        if rule.status != "active":
            raise Refused(f"{rule.ref} is {rule.status}")
        return {"rule": rule.ref, "retire_reply": reply_line("retire", rule.id, retire_ref(rule))}

    def retire(self, rule_ref: str, *, approval_msg: str, room_id: str, messages: MessageSource) -> dict[str, Any]:
        store = self.store
        with store.locked():
            rule = store.rule(rule_ref)
            if rule.status != "active":
                raise Refused(f"{rule.ref} is {rule.status}; only active rules can be retired")
            entry = messages.fetch(room_id, approval_msg)
            approval = verify_approval(
                entry,
                config=store.config,
                message_id=approval_msg,
                verb="retire",
                object_id=rule.id,
                ref=retire_ref(rule),
                not_before_ms=None,
                used=store.used_approvals(),
            )
            rule.status = "retired"
            rule.retired = {
                "by": approval.sender_id,
                "by_name": approval.sender_name,
                "approval_msg": approval_msg,
                "verified_via": messages.mode,
                "at": now_iso(),
            }
            paths = [
                store.save_rule(rule),
                store.spend_approval(approval_msg, {"action": f"retire {rule.ref}", "at": now_iso()}),
            ]
            commit = store.commit(paths, f"rule {rule.ref}: retired by {approval.sender_id} via msg {approval_msg}")
        return {"rule": rule.ref, "status": "retired", "commit": commit}

    # ── reporting ─────────────────────────────────────────────────────────

    def types(self) -> dict[str, Any]:
        self.store.check_untampered()
        return {
            name: {
                field: {
                    "type": spec.type,
                    "required": spec.required,
                    **({"values": list(spec.values)} if spec.values else {}),
                }
                for field, spec in case_type.fields.items()
            }
            for name, case_type in self.store.config.types.items()
        }

    def ledger(self) -> str:
        self.store.check_untampered()
        active = self.store.active_rules()
        lines = [
            "# Precedent ledger",
            "",
            "Rules this room has been taught. Each was backtested and adopted by an approver.",
            "",
        ]
        if self.store.config.offline_approvals:
            lines += ["> **Offline approvals are enabled: this ledger is a rehearsal, not a record.**", ""]
        if self.store.config.agent_reported_approvals:
            lines += [
                "> **Agent-reported approvals are enabled:** some approvals may rest on an agent's copy "
                "of the message rather than Switch's. Each rule's record says which.",
                "",
            ]
        if not active:
            return "\n".join(lines + ["_No rules yet._"])
        lines += ["| Rule | Applies to | When | Outcome | Adopted by | Backtest |", "|---|---|---|---|---|---|"]
        for rule in sorted(active, key=lambda r: (r.id, r.version)):
            when = "; ".join(
                f"{field} {' '.join(f'{op} {value}' for op, value in ops.items())}"
                for field, ops in rule.conditions.items()
            )
            adopted = (rule.adopted or {}).get("by_name", "?")
            summary = (rule.backtest or {}).get("summary", "")
            lines.append(f"| **{rule.ref}** {rule.title} | {rule.applies_to} | {when} | {rule.outcome} | {adopted} | {summary} |")
        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        self.store.check_untampered()
        cases = self.store.cases()
        decided = [c for c in cases if c.decision()]
        under_rule = [c for c in decided if (c.decision() or {}).get("under", "manual") != "manual"]
        live = [c for c in cases if c.source_msg]
        live_decided = [c for c in live if c.decision()]
        return {
            "cases": len(cases),
            "decided": len(decided),
            "pending": len(cases) - len(decided),
            "decided_under_a_rule": len(under_rule),
            "decided_manually": len(decided) - len(under_rule),
            "live_cases": len(live),
            "live_decided_under_a_rule": len([c for c in live_decided if (c.decision() or {}).get("under") != "manual"]),
            "active_rules": len(self.store.active_rules()),
            "offline_approvals": self.store.config.offline_approvals,
            "agent_reported_approvals": self.store.config.agent_reported_approvals,
        }

    def validate(self) -> dict[str, Any]:
        self.store.check_untampered()
        config = self.store.config
        rules = self.store.rules()
        cases = self.store.cases()
        for rule in rules:
            if rule.status == "active" and not rule.adopted:
                raise SchemaError(f"{rule.ref} is active but has no adoption record")
        ids = [(r.id, r.version) for r in rules]
        if len(ids) != len(set(ids)):
            raise SchemaError("Two rule files share an id and version")
        return {"ok": True, "rules": len(rules), "cases": len(cases), "approvers": [a.name for a in config.approvers]}
