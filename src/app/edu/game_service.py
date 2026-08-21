from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

from app.edu.glossary_service import list_glossary_terms


def new_game_state(
    game_id: str,
    *,
    rounds: int = 5,
    term_ids: Sequence[str] | None = None,
    shuffle: bool = True,
    show_explanation: bool = True,
) -> dict[str, Any]:
    if game_id != "guess_term":
        raise ValueError("unknown_game")
    catalog_ids = {term.id for term in list_glossary_terms()}
    identifiers = (
        [str(identifier) for identifier in term_ids if str(identifier) in catalog_ids]
        if term_ids is not None
        else list(catalog_ids)
    )
    if shuffle:
        random.SystemRandom().shuffle(identifiers)
    return {
        "game_id": game_id,
        "order": identifiers[: min(rounds, len(identifiers))],
        "index": 0,
        "score": 0,
        "answered": False,
        "selected": None,
        "show_explanation": show_explanation,
    }


def guess_options(term_id: str, language: str) -> list[dict[str, str]]:
    del language
    terms = list(list_glossary_terms())
    correct = next(term for term in terms if term.id == term_id)
    alternatives = [term for term in terms if term.id != term_id]
    random.SystemRandom().shuffle(alternatives)
    selected = [correct, *alternatives[:3]]
    random.SystemRandom().shuffle(selected)
    return [{"label": term.term, "value": term.id} for term in selected]
