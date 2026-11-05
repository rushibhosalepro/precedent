# Precedent

**Teach your team's agents once, in chat.** Every judgment call a manager makes in Slack can become a rule: tested against history, approved by a person, and applied to the next case that fits. A rule is never stretched to cover a case it doesn't fit.

Built for **Flip the Switch** (WeMakeDevs × DevTools Academy × Switch), Track 01: Best Business Workflow.

```
  sam │ @clerk refund for order 4821, INR 64, unopened, bought 17 days ago
Clerk │ C-043 · refund · INR 64 · 17 days · unopened. Sent to the Judge.
Judge │ @priya No rule covers this yet. Reply `approve C-043 #e3cf9b` or `deny C-043 #6c0403`.
priya │ approve C-043 #e3cf9b and make it a rule: unopened items up to 30 days
Auditor │ Draft P-001: unopened, at most 30 days → approve.
        │ Historical cases 43 · evaluated 41 (95%) · newly covered 12 · changed 0 · new conflicts 0
        │ Past decisions it would have made differently: C-004, C-011, C-019. Applies to new cases only.
        │ Reply `adopt P-001 #f4357c` to adopt.
priya │ adopt P-001 #f4357c
  ...next week...
Judge │ @priya P-001@1 applies: approve. Reply `approve C-044 #b57b2d` …
Judge │ No rule applies. Nearly: P-001@1 fails on item_state (opened). Your call.
```

## The problem

Every team re-decides the same things: refunds, expenses, discounts, access. The rules live in one person's head, get applied a little differently each time, and stall when that person is away. Writing a policy document up front never happens. The decisions do happen, though, one at a time, in chat.

## How it works

| Layer | What does it | What it's responsible for |
|---|---|---|
| Conversation | A **Switch** room bridged to Slack (or Discord, Teams…) | Threads, hand-offs, who may talk to whom, who sent what |
| Language | **Clerk**, **Judge** and **Auditor** (all Claude Code; any Switch provider works) | Reading requests, explaining results, drafting rules from the approver's words |
| Decisions | The `precedent` engine (deterministic Python) | Matching, backtesting, verifying approvals, every state change |
| Record | YAML in its own git repository | Cases with append-only history, immutable rule versions, one commit per transition |

**The LLMs interpret; the engine decides.** A rule matches only if the engine says so. It reports one of five results: `match`, `conflict`, `near_miss`, `missing_information` or `none`. Unknown information is never treated as a failed condition.

### Why it can't be done without Switch

- **Approvals are checked against Switch's own records.** The agent passes the engine only the *message id* of the approver's reply. The engine fetches that message from Switch (`POST /agents/{id}/ops/read_context`) and checks the sender id Switch recorded, which an agent can't fake. It then checks the sender is an approver, that the reply quotes the current approval reference (`#e3cf9b`, a hash of exactly what's being approved), that it came after the proposal, and that it wasn't used before.
- **Who can talk to whom is Switch's addressing setting.** Anyone can bring the Clerk a request. Only the owner and their agents can instruct the Judge and Auditor.
- **The workflow is the room.** Hand-offs are targeted messages in one thread per request; the ledger is a Switch room document; the whole team is one Switch template.

### What makes a rule safe to adopt

`rule backtest` replays every past case under **today's rules (A)** and **today's rules plus the draft (B)**, and reports:
- **Unchanged:** A and B agree.
- **Newly covered:** cases B would decide, each compared with what the person actually decided.
- **Changed:** cases where B decides differently from A.
- **New conflicts:** these **block adoption**.
- **Unresolved:** cases missing the data to check, with coverage shown on every report.

`adopt` refuses if the rule set changed after the backtest ran. A new rule applies to new cases only; past decisions stay as they were.

## Try it in two minutes (no Switch needed)

```bash
uv sync
uv run pytest -q
uv run python scripts/rehearse.py
```

`rehearse.py` plays all three demo flows through the real CLI, with approvals read from a local file instead of Switch. It prints the room transcript, the ledger, the stats and the git audit trail. (Offline approvals must be switched on in the config, and the ledger then labels itself a rehearsal.)

## Run it live with Switch

1. **Switch:** install [Switch Console](https://github.com/sandbox-quantum/switch), start the local server, and connect Slack (or Discord) under messaging apps. Sign in to Claude Code and Codex on the machine.
2. **Engine and state:**
   ```bash
   git clone <this repo> && cd precedent && uv sync
   uv run precedent --home ./state init --config precedent.config.yaml --seed seed/cases
   ```
3. **Template:** in Switch Console → Templates, import `precedent.template.yaml`. Set `engine_dir` to this checkout's absolute path and `state_dir` to `<checkout>/state`, then run it. It creates the three agents and the `precedent-approvals` room, with you in it.
4. **Fill in two ids.** Post any message in the room, then run this from any agent's working directory:
   ```bash
   uv run --project <engine_dir> precedent inspect --room <room id>
   ```
   Copy your `sender` id into `approvers[0].id` and the room id into `switch.room_id`, in `state/precedent.config.yaml`. Commit that change in the state repository (`git -C state commit -am "approver"`). The engine refuses to run with uncommitted edits.
5. Ask the Clerk for a refund.

## The commands

| Command | Role | What it does |
|---|---|---|
| `case new --type --source-msg --fields` | clerk | Validates fields and creates a case (idempotent on the request message) |
| `match <case>` | judge | Gives the result and the exact approval lines |
| `decide <case> --outcome --under --approval-msg` | judge | Records a decision after verifying the approval with Switch |
| `rule draft --from --conditions [--supersedes]` | auditor | Drafts a rule (operators: `eq`, `in`, `min`, `max`) |
| `rule backtest <rule>` | auditor | Compares policy sets and gives the adopt line |
| `rule adopt <rule> --approval-msg` | auditor | Activates the rule after a verified approval and a fresh backtest |
| `rule retire-reply` / `rule retire` | auditor | Retires a rule, with a verified approval |
| `ledger`, `stats`, `validate` | any | Reports and integrity checks |
| `inspect --room` | setup | Recent messages with Switch's sender ids |

Exit codes: `2` bad input · `3` refused · `4` state edited outside the engine · `5` Switch unreachable. Agents are instructed that any non-zero exit means "escalate and stop".

## Honest limits

- The agents and the engine run as the same OS user, so editing the state outside the engine is **detected** (every command checks the git state first), not prevented. Prevention needs the engine as a separate service with its own identity.
- Clicking an approval button (a Switch request card) is a convenience; the authority is the verified chat reply. The card's `answered_by` isn't readable with agent credentials yet.
- Auto-apply is off and not part of this version.

## More

- [`architecture.md`](architecture.md): the design, two review rounds, and what changed after testing.
- [`bugs.md`](bugs.md): bugs we found in Switch itself while building this, with reproductions (Track 03).
