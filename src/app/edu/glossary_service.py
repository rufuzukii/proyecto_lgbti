from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from app.edu.models import GlossaryTerm
from app.edu.repository import load_json

UNAM_SOURCE_URL = (
    "https://coordinaciongenero.unam.mx/avada_portfolio/"
    "glosario-de-las-diversidades-sexogenericas-lgbtiq/"
)
FUNDEU_SOURCE_URL = (
    "https://www.fundeu.es/noticia/"
    "diccionario-lgtb-guia-de-conceptos-de-un-lenguaje-inclusivo/"
)
ALLOWED_SOURCES = {"UNAM": UNAM_SOURCE_URL, "FundéuRAE": FUNDEU_SOURCE_URL}
PROHIBITED_TERM_KEYS = {
    "trasvestido",
    "trasvestida",
    "trasvestidoa",
    "travestido",
    "travestida",
    "travestidoa",
}
MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "�")


@lru_cache(maxsize=1)
def list_glossary_terms() -> tuple[GlossaryTerm, ...]:
    terms = tuple(GlossaryTerm.from_mapping(item) for item in load_json("glossary"))
    validate_glossary_catalog(terms)
    return tuple(sorted(terms, key=lambda item: _normalize(item.term)))


def get_glossary_term(term_id: str) -> GlossaryTerm | None:
    return next((term for term in list_glossary_terms() if term.id == term_id), None)


def search_glossary(
    query: str | None = None, category: str | None = None, language: str = "es"
) -> list[GlossaryTerm]:
    del language
    needle = _normalize(query or "")
    results = [
        term
        for term in list_glossary_terms()
        if (not category or category == "all" or term.category == category)
        and (
            not needle
            or needle in _normalize(term.term)
            or needle in _normalize(term.definition)
        )
    ]
    return sorted(results, key=lambda item: _normalize(item.term))


def glossary_categories() -> tuple[str, ...]:
    return tuple(sorted({term.category for term in list_glossary_terms()}))


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(plain.split())


def normalized_term_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize(value))


def validate_glossary_catalog(terms: tuple[GlossaryTerm, ...]) -> None:
    if not terms:
        raise ValueError("empty_glossary_catalog")

    identifiers: set[str] = set()
    term_keys: set[str] = set()
    for term in terms:
        key = normalized_term_key(term.term)
        if not term.id or not term.term or not term.definition or not term.category:
            raise ValueError(f"incomplete_glossary_term:{term.id or key}")
        if term.id in identifiers or key in term_keys:
            raise ValueError(f"duplicate_glossary_term:{term.id}:{term.term}")
        if key in PROHIBITED_TERM_KEYS:
            raise ValueError(f"prohibited_glossary_term:{term.term}")
        if not term.sources:
            raise ValueError(f"missing_glossary_source:{term.id}")
        if re.search(r"<[^>]+>", term.definition) or re.search(
            r"(?:https?://|www\.)", term.definition, flags=re.IGNORECASE
        ):
            raise ValueError(f"invalid_glossary_definition_markup:{term.id}")
        if "  " in term.definition or any(marker in term.definition for marker in MOJIBAKE_MARKERS):
            raise ValueError(f"invalid_glossary_definition_text:{term.id}")
        seen_sources: set[str] = set()
        for source in term.sources:
            if source.name in seen_sources or ALLOWED_SOURCES.get(source.name) != source.url:
                raise ValueError(f"invalid_glossary_source:{term.id}:{source.name}")
            seen_sources.add(source.name)
        identifiers.add(term.id)
        term_keys.add(key)
