# Submission draft: Flip the Switch

**Project name:** Precedent
**Track:** 01, Best Business Workflow (also: Code with Wispr, Best Blog)
**Tagline:** Teach your team's agents once, in chat. Decisions become tested, versioned rules, and Switch proves who approved them.

## What it does
Teams re-decide the same judgment calls in chat every week, such as refunds, expenses and exceptions, and the rules live in one person's head. Precedent puts three agents in a Switch room:
- the **Clerk** turns a request into a structured case
- the **Judge** checks it against the rules the room has been taught
- the **Auditor** turns an approver's decision into a new rule, backtested against every past case before it can be adopted

Next time, the room proposes the decision itself and cites the exact rule version. When a rule nearly fits, it names the condition that fails and asks a person instead of stretching the rule.

## How Switch is used (and why it can't be removed)
- **Approvals are checked against Switch's own records.** Agents give the engine only a message id. The engine reads that message from Switch's agent API and checks the sender id Switch recorded, plus a hash reference binding the approval to the exact case version or rule.
- **Switch's addressing policies** decide who can instruct each agent.
- **Hand-offs and threads** between the three agents happen in one room, with the ledger kept as a room document.
- **The whole team is one Switch template**, validated with Switch's own template linter.

## How it's built
- Python engine (strict schemas, deterministic matcher with true/false/unknown conditions, a backtest that compares whole rule sets, approval verification).
- State in its own git repository: one commit per transition, append-only case history, immutable rule versions, tamper detection.
- Agents: three Claude Code agents, run as Switch managed agents.
- 30 tests; `scripts/rehearse.py` replays the full demo offline.

## Challenges
- Making an LLM-driven workflow trustworthy: identity comes from Switch, the decision comes from code, and every failure escalates to a person instead of approving.
- Backtesting honestly: reporting coverage, and treating past disagreement as information, not error.

## Contributions to Switch (Track 03)
While building, we found and documented 4 bugs in Switch core, each with a reproduction (see `bugs.md`), including one that stops `switch_core` importing on Windows checkouts.

## Links
- Repo: <fill in>
- Demo video: <fill in>
- Blog post: <fill in>
- Wispr scorecard: <fill in, if entering>
