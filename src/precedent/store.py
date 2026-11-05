"""State on disk, and the only code that writes it.

The state home is a git repository of its own. Every write happens under a
lock, re-reads state, writes atomically, and commits exactly the paths it
touched. Before any command reads state, `check_untampered` refuses to go on
if those paths differ from the last engine commit: the agents share this
directory, so a hand edit is detected rather than trusted.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from precedent.config import Config, load_config
from precedent.errors import NotFound, PrecedentError, Refused, SchemaError, Tampered
from precedent.models import Case, Rule, parse_case, parse_rule

CONFIG_FILE = "precedent.config.yaml"
APPROVALS_FILE = "approvals.yaml"
LOCK_FILE = ".precedent.lock"
STATE_PATHS = ("cases", "precedents", APPROVALS_FILE, CONFIG_FILE)
LOCK_TIMEOUT_S = 15.0
STALE_LOCK_S = 120.0


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dump(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


class Store:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.cases_dir = home / "cases"
        self.rules_dir = home / "precedents"
        self._config: Config | None = None

    # ── git ───────────────────────────────────────────────────────────────

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.home), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise PrecedentError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout

    def init_repo(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        if not (self.home / ".git").exists():
            self._git("init", "-q")
            self._git("config", "user.name", "precedent-engine")
            self._git("config", "user.email", "precedent-engine@localhost")
        (self.home / ".gitignore").write_text(f"{LOCK_FILE}\n", encoding="utf-8")

    def check_untampered(self) -> None:
        if not (self.home / ".git").exists():
            raise Tampered(f"{self.home} is not a precedent state repository; run `precedent init`")
        changed = self._git("status", "--porcelain", "--untracked-files=all", "--", *STATE_PATHS).strip()
        if changed:
            raise Tampered(
                "State was changed outside the engine; nothing will run until a person "
                f"reviews it (`git -C {self.home} status`):\n{changed}"
            )

    def commit(self, paths: list[Path], message: str) -> str:
        rel = [str(p.relative_to(self.home)).replace("\\", "/") for p in paths]
        self._git("add", "--", *rel)
        self._git("commit", "-q", "-m", message, "--", *rel)
        return self._git("rev-parse", "--short", "HEAD").strip()

    # ── locking ───────────────────────────────────────────────────────────

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        lock = self.home / LOCK_FILE
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                with contextlib.suppress(FileNotFoundError):
                    if time.time() - lock.stat().st_mtime > STALE_LOCK_S:
                        lock.unlink()
                        continue
                if time.monotonic() > deadline:
                    raise Refused("State is locked by another command; try again shortly") from None
                time.sleep(0.05)
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self.check_untampered()
            yield
        finally:
            with contextlib.suppress(FileNotFoundError):
                lock.unlink()

    # ── files ─────────────────────────────────────────────────────────────

    def _write(self, path: Path, data: Any) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(_dump(data), encoding="utf-8")
        os.replace(tmp, path)
        return path

    def _read(self, path: Path) -> Any:
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise SchemaError(f"{path.name} is not valid YAML: {exc}") from exc

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = load_config(self.home / CONFIG_FILE)
        return self._config

    # cases

    def case_path(self, case_id: str) -> Path:
        return self.cases_dir / f"{case_id}.yaml"

    def cases(self) -> list[Case]:
        if not self.cases_dir.exists():
            return []
        return [
            parse_case(self._read(path), self.config)
            for path in sorted(self.cases_dir.glob("C-*.yaml"))
        ]

    def case(self, case_id: str) -> Case:
        path = self.case_path(case_id)
        if not path.exists():
            raise NotFound(f"No case {case_id}")
        return parse_case(self._read(path), self.config)

    def next_case_id(self) -> str:
        numbers = [int(p.stem.split("-")[1]) for p in self.cases_dir.glob("C-*.yaml")] if self.cases_dir.exists() else []
        return f"C-{(max(numbers, default=0) + 1):03d}"

    def save_case(self, case: Case) -> Path:
        return self._write(self.case_path(case.id), case.to_dict())

    # rules

    def rule_path(self, rule_id: str, version: int) -> Path:
        return self.rules_dir / f"{rule_id}.v{version}.yaml"

    def rules(self) -> list[Rule]:
        if not self.rules_dir.exists():
            return []
        rules = []
        for path in sorted(self.rules_dir.glob("P-*.v*.yaml")):
            rule = parse_rule(self._read(path), self.config)
            if path.name != f"{rule.id}.v{rule.version}.yaml":
                raise Tampered(f"{path.name} holds {rule.ref}; file names and contents must agree")
            rules.append(rule)
        return rules

    def active_rules(self, case_type: str | None = None) -> list[Rule]:
        return [
            r for r in self.rules()
            if r.status == "active" and (case_type is None or r.applies_to == case_type)
        ]

    def rule(self, ref: str) -> Rule:
        """`P-007` (its latest version) or `P-007@1`."""
        rule_id, _, version = ref.partition("@")
        candidates = [r for r in self.rules() if r.id == rule_id]
        if version:
            candidates = [r for r in candidates if r.version == int(version)]
        if not candidates:
            raise NotFound(f"No rule {ref}")
        return max(candidates, key=lambda r: r.version)

    def next_rule_id(self) -> str:
        numbers = [int(p.name.split(".")[0].split("-")[1]) for p in self.rules_dir.glob("P-*.yaml")] if self.rules_dir.exists() else []
        return f"P-{(max(numbers, default=0) + 1):03d}"

    def save_rule(self, rule: Rule) -> Path:
        return self._write(self.rule_path(rule.id, rule.version), rule.to_dict())

    # approvals that have been spent

    def used_approvals(self) -> dict[str, dict[str, Any]]:
        path = self.home / APPROVALS_FILE
        if not path.exists():
            return {}
        data = self._read(path) or {}
        if not isinstance(data, dict):
            raise SchemaError(f"{APPROVALS_FILE} must be a mapping")
        return data

    def spend_approval(self, message_id: str, record: dict[str, Any]) -> Path:
        used = self.used_approvals()
        if message_id in used:
            raise Refused(f"Approval message {message_id} was already used for {used[message_id].get('action')}")
        used[message_id] = record
        return self._write(self.home / APPROVALS_FILE, used)
