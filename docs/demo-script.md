# Demo video script (1:14)

The explainer is built with Remotion in `../precedent-video` (`npm run voice`, `npm run music`, then `npm run render` writes `out/precedent.mp4`). The lines below are the on-screen captions and the voice-over; they live in `src/scenes.tsx`. Every case, hash, count and refusal comes from `scripts/rehearse.py`. The first, slower cut is in `precedent-video/archive_v1`.

| Time | Scene | Narration |
|---|---|---|
| 0:00 | **Cold open:** four real seed cases, then the open questions | Approved. |
| 0:00 | | Denied. |
| 0:01 | | Approved. |
| 0:01 | | Denied. |
| 0:02 | | Same manager. Same kind of refund. Nobody wrote down why. |
| 0:05 | | Now hand that job to an AI agent. |
| 0:08 | | What stops it guessing? What stops someone faking the approval? |
| 0:11 | **Title** | This is Precedent. Teach your team's agents once, in chat. |
| 0:15 | **Teaching the room** | A refund request lands in the team's chat. No rule covers it. |
| 0:19 | | So the agent won't guess. It asks Priya. |
| 0:21 | | She approves, and in the same reply, teaches a rule. |
| 0:25 | **The backtest:** 43 cases as tiles | Before it goes live, the rule is replayed against every past decision. |
| 0:30 | | Twelve cases newly covered. Zero conflicts. |
| 0:33 | | But look. Three times, Priya denied what this rule would approve. |
| 0:36 | | She sees that before she says yes. |
| 0:38 | | Adopted. |
| 0:39 | **The next cases** | Next week, same kind of request. The agent cites the rule, and Priya confirms in one line. |
| 0:45 | | Then, nearly the same, but opened. Close isn't good enough. |
| 0:48 | | It goes back to a person. |
| 0:50 | **The forged approval:** the climax | So let's try to cheat it. Sam copies the approval line, character for character. |
| 0:54 | | The agent only passes along a message id. |
| 0:57 | | The engine asks Switch who really sent it. |
| 0:59 | | Sam isn't an approver. |
| 1:00 | | Refused. |
| 1:00 | | Nothing gets recorded. |
| 1:03 | **How it's built** | The LLMs only interpret. A deterministic engine decides. |
| 1:07 | | Switch proves who said what. Every step is a git commit. |
| 1:11 | **Close** | Teach it once. Every rule tested. Every approval checked. |

## What this script deliberately doesn't claim
- **"Handles it automatically."** Auto-apply isn't in this version, so a matching case still gets Priya's one-line confirmation. The script says so.
- **"40 of 40 → 9 of 40."** That number from `plan.md` was never measured, so it's left out.

## Update: third cut (1:49)
The table above is the first cut. The current narration lives in `src/scenes.tsx`. It now opens on the everyday problem, explains the idea in three plain steps by 0:29 ("Answer once. Your AI agents remember."), then shows it working, with real Slack footage (`public/real/`) and a live refusal.

## Before submitting
- [x] **Add real footage.** Screenshots from a live Slack run, shown in their own scene and labelled as live.
- [x] **Complete Flow 2 live.** C-044 was approved under `P-001@1` on the live server (commit `43750ac`).
- [x] **A live refusal.** Offered as an approval on the live server, the Judge's own message was refused: `precedent-judge is not an approver; approvers: rushibhosale84`.
- [ ] **Sam's refusal live.** Sam's own forged line has only run in the rehearsal and tests, because the live runs used one Slack identity. It needs a second account. The video's closing note says so.
- [ ] The voice-over is a synthetic Edge neural voice, so say so if the rules ask. If entering **Code with Wispr**, screenshot Insights for the usage scorecard.
