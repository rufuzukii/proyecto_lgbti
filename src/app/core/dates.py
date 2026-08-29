from __future__ import annotations

from datetime import UTC, date, datetime


def utc_today() -> date:
    """Return the current calendar date using Render's UTC reference timezone."""
    return datetime.now(UTC).date()


def utc_today_iso() -> str:
    return utc_today().isoformat()
