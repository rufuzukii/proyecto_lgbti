from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import bleach

from app.auth.permissions import can_manage_own_edu_games
from app.mongo import get_mongo_collection

COLLECTION_NAME = "didactica_docente_games"
GAME_TYPES = {"multiple_choice", "guess_term"}


class CustomGameAuthorizationError(PermissionError):
    pass


class CustomGameValidationError(ValueError):
    pass


def list_owned_games(user: object) -> list[dict[str, Any]]:
    owner_id = _authorized_owner(user)
    documents = get_mongo_collection(COLLECTION_NAME).find(
        {"owner_id": owner_id},
        {"_id": 0, "owner_id": 0},
    )
    return sorted((dict(item) for item in documents), key=lambda item: item["title_es"].casefold())


def get_owned_game(user: object, game_id: str) -> dict[str, Any] | None:
    owner_id = _authorized_owner(user)
    document = get_mongo_collection(COLLECTION_NAME).find_one(
        {"id": _identifier(game_id), "owner_id": owner_id},
        {"_id": 0, "owner_id": 0},
    )
    return dict(document) if document else None


def save_owned_game(
    user: object,
    game_id: str | None,
    values: dict[str, Any],
) -> dict[str, Any]:
    owner_id = _authorized_owner(user)
    clean_id = _identifier(game_id) if game_id else uuid4().hex
    collection = get_mongo_collection(COLLECTION_NAME)
    if game_id and collection.find_one({"id": clean_id, "owner_id": {"$ne": owner_id}}):
        raise CustomGameAuthorizationError("custom_game_not_owned")
    now = datetime.now(UTC)
    document = _validated_game(values)
    document.update({"id": clean_id, "owner_id": owner_id, "updated_at": now})
    collection.update_one(
        {"id": clean_id, "owner_id": owner_id},
        {"$set": document, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {key: value for key, value in document.items() if key != "owner_id"}


def delete_owned_game(user: object, game_id: str) -> bool:
    owner_id = _authorized_owner(user)
    result = get_mongo_collection(COLLECTION_NAME).delete_one(
        {"id": _identifier(game_id), "owner_id": owner_id}
    )
    return bool(result.deleted_count)


def _validated_game(values: dict[str, Any]) -> dict[str, Any]:
    game_type = str(values.get("game_type") or "").strip()
    if game_type not in GAME_TYPES:
        raise CustomGameValidationError("invalid_game_type")
    fields = {
        "title_es": _text(values.get("title_es"), 120),
        "title_en": _text(values.get("title_en"), 120),
        "prompt_es": _text(values.get("prompt_es"), 600),
        "prompt_en": _text(values.get("prompt_en"), 600),
        "answer_es": _text(values.get("answer_es"), 160),
        "answer_en": _text(values.get("answer_en"), 160),
        "explanation_es": _text(values.get("explanation_es"), 800),
        "explanation_en": _text(values.get("explanation_en"), 800),
    }
    if any(not value for value in fields.values()):
        raise CustomGameValidationError("missing_game_fields")
    distractors_es = _lines(values.get("distractors_es"))
    distractors_en = _lines(values.get("distractors_en"))
    if game_type == "multiple_choice" and (
        len(distractors_es) < 2 or len(distractors_en) < 2
    ):
        raise CustomGameValidationError("not_enough_options")
    return {
        "game_type": game_type,
        **fields,
        "distractors_es": distractors_es,
        "distractors_en": distractors_en,
    }


def _authorized_owner(user: object) -> str:
    if not can_manage_own_edu_games(user):
        raise CustomGameAuthorizationError("docente_required")
    owner_id = str(getattr(user, "get_id", lambda: "")() or "").strip()
    if not owner_id:
        raise CustomGameAuthorizationError("authenticated_user_required")
    return owner_id


def _text(value: Any, maximum: int) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    clean = bleach.clean(normalized, tags=[], attributes={}, strip=True)
    return clean[:maximum].strip()


def _lines(value: Any) -> list[str]:
    return [line for item in str(value or "").splitlines() if (line := _text(item, 160))][:6]


def _identifier(value: Any) -> str:
    clean = str(value or "").strip().casefold()
    if not clean or len(clean) > 64 or not all(character.isalnum() for character in clean):
        raise CustomGameValidationError("invalid_game_id")
    return clean
