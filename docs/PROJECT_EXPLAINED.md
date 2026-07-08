# Meeting Debt Collector — Everything It Does, and Why

This is the "know your own project cold" document. Every component, every design decision, every gotcha — written so you can answer any judge question without looking at code.

---

## 1. The One-Sentence Pitch

Slack is full of promises ("I'll ship PR #482 by Friday") that scroll away and die. Meeting Debt Collector automatically captures those promises, verifies whether they actually happened against **ground truth** (GitHub, via MCP) and **workspace context** (Slack Real-Time Search), and sends each person a weekly Block Kit digest of what they still owe.

The core idea judges should remember: **it never trusts anyone's word — it checks.** A commitment isn't "done" because someone said so in Slack; it's done when the PR is actually merged.

## 2. The Stack (and why each piece)

| Piece | Choice | Why |
|---|---|---|
| Slack framework | **Bolt for Python**, Socket Mode | Official SDK; Socket Mode needs no public URL, so it runs anywhere |
| Agent framework | **Pydantic AI** | The `slack-samples/bolt-python-starter-agent` template ships three variants; Pydantic AI has first-class Groq support (`groq:openai/gpt-oss-120b` via a model string) and its MCP client class is the same one used for both Slack MCP and GitHub MCP — one pattern everywhere |
| LLM | **Groq, `openai/gpt-oss-120b`** | Fast + cheap; `llama-3.3-70b` failed the sarcasm and multi-commitment test cases (15/17); `gpt-oss-120b` passes all 17. JSON mode + temperature 0 for deterministic structured output |
| Storage | **SQLite** (`commitments.db`) | One file, stdlib, zero setup. Two tables is not a "database project" — a server DB would be pure overhead |
| Scheduling | **stdlib `threading`** hourly poll | A daemon thread that checks "is it Monday 9:00 UTC?" once an hour. No cron, no Celery — nothing else was needed |

## 3. How a Message Flows Through the System

