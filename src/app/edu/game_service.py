from __future__ import annotations

import random
from typing import Any

from app.edu.glossary_service import get_glossary_term, list_glossary_terms


def new_game_state(game_id: str, *, rounds: int = 5) -> dict[str, Any]:
    if game_id == "guess_term":
        identifiers = [term.id for term in list_glossary_terms()]
    elif game_id == "true_false":
        identifiers = _true_false_identifiers(rounds)
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
    try:
        expected_id, shown_id = question_id.split("::", maxsplit=1)
    except ValueError:
        return None
    expected = get_glossary_term(expected_id)
    shown = get_glossary_term(shown_id)
    if expected is None or shown is None:
        return None
    answer = expected_id == shown_id
    sources = " · ".join(source.name for source in shown.sources)
    return {
        "id": question_id,
        "statement": {
            "es": f"Esta definición corresponde a «{expected.term}»: {shown.definition}",
            "en": f"Does this Spanish definition correspond to «{expected.term}»? {shown.definition}",
        },
        "answer": answer,
        "explanation": {
            "es": (
                f"Sí. Es la definición de «{expected.term}»."
                if answer
                else f"No. La definición corresponde a «{shown.term}»."
            ),
            "en": (
                f"Yes. It is the Spanish definition of «{expected.term}»."
                if answer
                else f"No. The Spanish definition corresponds to «{shown.term}»."
            ),
        },
        "source": sources,
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


def _true_false_identifiers(rounds: int) -> list[str]:
    terms = list(list_glossary_terms())
    randomizer = random.SystemRandom()
    randomizer.shuffle(terms)
    selected = terms[: min(rounds, len(terms))]
    identifiers: list[str] = []
    for index, term in enumerate(selected):
        shown = term
        if index % 2 and len(terms) > 1:
            alternatives = [item for item in terms if item.id != term.id]
            shown = randomizer.choice(alternatives)
        identifiers.append(f"{term.id}::{shown.id}")
    randomizer.shuffle(identifiers)
    return identifiers
