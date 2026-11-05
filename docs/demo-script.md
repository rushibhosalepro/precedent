# Demo video script (target 2:45)

Record the screen at 1080p: Slack (or Mattermost) on the left, a terminal on the right for the last scene.
**Have ready:** a fresh state (`precedent init … --seed seed/cases`), the template already run, and the ledger document showing "No rules yet".
**Fallback:** if the live room misbehaves, record `uv run python scripts/rehearse.py` and narrate the same beats.

| Time | On screen | Say (roughly) |
|---|---|---|
| 0:00–0:15 | A title card: **Precedent, teach your team's agents once, in chat** | "Every team re-decides the same things in chat: refunds, expenses, exceptions. The rules live in one person's head. Precedent turns those decisions into tested rules, and Switch is what makes it safe." |
| 0:15–0:30 | The Switch room: three agents and Priya | "This is a Switch room in Slack. Three agents: the Clerk takes requests, the Judge checks rules, the Auditor writes new ones. Only Priya can approve, and Switch enforces that." |
| 0:30–1:05 | **Flow 1.** Sam asks for a refund; the Clerk makes C-043; the Judge says no rule covers it | "No precedent, so the Judge doesn't guess. It asks Priya, and gives her an exact line to reply with. That `#e3cf9b` is a hash of exactly this case and outcome." |
| | Priya replies `approve C-043 #… make it a rule: unopened up to 30 days` | "She approves, and teaches the room in plain words." |
| 1:05–1:35 | The Auditor's backtest message | "Before the rule exists, the Auditor replays all 43 past cases with today's rules and with the new one. 95% could be evaluated. 12 newly covered, zero conflicts. And three times Priya denied a case this rule would approve. That's shown as information, not as mistakes, and the rule applies to new cases only." |
| | Priya: `adopt P-001 #…`; the ledger document updates | "She adopts it. It's now in the room's ledger." |
| 1:35–1:55 | **Flow 2.** A similar request; the Judge cites P-001@1 | "Next week, a similar case. The Judge cites the exact rule version. One reply." |
| 1:55–2:15 | **Flow 3.** An opened item; near miss | "An opened item. The rule nearly fits, but the Judge names the condition that fails and refuses to stretch it." |
| 2:15–2:35 | Terminal: Sam tries to approve (refused); then `git -C state log --oneline` | "And trust: when Sam types the approval line, the engine asks Switch who sent it and refuses. Every decision is a git commit naming the approver's Switch id and the message." |
| 2:35–2:45 | The architecture diagram from the README | "LLMs read and write language. A deterministic engine decides. Switch carries the conversation and proves who said what. Precedent." |

**Checklist before recording:**
- [ ] Notifications are muted, and no tokens are visible in the terminal or Console.
- [ ] Font size is large enough to read on a phone.
- [ ] Every approval line is pasted exactly. A typo shows the refusal, which is fine, but not mid-flow.
- [ ] If entering **Code with Wispr**, dictate the prompts and narration with Wispr Flow, then screenshot Insights for the usage scorecard.
