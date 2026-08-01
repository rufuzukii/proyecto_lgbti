from __future__ import annotations

import unicodedata
from functools import lru_cache

from app.edu.models import GlossaryTerm
from app.edu.repository import load_json


@lru_cache(maxsize=1)
def list_glossary_terms() -> tuple[GlossaryTerm, ...]:
    return tuple(GlossaryTerm.from_mapping(item) for item in load_json("glossary"))


def get_glossary_term(term_id: str) -> GlossaryTerm | None:
    return next((term for term in list_glossary_terms() if term.id == term_id), None)


def search_glossary(
    query: str | None = None, category: str | None = None, language: str = "es"
) -> list[GlossaryTerm]:
    needle = _normalize(query or "")
    results = [
        term
        for term in list_glossary_terms()
        if (not category or category == "all" or term.category == category)
        and (
            not needle
            or needle in _normalize(term.term.get(language))
            or needle in _normalize(term.short_definition.get(language))
            or needle in _normalize(term.definition.get(language))
        )
    ]
    return sorted(results, key=lambda item: _normalize(item.term.get(language)))


def glossary_categories() -> tuple[str, ...]:
    return tuple(sorted({term.category for term in list_glossary_terms()}))


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))
