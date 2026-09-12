from __future__ import annotations

from datetime import UTC, date, datetime


def utc_today() -> date:
    """Devuelve la fecha actual según la zona horaria UTC de referencia en Render."""
    return datetime.now(UTC).date()


def utc_today_iso() -> str:
    return utc_today().isoformat()
