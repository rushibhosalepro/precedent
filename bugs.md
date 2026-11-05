# Switch core: bugs found (for Track 03 PRs)

Repo: https://github.com/sandbox-quantum/switch (local clone: `../switch-core`, at `e47cab4`)
Checked against every open and closed issue and the latest ~150 PRs on 2026-11-04. None of the bugs below is reported or being fixed yet.

> **Track 03 rule, read first:** only issues labelled `hackathon` count, and a PR for an issue that isn't assigned to you won't be judged.
> So for each bug: **open an issue first** (with the repro below), comment on it tagging `@petr-sandbox` with a plan and asking for the `hackathon` label and to be assigned, and **write no PR code until you're assigned**.
> Read `CONTRIBUTING.md` and sign the CLA on your first PR. Link the issue in the PR with `Closes #N`. PR deadline: Nov 7, 11:59 PM IST.

| # | Bug | Area | Severity | Status |
|---|---|---|---|---|
| 1 | Telegram splits a long message inside an HTML entity (`&lt;` → `&lt` + `;`) | `bridges/collaboration/telegram/chunking.py` | Medium: mangled text in agent replies containing `<`, `>`, `&` | Confirmed by repro |
| 2 | Discord treats a one-line fence (```` ```npm test``` ````) as opening a code block, so every later chunk gets a stray fence and a repeated header | `bridges/collaboration/discord/chunking.py` | Medium: corrupts long replies | Confirmed by repro |
| 3 | Mattermost never splits long agent replies; a post over the server's `MaxPostSize` is rejected and dropped with only a log line | `bridges/collaboration/mattermost/adapter.py` | High: the reply is lost and the room sees nothing | Confirmed by reading the code; needs a live check |
| 5 | **Console leaves `{params}` unfilled in a managed agent's `instructions`:** the agent receives `{engine_dir}` literally, though every other field is filled and the docs say params work anywhere | `console/apps/switch-console-desktop/src/renderer/features/templates/use/managed-run.ts` (around line 158) | High for template authors: agents start with broken instructions and no error | **Confirmed live** (found 2026-11-05 running our template) |
| 4 | **On a Windows checkout, `switch_core` can't be imported:** the connection catalog's `SKILL.md` frontmatter regex only accepts `\n`, and Git for Windows checks those files out with `\r\n` | `core/switch_core/connections/loader.py` (`FRONTMATTER_RE`, line 44); no `.gitattributes` in the repo | High for Windows contributors: tests, `just run` and any import of the app fail at startup | **Confirmed by running it** (found 2026-11-04 while validating our template) |

---

## Bug 1: Telegram chunking cuts through an HTML entity

**File:** `core/switch_core/bridges/collaboration/telegram/chunking.py`, `safe_split()`

**What happens:** bodies are HTML-escaped before chunking (`<` becomes `&lt;`). `safe_split` avoids cutting inside a *tag* (`<…>`) but not inside an *entity* (`&…;`). When a long piece has no newline in its second half (a long code line, minified JSON, a stack trace, Java/TS generics), the 4096 cut can land in the middle of `&lt;`. Message 1 ends with `&lt` and message 2 starts with `;`, so each half renders wrong. Telegram may also reject the dangling `&lt` under HTML parse mode, which sends that chunk through the plain-text fallback.

**Repro** (no dependencies; run from `switch-core/core`):
```bash
python -I -c "
import importlib.util,html
s=importlib.util.spec_from_file_location('c','switch_core/bridges/collaboration/telegram/chunking.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
body=html.escape('Map<String, List<Integer>> x; '*200,quote=False)
for i,c in enumerate(m.chunk_message(body)): print(i,len(c),repr(c[:12]),repr(c[-12:]))
"
```
Output (chunk 0 ends with `&lt`, chunk 1 starts with `;Integer`):
```
0 4096 'Map&lt;Strin' 'ing, List&lt'
1 4096 ';Integer&gt;' 't;&gt; x; Ma'
2 208 'p&lt;String,' '&gt;&gt; x; '
```

**Proposed fix:** in `safe_split`, after the tag check, step back to before an unterminated `&` when it's close enough to be an entity:
```python
last_amp = text.rfind("&", 0, cut)
if last_amp > text.rfind(";", 0, cut) and cut - last_amp <= 10:
    cut = last_amp
```
Optionally, prefer a space over a hard cut when there's no usable newline (it currently cuts mid-word too).

**Test to add:** `core/tests/switch_core/bridges/collaboration/test_telegram_chunking.py`. Every chunk of an escaped long line must contain no `&` without a matching `;`, and `html.unescape("".join(chunks))` must equal the input.

---

## Bug 2: Discord chunking mistakes a one-line fence for an open code block

**File:** `core/switch_core/bridges/collaboration/discord/chunking.py`, `chunk_message()`

**What happens:** any line whose stripped text *starts with* ```` ``` ```` toggles the "inside a code block" state. A self-contained fenced span on one line, such as ```` ```npm test``` ````, sets `language = "npm test```"`. From then on, every split appends a closing ```` ``` ```` and reopens the next chunk with ```` ```npm test``` ````. Plain prose turns into code blocks, and the line `npm test` is repeated at the top of every chunk.

