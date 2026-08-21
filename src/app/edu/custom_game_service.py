from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import bleach

from app.analytics.legal_ranking import build_legal_ranking
from app.analytics.repository import get_ilga_document_by_year, get_ilga_years
from app.auth.permissions import can_manage_own_edu_games, is_admin_user
from app.edu.game_service import new_game_state
from app.edu.glossary_service import list_glossary_terms
from app.edu.ranking_game_service import new_ranking_game
from app.edu.word_search_service import (
    MAX_BOARD_SIZE,
    MAX_WORD_COUNT,
    MIN_WORD_COUNT,
    create_word_search_game,
    normalize_word_search_term,
)
from app.mongo import get_mongo_collection

COLLECTION_NAME = "didactica_docente_games"
ACTIVITY_STATUSES = frozenset({"DRAFT", "ACTIVE", "ARCHIVED"})
GAME_TYPE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "guess_term": {
        "label_key": "guess_term",
        "route_id": "games",
        "icon": "?",
        "configuration": (
            "selection_mode",
            "term_ids",
            "question_count",
            "shuffle",
            "show_explanation",
        ),
    },
    "word_search": {
        "label_key": "word_search",
        "route_id": "word_search",
        "icon": "ABC",
        "configuration": ("selection_mode", "term_ids", "word_count", "board_size"),
    },
    "legal_ranking": {
        "label_key": "rank_countries",
        "route_id": "games",
        "icon": "↕",
        "configuration": ("selection_mode", "country_codes", "country_count", "year"),
    },
}
GAME_TYPES = frozenset(GAME_TYPE_DEFINITIONS)


class CustomGameAuthorizationError(PermissionError):
    pass


class CustomGameValidationError(ValueError):
    pass


def list_owned_games(user: object) -> list[dict[str, Any]]:
    owner_id = _authorized_user_id(user)
    documents = get_mongo_collection(COLLECTION_NAME).find(
        {"owner_user_id": owner_id},
        {
            "_id": 0,
            "owner_user_id": 0,
            "configuration": 0,
            "description": 0,
            "instructions": 0,
            "teacher_note": 0,
        },
    )
    return sorted(
        (dict(item) for item in documents),
        key=lambda item: item.get("updated_at") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )


def list_all_games(user: object) -> list[dict[str, Any]]:
    _authorized_user_id(user)
    if not is_admin_user(user):
        raise CustomGameAuthorizationError("admin_required")
    documents = get_mongo_collection(COLLECTION_NAME).find({}, {"_id": 0})
    return [dict(item) for item in documents]


def get_owned_game(user: object, game_id: str) -> dict[str, Any] | None:
    owner_id = _authorized_user_id(user)
    document = get_mongo_collection(COLLECTION_NAME).find_one(
        {"id": _identifier(game_id)}, {"_id": 0}
    )
    if not document:
        return None
    if str(document.get("owner_user_id") or "") != owner_id and not is_admin_user(user):
        raise CustomGameAuthorizationError("custom_game_not_owned")
    return dict(document)


def save_owned_game(
    user: object,
    game_id: str | None,
    values: Mapping[str, Any],
) -> dict[str, Any]:
    owner_id = _authorized_user_id(user)
    collection = get_mongo_collection(COLLECTION_NAME)
    now = datetime.now(UTC)
    if game_id:
        clean_id = _identifier(game_id)
        existing = collection.find_one({"id": clean_id}, {"_id": 0})
        if not existing:
            raise CustomGameValidationError("activity_not_found")
        if str(existing.get("owner_user_id") or "") != owner_id and not is_admin_user(user):
            raise CustomGameAuthorizationError("custom_game_not_owned")
        activity_owner = str(existing.get("owner_user_id") or "")
        created_at = existing.get("created_at") or now
    else:
        clean_id = uuid4().hex
        activity_owner = owner_id
        created_at = now

    document = _validated_activity(values)
    document.update(
        {
            "id": clean_id,
            "owner_user_id": activity_owner,
            "created_at": created_at,
            "updated_at": now,
        }
    )
    collection.update_one(
        {"id": clean_id},
        {"$set": document, "$setOnInsert": {"created_at": created_at}},
        upsert=True,
    )
    return {key: value for key, value in document.items() if key != "owner_user_id"}


