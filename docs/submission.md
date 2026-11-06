# Flip the Switch submission: Precedent

Each block is ready to paste. Items marked **[YOU]** need you.

## Project name
Precedent

## Tagline
Answer once. Your AI agents remember.

## Track
Track 01: Best Business Workflow

## Links
| | |
|---|---|
| Repository | https://github.com/rushibhosalepro/precedent |
| README (setup, how Switch is used) | https://github.com/rushibhosalepro/precedent#readme |
| Demo video | https://youtu.be/rHvyygxSsvI |
| Bugs found in Switch | https://github.com/rushibhosalepro/precedent/blob/main/bugs.md |

## Short description
Every team asks the same questions in chat, every week, and the answers live in one manager's head. With Precedent, the manager answers once in Slack and the AI agents keep it as a tested rule. Next time, the agent already knows the answer and the manager just says yes. If a case is different, it asks instead of guessing.

## Full description

### The problem
Can we refund this? Is this okay to expense? Teams answer the same questions again and again. The rules are never written down, get applied a little differently each time, and everything stalls when that one person is away. Nobody writes the policy document up front, but the decisions do happen, one at a time, in chat.

### What it does
Precedent is a Switch room in Slack with three AI agents.

1. **You answer once.** A teammate asks the Clerk for a refund, and the Clerk turns it into a case. No rule covers it, so the Judge asks the manager instead of guessing. The manager approves and types the rule in plain words.
2. **It becomes a tested rule.** The Auditor drafts the rule and replays it on every past decision. On our demo data, it checked 41 of 43 cases and found 12 newly covered and no conflicts. It also showed 3 past cases where the manager had said no but the rule says yes. The manager sees all of this before agreeing.
3. **Next time, just say yes.** A similar request comes in, the Judge cites the exact rule, and the manager confirms in one line. An opened item nearly fits the rule but doesn't, so the Judge names what's different and asks a person.

### How we use Switch
Switch is central, and the project stops working without it.

- **Approvals are checked against Switch's own record.** An agent gives the engine only a message id. The engine reads that message from Switch's agent API and checks the sender id Switch recorded, which an agent can't set for a person. The reply must also quote a code tied to the exact case or rule, come after the proposal, and not have been used before.
- **Switch's addressing decides who can instruct each agent.** Anyone in the room can ask the Clerk. Only the owner and the owner's agents can instruct the Judge and the Auditor.
- **The workflow is the room.** There's one thread per request, the agents hand off to each other in it, and the rule ledger is a Switch room document.
- **The whole team is one Switch template**, which passes Switch's own template validator.

### How it's built
The AI reads the words, and plain code decides. The engine is deterministic Python:
- strict schemas, so an AI can't invent new rule operators
- a matcher where missing information is never treated as a failed condition
- a backtest that compares whole rule sets, and blocks a rule that adds a conflict
- approval checks through Switch
- cases and rules in their own git repository, with one commit per step, immutable rule versions, and tamper detection

The agents are three Claude Code agents, run as Switch managed agents.

### What we tested
There are 31 automated tests, and a clean clone installs, passes them, and plays the full rehearsal. We ran the flows live on Slack through a real Switch server: teaching a rule, a repeat case approved under it, and a near miss. On the live server, an agent's own message offered as an approval was refused with `precedent-judge is not an approver`. The scene where a teammate forges an approval ran in rehearsal and tests, because the live run used one Slack account.

### Challenges
- **Trusting an approval.** Our first design took the approver's name from the agent, which meant trusting the very thing we were checking. So the engine now asks Switch directly.
- **Backtesting honestly.** A new rule has to be tested alongside the existing ones. We also report coverage, and we show past disagreements as information, not mistakes.
- **Live testing beat assumptions.** Our template passed validation, but a live agent told us in the room that its instructions still had `{engine_dir}` in them. That turned out to be a bug in Switch Console, and we worked around it and documented it.

### Honest limits
- Tampering with the state is detected, not prevented, because the agents and engine share an OS user.
- A person still confirms every case. Automatic application isn't built.
- The demo's 42 past cases are synthetic.

### Bugs found in Switch
We documented 5 bugs with evidence and proposed fixes, including one that stops `switch_core` importing on Windows checkouts and one that leaves template params unfilled in managed agents' instructions.

### Inspiration
Inspired by OneDecision, a winner at the Agents for Humans Hackathon. Precedent brings the idea into team chat, with people and several agents in one room, and approvals verified through Switch.

### AI assistance
Built with Claude Code as a pair programmer, covering the engine, tests, template, docs and video. The video's voice-over is AI-generated. **[YOU]** Add what you decided and checked yourself. For example: choosing the idea, the reviews you ran, the live Switch and Slack setup, and reviewing the video.

## Social post (#HowISwitch)
**[YOU]** Attach the video or a clip.

> Every team answers the same questions in chat, every week. Precedent: answer once in Slack, and your AI agents remember it as a tested rule. Different case? It asks you. Built with Switch for #FliptheSwitch.
> https://youtu.be/rHvyygxSsvI #HowISwitch

## Before you submit
- [ ] Be ready to explain the code yourself, because the rules ask for this. Key parts: `matcher.py`, `backtest.py`, `verify.py`, and why the agent passes only a message id.
- [ ] Check the repo opens logged out, and that the video link works in a private window.
- [ ] Confirm on the Rules tab that the video length and AI voice are within the rules.
- [ ] Submit by **Nov 7, 11:59 PM IST**. Aim for earlier.
- [ ] Optional: file bugs 4 and 5 for Track 03, and ask for the `hackathon` label.
