# Demo Video Script — Meeting Debt Collector (~3:00)

## What the video MUST contain (per the official rules + judging reality)

- **Under 3 minutes** — judges are not required to watch past 3:00, and they spend ~5–7 minutes per project total. The first 60 seconds decide everything.
- **Footage of the working project** running in Slack (screen recording of your sandbox). Not slides describing it.
- **Publicly visible** on YouTube/Vimeo/Facebook Video/Youku; paste the link into Devpost.
- **No copyrighted music** or third-party material you don't have rights to. Use royalty-free BGM or none.
- **No confidential/sensitive info** — don't show your `.env`, tokens, or real workspace data. Record in the sandbox.
- English (or provide an English translation).

Prep before recording: `DELETE FROM commitments WHERE channel_id = 'C_TEST'` (clear seeded test rows), restart `slack run`, close other apps/notifications, zoom Slack to ~110–125% so text is readable at 1080p.

---

## Script

**Format:** [SCREEN — what to show] / **VO** — what to say. Target pace ~140 wpm.

### 0:00–0:25 — The Hook (problem)

[SCREEN: a busy Slack channel; slowly scroll past messages like "I'll ship the PR by Friday", "I'll send the contract to legal by 5pm"]

**VO:** "Every day, people make promises in Slack. 'I'll ship the PR by Friday.' 'I'll send the contract by five.' And then… they scroll away and die. Nobody tracks them. Nobody follows up. I call that *meeting debt* — and this is the Meeting Debt Collector: a Slack agent that remembers what you promised, and *checks whether it actually happened*."

### 0:25–0:50 — Smart capture (the extractor)

[SCREEN: DM with the bot. Type: "I'll open PR #1 for the changelog by Thursday" — bot reacts/replies. Then type: "I might get to the dashboard stuff at some point" — then ask "what did you track from those two messages?"]

**VO:** "Every message the agent sees is screened by an LLM extractor. Watch: a real commitment — a PR, a deadline — gets captured automatically, with the PR number pulled out as an external reference. But a hedge — 'I *might* get to it' — is rejected. It also rejects questions, past tense, sarcasm, and 'somebody should really…'. Validated against seventeen hand-built test cases: seventeen out of seventeen."

### 0:50–1:35 — Verification: never trust, always check (GitHub MCP)

[SCREEN: ask the bot "is PR #2 merged?" → it answers with real status + merge date. Then ask about PR #1 → "still open".]

**VO:** "Here's the core idea: the agent never takes anyone's word for it. When a commitment points at GitHub, it calls the **real GitHub MCP server** and checks the actual PR. PR 2? Merged — here's the date. PR 1? Still open, last commit three days ago. Someone saying 'done' in Slack is a claim. A merged PR is ground truth. This agent knows the difference."

### 1:35–2:05 — Slack Real-Time Search

[SCREEN: brief shot of the RTS flow — ask about a non-GitHub commitment ("has the Q3 report been sent?"), or show the tool's generated query in the reply/log overlay]

**VO:** "For promises that don't live on GitHub — reports, docs, contracts — it uses Slack's **Real-Time Search API**. An LLM builds the search query, and the agent searches the workspace with the *user's own token*, so it only sees what they can see. If someone already reported it done, you don't get nagged."

### 2:05–2:40 — The payoff: the weekly digest

[SCREEN: type "send me my digest" → Block Kit DM arrives. Point at each line.]

**VO:** "Then, every Monday morning — or on demand — the collector comes knocking. Each overdue commitment is re-verified *live* before it's shown. The merged PR? Silently dropped — no false nagging. The open PR? Listed with its real status. And anything it can't verify says 'check manually' — it never guesses. Clean Block Kit, straight to your DMs."

### 2:40–3:00 — Architecture + close

[SCREEN: architecture diagram, 10 seconds. Then app home / bot avatar.]

**VO:** "Under the hood: Bolt for Python on Socket Mode, a Pydantic AI agent on Groq, SQLite, and two of the hackathon's three technologies — MCP server integration and the Real-Time Search API. Meeting Debt Collector: because a promise in Slack should be worth something. Thanks for watching."

---

## Shot checklist (tick during recording)

- [ ] Commitment auto-captured from a plain message
- [ ] Hedge/vague message rejected
- [ ] GitHub MCP: merged PR verified with date
- [ ] GitHub MCP: open PR shows "open"
- [ ] RTS query moment (even briefly)
- [ ] Digest DM with all three behaviors visible (excluded / open / unknown)
- [ ] Architecture diagram on screen ≥5s
- [ ] Total runtime ≤ 3:00
