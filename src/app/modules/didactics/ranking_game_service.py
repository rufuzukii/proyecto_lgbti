from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from app.modules.home.legal_service import HOME_LEGAL_YEAR
from app.shared.data.legal_ranking import LegalRankingEntry, build_legal_ranking
from app.shared.data.repository import get_ilga_document_by_year

RANKING_GAME_COUNTRY_COUNT = 4


def new_ranking_game(
    *,
    seed: int | None = None,
    previous_codes: Sequence[str] = (),
    document: Mapping[str, Any] | None = None,
    country_count: int = RANKING_GAME_COUNTRY_COUNT,
    year: int = HOME_LEGAL_YEAR,
    country_codes: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Create a short ILGA legal-ranking round from the cached map dataset."""
    source = document
    if source is None:
        source = get_ilga_document_by_year(year)
    ranking = _unique_countries(build_legal_ranking(source))
    requested_codes = {
        str(code).strip().upper() for code in country_codes or () if str(code).strip()
    }
    if country_codes is not None:
        ranking = [entry for entry in ranking if entry.country_code in requested_codes]
    count = min(max(2, int(country_count)), 5, len(ranking))
    if count < 2:
        return _empty_state(year)

    excluded = {str(code).strip().upper() for code in previous_codes if str(code).strip()}
    fresh = [entry for entry in ranking if entry.country_code not in excluded]
    pool = fresh if len(fresh) >= count else ranking
    randomizer: random.Random = random.Random(seed) if seed is not None else random.SystemRandom()
    selected = _sample_prefer_distinct_scores(pool, count, randomizer)
    randomizer.shuffle(selected)
    return {
        "game_id": "rank_countries",
        "year": year,
        "items": [_entry_payload(entry) for entry in selected],
        "checked": False,
        "positions_correct": 0,
        "is_correct": False,
        "correct_order": [],
    }


def move_ranking_country(
    state: Mapping[str, Any] | None,
    index: int,
    direction: int,
) -> dict[str, Any]:
    updated = deepcopy(dict(state or {}))
    items = updated.get("items")
    if updated.get("checked") or not isinstance(items, list):
        return updated
    target = int(index) + (-1 if int(direction) < 0 else 1)
    if 0 <= int(index) < len(items) and 0 <= target < len(items):
        items[int(index)], items[target] = items[target], items[int(index)]
    return updated


def check_ranking_game(state: Mapping[str, Any] | None) -> dict[str, Any]:
    updated = deepcopy(dict(state or {}))
    items = _valid_items(updated.get("items"))
    expected_scores = sorted((float(item["score"]) for item in items), reverse=True)
    current_scores = [float(item["score"]) for item in items]
    correct_order = sorted(
        items,
        key=lambda item: (
            -float(item["score"]),
            str(item["country_name"]).casefold(),
            str(item["country_code"]),
        ),
    )
    updated.update(
        items=items,
        checked=True,
        positions_correct=sum(
            current == expected
            for current, expected in zip(current_scores, expected_scores, strict=True)
        ),
        is_correct=current_scores == expected_scores,
        correct_order=correct_order,
    )
    return updated


def _sample_prefer_distinct_scores(
    entries: Sequence[LegalRankingEntry],
    count: int,
    randomizer: random.Random,
) -> list[LegalRankingEntry]:
    by_score: dict[float, list[LegalRankingEntry]] = defaultdict(list)
    for entry in entries:
        by_score[entry.score].append(entry)
    scores = list(by_score)
    if len(scores) >= count:
        return [randomizer.choice(by_score[score]) for score in randomizer.sample(scores, count)]
    return randomizer.sample(list(entries), count)


def _unique_countries(entries: Sequence[LegalRankingEntry]) -> list[LegalRankingEntry]:
    seen: set[str] = set()
    unique: list[LegalRankingEntry] = []
    for entry in entries:
        if entry.country_code in seen:
            continue
        seen.add(entry.country_code)
        unique.append(entry)
    return unique


def _valid_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        try:
            score = float(item["score"])
        except KeyError, TypeError, ValueError:
            continue
        code = str(item.get("country_code") or "").strip().upper()
        name = str(item.get("country_name") or code).strip()
        if code and name:
            items.append({"country_code": code, "country_name": name, "score": score})
    return items


def _entry_payload(entry: LegalRankingEntry) -> dict[str, Any]:
    return {
        "country_code": entry.country_code,
        "country_name": entry.country_name,
        "score": entry.score,
    }


def _empty_state(year: int = HOME_LEGAL_YEAR) -> dict[str, Any]:
    return {
        "game_id": "rank_countries",
        "year": year,
        "items": [],
        "checked": False,
        "positions_correct": 0,
        "is_correct": False,
        "correct_order": [],
    }
