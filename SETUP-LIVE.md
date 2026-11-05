# Live setup: Precedent on a real Switch server

A checklist from nothing to the end-to-end milestone. Every Switch step below comes from Switch's own docs (`switch-core/docs/official/getting-started/` and `deploy/messaging-apps/`).
Tick each box. When a **🔎 check** fails, stop and note it in `bugs.md` (if it's Switch's fault) or tell me (if it's ours).

Estimated time: about 60–90 minutes, most of it Slack app setup and first sign-ins.

---

## Part A: Switch running (about 30 min)

### A1. Install Switch Console
- [ ] Download the Windows `.exe` or `.msi` from https://github.com/sandbox-quantum/switch/releases and install it.
- [ ] Open it. The **Setting up Switch** checklist appears in the sidebar.

### A2. Add a server: "Run a server on this computer"
- [ ] Choose **Add a server → Run a server on this computer**. No Docker is needed; it takes about a minute.
- [ ] 🔎 The top of the sidebar says **Running locally**.

> Windows risk: issue #1335 ("initdb.exe failed" when using a local PostgreSQL). If you hit it, uninstall or stop the local PostgreSQL so Console uses its bundled copy, or install Docker Desktop and retry.

**Pick the messaging app (decide now):**

| Option | Effort | Use it if |
|---|---|---|
| **Mattermost** (built in) | About 0 min: on by default when **Docker Desktop** is installed and running | You want the fastest path. Open it via server **Home → Messaging apps → Sign-in details…** |
| **Slack** | About 15 min: create an app from a manifest and paste two tokens | You have a Slack workspace where you can install apps. Looks best in the demo |
| Discord | About 15 min | You'd rather use Discord |

**My recommendation:** get the whole flow working on **Mattermost first** if you have Docker (nothing to set up), then add Slack for the recorded demo. If there's no Docker, go straight to Slack.

### A3. (Slack only) Connect Slack
- [ ] In Console: **Connect a messaging app → Use your own app instead → Slack**. Console opens Slack with the app manifest filled in.
- [ ] Create the app in your workspace, then paste the **two tokens** Console asks for. It checks them and fills in the workspace id.
- [ ] Nothing needs to be publicly reachable; Slack connects over Socket Mode, so a laptop works.
- [ ] ⚠ The manifest declares the app an *Agent*, which blocks workspace guests. In a personal workspace that's fine.
- [ ] If linking fails with `missing_scope … needed: users:read`, the app wasn't created from Switch's manifest. In the app's settings, open **App Manifest**, paste `slack-manifest.json` over the JSON, save, then **Install App → Reinstall to Workspace**. If the `xoxb-` token shown there changed, update it in Console.

### A4. Link your messaging account (**don't skip**)
- [ ] Server **Home → Messaging apps → Link**, search for yourself, then **This is me**.
- [ ] 🔎 The row shows your handle instead of **No account linked**.

> Without this, the Judge and Auditor ignore you ("only takes instructions from its owner").

### A5. Agent providers
- [ ] **Settings → Agent providers:** **Claude Code** and **Codex** both say **Installed**.
- [ ] You're signed in to both on this machine (`claude` and `codex login`).
- [ ] **Settings → General → Auto-trust worktree directories** is on (the default).

### A6. Smoke test Switch itself (5 min)
Before Precedent, prove Switch works with one throwaway agent:
- [ ] **Your Agents → add an agent** (Claude Code, any empty folder), and create a room with it on your messaging app.
- [ ] In the channel, ask `@<agent> what files are in your working directory?`
- [ ] 🔎 It answers from your machine. If not, see the "When a step doesn't match" table in `docs/official/getting-started/smoke-test.md`.

---

## Part B: Precedent installed (about 10 min)

Run these in Git Bash (or PowerShell; the commands are the same):

```bash
cd D:/projects/hackathons/switch/precedent
uv sync
uv run pytest -q
```

```bash
uv run precedent --home D:/projects/hackathons/switch/precedent/state init --config precedent.config.yaml --seed seed/cases
```

- [ ] 🔎 `init` prints `"imported_cases": 42`.
- [ ] Write down the two absolute paths:
  - `engine_dir` = `D:/projects/hackathons/switch/precedent`
  - `state_dir` = `D:/projects/hackathons/switch/precedent/state`

> Use forward slashes. The agents run these paths through a shell.

---

## Part C: The template (about 10 min)

### C1. Run the template

> Import `precedent.local.template.yaml`, not `precedent.template.yaml`. Console leaves `{params}` unfilled in agents' instructions (`bugs.md`, Bug 5), so render your paths in first:
> `uv run python scripts/render_template.py --state-dir <absolute state path>`. The form then only asks for the messaging app and machine.

- [ ] Console → **Templates**. Add `precedent.template.yaml` as a template.
  - If your Console version has no import button, ask the Switch expert agent in Console: "Save this file as a template: `<path>`". It has `save_template`.
- [ ] Fill the form:
  - `team` = `precedent`
  - `engine_dir` and `state_dir` as written down in Part B
  - `bridge` = your messaging app
- [ ] Run it.
- [ ] 🔎 Three agents appear (`precedent-clerk`, `precedent-judge`, `precedent-auditor`), plus a room `precedent-approvals` with you in it.
- [ ] 🔎 After the kickoff, the agents say hello, and the Auditor creates the **"Precedent ledger"** room document. It says "No rules yet".

> If the run is refused, the reason has a code: `provider_not_installed`, `provider_login_missing`, `name_taken`, and so on. Fix that and run it again; nothing is half-created.

### C2. Fill in the approver id and room id (the **Q3/Q4 spike**)
1. [ ] In the channel, post anything, e.g. `hello from priya`.
2. [ ] Get the room id. Ask in the channel: `@precedent-judge what is this room's id?` (it knows from `connect_to_room`). Or read it from the room's page in Console/Gateway.
3. [ ] From the Judge's working directory, which holds its credentials:
   ```bash
   cd "<Console's agents folder>/precedent-judge"
   uv run --project D:/projects/hackathons/switch/precedent precedent inspect --room "<room id>"
   ```
   - The Judge's folder is shown on the agent's page in **Your Agents**.
   - It must contain `.switch/agents/precedent-judge.json`.
4. 🔎 **This is the key test (Q3).**

| What you get | Meaning | Next |
|---|---|---|
| A list of messages with `sender` ids | ✅ Q3 works: the engine can read Switch with the agent's own token | Continue |
| `switch_unavailable … 401/403` | The token isn't accepted for `ops/read_context` without a live session | Use the fallback below, and tell me the exact message |
| `switch_unavailable … 409` / "connection" | The operation needs a live connection header | Same fallback |

**Fallback (already built):**
1. Set `agent_reported_approvals: true` in `state/precedent.config.yaml` and commit.
2. The Judge and Auditor then pass `--approval-entry '<the message JSON from their read_context tool>'` alongside `--approval-msg`.
3. Every approval made this way is recorded as `verified_via: agent_reported`, and the ledger says so.
4. Tell me, and I'll add that one line to the two agents' instructions.

5. [ ] 🔎 **Q4:** find your `hello from priya` line. Its `sender` is your id. Check that `sender_kind` is absent or `null` for your message, and look at what an agent's message shows (its kickoff hello).
6. [ ] Put both ids into the state repo's config and commit. The engine refuses to run with uncommitted state edits, by design:
   ```bash
   cd D:/projects/hackathons/switch/precedent/state
   ```
   Edit `precedent.config.yaml`:
   - `approvers[0].id` = your `sender` id
   - add `switch: { room_id: "<room id>" }`
   ```bash
   git commit -am "approver and room ids from the live server"
   ```
7. [ ] Save the `inspect` output to `precedent/tests/fixtures/read_context.live.json`, so the tests can pin the real shape. Remove anything private first.

---

## Part D: The end-to-end milestone (about 15 min)

In the channel, as yourself:

| # | You type | 🔎 Expect |
|---|---|---|
| 1 | `@precedent-clerk refund for order 4821, INR 64, unopened, bought 17 days ago` | The Clerk replies in a thread: `C-043 · refund · INR 64 · 17 days · unopened. Sent to the Judge.` |
| 2 | – | The Judge, in the thread: "No rule covers this yet. Reply `approve C-043 #……` or `deny C-043 #……`" |
| 3 | `approve C-043 #…… make it a rule: unopened items up to 30 days` (copy the exact code) | The Judge: `C-043 approved by priya under manual.` It hands off to the Auditor |
| 4 | – | The Auditor posts the draft, the summary line (`evaluated 41 (95%) … new conflicts 0`), C-004/C-011/C-019, and `adopt P-001 #……` |
| 5 | `adopt P-001 #……` | `P-001@1 is active.` The ledger document updates |
| 6 | `@precedent-clerk order 5102, INR 31, unopened, 22 days` | The Judge: "P-001@1 applies: approve. Reply `approve C-044 #……`" |
| 7 | `@precedent-clerk order 5110, INR 64, opened, 22 days` | The Judge: "No rule applies. Nearly: P-001@1 fails on item_state" |

**Q2 check** at step 3: do you need to `@precedent-judge` in your reply, or does a plain thread reply reach it?
- If a plain reply works, great.
- If not, prefix your replies with `@precedent-judge` / `@precedent-auditor`. That's fine for the demo; tell me and I'll update the agents' wording.

Afterwards:
```bash
git -C D:/projects/hackathons/switch/precedent/state log --oneline
```
🔎 One commit per step, each naming your sender id and the message id.

---

## If something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| The agent says it only takes instructions from its owner | Messaging account not linked | A4 |
| The agent "isn't available / no session" | No session running | Console starts one when the agent is addressed; check **Your Agents** |
| Engine exit `4`: "changed outside the engine" | You edited `state/` without committing | Inspect with `git -C state status`, then commit or revert |
| Engine exit `3`: "reference does not match" | A stale or mistyped `#code` | Copy the newest line the Judge posted |
| Engine exit `3`: "not an approver" | `approvers[0].id` isn't your real `sender` | Redo C2 |
| Engine exit `2`: "expected exactly one .switch/agents/*.json" | The agent ran from the wrong folder | Its working directory must be its own Console folder |
| `uv` not found inside agent sessions | `uv` isn't on the PATH that sessions inherit | Use the full path to `uv.exe` in the template's commands (tell me and I'll add a param) |

## What to send me after Part C2

1. The output of `inspect` (redact anything private).
2. Whether Q2 needed an `@`-mention.
3. Any refusal message, word for word.

With those I can pin the tests to the real responses and fix any wording before you record the demo.
