import os
import re

from pydantic_ai import RunContext
from pydantic_ai.mcp import MCPServerStreamableHTTP

from agent.deps import AgentDeps

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"

# "482", "#482", or "owner/repo#482"
PR_REF_RE = re.compile(r"^(?:(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)#)?#?(?P<number>\d+)$")


async def check_pr_status(
    ctx: RunContext[AgentDeps],
    pr_reference: str,
) -> dict:
    """Check if a GitHub PR is open, merged, or has recent activity.

    Calls the real GitHub MCP server (api.githubcopilot.com/mcp) for ground-truth
    PR state — this is external verification, not something RTS or Slack search
    can answer. Use it whenever a commitment's external_ref_type is "github_pr".

    Args:
        ctx: The run context with dependencies.
        pr_reference: PR number (e.g. "482") to check against the default repo
            (GITHUB_REPO env var), or "owner/repo#482" to target a different repo.
    """
    match = PR_REF_RE.match(pr_reference.strip())
    if not match:
        return {
            "status": "unknown",
            "last_commit_date": None,
            "merged_at": None,
            "error": f"could not parse PR reference: {pr_reference!r}",
        }

    owner, repo = match.group("owner"), match.group("repo")
    if not owner or not repo:
        default_repo = os.environ.get("GITHUB_REPO", "")
        if "/" not in default_repo:
            return {
                "status": "unknown",
                "last_commit_date": None,
                "merged_at": None,
                "error": "no owner/repo in pr_reference and GITHUB_REPO env var not set",
            }
        owner, repo = default_repo.split("/", 1)

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return {
            "status": "unknown",
            "last_commit_date": None,
            "merged_at": None,
            "error": "GITHUB_TOKEN not configured",
        }

    pull_number = int(match.group("number"))
    server = MCPServerStreamableHTTP(
        GITHUB_MCP_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    try:
        async with server:
            pr = await server.direct_call_tool(
                "pull_request_read",
                {
                    "method": "get",
                    "owner": owner,
                    "repo": repo,
                    "pullNumber": pull_number,
                },
            )
            commits = await server.direct_call_tool(
                "pull_request_read",
                {
                    "method": "get_commits",
                    "owner": owner,
                    "repo": repo,
                    "pullNumber": pull_number,
                    "perPage": 100,
                },
            )
    except Exception as e:
        # Covers a nonexistent PR/repo, auth failure, or a network error — the
        # MCP call raises rather than returning a clean error for these.
        return {
            "status": "unknown",
            "last_commit_date": None,
            "merged_at": None,
            "error": f"GitHub check failed for {owner}/{repo}#{pull_number}: {e}",
        }

    status = "merged" if pr.get("merged") else pr.get("state", "unknown")
    last_commit_date = commits[-1]["author"]["date"] if commits else None

    return {
        "status": status,
        "last_commit_date": last_commit_date,
        "merged_at": pr.get("merged_at"),
    }