1. A user DMs the bot (or @mentions it, or uses the Assistant panel). Slack delivers the event over a **Socket Mode WebSocket** — our process connected *outbound* to Slack, so no public URL is required.
2. The Bolt listener (`listeners/events/message.py`) fires. Before the agent even replies, it does **auto-capture**: `store.upsert_user_token()` (remembers the user's token for the weekly digest) and `store.track_message()` (runs the commitment extractor on the raw message and persists any hits). This is wrapped in its own try/except — **a capture failure can never break the live reply**.
3. The Pydantic AI agent runs with conversation history (in-memory, keyed by `(channel_id, thread_ts)`) and its five tools. It replies in-thread, streamed, with feedback buttons.
4. Independently, a background scheduler fires every Monday 9:00 UTC, pulls each user's overdue commitments, **re-verifies each one live** (GitHub MCP + RTS), composes a digest with an LLM, and DMs it as Block Kit.

## 4. The Four Custom Tools (the heart of the project)

### 4.1 `extract_commitments` — the commitment extractor (Stage 1)

- **What:** LLM few-shot classifier/extractor. Input: message text + up to 3 preceding thread messages. Output: JSON list of `{who, what, deadline_raw, deadline_resolved, confidence, external_ref, external_ref_type}`.
- **The hard part is what it REJECTS:** hedges ("I might…"), questions ("should I…?"), past tense ("I sent it yesterday"), requests aimed at others ("can you close JIRA-88?"), plural non-ownership ("we should really…", "the team will…", "someone needs to…"), vague intentions with deadlines ("I'll think about it by Friday"), commitments with no deadline at all, and **sarcasm detected from thread context** ("sure, I'll totally have that done in an hour 🙃" after admitting no progress).
- **Validation:** `validate_extractor.py` — 17 hand-written cases, one per category above, *none copied from the prompt's few-shot examples* (that would test memorization, not generalization). Asserts commitment count on every case plus field values where deterministic. Currently 17/17.
- **Known limitation (be upfront if asked):** `deadline_resolved` is untrusted — the model doesn't know today's date, so "by 5pm today" can resolve to the wrong day. Downstream code treats it as a hint: the store uses it only if it parses as an ISO date, otherwise falls back to the date the commitment was captured.
- **Engineering details:** JSON mode, temperature 0, `max_tokens=1024`. Extraction quality lives entirely in the prompt (spec'd in `docs/SPEC.md`); the code is a thin, testable wrapper.

### 4.2 `check_pr_status` — GitHub verification via MCP (Stage 3)

- **What:** connects to the **real GitHub MCP server** (`https://api.githubcopilot.com/mcp/`, streamable HTTP) and calls its `pull_request_read` tool — `method="get"` for state/merged_at, `method="get_commits"` for the last commit date. Returns `{status: open|closed|merged|unknown, last_commit_date, merged_at}`.
- **Why MCP and not the plain GitHub REST API:** MCP is one of the hackathon's three core technologies, and it's genuinely the same integration class (`MCPServerStreamableHTTP`) the template already uses for the Slack MCP server — one integration pattern, two external systems.
- **Auth:** `GITHUB_TOKEN` in `.env`. `GITHUB_REPO` sets a default repo so users can say "PR 482"; `owner/repo#482` overrides it.
- **Hardening (found in live testing):** a nonexistent PR used to make the MCP call raise and kill the whole digest. Now every MCP call is wrapped, returning `{"status": "unknown", "error": ...}` — and the digest additionally catches per-item, so one bad commitment can never sink the send.

### 4.3 `check_rts_status` — Slack Real-Time Search (Stage 2)

- **What:** for a commitment whose deadline has passed, checks whether it was *already reported done somewhere in Slack* before nagging. Two steps: an LLM prompt turns `{what, external_ref}` into a search query (e.g. "is PR 482 merged or closed?"), then calls Slack's `search.messages` with the **user token** and granular `search:read.*` scopes (this is the RTS API surface).
- **Critical distinction the system prompt enforces:** RTS searches *conversational data* — someone saying "I merged it" in Slack is a claim, not ground truth. RTS **never substitutes** for `check_pr_status`. The digest treats "RTS says done but GitHub says open" as *not done*.
- **Why user token, not bot token:** `search.messages` only works with a user token, and results respect that user's visibility — the agent can't see anything the user can't. If there's no user token (true in local `slack run` dev sessions), the tool returns a clean `{query: None, matches: [], error: ...}` instead of crashing — and the caller says "Slack context check was unavailable."
- **Gotchas hit while building:** `gpt-oss-120b` burns hidden chain-of-thought tokens before answering, so `max_tokens=64` silently returned empty strings — it needs ≥300. And the prompt's few-shot JSON examples contain literal `{}` braces, so template substitution uses `.replace()` instead of `.format()`.

### 4.4 `send_weekly_digest_now` + the scheduler (Stage 4)

- **Store (`agent/store.py`):** SQLite, two tables. `commitments` holds extractor fields + `resolved` flag + GitHub/RTS verification columns. `users` maps user_id → last-seen user token (nothing else in the codebase persists that, and the Monday scheduler needs to know who to DM). `get_overdue(user_id, older_than_days=3)` computes `days_overdue` using `deadline_resolved` if it's a valid ISO date, else the capture date.
- **Composer (`agent/tools/build_digest.py`):** for each overdue item, `_verify()` re-runs `check_pr_status` and `check_rts_status` **live at digest time** (statuses go stale; a PR merged an hour ago must not be nagged about). Then one LLM call composes the human-readable lines. Three behaviors, all validated live in the sandbox:
  1. **Verified-done items are silently excluded** (merged PR → not in the digest at all).
  2. **Open items show real status** ("PR #1 — still open, last commit …").
  3. **Unverifiable items are flagged** ("status unknown — check manually"), never guessed.
- **Output is Block Kit only** (`SectionBlock`), never plain `text=` — richer rendering, and it's the design the spec mandates.
- **Delivery:** `agent/scheduler.py` — daemon thread, polls hourly, fires Monday 9:00 UTC, DMs every user in the `users` table. `send_weekly_digest_now` is the same pipeline exposed as an agent tool so anyone (including a judge) can trigger it on demand with "send me my digest."

## 5. What's Automatic vs. On-Demand

- **Automatic:** commitment capture on every message the bot sees; the Monday digest.
- **On-demand (agent tools, invoked by natural language):** extract commitments from a pasted message, check a PR's status, run the RTS check, send the digest now.

The auto-capture design means the demo works with zero ceremony: just *talk* near the bot and the debt ledger builds itself.

## 6. Hackathon Technology Mapping

- **MCP server integration ✅** — two MCP servers: GitHub (`api.githubcopilot.com/mcp`) for PR verification, Slack (`mcp.slack.com/mcp`) attached as a toolset when a user token is present (search/read/write/canvases).
- **Real-Time Search API ✅** — `check_rts_status` with granular `search:read.*` user scopes.
- **Slack AI capabilities ✗** — not used; the LLM is Groq. (Only 1 of 3 technologies is required; we use 2.)
- **Track:** New Slack Agent.

## 7. Testing Story (judges score "quality of the code")

- 7/7 template pytest suite, ruff clean.
- `validate_extractor.py`: 17/17 extraction cases.
- Stdlib self-checks runnable per module: `python3 -m agent.store`, `agent.tools.rts_query`, `agent.tools.build_digest`, `agent.scheduler` — each asserts its module's core behaviors.
- **Live end-to-end sandbox test** (documented): auto-capture from a plain DM, digest correctness across a bad PR ref / a real open PR / a real merged PR, and the crash-hardening fix that testing surfaced.

## 8. Honest Limitations (say these before a judge finds them)

- `deadline_resolved` is unreliable (model doesn't know the date) — mitigated by the ISO-parse-or-fallback rule, fixable by injecting the current date into the extractor prompt.
- Auto-capture doubles Groq calls per message (capture + conversational run) — accepted tradeoff for the zero-ceremony demo.
- User tokens for RTS require an OAuth install (`app_oauth.py` exists); local `slack run` dev sessions don't carry one, so RTS degrades cleanly in dev.
- SQLite = single host. Fine for a hackathon; a multi-tenant production version would move to Postgres and per-workspace token storage.
- `MCPServerStreamableHTTP` is deprecated in pydantic-ai v2 (→ `MCPToolset`); pinned versions make this a non-issue for judging.

## 9. Likely Judge Questions, Answered

- **"Why not just use reminders / Slackbot?"** Reminders require someone to *set* them. This captures promises nobody thought to track, and verifies them against external ground truth — a reminder can't know a PR merged.
- **"What stops it from nagging about things that got done?"** Verification at digest time: GitHub MCP for PRs (merged → silently dropped), RTS for everything else, and "unknown" is reported as unknown, never guessed.
- **"How does it avoid false positives?"** The extractor's rejection categories (hedges, questions, sarcasm-via-context, plural non-ownership, no deadline) + a 17-case validation harness that tests exactly those.
- **"Is the LLM output trusted?"** Structured JSON mode at temperature 0, schema-checked in code, and the one known-unreliable field (`deadline_resolved`) is explicitly treated as untrusted downstream.
- **"How do I connect it to MY repo?"** For any **public** repo: no setup at all — say `owner/repo#123` in the request and the agent checks it live (the operator's `GITHUB_TOKEN` can read all public repos; `GITHUB_REPO` is just the default for bare PR numbers). For someone else's **private** repo: the operator would add a token with access — per-user config, not per-user identity. Production roadmap: a per-user GitHub OAuth flow ("Connect GitHub" link → GitHub App → token stored per user, exactly like the `users` table already stores per-user Slack tokens → passed as the MCP auth header per request). The architecture already supports it; it's an OAuth flow away, not a redesign.
- **"What's MCP doing that a REST call couldn't?"** Functionally similar for one endpoint — but MCP gives the *agent* a uniform tool surface: the same client class drives Slack and GitHub, and new MCP servers (Jira, Linear…) drop in without new integration code. That's the extensibility story.
