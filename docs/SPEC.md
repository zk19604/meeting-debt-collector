---
name: meeting-debt-collector
description: Build spec for "Meeting Debt Collector," a Slack Agent Builder Challenge submission. Use this whenever working on this project — scaffolding the agent, writing the commitment extractor, wiring RTS or the GitHub MCP tool, building the weekly digest, or preparing the hackathon submission. This file is the single source of truth for the project; do not ask the user to re-explain architecture, prompts, scopes, or track requirements — they are all specified here. If something needed isn't covered here, flag the gap explicitly rather than inventing an API, scope, or method name.
---

# Meeting Debt Collector — Build Spec

## What this is

A Slack agent for the **Slack Agent Builder Challenge**, track: **New Slack Agent**
(stretchable to Orgs track if time allows, but do not attempt Marketplace
submission — the 5-live-install requirement is out of scope for a hackathon
timeline unless explicitly revisited).

**One-line pitch:** tracks commitments people make in Slack threads ("I'll
ship the PR by Friday"), checks whether they actually happened, and sends a
weekly digest of what's still owed — not a reminders bot, a verification bot.

**Why this beats a generic reminders bot:** it doesn't just re-post what
someone said. It checks *ground truth* (GitHub/Jira) and *internal context*
(has it already been mentioned as done elsewhere in Slack) before ever
bothering the user.

---

## Non-negotiable architecture

Three technologies, three distinct jobs. Do not blur these — a judge (and
the submission requirements) will be looking for each one doing real work.

| Technology | Job | Data source |
|---|---|---|
| Slack AI (LLM call) | Extract commitments from message text | The message itself, plain text |
| RTS API | Check if it was already resolved *inside Slack* | Slack's own conversational data, permission-scoped |
| MCP (GitHub MCP server) | Check if it was actually resolved *externally* | GitHub (or Jira), ground truth |

**Common mistake to avoid:** RTS does NOT reach outside Slack. It cannot
check GitHub. If you find yourself trying to make RTS verify a PR status,
stop — that's the MCP tool's job.

```
Slack thread message
        │
        ▼
[1] Commitment Extractor (LLM call) ──► structured JSON commitment
        │
        ▼
[2] RTS query ──► "was this already mentioned as resolved in Slack?"
        │
        ▼
[3] GitHub MCP tool ──► "is PR #X actually merged?"
        │
        ▼
[4] Store result (SQLite for demo) ──► weekly scheduled job
        │
        ▼
[5] Digest Composer (LLM call) ──► Block Kit DM to the user
```

---

## Setup — do this first, exactly this way

```bash
slack create meeting-debt-collector --template slack-samples/bolt-python-starter-agent
cd meeting-debt-collector
```

Do not hand-roll OAuth, listener setup, or the "thinking status" — the
starter template already provides these. It also already connects to the
Slack MCP Server and demonstrates the `@tool` registration pattern via one
example tool (emoji reactions). Copy that pattern for new tools; do not
invent a different registration mechanism.

### Manifest requirements

```json
{
  "oauth_config": {
    "scopes": {
      "bot": ["channels:history", "chat:write", "search:read.messages"]
    }
  },
  "features": {
    "agent_view": true
  }
}
```

- `search:read.messages` scope is required for RTS. Without it, RTS calls
  fail (often silently or with a 403) — verify this scope is present before
  debugging anything else RTS-related.
- **RTS must be called with a user token** when used outside a native
  in-Slack AI interaction. This is not optional — do not attempt it with
  only a bot token.

---

## Stage 1 — Commitment Extractor

Full prompt with few-shot examples baked in. Use exactly this — the
few-shot examples were chosen specifically to cover the failure modes that
break naive extractors (requests-mistaken-for-commitments, sarcasm, vague
intentions, plural/group commitments).

```
SYSTEM:
You are a commitment-detection engine embedded in a Slack agent called
"Meeting Debt Collector." You read a single Slack message plus up to 3
preceding messages of thread context. Your only job is to decide whether
the message contains a genuine, checkable commitment, and if so, extract
it into structured JSON. You are not a summarizer and not a chatbot —
you never explain yourself, never add commentary, and never respond in
prose. Output JSON only, matching the schema below, with no markdown
fences and no leading/trailing text.

DEFINITION OF A COMMITMENT:
A commitment exists only if ALL of these are true:
1. A single, identifiable person is the actor (first-person singular:
   "I'll", "I will", "I'm going to", "I can have this", or a message
   where the sender is unambiguously self-assigning a task).
2. The action is concrete and checkable — something with an observable
   end-state (a PR opened, a doc shared, a ticket closed, a report sent).
   Not a vague intention ("I'll think about it", "I'll try to get to it").
3. There is a deadline or a strong time signal, either explicit
   ("by Friday", "before the 3pm call", "tomorrow morning") or clearly
   implied by context ("before we ship next week" in a thread about a
   Tuesday release).

NOT a commitment:
- Group/plural intentions ("we should", "someone needs to", "the team will")
- Past-tense reports ("I already sent that", "I did this yesterday")
- Questions or hedges ("should I look at this?", "I might get to this")
- Sarcasm or jokes (use thread tone to judge — if uncertain, treat as
  NOT a commitment; false negatives are safer than false positives here)
- Commitments with no deadline signal at all ("I'll get to the report
  eventually")
- Someone describing what THEY WANT SOMEONE ELSE to do

MULTIPLE COMMITMENTS:
If a single message contains more than one distinct commitment, return
an array. If it contains one, return an array of length one. If none,
return an empty array — never null, never omit the key.

OUTPUT SCHEMA (strict):
{
  "commitments": [
    {
      "who": "<slack display name or 'the sender' if unresolvable>",
      "what": "<short imperative description, e.g. 'open PR for auth fix'>",
      "deadline_raw": "<the exact phrase used, e.g. 'by Friday'>",
      "deadline_resolved": "<ISO 8601 date if resolvable from context, else null>",
      "confidence": "high" | "medium",
      "external_ref": "<PR number, doc name, ticket ID if mentioned, else null>",
      "external_ref_type": "github_pr" | "jira_ticket" | "doc" | "other" | null
    }
  ]
}

CONFIDENCE RULES:
- "high": explicit deadline + explicit checkable artifact (e.g. "I'll open
  PR #482 by Friday")
- "medium": explicit deadline but vague artifact (e.g. "I'll get the auth
  stuff done by Friday") — still worth tracking, just less precise to verify

FEW-SHOT EXAMPLES:

Message: "I'll get the auth PR up by Friday"
Thread context: (none)
Output:
{"commitments": [{"who": "the sender", "what": "open the auth PR", "deadline_raw": "by Friday", "deadline_resolved": null, "confidence": "medium", "external_ref": null, "external_ref_type": null}]}

Message: "ok I'll open PR #482 for the login bug before EOD tomorrow"
Thread context: (none)
Output:
{"commitments": [{"who": "the sender", "what": "open PR #482 for the login bug", "deadline_raw": "before EOD tomorrow", "deadline_resolved": null, "confidence": "high", "external_ref": "482", "external_ref_type": "github_pr"}]}

Message: "we should probably fix this at some point"
Thread context: (none)
Output:
{"commitments": []}

Message: "I already pushed that fix yesterday, should be live now"
Thread context: (none)
Output:
{"commitments": []}

Message: "haha yeah I'll get right on that 😂"
Thread context: "person A: did you finish the report" / "person B: lol nope, been slammed"
Output:
{"commitments": []}

Message: "I'll send the Q3 report to finance and also close out JIRA-1123 before Monday's meeting"
Thread context: (none)
Output:
{"commitments": [
  {"who": "the sender", "what": "send the Q3 report to finance", "deadline_raw": "before Monday's meeting", "deadline_resolved": null, "confidence": "medium", "external_ref": null, "external_ref_type": null},
  {"who": "the sender", "what": "close out JIRA-1123", "deadline_raw": "before Monday's meeting", "deadline_resolved": null, "confidence": "high", "external_ref": "JIRA-1123", "external_ref_type": "jira_ticket"}
]}

Message: "someone should really update the onboarding doc before new hires start"
Thread context: (none)
Output:
{"commitments": []}

Message: "I might try to look at the perf issue if I have time this week"
Thread context: (none)
Output:
{"commitments": []}

Message: "yep on it, will have the design doc shared with you all by tomorrow morning"
Thread context: "person A: hey can you write up the design doc for the new flow?"
Output:
{"commitments": [{"who": "the sender", "what": "share the design doc", "deadline_raw": "by tomorrow morning", "deadline_resolved": null, "confidence": "medium", "external_ref": "design doc", "external_ref_type": "doc"}]}

Message: "can you get PR #91 merged by Wednesday?"
Thread context: (none)
Output:
{"commitments": []}
(reason: this is a request directed at someone else, not a self-commitment — the
sender is not the actor)

END OF FEW-SHOT EXAMPLES.

Now process the following message. Return JSON only.

Message: "{{MESSAGE_TEXT}}"
Thread context: "{{THREAD_CONTEXT}}"
```

File location: `agent/tools/extract_commitment.py`, registered with the
`@tool` decorator matching the starter template's pattern.

**Do not skip validation.** Before wiring this into the live listener, run
it against a hand-written test set of 15+ messages covering every category
in the few-shot list above, and eyeball the output. This is the single
highest-risk part of the build — a sloppy extractor makes the whole demo
look untrustworthy.

---

## Stage 2 — RTS Query Builder

```
SYSTEM:
You generate a single Slack search query to check whether a commitment
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
Input: {{COMMITMENT_JSON}}
Output:
```

Called only when a commitment's deadline has passed, before flagging it as
overdue — this is what stops the digest from nagging someone who already
resolved it in another channel.

```python
def check_slack_context(query: str, user_token: str):
    result = client.search_messages(query=query, token=user_token)
    return result  # array of relevant messages/files, permission-scoped
```

---

## Stage 3 — GitHub MCP tool

Connect an actual GitHub MCP server (not a raw REST call standing in for
one) — the hackathon names "MCP server integration" as a qualifying
technology, and this is how the submission honestly claims it.

```python
# agent/tools/check_github.py
from bolt_agent import tool

@tool(name="check_pr_status", description="Check if a GitHub PR is open, merged, or has recent activity")
def check_pr_status(pr_reference: str) -> dict:
    # calls GitHub MCP server
    # returns {status, last_commit_date, merged_at}
    ...
```

Seed a real test repo with a couple of open PRs before the demo so this
returns real data, not a mock.

---

## Stage 4 — Digest Composer

```
SYSTEM:
You write the copy for a weekly Slack digest DM. Input is a list of
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

Output: an array of formatted strings, one per line, ready to drop into
Block Kit section blocks. Nothing else.
```

```python
def send_weekly_digest(user_id):
    stale_commitments = db.get_unresolved(user_id, older_than_days=3)
    blocks = build_digest_blocks(stale_commitments)  # Block Kit, not plain text
    client.chat_postMessage(channel=user_id, blocks=blocks)
```

Use `blocks=`, never plain `text=` — plain text reads as an unfinished demo.

---

## Build order (follow in this sequence, don't skip ahead)

1. Scaffold with `slack create agent`, confirm @mention → reply works in
   the sandbox. This derisks everything downstream.
2. Build and validate the extractor against the 15+ test-message set
   before touching anything else.
3. Wire the GitHub MCP tool against a seeded test repo.
4. Wire the RTS check. This is the first thing to cut if time runs short —
   valuable, but not load-bearing for the core loop.
5. Build the digest Block Kit message + scheduler.
6. Record the demo, build the architecture diagram (the 5-box flow above),
   write the description.

---

## Submission checklist — do not treat as optional

- [ ] Track selected: **New Slack Agent** (do not attempt Marketplace track)
- [ ] Text description written, explaining features + functionality
- [ ] ~3-minute demo video with real working footage (not slides)
- [ ] Architecture diagram included
- [ ] Sandbox URL included
- [ ] Sandbox access granted to `slackhack@salesforce.com` **and**
      `testing@devpost.com` — missing this can zero the submission's score
      regardless of build quality; verify it explicitly before submitting

---

## Things to never do in this build

- Never have RTS attempt to check external system state (GitHub, Jira) —
  it only searches Slack's own data.
- Never call RTS with only a bot token when it's being used outside a
  native in-Slack AI interaction — it requires a user token in that case.
- Never invent a Bolt/Slack CLI method or manifest field that isn't named
  in this file — flag the gap and look it up instead of guessing.
- Never send the digest as plain text — always Block Kit.
- Never skip the extractor validation step before wiring it live.