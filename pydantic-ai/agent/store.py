"""SQLite store for tracked commitments — Stage 4 (weekly digest) data layer.

No schema is specified in SKILLS.md; this one was designed to satisfy the
Stage 4 pseudocode's `db.get_unresolved(user_id, older_than_days=3)` and to
carry each commitment's GitHub/RTS verification state alongside it. Also
holds a tiny `users` table (user_id -> last-seen user_token) since nothing
else in this codebase persists that across requests, and the weekly
scheduler needs it to know who to DM.

`deadline_resolved` from the extractor is known-unreliable (Stage 1 gap: the
model doesn't know today's date). We use it when it parses as an ISO date,
and fall back to `created_at` (when the commitment was first tracked) so
overdue filtering degrades gracefully instead of guessing wrong.
"""

import json
import os
import sqlite3
from datetime import date, datetime, timezone

DB_PATH = os.environ.get(
    "COMMITMENTS_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "commitments.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    thread_ts TEXT NOT NULL,
    message_ts TEXT NOT NULL,
    who TEXT,
    what TEXT NOT NULL,
    deadline_raw TEXT,
    deadline_resolved TEXT,
    confidence TEXT,
    external_ref TEXT,
    external_ref_type TEXT,
    created_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    github_status TEXT,
    github_last_commit_date TEXT,
    github_merged_at TEXT,
    rts_query TEXT,
    rts_matches TEXT,
    last_checked_at TEXT
);
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    user_token TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_commitment(
    user_id: str, channel_id: str, thread_ts: str, message_ts: str, commitment: dict
) -> int:
    """Persist one extracted commitment. Returns the new row id."""
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO commitments
               (user_id, channel_id, thread_ts, message_ts, who, what, deadline_raw,
                deadline_resolved, confidence, external_ref, external_ref_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                channel_id,
                thread_ts,
                message_ts,
                commitment.get("who"),
                commitment["what"],
                commitment.get("deadline_raw"),
                commitment.get("deadline_resolved"),
                commitment.get("confidence"),
                commitment.get("external_ref"),
                commitment.get("external_ref_type"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def track_message(
    user_id: str, channel_id: str, thread_ts: str, message_ts: str, text: str
) -> list[int]:
    """Run the Stage 1 extractor on a raw message and persist any commitments found.

    ponytail: called with no thread context (the live conversational tool path
    already handles the full 3-message context; this background capture just
    needs to catch commitments so the digest has data to work with).
    """
    from agent.tools.extract_commitment import extract_commitments

    commitments = extract_commitments(text)
    return [
        add_commitment(user_id, channel_id, thread_ts, message_ts, c)
        for c in commitments
    ]


def update_verification(
    commitment_id: int, github: dict | None = None, rts: dict | None = None
) -> None:
    """Store the latest GitHub/RTS verification results for a commitment."""
    with _connect() as conn:
        conn.execute(
            """UPDATE commitments SET
                 github_status = COALESCE(?, github_status),
                 github_last_commit_date = COALESCE(?, github_last_commit_date),
                 github_merged_at = COALESCE(?, github_merged_at),
                 rts_query = COALESCE(?, rts_query),
                 rts_matches = COALESCE(?, rts_matches),
                 last_checked_at = ?
               WHERE id = ?""",
            (
                (github or {}).get("status"),
                (github or {}).get("last_commit_date"),
                (github or {}).get("merged_at"),
                (rts or {}).get("query"),
                json.dumps(rts["matches"])
                if rts and rts.get("matches") is not None
                else None,
                datetime.now(timezone.utc).isoformat(),
                commitment_id,
            ),
        )


def mark_resolved(commitment_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE commitments SET resolved = 1 WHERE id = ?", (commitment_id,)
        )


def _reference_date(row: sqlite3.Row) -> date:
    if row["deadline_resolved"]:
        try:
            return date.fromisoformat(row["deadline_resolved"][:10])
        except ValueError:
            pass
    return date.fromisoformat(row["created_at"][:10])


def get_overdue(user_id: str, older_than_days: int = 3) -> list[dict]:
    """Unresolved commitments whose deadline (or tracked date, as a fallback)
    is at least `older_than_days` in the past."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM commitments WHERE user_id = ? AND resolved = 0", (user_id,)
        ).fetchall()

    today = date.today()
    overdue = []
    for row in rows:
        days = (today - _reference_date(row)).days
        if days >= older_than_days:
            item = dict(row)
            item["days_overdue"] = days
            item["rts_matches"] = (
                json.loads(item["rts_matches"]) if item["rts_matches"] else []
            )
            overdue.append(item)
    return overdue


def upsert_user_token(user_id: str, user_token: str | None) -> None:
    """Remember a user's token so the weekly scheduler can DM them later."""
    if not user_token:
        return
    with _connect() as conn:
        conn.execute(
            """INSERT INTO users (user_id, user_token, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET user_token = excluded.user_token,
                                                    updated_at = excluded.updated_at""",
            (user_id, user_token, datetime.now(timezone.utc).isoformat()),
        )


def get_all_user_tokens() -> dict[str, str]:
    with _connect() as conn:
        rows = conn.execute("SELECT user_id, user_token FROM users").fetchall()
    return {row["user_id"]: row["user_token"] for row in rows}


def _demo() -> None:
    """Self-check: overdue filtering, verification updates, and resolution all work."""
    global DB_PATH
    import tempfile

    DB_PATH = tempfile.mktemp(suffix=".db")

    cid = add_commitment(
        "U1",
        "C1",
        "100.0",
        "100.0",
        {
            "what": "open PR #482",
            "deadline_raw": "by Friday",
            "deadline_resolved": "2020-01-01",
            "confidence": "high",
            "external_ref": "482",
            "external_ref_type": "github_pr",
        },
    )
    overdue = get_overdue("U1", older_than_days=3)
    assert len(overdue) == 1 and overdue[0]["days_overdue"] > 3

    update_verification(
        cid,
        github={
            "status": "merged",
            "last_commit_date": None,
            "merged_at": "2020-01-02",
        },
    )
    mark_resolved(cid)
    assert get_overdue("U1") == []

    upsert_user_token("U1", "xoxp-fake")
    assert get_all_user_tokens() == {"U1": "xoxp-fake"}

    os.remove(DB_PATH)
    print("ok")


if __name__ == "__main__":
    _demo()
