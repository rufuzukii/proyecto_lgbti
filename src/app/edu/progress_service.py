from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.edu.lesson_service import list_lessons
from app.mongo import get_mongo_collection

logger = logging.getLogger(__name__)
COLLECTION_NAME = "didactica_progress"


def get_user_progress(user_id: str) -> dict[str, Any]:
    if not user_id:
        return _empty_progress()
    try:
        document = get_mongo_collection(COLLECTION_NAME).find_one({"user_id": user_id}, {"_id": 0})
    except Exception:
        logger.warning("didactica_progress_read_failed", exc_info=True)
        return _empty_progress()
    return document or _empty_progress()


def complete_lesson(user_id: str, lesson_id: str) -> None:
    if user_id and lesson_id:
        _update(
            user_id,
            {"$addToSet": {"completed_lessons": lesson_id}, "$set": _activity("lesson", lesson_id)},
        )


def save_game_score(user_id: str, game_id: str, score: int) -> None:
    if not user_id or game_id not in {"guess_term", "true_false"}:
        return
    _update(
        user_id,
        {
            "$max": {f"game_scores.{game_id}": int(score)},
            "$set": _activity("game", game_id),
        },
    )


def progress_summary(user_id: str) -> dict[str, Any]:
    progress = get_user_progress(user_id)
    completed = len(progress.get("completed_lessons", []))
    played = len(progress.get("game_scores", {}))
    total = len(list_lessons()) + 2
    return {
        **progress,
        "completed_count": completed,
        "played_count": played,
        "percentage": round(((completed + played) / total) * 100) if total else 0,
    }


def _empty_progress() -> dict[str, Any]:
    return {"completed_lessons": [], "game_scores": {}, "last_activity": None, "updated_at": None}


def _activity(kind: str, identifier: str) -> dict[str, Any]:
    return {"last_activity": {"kind": kind, "id": identifier}, "updated_at": datetime.now(UTC)}


def _update(user_id: str, update: dict[str, Any]) -> None:
    try:
        get_mongo_collection(COLLECTION_NAME).update_one(
            {"user_id": user_id}, {**update, "$setOnInsert": {"user_id": user_id}}, upsert=True
        )
    except Exception:
        logger.warning("didactica_progress_write_failed", exc_info=True)
