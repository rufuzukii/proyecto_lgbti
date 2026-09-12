from __future__ import annotations

from app.modules.didactics import word_search_service
from app.modules.didactics.glossary_service import get_glossary_term, list_glossary_terms
from app.modules.didactics.models import GlossarySource, GlossaryTerm
from app.modules.didactics.word_search_service import create_word_search_game


def test_glossary_selection_generation_and_detection_use_one_canonical_catalog() -> None:
    catalog_ids = {term.id for term in list_glossary_terms()}

    game = create_word_search_game(seed=1234)
    first = game["words"][0]
    start_index = first["start"][0] * game["columns"] + first["start"][1]
    end_index = first["end"][0] * game["columns"] + first["end"][1]
    selected, _status = word_search_service.apply_word_search_selection(game, start_index)
    selected, status = word_search_service.apply_word_search_selection(selected, end_index)

    assert {word["id"] for word in game["words"]} <= catalog_ids
    assert all(get_glossary_term(word["id"]) is not None for word in game["words"])
    assert first["id"] in selected["found"]
    assert status in {"found", "complete"}


def test_a_new_glossary_entry_is_automatically_available_to_the_game(monkeypatch) -> None:
    future_term = GlossaryTerm(
        id="future_glossary_term",
        term="Futuro",
        definition="Entrada añadida al catálogo canónico.",
        category="rights",
        sources=(GlossarySource("UNAM", "https://example.test"),),
    )
    monkeypatch.setattr(
        word_search_service.glossary_service,
        "list_glossary_terms",
        lambda: (future_term,),
    )

    game = create_word_search_game(seed=9, word_count=6)

    assert [(word["id"], word["display"]) for word in game["words"]] == [
        ("future_glossary_term", "Futuro")
    ]
