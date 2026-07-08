"""Stage 4 — Weekly Digest Composer for Meeting Debt Collector.

Prompt copied verbatim from skills/hackathon-project/SKILLS.md. Consumes
check_pr_status's {status, last_commit_date, merged_at} and
check_rts_status's {query, matches} as-is — this file only re-runs those
checks to refresh stale data and formats the result, it never reshapes
their contracts.
"""

import json
from dataclasses import dataclass

from dotenv import load_dotenv
from groq import Groq
from pydantic_ai import RunContext
from slack_sdk import WebClient
from slack_sdk.models.blocks import SectionBlock

from agent import store
from agent.deps import AgentDeps
from agent.tools.check_pr_status import check_pr_status
from agent.tools.rts_query import check_rts_status

SYSTEM_PROMPT = """You write the copy for a weekly Slack digest DM. Input is a list of
overdue commitments, each already checked against GitHub/Jira (ground
truth) and Slack (context). You write ONE short line per item — no
guilt-tripping, no exclamation points, matter-of-fact and useful.

Format per item:
"<what> — <deadline_raw> · <status from verification> · <days overdue>d overdue"

If a GitHub/Jira check found it's actually done, EXCLUDE it from the
digest entirely — do not mention resolved items.

If RTS found conversational evidence it might be resolved but the
external check disagrees, flag it as:
"<what> — mentioned as done in #channel-name but PR #X is still open"

Never invent a status. If verification returned null/unknown, say
"status unknown — check manually" rather than guessing.

Output: a JSON object {"lines": [...]} — an array of formatted strings, one
per line, ready to drop into Block Kit section blocks. Nothing else."""

MODEL = "openai/gpt-oss-120b"

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        load_dotenv()
        _client = Groq()
    return _client


@dataclass
class _FakeDeps:
    user_token: str | None


@dataclass
class _FakeCtx:
    deps: _FakeDeps


async def _verify(item: dict, user_token: str | None) -> dict:
    """Refresh github/RTS checks for one stored commitment before digesting.

    A single item's verification failing (bad PR ref, MCP hiccup, etc.) must
    never take down the whole digest — worst case that item's status reads
    "unknown" and every other item still gets composed and sent.
    """
    ctx = _FakeCtx(_FakeDeps(user_token=user_token))
    github = None
    if item["external_ref_type"] == "github_pr" and item["external_ref"]:
        try:
            github = await check_pr_status(ctx, item["external_ref"])
        except Exception as e:
            github = {
                "status": "unknown",
                "last_commit_date": None,
                "merged_at": None,
                "error": str(e),
            }
        if "error" not in github:
            store.update_verification(item["id"], github=github)

    try:
        rts = await check_rts_status(ctx, item["what"], item["external_ref"])
    except Exception as e:
        rts = {"query": None, "matches": [], "error": str(e)}
    if "error" not in rts:
        store.update_verification(item["id"], rts=rts)

    return {
        "what": item["what"],
        "deadline_raw": item["deadline_raw"],
        "days_overdue": item["days_overdue"],
        "github_check": github,
        "rts_check": rts,
    }


MAX_MATCHES_PER_ITEM = 3
MAX_MATCH_TEXT_CHARS = 200


def _trim_for_prompt(item: dict) -> dict:
    """Cap RTS match count/length so one item's search hits can't blow the TPM budget."""
    trimmed = dict(item)
    rts = trimmed.get("rts_check")
    if rts and rts.get("matches"):
        trimmed["rts_check"] = {
            **rts,
            "matches": [
                {**m, "text": m["text"][:MAX_MATCH_TEXT_CHARS]}
                for m in rts["matches"][:MAX_MATCHES_PER_ITEM]
            ],
        }
    return trimmed


def _compose_digest_lines(items: list[dict]) -> list[str]:
    if not items:
        return []
    trimmed_items = [_trim_for_prompt(item) for item in items]
    user_prompt = "Overdue commitments:\n" + json.dumps(trimmed_items)
    response = _get_client().chat.completions.create(
        model=MODEL,
        max_tokens=1024,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("lines", [])


def build_digest_blocks(lines: list[str]) -> list[dict]:
    """Block Kit section blocks for the digest — never send this as plain text=."""
    if not lines:
        return [
            SectionBlock(
                text="No overdue commitments — you're all caught up."
            ).to_dict()
        ]
    return [SectionBlock(text=line).to_dict() for line in lines]


async def _send_digest(
    user_id: str, client: WebClient, user_token: str | None, older_than_days: int = 3
) -> dict:
    overdue = store.get_overdue(user_id, older_than_days=older_than_days)
    annotated = [await _verify(item, user_token) for item in overdue]
    lines = _compose_digest_lines(annotated)
    blocks = build_digest_blocks(lines)
    client.chat_postMessage(channel=user_id, blocks=blocks)
    return {"sent": True, "item_count": len(overdue), "line_count": len(lines)}


async def send_weekly_digest_now(
    ctx: RunContext[AgentDeps], older_than_days: int = 3
) -> dict:
    """Send the requesting user their weekly overdue-commitments digest right now.

    Call this only when the user explicitly asks to see/test/send their digest
    (e.g. "send me my digest", "what's overdue"). Pulls unresolved commitments
    from the store, re-verifies each against GitHub/RTS, and DMs a Block Kit
    summary — never plain text.

    Args:
        ctx: The run context with dependencies.
        older_than_days: Only include commitments at least this many days
            overdue (default 3, matching the weekly scheduler).
    """
    return await _send_digest(
        ctx.deps.user_id, ctx.deps.client, ctx.deps.user_token, older_than_days
    )


def _demo() -> None:
    """Self-check against the spec's two edge cases: a resolved item is
    excluded, an RTS/GitHub disagreement is flagged, unknown status is
    labeled rather than guessed."""
    items = [
        {
            "what": "open PR #482 for the login bug",
            "deadline_raw": "by Friday",
            "days_overdue": 4,
            "github_check": {
                "status": "open",
                "last_commit_date": None,
                "merged_at": None,
            },
            "rts_check": {
                "query": "is PR 482 merged?",
                "matches": [
                    {"text": "PR 482 is done", "channel": "eng", "permalink": None}
                ],
            },
        },
        {
            "what": "send the Q3 report to finance",
            "deadline_raw": "by Monday",
            "days_overdue": 2,
            "github_check": None,
            "rts_check": {"query": "has the Q3 report been sent?", "matches": []},
        },
        {
            "what": "close JIRA-1123",
            "deadline_raw": "by Wednesday",
            "days_overdue": 1,
            "github_check": {
                "status": "merged",
                "last_commit_date": None,
                "merged_at": "2026-07-01",
            },
            "rts_check": {"query": "...", "matches": []},
        },
    ]
    lines = _compose_digest_lines(items)
    assert lines, "expected at least one digest line"
    assert not any("JIRA-1123" in line for line in lines), (
        "resolved item leaked into digest"
    )

    blocks = build_digest_blocks(lines)
    assert blocks and all(b["type"] == "section" for b in blocks)

    empty_blocks = build_digest_blocks([])
    assert empty_blocks[0]["type"] == "section"

    print(lines)
    print("ok")


if __name__ == "__main__":
    _demo()
