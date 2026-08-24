from unittest.mock import patch

from app.analytics.country_status_service import get_country_lgbti_status


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