def duplicate_owned_game(user: object, game_id: str) -> dict[str, Any]:
    source = get_owned_game(user, game_id)
    if source is None:
        raise CustomGameValidationError("activity_not_found")
    copy_values = {
        key: value
        for key, value in source.items()
        if key not in {"id", "owner_user_id", "created_at", "updated_at"}
    }
    copy_values["title"] = _text(f"{copy_values['title']} (copia)", 120)
    copy_values["status"] = "DRAFT"
    return save_owned_game(user, None, copy_values)


def delete_owned_game(user: object, game_id: str) -> bool:
    activity = get_owned_game(user, game_id)
    if activity is None:
        return False
    result = get_mongo_collection(COLLECTION_NAME).delete_one(
        {"id": _identifier(game_id)}
    )
    return bool(result.deleted_count)


def build_activity_game_state(activity: Mapping[str, Any], *, seed: int | None = None):
    game_type = str(activity.get("game_type") or "")
    configuration = dict(activity.get("configuration") or {})
    selection_mode = configuration.get("selection_mode")
    if game_type == "guess_term":
        term_ids = configuration.get("term_ids") if selection_mode == "manual" else None
        return new_game_state(
            "guess_term",
            rounds=int(configuration["question_count"]),
            term_ids=term_ids,
            shuffle=bool(configuration.get("shuffle", True)),
            show_explanation=bool(configuration.get("show_explanation", True)),
        )
    if game_type == "word_search":
        term_ids = configuration.get("term_ids") if selection_mode == "manual" else None
        return create_word_search_game(
            seed=seed,
            word_count=int(configuration["word_count"]),
            term_ids=term_ids,
            board_size=int(configuration["board_size"]),
        )
    if game_type == "legal_ranking":
        country_codes = (
            configuration.get("country_codes") if selection_mode == "manual" else None
        )
        return new_ranking_game(
            seed=seed,
            year=int(configuration["year"]),
            country_count=int(configuration["country_count"]),
            country_codes=country_codes,
        )
    raise CustomGameValidationError("invalid_game_type")


