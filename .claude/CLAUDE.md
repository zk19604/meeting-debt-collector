# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

**Meeting Debt Collector** — a Slack agent (Slack Agent Builder Challenge hackathon entry) that extracts commitments from Slack messages, verifies them against GitHub (MCP) and Slack Real-Time Search, and sends a weekly Block Kit digest of overdue items.

The app lives in `pydantic-ai/` (Bolt for Python + Pydantic AI, scaffolded from `slack-samples/bolt-python-starter-agent`; the other two framework variants were removed). Spec and submission docs live in `docs/` — `docs/SPEC.md` is the single source of truth for prompts and rules.

## Commands

All commands run from `pydantic-ai/`:

```sh
slack run          # run via Slack CLI (Socket Mode dev session)
python3 app.py     # run directly (needs SLACK_BOT_TOKEN + SLACK_APP_TOKEN)

ruff check . && ruff format --check .
pytest
python validate_extractor.py          # 17-case extractor validation (Groq)
python3 -m agent.store                # self-checks
python3 -m agent.tools.rts_query
python3 -m agent.tools.build_digest
python3 -m agent.scheduler
```

Env (`pydantic-ai/.env`): `GROQ_API_KEY` (LLM: `groq:openai/gpt-oss-120b`), `GITHUB_TOKEN`, `GITHUB_REPO`.

## Architecture

Three-layer design: **app.py** → **listeners/** → **agent/**

- `app.py` initializes Bolt (Socket Mode), registers listeners, starts `agent/scheduler.py` (weekly digest thread).
- `listeners/events/` (`app_home_opened`, `app_mentioned`, `message`) — DM/mention handlers also auto-capture commitments via `store.track_message()` (wrapped in try/except; capture must never break the reply).
- `agent/agent.py` — Pydantic AI `Agent` with `deps_type=AgentDeps`; model chosen at runtime by `get_model()` (Groq preferred); tools passed via `tools=[]`, one file per tool under `agent/tools/`:
  - `extract_commitment.py` — few-shot LLM extractor (JSON mode, temp 0). `deadline_resolved` is UNTRUSTED (model doesn't know today's date).
  - `check_pr_status.py` — GitHub MCP server (`MCPServerStreamableHTTP`, deprecated in favor of `MCPToolset` in pydantic-ai v2).
  - `rts_query.py` — LLM query builder + `search.messages` with `ctx.deps.user_token` (never bot token).
  - `build_digest.py` — digest composer (Groq, Block Kit only, never `text=`).
- `agent/store.py` — SQLite (`commitments.db`): `commitments` + `users` (user_id → last-seen user token) tables.
- `thread_context/store.py` — in-memory conversation history keyed by `(channel_id, thread_ts)`.

## Gotchas

- `gpt-oss-120b` burns hidden reasoning tokens — small `max_tokens` silently returns empty strings; use ≥300.
- Prompts with literal JSON braces: use `.replace()`, not `.format()`.
- Local `slack run` sessions have no per-request `context.user_token`, so RTS returns its "no user token" error path in dev — expected; real user tokens require an OAuth install (`app_oauth.py`).
