# PR rules: Switch Track 03 (Best Core Contribution)

Sources: the hackathon page (Track 03 rules), `switch-core/CONTRIBUTING.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/workflows/pr-ci.yml`, `CLAUDE.md`, and merged/open hackathon PRs (e.g. sandbox-quantum/switch#1333).

## 1. Hackathon rules (what gets a PR judged)

| Rule | What it means for us |
|---|---|
| Only issues labelled **`hackathon`** count | Our bugs are new, so they have no label yet. **File the issue, then ask for the label** |
| **Get assigned before writing code** | Comment on the issue tagging `@petr-sandbox` with a 1–2 line plan. Wait until you're assigned. A PR for an issue that isn't assigned to you **won't be judged** |
| One person per issue | If someone already asked for it, pick another |
| Max **5 open PRs** at a time | We have 4 bugs, so that's fine |
| No spam, no low-effort PRs | Typo, formatting-only or unreviewed AI output won't be judged. Every PR needs a real test |
| 48 hours with no activity → the issue can be reassigned | Start as soon as you're assigned |
| **Deadline:** the PR must be open by **Nov 7, 11:59 PM IST** | Aim for Nov 6 |
| Top 20 PRs win **$100 each** | Quality over count |

## 2. Repository rules (what gets a PR merged)

**CLA (required, one time):** after you open the PR, a bot comments. Reply with exactly:
> I have read the CLA Document and I hereby sign the CLA

**Before opening the PR, run** (CI runs the same):
```bash
just check
```
```bash
just typecheck
```
```bash
just test -k <your test>
```
Without `just`, the CI equivalents from `core/` are:
```bash
uv run ruff format --check .
```
```bash
uv run ruff check .
```
```bash
uv run mypy --config-file pyproject.toml switch_core/
```
```bash
uv run pytest tests/switch_core/<path to your test>
```

**Code style (`CLAUDE.md`):**
- Imports at the top of the file only.
- Ruff with `E, F, I, UP` rules; line length isn't enforced.
- **No comments that narrate the change** ("fixed X by…"). That goes in the PR description.
- Avoid optional parameters and defaults unless they're truly needed.
- **Fail loud, never fake:** no silent fallbacks, and use warning/error logs for degraded paths.
- Tests mirror the module path under `core/tests/switch_core/`. Store tests use real PostgreSQL, not mocks.
- **The repo is public.** No tokens, hostnames, personal emails or Slack ids, including in test fixtures.

**Commit messages:** Conventional Commits: `fix(scope): short imperative summary`, e.g. `fix(connections): accept CRLF line endings in connector skill frontmatter`.

**PR title convention used by hackathon PRs:** `fix(scope): summary (#issue) #FliptheSwitch`.

**PR body:** fill in the repo template. Delete the agent-CLI and messaging-platform sections when they don't apply:
```markdown
## What this changes
<1–2 sentences: what changes for someone using Switch, and why.>

Closes #<issue>

## How it was tested
<What you ran and what you saw: the failing case before, passing after, and the test names.>

#FliptheSwitch
```

**Only for messaging-platform PRs** (our bugs 1–3 *change* adapters): the template's platform section asks for an adapter test summary and a video. For a small bug fix inside an existing adapter, paste the adapter test summary and **say in the PR why a video isn't included** (a pure chunking fix with no new platform behaviour), or record a 30-second clip if possible.

**Changelog:** `CHANGELOG.md` is per artifact (switch-core, switch-console, and so on). Recent community fix PRs (e.g. sandbox-quantum/switch#1333) don't touch it. Leave it out unless the maintainer asks.

## 3. Issue rules (`bug_report.yml`)

Required fields:
- **Component**
- **Version or commit:** we use `e47cab4` (also check that it still happens on the current `upstream/main`)
- **What happened** (observed vs. expected)
- **Steps to reproduce**

Optional fields: **Logs**, **Environment** (OS, provider, messaging app).

## 4. Our workflow per bug

1. `git fetch upstream` and confirm the bug **still reproduces on `upstream/main`**. Someone may have fixed it since.
2. Search issues and PRs once more for duplicates.
3. File the issue (template fields above, repro from `bugs.md`). **You** post it from your GitHub account.
4. Comment: `@petr-sandbox I'd like to fix this for Flip the Switch. Plan: <one line>. Could you add the hackathon label and assign me?`
5. **Wait for assignment.** Meanwhile I can prepare the fix on a local branch, without pushing or opening anything.
6. Once assigned:
   ```bash
   git switch -c fix/<short-name> upstream/main
   ```
   Make the fix plus a test, run `just check`, `just typecheck` and the test, then commit and push to `origin` (your fork).
7. Open the PR against `sandbox-quantum/switch:main` with `Closes #N`, and sign the CLA in the comments.
8. Respond to review comments within a day.

## 4b. Open-issue scan (2026-11-04, evening)

- **All 63 open `hackathon` issues are already assigned to 4–10 people each.** "One person per issue" isn't how the maintainer works in practice: they assign everyone who asks, and the PRs compete.
- Most issues already have 1–4 open PRs.
- On #799 the maintainer (`petr-sandbox`) pointed newcomers to the least contested issues: **#785 Auggie, #787 Junie, #795 Webex, #797 Lark/Feishu**. Those now have 2–4 PRs each too (#1345 #1243 #1065 · #1463 #1115 #1067 · #1234 #1027 · #1239).
- Every `hackathon` issue was opened by the maintainers (`amaudruz`). Community-found bugs (#453, #1320, #1158) were **not** given the label, and nobody was assigned to them.

**What this means:**
1. **Our own bugs have zero competition**, but only count for Track 03 if the maintainer labels them `hackathon`. We must **ask explicitly** in the issue.
2. Official issues count for sure, but we'd be the 3rd–5th PR on each. To place in the top 20, ours must be the best-built one.
3. Agent-CLI issues need that CLI installed and signed in, plus a video. Messaging-platform issues need a developer account on that platform, plus a video.

## 5. Which bug first

| Bug | Fit for Track 03 | Why |
|---|---|---|
| **4, Windows CRLF import crash** | ⭐ Best | Confirmed by running it, one-line root cause, small fix plus `.gitattributes`, easy to test, blocks every Windows contributor |
| 2, Discord one-line fence | Good | Pure function with a clear repro test; touches only `discord/chunking.py` |
| 1, Telegram entity split | Good | Pure function with a clear repro test; touches only `telegram/chunking.py` |
| 3, Mattermost long posts dropped | Bigger | Needs a design decision on edit semantics, so ask the maintainer in the issue first |
