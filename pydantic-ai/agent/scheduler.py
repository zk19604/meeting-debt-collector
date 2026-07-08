"""Weekly digest scheduler.

ponytail: stdlib threading + hourly poll, not calendar-aware cron — the
template ships no scheduling dependency and a once-a-week job doesn't need
one. Swap for apscheduler if per-user schedules or DST correctness ever
matter. For live demos, don't wait for this: use the `send_weekly_digest_now`
agent tool instead.
"""

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone

from slack_sdk import WebClient

from agent import store
from agent.tools.build_digest import _send_digest

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 3600
DIGEST_WEEKDAY = 0  # Monday
DIGEST_HOUR_UTC = 9


def _due_now(now: datetime) -> bool:
    return now.weekday() == DIGEST_WEEKDAY and now.hour == DIGEST_HOUR_UTC


def start(client: WebClient) -> None:
    """Start the background weekly-digest loop as a daemon thread."""

    def _loop():
        last_sent_week = None
        while True:
            now = datetime.now(timezone.utc)
            week_key = now.isocalendar()[:2]
            if _due_now(now) and week_key != last_sent_week:
                for user_id, user_token in store.get_all_user_tokens().items():
                    try:
                        asyncio.run(_send_digest(user_id, client, user_token))
                    except Exception:
                        logger.exception("weekly digest failed for %s", user_id)
                last_sent_week = week_key
            time.sleep(CHECK_INTERVAL_SECONDS)

    threading.Thread(target=_loop, daemon=True).start()
    logger.info("weekly digest scheduler started (Mon %02d:00 UTC)", DIGEST_HOUR_UTC)


def _demo() -> None:
    assert _due_now(
        datetime(2026, 7, 6, DIGEST_HOUR_UTC, 0, tzinfo=timezone.utc)
    )  # a Monday
    assert not _due_now(
        datetime(2026, 7, 7, DIGEST_HOUR_UTC, 0, tzinfo=timezone.utc)
    )  # a Tuesday
    assert not _due_now(
        datetime(2026, 7, 6, DIGEST_HOUR_UTC + 1, 0, tzinfo=timezone.utc)
    )
    print("ok")


if __name__ == "__main__":
    _demo()
