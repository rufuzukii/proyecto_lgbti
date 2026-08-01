from __future__ import annotations

import random
from functools import lru_cache
from typing import Any

from app.edu.glossary_service import list_glossary_terms
from app.edu.repository import load_json


@lru_cache(maxsize=1)
def game_content() -> dict[str, Any]:
    return load_json("games")


def new_game_state(game_id: str, *, rounds: int = 5) -> dict[str, Any]:
    if game_id == "guess_term":
        identifiers = [term.id for term in list_glossary_terms()]
    elif game_id == "true_false":
        identifiers = [str(item["id"]) for item in game_content()["true_false"]]
    else:
        raise ValueError("unknown_game")
    random.SystemRandom().shuffle(identifiers)
    return {
        "game_id": game_id,
        "order": identifiers[: min(rounds, len(identifiers))],
        "index": 0,
        "score": 0,
        "answered": False,
        "selected": None,
    }


def true_false_question(question_id: str) -> dict[str, Any] | None:
    return next((item for item in game_content()["true_false"] if item["id"] == question_id), None)


def guess_options(term_id: str, language: str) -> list[dict[str, str]]:
    terms = list(list_glossary_terms())
    correct = next(term for term in terms if term.id == term_id)
    alternatives = [term for term in terms if term.id != term_id]
    random.SystemRandom().shuffle(alternatives)
    selected = [correct, *alternatives[:3]]
    random.SystemRandom().shuffle(selected)
    return [{"label": term.term.get(language), "value": term.id} for term in selected]
