import hashlib
import json
from unittest.mock import patch

from app.analytics.country_status_service import (
    _load_english_catalog,
    get_country_lgbti_status,
)


def test_country_status_returns_requested_order_and_deduplicates() -> None:
    records = [
        {
            "country_code": "PT",
            "country": "Portugal",
            "year": 2026,
            "summary": "Resumen valido de Portugal.",
            "source_name": "ILGA-Europe Annual Review 2026",
            "source_url": "https://example.test/report.pdf",
            "reviewed_at": "2026-03-15",
            "active": True,
        },
        {
            "country_code": "ES",
            "country": "Spain",
            "year": 2026,
            "summary": "Resumen valido de Spain.",
            "source_name": "ILGA-Europe Annual Review 2026",
            "source_url": "https://example.test/report.pdf",
            "reviewed_at": "2026-03-15",
            "active": True,
        },
    ]

    with patch(
        "app.analytics.country_status_service.get_country_lgbti_status_records",
        return_value=records,
    ) as repository:
        result = get_country_lgbti_status(["ES", "PT", "ES"], 2026)

    repository.assert_called_once_with(("ES", "PT"), 2026)
    assert [item["country_code"] for item in result] == ["ES", "PT"]
    assert all(item["available"] for item in result)


def test_country_status_keeps_fallback_year_visible() -> None:
    with patch(
        "app.analytics.country_status_service.get_country_lgbti_status_records",
        return_value=[
            {
                "country_code": "ES",
                "country": "Spain",
                "year": 2025,
                "summary": "Resumen cualitativo de un ano anterior.",
                "source_name": "ILGA-Europe Annual Review 2025",
                "source_url": "https://example.test/report.pdf",
                "reviewed_at": "2025-03-15",
                "active": True,
            }
        ],
    ):
        result = get_country_lgbti_status(["ES"], 2026)

    assert result[0]["available"] is True
    assert result[0]["year"] == 2025


def test_country_status_preserves_stored_bilingual_content() -> None:
    with patch(
        "app.analytics.country_status_service.get_country_lgbti_status_records",
        return_value=[
            {
                "country_code": "ES",
                "country": "Spain",
                "year": 2026,
                "summary": "Resumen.",
                "summary_i18n": {"es": "Resumen.", "en": "Summary."},
                "positive_developments": ["Avance."],
                "positive_developments_i18n": {
                    "es": ["Avance."],
                    "en": ["Progress."],
                },
                "source_name": "ILGA-Europe",
                "active": True,
            }
        ],
    ):
        result = get_country_lgbti_status(["ES"], 2026)

    assert result[0]["summary_i18n"] == {"es": "Resumen.", "en": "Summary."}
    assert result[0]["positive_developments_i18n"] == {
        "es": ["Avance."],
        "en": ["Progress."],
    }


def test_country_status_adds_versioned_english_content_when_source_matches() -> None:
    summary = "Resumen cualitativo estable."
    developments = ["Avance estable."]
    catalog = {
        "ES": {
            "summary": "Stable qualitative summary.",
            "positive_developments": ["Stable progress."],
            "_source_fingerprints": {
                "summary": _fingerprint_for(summary),
                "positive_developments": _fingerprint_for(developments),
            },
        }
    }
    with (
        patch(
            "app.analytics.country_status_service.get_country_lgbti_status_records",
            return_value=[
                {
                    "country_code": "ES",
                    "country": "Spain",
                    "year": 2026,
                    "summary": summary,
                    "positive_developments": developments,
                    "source_name": "ILGA-Europe",
                    "active": True,
                }
            ],
        ),
        patch(
            "app.analytics.country_status_service._load_english_catalog",
            return_value=(2026, catalog),
        ),
    ):
        result = get_country_lgbti_status(["ES"], 2026)

    assert result[0]["summary_i18n"]["en"] == "Stable qualitative summary."
    assert result[0]["positive_developments_i18n"]["en"] == ["Stable progress."]


def test_country_status_does_not_apply_stale_versioned_translation() -> None:
    catalog = {
        "ES": {
            "summary": "Old English summary.",
            "_source_fingerprints": {"summary": _fingerprint_for("Resumen anterior.")},
        }
    }
    with (
        patch(
            "app.analytics.country_status_service.get_country_lgbti_status_records",
            return_value=[
                {
                    "country_code": "ES",
                    "country": "Spain",
                    "year": 2026,
                    "summary": "Resumen actualizado.",
                    "source_name": "ILGA-Europe",
                    "active": True,
                }
            ],
        ),
        patch(
            "app.analytics.country_status_service._load_english_catalog",
            return_value=(2026, catalog),
        ),
    ):
        result = get_country_lgbti_status(["ES"], 2026)

    assert "summary_i18n" not in result[0]


def test_versioned_english_catalog_is_complete_and_fingerprinted() -> None:
    year, records = _load_english_catalog()
    fields = {
        "title",
        "summary",
        "legal_context",
        "social_context",
        "observations",
        "positive_developments",
        "main_challenges",
    }

    assert year == 2026
    assert len(records) == 49
    for record in records.values():
        assert fields <= record.keys()
        assert all(record[field] for field in fields)
        assert fields <= record["_source_fingerprints"].keys()


def test_country_status_returns_missing_card_payload() -> None:
    with patch(
        "app.analytics.country_status_service.get_country_lgbti_status_records",
        return_value=[],
    ):
        result = get_country_lgbti_status(["FR"], 2026)

    assert result[0]["available"] is False
    assert result[0]["country_code"] == "FR"
    assert result[0]["year"] == 2026
    assert result[0]["summary"] == "Todavía no hay información disponible para este país."
    assert result[0]["summary_i18n"] == {
        "es": "Todavía no hay información disponible para este país.",
        "en": "No information is available for this country yet.",
    }


def _fingerprint_for(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
