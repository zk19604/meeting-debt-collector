"""Validation harness for the Stage 1 commitment extractor.

Run from this directory: .venv/bin/python validate_extractor.py   (needs GROQ_API_KEY)

17 hand-written messages covering every category in the spec's few-shot list
(none copied from the few-shot examples — those would just test memorization).
Asserts commitment COUNT for every case, plus external_ref/type/confidence
where deterministic. Prints raw output for the mandatory eyeball pass.
"""

import json
import sys
import time

import groq

from agent.tools.extract_commitment import extract_commitments

# (name, message, thread_context, expected_count, extra_checks)
# extra_checks: dict of field -> expected value, checked on the matching commitment
CASES = [
    ("explicit PR + deadline", "I'll open PR #217 for the rate limiter by Thursday", None, 1,
     {"external_ref": "217", "external_ref_type": "github_pr", "confidence": "high"}),
    ("vague artifact + deadline", "I'll get the billing stuff sorted by end of week", None, 1,
     {"confidence": "medium"}),
    ("plural 'we'", "we should really clean up the deploy scripts sometime", None, 0, {}),
    ("plural 'the team'", "the team will handle the data migration next sprint", None, 0, {}),
    ("past tense", "I sent the invoice over to finance yesterday", None, 0, {}),
    ("hedge", "I might pick up the dashboard work if I get time this week", None, 0, {}),
    ("question", "should I take a look at the flaky e2e tests?", None, 0, {}),
    ("request to someone else", "can you close JIRA-88 by Monday?", None, 0, {}),
    ("sarcasm with context", "sure, I'll totally have that done in an hour 🙃",
     'person A: any progress on the API docs? / person B: lol none, been in meetings all week', 0, {}),
    ("no deadline", "I'll refactor the auth module eventually", None, 0, {}),
    ("vague intention with deadline", "I'll think about the pricing proposal by Friday", None, 0, {}),
    ("two commitments", "I'll push the hotfix branch and file INFRA-204 before standup tomorrow", None, 2,
     {"external_ref": "INFRA-204", "external_ref_type": "jira_ticket"}),
    ("jira + time signal", "I'm going to close out OPS-341 before the 3pm call", None, 1,
     {"external_ref": "OPS-341", "external_ref_type": "jira_ticket", "confidence": "high"}),
    ("doc via thread context", "yep, will have the postmortem doc shared by tomorrow morning",
     "person A: could you write up the incident postmortem?", 1,
     {"external_ref_type": "doc"}),
    ("deadline implied by context", "I'll have the migration script merged before we ship",
     "person A: reminder, the release is locked for Tuesday", 1, {}),
    ("plain explicit commitment", "I will send the updated contract to legal by 5pm today", None, 1, {}),
    ("'someone needs to'", "someone needs to rotate the API keys before Friday", None, 0, {}),
]


def check(message, context, expected_count, extra):
    for attempt in range(4):  # ponytail: free-tier Groq is 8k TPM; naive backoff is enough
        try:
            commitments = extract_commitments(message, context or "(none)")
            break
        except groq.RateLimitError:
            if attempt == 3:
                raise
            time.sleep(15 * (attempt + 1))
    problems = []
    if len(commitments) != expected_count:
        problems.append(f"expected {expected_count} commitment(s), got {len(commitments)}")
    if extra and commitments:
        # extra checks must all match on at least one extracted commitment
        if not any(all(c.get(k) == v for k, v in extra.items()) for c in commitments):
            problems.append(f"no commitment matched {extra}")
    return commitments, problems


def main():
    failures = 0
    for name, message, context, expected_count, extra in CASES:
        commitments, problems = check(message, context, expected_count, extra)
        status = "PASS" if not problems else "FAIL"
        failures += bool(problems)
        print(f"[{status}] {name}")
        if problems:
            for p in problems:
                print(f"       {p}")
        print(f"       {json.dumps(commitments)}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
