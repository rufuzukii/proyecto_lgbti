from __future__ import annotations

import pytest

from app.edu.models import GlossarySource, GlossaryTerm
from app.edu.word_search_service import (
    DIRECTIONS,
    apply_word_search_selection,
    detect_word_selection,
    generate_word_search,
    is_word_search_complete,
    normalize_word_search_term,
    select_word_search_terms,
)


def _term(identifier: str, display: str) -> GlossaryTerm:
    return GlossaryTerm(
        id=identifier,
        term=display,
        definition=f"Definición de {display}.",
        category="rights",
        sources=(GlossarySource("UNAM", "https://example.test"),),
    )


def test_normalization_removes_accents_spaces_hyphens_and_symbols() -> None:
    # Arrange
    display = "Orientación sexo-afectiva +"

    # Act
    normalized = normalize_word_search_term(display)

    # Assert
    assert normalized == "ORIENTACIONSEXOAFECTIVA"


def test_term_selection_is_seeded_unique_limited_and_uses_all_if_catalog_is_small() -> None:
    # Arrange
    terms = [
        _term("one", "Género"),
        _term("duplicate", "Genero"),
        _term("two", "Queer"),
        _term("empty", "---"),
        _term("long", "Una palabra demasiado larga"),
    ]

    # Act
    first = select_word_search_terms(terms, count=6, max_length=8, seed=1234)
    second = select_word_search_terms(terms, count=6, max_length=8, seed=1234)

    # Assert
    assert first == second
    assert len(first) == 2
    assert {normalize_word_search_term(term.term) for term in first} == {"GENERO", "QUEER"}


def test_term_selection_returns_the_requested_random_count() -> None:
    # Arrange
    terms = [
        _term(str(index), display)
        for index, display in enumerate(
            (
                "Agénero",
                "Bifobia",
                "Cisgénero",
                "Diversidad",
                "Endosex",
                "Género",
                "Homofobia",
                "Intersexual",
                "Lesbiana",
                "Pansexual",
                "Queer",
                "Transfobia",
            )
        )
    ]

    # Act
    selected = select_word_search_terms(terms, count=8, max_length=12, seed=21)

    # Assert
    assert len(selected) == 8
    assert len({term.id for term in selected}) == 8


def test_generation_with_seed_is_deterministic_and_fills_every_cell() -> None:
    # Arrange
    words = ["Diversidad", "Género", "Queer", "Bisexual"]

    # Act
    first = generate_word_search(words, 12, 12, seed=1234)
    second = generate_word_search(words, 12, 12, seed=1234)

    # Assert
    assert first == second
    assert len(first["grid"]) == 12
    assert all(len(row) == 12 and all(letter.isalpha() for letter in row) for row in first["grid"])


def test_words_too_long_for_the_requested_direction_are_discarded() -> None:
    # Arrange
    words = ["CORTA", "DEMASIADOLARGA"]

    # Act
    generated = generate_word_search(words, 5, 5, seed=4, directions=["right"])

    # Assert
    assert generated["words_used"] == ["CORTA"]


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_generation_supports_every_forward_and_reverse_direction(direction: str) -> None:
    # Arrange / Act
    generated = generate_word_search(["QUEER"], 6, 6, seed=1, directions=[direction])

    # Assert
    assert generated["placements"][0]["direction"] == direction


def test_valid_collisions_share_only_matching_letters() -> None:
    # Arrange
    generated = generate_word_search(["CASA", "ASA"], 5, 5, seed=8, directions=["right"])

    # Act
    letters_by_cell: dict[tuple[int, int], set[str]] = {}
    uses_by_cell: dict[tuple[int, int], int] = {}
    for placement in generated["placements"]:
        for letter, cell in zip(placement["word"], placement["cells"], strict=True):
            key = tuple(cell)
            letters_by_cell.setdefault(key, set()).add(letter)
            uses_by_cell[key] = uses_by_cell.get(key, 0) + 1

    # Assert
    assert any(uses > 1 for uses in uses_by_cell.values())
    assert all(len(letters) == 1 for letters in letters_by_cell.values())


def test_detection_accepts_a_word_in_both_selection_orders() -> None:
    # Arrange
    words = [{"id": "queer", "cells": [[1, 1], [1, 2], [1, 3], [1, 4], [1, 5]]}]

    # Act / Assert
    assert detect_word_selection(words, (1, 1), (1, 5)) == "queer"
    assert detect_word_selection(words, (1, 5), (1, 1)) == "queer"
    assert detect_word_selection(words, (1, 1), (2, 4)) is None


def test_selection_marks_a_word_once_and_detects_completed_game() -> None:
    # Arrange
    state = {
        "rows": 2,
        "columns": 3,
        "grid": [["G", "A", "Y"], ["A", "B", "C"]],
        "words": [{"id": "gay", "cells": [[0, 0], [0, 1], [0, 2]]}],
        "found": [],
        "start": None,
    }

    # Act
    started, start_status = apply_word_search_selection(state, 0)
    completed, completed_status = apply_word_search_selection(started, 2)
    restarted, _ = apply_word_search_selection(completed, 0)
    duplicate, duplicate_status = apply_word_search_selection(restarted, 2)

    # Assert
    assert start_status == "start"
    assert completed_status == "complete"
    assert completed["found"] == ["gay"]
    assert is_word_search_complete(completed)
    assert duplicate_status == "duplicate"
    assert duplicate["found"] == ["gay"]