This is different from the already-reported #1226 (over-long lines inside a code block exceeding 2,000 characters).

**Repro:**
```bash
python -I -c "
import importlib.util
s=importlib.util.spec_from_file_location('c','switch_core/bridges/collaboration/discord/chunking.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
body='\`\`\`npm test\`\`\`\n'+'\n'.join('plain prose line number %d with some words'%i for i in range(120))
for i,c in enumerate(m.chunk_message(body)): print(i,len(c),repr(c[:30]),repr(c[-20:]))
"
```
Output (every chunk ends with a stray fence; chunks 1 and 2 start with a fake reopened fence):
```
0 1986 '```npm test```\nplain prose lin' ' with some words\n```'
1 1953 '```npm test```\nplain prose lin' ' with some words\n```'
2 1281 '```npm test```\nplain prose lin' ' 119 with some words'
```

**Proposed fix:** only treat a line as a fence opener when it doesn't also close on the same line:
```python
if stripped.startswith(_FENCE):
    if language is None:
        if _FENCE not in stripped[len(_FENCE):]:
            language = stripped[len(_FENCE):].strip()
    else:
        language = None
```

**Test to add:** `core/tests/switch_core/bridges/collaboration/` (Discord chunking test). A body that starts with a one-line fence must produce chunks that never contain an unbalanced ```` ``` ```` and never repeat the first line.

---

## Bug 3: Mattermost drops agent replies longer than the post limit

**File:** `core/switch_core/bridges/collaboration/mattermost/adapter.py`, `send_message()` (around line 938) → `_create_post()` (around line 1160)

**What happens:**
- Discord and Telegram split long outbound messages (`chunk_message`), but Mattermost's `send_message` posts the whole body in one `create_post`.
- Mattermost rejects a message longer than its `MaxPostSize`. The adapter's own comment at line 150 says the default is 4000 and servers can raise it to 16383.
- `_create_post` catches the exception, logs `Failed to send Mattermost message`, and returns `None`. The room sees nothing, and the agent believes it replied.
- The adapter already knows about the limit: `_MAX_POST = 4000` is used by `rich_fallback_limit()`. Only the plain message path ignores it.
- This also goes against the repo's "Fail loud, never fake" rule in `CLAUDE.md`.

**How to confirm live:**
1. Run `just up`, which starts a local Mattermost.
2. Connect the bridge.
3. Have an agent post 20,000 characters.
4. Expect no post in the channel and one `Failed to send Mattermost message` error in the switch-core log.

**Proposed fix:**
- Split in `send_message` the way Discord does: line-aware, keeping code fences balanced, at `_MAX_POST`.
- Post the chunks in order in the same thread, and return the first post's id as the message ref.
- If posting any chunk fails, log it as an error.

Before writing the fix, decide the ref and edit semantics with the maintainer in the issue, for example what `update_message` does to a split message.

**Test to add:** a Mattermost adapter test with a fake driver. A 10,000-character body becomes several `create_post` calls, each at or under `_MAX_POST`, all threaded under the same root.

---

## Bug 4: switch-core fails to import on a Windows checkout (CRLF in connector skills)

**File:** `core/switch_core/connections/loader.py`, `FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)` (line 44), used by `_load_skill`.

**What happens:**
- Git for Windows defaults to `core.autocrlf=true`, and the repo has no `.gitattributes`, so every `connections/catalog/*/skill/SKILL.md` is checked out with `\r\n` line endings.
- The frontmatter regex requires bare `\n`, so it doesn't match. `_load_skill` then raises `CatalogError: Connection airtable SKILL.md needs frontmatter with name: airtable and a description.`
- That happens at **import time**: `loader.py` line 838 runs `CATALOG = load_catalog(CATALOG_ROOT)` at module level.
- So anything that imports `switch_core.connections` (which includes `agent_templates`, `template_runs` and the app itself) crashes on a Windows checkout.

**Repro** (Windows, Git for Windows defaults):
```bash
git clone https://github.com/sandbox-quantum/switch.git && cd switch/core
uv sync
uv run python -c "import switch_core.agent_templates"
```
Output:
```
switch_core.connections.loader.CatalogError: Connection airtable SKILL.md needs frontmatter with name: airtable and a description.
```
`file core/switch_core/connections/catalog/airtable/skill/SKILL.md` reports `ASCII text, with CRLF line terminators`. Re-checking those files out with `git -c core.autocrlf=false checkout -- core/switch_core/connections/catalog` makes the import succeed, which confirms the cause.

**Proposed fix:**
1. Make the parser tolerant: normalise the file content with `content.replace("\r\n", "\n")` before matching, or use `\A---\r?\n(.*?)\r?\n---\r?\n`.
2. Add a `.gitattributes` with `* text=auto eol=lf` (at least for `core/**/*.md`, `*.yaml` and `*.py`), so checkouts are consistent on every OS.
3. Add a test that loads a skill written with CRLF.

**Related, not duplicates:** #1335 (Windows initdb failure), #1357 (dev setup docs). Neither covers this.

