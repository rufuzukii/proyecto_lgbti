from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.imports import country_status


def _markdown(*, code: str = "ES", country: str = "España") -> str:
    return f"""# ILGA-Europe Annual Review 2026

## {country} ({code})
**Estado general:** Avance con retos pendientes
**Descripción:** La situación muestra avances sostenidos y retos relevantes para la igualdad.
**Contexto legal:** Existe protección legal estatal.
**Contexto social:** Persisten diferencias territoriales.
**Organización o informe:** ILGA-Europe
**Enlace de la fuente:** https://example.test/review
**Fecha de actualización:** 2026-02-01
**Observaciones:** Revisión anual.
**Avances destacados:**
- Nueva protección
- Mejor acceso

**Retos principales:**
- Aplicación desigual
- Falta de datos
"""


def test_country_status_markdown_parses_file_and_normalizes_records(tmp_path) -> None:
    source = tmp_path / "status.md"
    source.write_text(_markdown(), encoding="utf-8")

    records = country_status.parse_country_status_markdown(source)

    assert records == [
        {
            "dataset": "country_lgbti_status",
            "country_code": "ES",
            "country": "España",
            "year": 2026,
            "title": "Avance con retos pendientes",
            "summary": "La situación muestra avances sostenidos y retos relevantes para la igualdad.",
            "legal_context": "Existe protección legal estatal.",
            "social_context": "Persisten diferencias territoriales.",
            "observations": "Revisión anual.",
            "positive_developments": ["Nueva protección", "Mejor acceso"],
            "main_challenges": ["Aplicación desigual", "Falta de datos"],
            "source_name": "ILGA-Europe",
            "source_url": "https://example.test/review",
            "reviewed_at": "2026-02-01",
            "active": True,
        }
    ]


@pytest.mark.parametrize(
    ("markdown", "message"),
    [
        ("## España (ES)", "Annual Review"),
        ("Annual Review 2026", "fichas de países"),
        (_markdown() + "\n" + _markdown(), "duplicado"),
        (_markdown().replace("**Estado general:** Avance con retos pendientes\n", ""), "Estado general"),
        (_markdown().replace("https://example.test/review", "not-a-url"), "no es válida"),
    ],
)
def test_country_status_markdown_rejects_invalid_documents(markdown: str, message: str) -> None:
    with pytest.raises(country_status.CountryStatusMarkdownError, match=message):
        country_status.parse_country_status_markdown_text(markdown)


def test_country_status_import_handles_empty_and_bulk_upsert(monkeypatch) -> None:
    assert country_status.import_country_status_records([]) == {
        "matched": 0,
        "modified": 0,
        "upserted": 0,
    }

    recorded = SimpleNamespace(operations=None, ordered=None)

    class Collection:
        def bulk_write(self, operations, *, ordered):
            recorded.operations = operations
            recorded.ordered = ordered
            return SimpleNamespace(matched_count=1, modified_count=2, upserted_count=3)

    invalidations: list[str] = []
    monkeypatch.setattr(country_status, "get_mongo_collection", lambda _name: Collection())
    monkeypatch.setattr(country_status.cache, "app", object(), raising=False)
    monkeypatch.setattr(country_status, "invalidate_analytics_cache", invalidations.append)
    records = country_status.parse_country_status_markdown_text(_markdown())

    result = country_status.import_country_status_records(records)

    assert result == {"matched": 1, "modified": 2, "upserted": 3}
    assert recorded.ordered is False
    assert len(recorded.operations) == 1
    assert invalidations == ["country_status"]
