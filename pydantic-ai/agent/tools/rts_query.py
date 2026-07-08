"""Stage 2 — RTS Query Builder for Meeting Debt Collector.

Prompt copied verbatim from skills/hackathon-project/SKILLS.md. Only checks
Slack's own conversational data (RTS) — never GitHub/Jira, that's
check_pr_status's job. Must be called with a user token: Slack's
search.messages API rejects bot tokens.
"""

import json
import os

from dotenv import load_dotenv
from groq import Groq
from pydantic_ai import RunContext
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from agent.deps import AgentDeps

SYSTEM_PROMPT = """You generate a single Slack search query to check whether a commitment
was already resolved and mentioned somewhere in the workspace. You do
not answer the question yourself — you only produce the query string.

Rules:
- Phrase it as a natural-language question when possible (this triggers
  RTS semantic search rather than plain keyword search).
- Keep it under 12 words.
- Include the specific artifact name/number if one exists.
- Do not include the person's name unless it's necessary to disambiguate.

Input: {"what": "open PR #482 for the login bug", "external_ref": "482"}
Output: "is PR 482 merged or closed?"

Input: {"what": "send the Q3 report to finance", "external_ref": null}
Output: "has the Q3 report been sent to finance?"

Now generate a query for:
Input: __COMMITMENT_JSON__
Output:"""

MODEL = "openai/gpt-oss-120b"

_client = None


def _get_client():
    global _client
    if _client is None:
        load_dotenv()
        _client = Groq()
    return _client


def _build_query(what: str, external_ref: str | None) -> str:
    prompt = SYSTEM_PROMPT.replace(
        "__COMMITMENT_JSON__", json.dumps({"what": what, "external_ref": external_ref})
    )
    response = _get_client().chat.completions.create(
        model=MODEL,
        max_tokens=300,  # gpt-oss-120b burns tokens on hidden reasoning before the answer
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip().strip('"')


async def check_rts_status(
    ctx: RunContext[AgentDeps],
    what: str,
    external_ref: str | None = None,
) -> dict:
    """Check whether a commitment was already mentioned as resolved in Slack.

    Call this only for a commitment whose deadline has already passed, before
    flagging it overdue — it stops the digest from nagging someone who
    resolved it in another channel. This checks Slack's own conversational
    data ONLY; it can never verify external systems like GitHub or Jira
    (that's check_pr_status's job).

    Args:
        ctx: The run context with dependencies.
        what: Short description of the commitment (e.g. "open PR #482 for the login bug").
        external_ref: Artifact number/name if one exists (e.g. "482"), else None.

    Returns:
        {"query": str, "matches": [...]} or {"query": None, "matches": [], "error": str}
        if a user token isn't available or the search failed.
    """
    if not ctx.deps.user_token:
        return {
            "query": None,
            "matches": [],
            "error": "no user token available — RTS requires a user token, not a bot token",
        }

    query = _build_query(what, external_ref)
    try:
        client = WebClient(token=ctx.deps.user_token)
        # Enterprise (org-wide) installs require an explicit workspace team_id.
        kwargs = {}
        if os.environ.get("SLACK_TEAM_ID"):
            kwargs["team_id"] = os.environ["SLACK_TEAM_ID"]
        result = client.search_messages(query=query, **kwargs)
        matches = [
            {
                "text": m.get("text"),
                "channel": m.get("channel", {}).get("name"),
                "permalink": m.get("permalink"),
            }
            for m in result.get("messages", {}).get("matches", [])
        ]
        return {"query": query, "matches": matches}
    except SlackApiError as e:
        return {"query": query, "matches": [], "error": str(e)}


def _demo() -> None:
    """Self-check: query builder matches spec examples; no-token path errors cleanly."""
    import asyncio
    from dataclasses import dataclass

    assert (
        _build_query("open PR #482 for the login bug", "482")
        == "is PR 482 merged or closed?"
    )
    assert (
        _build_query("send the Q3 report to finance", None)
        == "has the Q3 report been sent to finance?"
    )

    @dataclass
    class FakeDeps:
        user_token: str | None = None

    @dataclass
    class FakeCtx:
        deps: FakeDeps

    result = asyncio.run(check_rts_status(FakeCtx(FakeDeps(user_token=None)), "test"))
    assert result["error"] and result["matches"] == []
    print("ok")


if __name__ == "__main__":
    _demo()
