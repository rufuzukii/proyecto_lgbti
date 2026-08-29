from __future__ import annotations

from typing import Any

from app.modules.reports import service
from app.modules.reports.models import ReportConfiguration
from app.modules.reports.recommendations import (
    build_recommendations,
    indicator_semantics,
    result_level,
)


def test_reports_use_one_hr_rule_based_guidance_catalogue() -> None:
    recommendations = build_recommendations(
        indicator="Felt discriminated at work",
        answer="Yes",
        country_value=70.0,
        benchmark=45.0,
        language="es",
    )

    assert recommendations
    assert any(item.derived_from_metrics for item in recommendations)


def test_hr_adverse_result_does_not_return_legacy_profile_guidance() -> None:
    recommendations = build_recommendations(
        indicator="Felt discriminated at work",
        answer="Yes",
        country_value=70.0,
        benchmark=45.0,
        language="es",
    )
    text = " ".join(item.text for item in recommendations).casefold()

    assert "protocolos" in text
    assert "alumnado" not in text
    assert "actividad" not in text


def test_indicator_answer_semantics_prevent_inverted_conclusions() -> None:
    assert indicator_semantics("Felt discriminated", "Yes") == "adverse"
    assert indicator_semantics("Felt discriminated", "No") == "favourable"
    assert indicator_semantics("Feels safe", "Yes") == "favourable"
    assert result_level(
        semantics="adverse", country_value=60.0, benchmark=40.0
    ) == "adverse"
    assert result_level(
        semantics="favourable", country_value=60.0, benchmark=40.0
    ) == "favourable"
    assert result_level(
        semantics="adverse", country_value=0.0, benchmark=10.0
    ) == "favourable"
    assert result_level(
        semantics="adverse", country_value=None, benchmark=10.0
    ) == "unknown"


def test_combined_report_reuses_one_fra_result_for_shared_analysis(monkeypatch) -> None:
    fra_result: dict[str, Any] = {
        "status": "ok",
        "source": "FRA",
        "year": 2023,
        "indicator": "Felt discriminated",
        "ranking": [{"country": "Spain", "iso": "ES", "value": 30.0}],
    }
    combined = {
        "status": "ok",
        "fra_year": 2023,
        "ilga_year": 2023,
        "rows": [{"country": "Spain", "iso": "ES", "fra_value": 30.0, "ilga_value": 75.0}],
        "metrics": {"n": 1},
        "ranking_gap": {"available": False, "rows": []},
    }
    calls = {"fra": 0, "combined": 0}

    def fake_fra(_query):
        calls["fra"] += 1
        return fra_result

    def fake_combined(_query, *, fra_result=None):
        calls["combined"] += 1
        assert fra_result is not None
        return combined

    monkeypatch.setattr(service, "get_fra_statistics", fake_fra)
    monkeypatch.setattr(service, "get_combined_statistics_analysis", fake_combined)

    dataset = service.load_report_dataset(
        ReportConfiguration.from_mapping(
            {
                "source": "combined",
                "year": 2023,
                "category": "Discrimination",
                "indicator_id": "D1",
                "answer": "Yes",
                "sections": ["executive"],
                "charts": ["scatter"],
            }
        )
    )

    assert calls == {"fra": 1, "combined": 1}
    assert dataset.result["source"] == "FRA + ILGA-Europe"
    assert dataset.result["combined_analysis"]["ilga_year"] == 2023