**Search done:** issues and PRs searched for "CRLF", "autocrlf", "line endings" and "frontmatter": nothing matching.

---

## Bug 5: Console doesn't fill template params in a managed agent's instructions

**File:** `console/apps/switch-console-desktop/src/renderer/features/templates/use/managed-run.ts`. Around lines 147–167, `filled(...)` is applied to `description`, `model` and `isolation`, but `instructions` is passed as the raw `entry.instructions`.

**What happens:**
- On a server with agent management, Console posts agents to `/rooms/from-template` with their instructions already final, so the server doesn't interpolate them either.
- `docs/TEMPLATES.md` says params are referred to as `{name}` "anywhere below", and `plan_template` (the `run_template` path an agent uses) does fill them. So the same template behaves differently depending on who runs it.
- No error is shown. The agent just receives literal `{engine_dir}`.

**Evidence from the live run** (Console 0.40.1, server 0.31.0): the controller's `watchers/<agent id>/config.json` has `start.input.agentDefinition.prompt` containing `{uv} run --project {engine_dir} precedent --home {state_dir}…`, with params given in the form. The Auditor also reported it in the room.

**Proposed fix:** `const body = filled(entry.instructions);` and use `body` in both branches at line 158. Add a test to `managed-run`'s suite that a `{param}` in `instructions` is filled and an unknown `{word}` is left alone.

**Search done:** issues and PRs searched for template instructions and placeholder/interpolation terms: nothing matching. Check again before filing.

---

## Already reported (don't file): on Windows, the template form says every provider is "Not supported here"

**This is sandbox-quantum/switch#1511, opened 2026-11-05 by someone else.** Our notes below add detail. Our workaround: write `provider: claude` literally and use a `type: machine` param, so the form never shows the broken picker.

Seen 2026-11-05 on Windows 11, Console v0.40.1, while using a template with a `type: provider` param.

**What happens:**
- `main/core/agent-types/availability.ts` (`listLocalAgentTypeAvailability`) marks every provider unavailable when `process.platform === 'win32'`, with the reason "SDK sessions require a POSIX SSH execution host."
- But `main/core/embedded-controller/embedded-controller-service.ts` lists `win32` in `SUPPORTED_PLATFORMS`, and its message says "Managed agents run on macOS, Linux and Windows."
- So the provider picker shows **Not supported here** on all five tiles and "No agent type is set up for Switch on this computer. Install an agent CLI…". Installing a CLI can't fix that. **Create all** stays disabled with "Fill in Provider", with no hint to turn on "Run managed agents on this computer".
- Separately, Settings → Agent providers shows "Claude Code · CLI not installed" and "Found v2.1.318 installed" in the same panel. The controller's own precheck found Claude installed and signed in (`provider-precheck.json`).

---

## Lead (unconfirmed): the native local server dies silently on Windows, and Console never restarts it

Seen 2026-11-04 on Windows 11 with Console's native local server (switch-core 0.31.0):

- switch-core started cleanly at 19:13:07 (`Uvicorn running on http://127.0.0.1:53043`). Its log then **stops at 19:14:20, with no error or traceback**.
- At 19:14:54, Postgres logs "connection was forcibly closed by the remote host" for every pooled connection. That means the process was terminated, not shut down.
- Nothing was logged in the Windows Application event log.
- Postgres kept running. Console then logged "Could not reach http://localhost:53043" every 30 seconds, and offered "Choose your workspace → Retry", which can never succeed because nothing restarts the server.

- Later the same evening, the setup page showed **"✓ Local server is running"** with **Continue** enabled. At that same moment there was no switch-core process (`Win32_Process` has no `switch_core`/`uvicorn` command line), nothing was listening on 53043, `/health/ready` refused the connection, and `switch-core.log` hadn't been written since 19:14:20. So Console reports a dead server as running.

**To confirm before filing:**
1. Restart the server from Console and see whether it dies again, and after how long.
2. Check whether it coincides with Console's update check, the PC sleeping, or antivirus.
3. Find which process owns the switch-core child (`Get-CimInstance Win32_Process`), to see whether Console kills it.

If it reproduces, the bug is "Console doesn't detect or restart a dead native switch-core, and its UI suggests Retry". Check existing Console issues first (e.g. #1441 "Console opens to blank screen" is different).

## Leads checked and ruled out

- `room_wide_mention` is unused in Mattermost `send_message`: not a bug. `CollaborationCore` already renders the mention through `adapter.render_room_wide_mention` before calling it.
- `content_disposition()`, `aliases.py`, `budgets.py`: no defects found.

## Next steps

1. Open 4 issues (titles above, body = the "What happens" and "Repro" sections). Bug 4 is the easiest to get accepted: it's confirmed, has a one-line root cause, and blocks every Windows contributor.
2. Comment on each one tagging `@petr-sandbox` with a plan and asking for the `hackathon` label and to be assigned.
3. Fork the repo and set up the dev environment (`uv sync`, `just test -k chunking`).
4. Once assigned: fix, add tests, run `just check` and `just test`, and open the PR with `Closes #N`.