def validate_activity(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and sanitize an unsaved activity without trusting browser data."""
    return _validated_activity(values)


def _validated_activity(values: Mapping[str, Any]) -> dict[str, Any]:
    game_type = str(values.get("game_type") or "").strip()
    if game_type not in GAME_TYPES:
        raise CustomGameValidationError("invalid_game_type")
    title = _text(values.get("title"), 120)
    if not title:
        raise CustomGameValidationError("missing_title")
    language = str(values.get("language") or "es").strip().lower()
    if language not in {"es", "en"}:
        raise CustomGameValidationError("invalid_language")
    status = str(values.get("status") or "DRAFT").strip().upper()
    if status not in ACTIVITY_STATUSES:
        raise CustomGameValidationError("invalid_status")
    configuration = _validated_configuration(game_type, values.get("configuration"))
    return {
        "game_type": game_type,
        "title": title,
        "description": _text(values.get("description"), 600),
        "instructions": _text(values.get("instructions"), 800),
        "teacher_note": _text(values.get("teacher_note"), 800),
        "language": language,
        "configuration": configuration,
        "status": status,
        "schema_version": 2,
    }


def _validated_configuration(game_type: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CustomGameValidationError("invalid_configuration")
    mode = str(raw.get("selection_mode") or "manual").strip().lower()
    if mode not in {"manual", "random"}:
        raise CustomGameValidationError("invalid_selection_mode")
    if game_type in {"guess_term", "word_search"}:
        return _validated_glossary_configuration(game_type, mode, raw)
    return _validated_ranking_configuration(mode, raw)


def _validated_glossary_configuration(
    game_type: str, mode: str, raw: Mapping[str, Any]
) -> dict[str, Any]:
    catalog = {term.id: term for term in list_glossary_terms()}
    term_ids = _identifier_list(raw.get("term_ids"))
    if any(identifier not in catalog for identifier in term_ids):
        raise CustomGameValidationError("invalid_term_ids")
    minimum = 5 if game_type == "guess_term" else MIN_WORD_COUNT
    maximum = 20 if game_type == "guess_term" else MAX_WORD_COUNT
    count_key = "question_count" if game_type == "guess_term" else "word_count"
    count = _bounded_integer(raw.get(count_key), minimum, maximum, count_key)
    if mode == "manual" and len(term_ids) < count:
        raise CustomGameValidationError("not_enough_terms")
    if mode == "random" and term_ids:
        term_ids = []
    configuration: dict[str, Any] = {
        "selection_mode": mode,
        "term_ids": term_ids,
        count_key: count,
    }
    if game_type == "guess_term":
        configuration.update(
            shuffle=_boolean(raw.get("shuffle"), default=True),
            show_explanation=_boolean(raw.get("show_explanation"), default=True),
        )
        return configuration
    board_size = _bounded_integer(raw.get("board_size") or 12, 10, MAX_BOARD_SIZE, "board_size")
    if mode == "manual":
        normalized = [normalize_word_search_term(catalog[item].term) for item in term_ids]
        if any(not word or len(word) > board_size for word in normalized):
            raise CustomGameValidationError("word_does_not_fit")
        if len(set(normalized)) != len(normalized):
            raise CustomGameValidationError("duplicate_words")
    configuration["board_size"] = board_size
    return configuration


def _validated_ranking_configuration(
    mode: str, raw: Mapping[str, Any]
) -> dict[str, Any]:
    year = _bounded_integer(raw.get("year"), 2000, 2100, "year")
    available_years = {int(item) for item in get_ilga_years()}
    if year not in available_years:
        raise CustomGameValidationError("invalid_legal_year")
    ranking = build_legal_ranking(get_ilga_document_by_year(year))
    available_codes = {entry.country_code for entry in ranking}
    country_codes = [item.upper() for item in _identifier_list(raw.get("country_codes"))]
    country_count = _bounded_integer(raw.get("country_count"), 2, 5, "country_count")
    if mode == "manual":
        if len(country_codes) < country_count:
            raise CustomGameValidationError("not_enough_countries")
        if any(code not in available_codes for code in country_codes):
            raise CustomGameValidationError("invalid_country_codes")
    else:
        country_codes = []
        if len({entry.score for entry in ranking}) < country_count:
            raise CustomGameValidationError("not_enough_distinct_scores")
    return {
        "selection_mode": mode,
        "country_codes": country_codes,
        "country_count": country_count,
        "year": year,
        "source_dataset_version": f"ilga-{year}",
    }


def _authorized_user_id(user: object) -> str:
    if not can_manage_own_edu_games(user):
        raise CustomGameAuthorizationError("docente_required")
    owner_id = str(getattr(user, "get_id", lambda: "")() or "").strip()
    if not owner_id:
        raise CustomGameAuthorizationError("authenticated_user_required")
    return owner_id


def _text(value: Any, maximum: int) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    return bleach.clean(normalized, tags=[], attributes={}, strip=True)[:maximum].strip()


def _identifier_list(value: Any) -> list[str]:
    values: Sequence[Any] = value if isinstance(value, list | tuple) else ()
    result: list[str] = []
    for item in values:
        clean = str(item or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result[:50]


def _bounded_integer(value: Any, minimum: int, maximum: int, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CustomGameValidationError(f"invalid_{field}") from exc
    if not minimum <= number <= maximum:
        raise CustomGameValidationError(f"invalid_{field}")
    return number


def _boolean(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, list):
        return bool(value)
    return bool(value)


def _identifier(value: Any) -> str:
    clean = str(value or "").strip().casefold()
    if not clean or len(clean) > 64 or not all(character.isalnum() for character in clean):
        raise CustomGameValidationError("invalid_game_id")
    return clean
