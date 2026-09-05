from __future__ import annotations

import math
from typing import Any, cast

import pytest

from app.modules.statistics.combined_analysis import (
    build_combined_analysis,
    classify_quadrant,
    combined_metrics,
    correlation_strength,
    get_supported_combined_analyses,
    infer_indicator_semantics,
    nearest_ilga_year,
    quadrant_eligibility,
    ranking_position_rows,
)
from app.modules.statistics.exports import export_summary_table
from app.modules.statistics.figures import (
    build_combined_quadrant_chart,
    build_combined_scatter,
    build_ranking_position_gap_chart,
)
from app.modules.statistics.models import FraStatisticsQuery
from app.modules.statistics.page import (
    _combined_compatibility_messages,
    _combined_intro,
    _map_ranking_content,
    build_statistics_layout,
)
from app.modules.statistics.service import get_combined_statistics_analysis


def _rows(count: int, *, inverse: bool = False) -> list[dict[str, float | str]]:
    return [
        {
            "country": f"Country {index}",
            "iso": f"X{index:02d}",
            "ilga_value": float(index * 10),
            "fra_value": float((count - index) * 5 if inverse else index * 5),
        }
        for index in range(1, count + 1)
    ]


def _component_text(component: object) -> str:
    if component is None:
        return ""
    if isinstance(component, str):
        return component
    if isinstance(component, (list, tuple)):
        return " ".join(_component_text(item) for item in component)
    return _component_text(getattr(component, "children", None))


def _component_by_id(component: object, component_id: str):
    if getattr(component, "id", None) == component_id:
        return component
    children = getattr(component, "children", None)
    if not isinstance(children, (list, tuple)):
        children = [children] if children is not None else []
    for child in children:
        found = _component_by_id(child, component_id)
        if found is not None:
            return found
    return None


def test_nearest_ilga_year_prefers_exact_then_earlier_tie() -> None:
    assert nearest_ilga_year(2023, [2019, 2023, 2026]) == 2023
    assert nearest_ilga_year(2021, [2019, 2023]) == 2019
    assert nearest_ilga_year(None, [2019, 2023]) == 2023
    assert nearest_ilga_year(2023, []) is None


def test_combination_preserves_real_zero_and_drops_null_or_non_finite() -> None:
    analysis = build_combined_analysis(
        {
            "year": 2023,
            "indicator": "Felt discriminated",
            "answer": "Yes",
            "ranking": [
                {"country": "Spain", "iso": "ES", "value": 0},
                {"country": "France", "iso": "FR", "value": None},
                {"country": "Germany", "iso": "DE", "value": math.inf},
            ],
        },
        {
            "year": 2023,
            "ranking": [
                {"country": "Spain", "iso": "ES", "value": 75},
                {"country": "France", "iso": "FR", "value": 60},
                {"country": "Germany", "iso": "DE", "value": 70},
            ],
        },
    )

    assert analysis["rows"] == [
        {"country": "Spain", "iso": "ES", "fra_value": 0.0, "ilga_value": 75.0}
    ]
    assert analysis["metrics"]["n"] == 1


def test_spearman_is_preferred_and_sample_rules_are_enforced() -> None:
    insufficient = combined_metrics(_rows(4, inverse=True))
    exploratory = combined_metrics(_rows(7, inverse=True))
    normal = combined_metrics(_rows(10, inverse=True))

    assert insufficient["sample_status"] == "insufficient"
    assert insufficient["spearman"] is None
    assert exploratory["sample_status"] == "exploratory"
    assert exploratory["spearman"] == pytest.approx(-1.0)
    assert normal["sample_status"] == "normal"
    assert normal["preferred"] == "spearman"
    assert normal["spearman"] == pytest.approx(-1.0)
    assert normal["pearson"] == pytest.approx(-1.0)
    assert normal["trend_slope"] is not None


def test_correlation_strength_taxonomy_has_stable_boundaries() -> None:
    assert correlation_strength(0.0) == "very_weak"
    assert correlation_strength(0.2) == "weak"
    assert correlation_strength(-0.4) == "moderate"
    assert correlation_strength(0.6) == "strong"
    assert correlation_strength(-0.8) == "very_strong"
    assert correlation_strength(None) == "unavailable"


def test_indicator_semantics_does_not_invert_yes_and_no() -> None:
    assert (
        infer_indicator_semantics("Felt discriminated in the last 12 months", "Yes")["direction"]
        == "adverse"
    )
    assert (
        infer_indicator_semantics("Felt discriminated in the last 12 months", "No")["direction"]
        == "favourable"
    )
    assert infer_indicator_semantics("Feels safe holding hands", "Yes")["direction"] == (
        "favourable"
    )
    assert infer_indicator_semantics("Unclassified response", "Sometimes")["direction"] == (
        "unknown"
    )


def test_combined_methodology_is_localized_in_english() -> None:
    analysis = {
        "indicator": "Felt discriminated",
        "answer": "Yes",
        "fra_year": 2019,
        "ilga_year": 2020,
        "semantics": {"direction": "adverse"},
        "metrics": combined_metrics(_rows(7, inverse=True)),
    }
    intro = _component_text(_combined_intro(analysis, "en"))

    assert "does not show that one variable causes" in intro
    assert "FRA 2019 and ILGA-Europe 2020" in intro
    assert "different years" in intro
    assert "European Union Agency for Fundamental Rights" in intro


def test_quadrants_only_accept_yes_no_or_quantitative_answers() -> None:
    assert quadrant_eligibility("Felt discriminated", "Yes")["eligible"] is True
    assert quadrant_eligibility("Felt discriminated", "No")["eligible"] is True
    assert quadrant_eligibility("Felt discriminated", "Sí")["eligible"] is True
    assert quadrant_eligibility("Number of incidents", "5")["eligible"] is True
    assert quadrant_eligibility("Age range", "25-39")["eligible"] is True
    assert quadrant_eligibility("Felt discriminated", "Sometimes")["eligible"] is False
    assert quadrant_eligibility("Unclassified question", "Yes")["eligible"] is False


def test_map_ranking_uses_descending_values_localized_ties_and_keeps_zero() -> None:
    content = _map_ranking_content(
        [
            {"country": "Spain", "iso": "ES", "value": 50},
            {"country": "France", "iso": "FR", "value": 60},
            {"country": "Germany", "iso": "DE", "value": 50},
            {"country": "Italy", "iso": "IT", "value": 0},
            {"country": "Portugal", "iso": "PT", "value": None},
        ],
        "es",
    )
    rows = cast(Any, content[1]).children

    assert [row.children[1].children for row in rows] == [
        "Francia",
        "Alemania",
        "España",
        "Italia",
    ]
    assert rows[-1].children[2].children == "0 %"


def test_combined_figures_use_full_scales_medians_and_country_hover() -> None:
    rows = _rows(10, inverse=True)
    metrics = combined_metrics(rows)
    scatter = build_combined_scatter(
        rows,
        "es",
        ["X01"],
        answer="Yes",
        fra_year=2023,
        ilga_year=2023,
        metrics=metrics,
        segmentation="Edad: 25-39",
    )
    quadrants = build_combined_quadrant_chart(
        rows,
        "es",
        ["X01"],
        semantic_direction="adverse",
        answer="Yes",
        metrics=metrics,
    )
    rank_positions = ranking_position_rows(rows, "adverse")
    ranking_gap = build_ranking_position_gap_chart(rank_positions, "es", answer="Yes")

    assert list(scatter.layout.xaxis.range) == [0, 100]
    assert list(scatter.layout.yaxis.range) == [0, 100]
    scatter_data = cast(Any, scatter.data)
    quadrant_data = cast(Any, quadrants.data)
    ranking_gap_data = cast(Any, ranking_gap.data)
    assert len(scatter_data) == 2
    assert "País" in scatter_data[0].hovertemplate
    assert "Encuesta FRA" in scatter_data[0].hovertemplate
    assert len(quadrant_data) == 1
    assert len(cast(Any, quadrants.layout.shapes)) == 2
    assert "Situación" in quadrant_data[0].hovertemplate
    assert len(ranking_gap_data) == 3
    assert "Posición legal" in ranking_gap_data[1].hovertemplate
    assert "Posición social" in ranking_gap_data[1].hovertemplate


def test_quadrant_classification_respects_semantics_and_median_equality() -> None:
    common = {"fra_median": 50, "ilga_median": 50}
    high_high = classify_quadrant(70, 70, semantic_direction="favourable", **common)
    high_low = classify_quadrant(30, 70, semantic_direction="favourable", **common)
    low_high = classify_quadrant(70, 30, semantic_direction="adverse", **common)
    low_low = classify_quadrant(30, 30, semantic_direction="adverse", **common)
    equal = classify_quadrant(50, 50, semantic_direction="favourable", **common)

    assert high_low is not None
    assert low_high is not None
    assert low_low is not None
    assert equal is not None

    assert high_high == {
        "legal_level": "high",
        "fra_level": "high",
        "experience": "favourable",
        "quadrant": "high_legal_favourable",
    }
    assert high_low["experience"] == "unfavourable"
    assert low_high["experience"] == "unfavourable"
    assert low_low["experience"] == "favourable"
    assert equal["legal_level"] == equal["fra_level"] == "high"


def test_ranking_positions_respect_direction_ties_zero_and_null() -> None:
    rows = [
        {"country": "A", "iso": "AA", "fra_value": 0, "ilga_value": 90},
        {"country": "B", "iso": "BB", "fra_value": 30, "ilga_value": 80},
        {"country": "C", "iso": "CC", "fra_value": 60, "ilga_value": 80},
        {"country": "D", "iso": "DD", "fra_value": None, "ilga_value": 70},
    ]
    adverse = ranking_position_rows(rows, "adverse")
    by_iso = {row["iso"]: row for row in adverse["rows"]}

    assert adverse["available"] is True
    assert by_iso["AA"]["fra_rank"] == 1
    assert by_iso["CC"]["fra_rank"] == 3
    assert by_iso["BB"]["ilga_rank"] == by_iso["CC"]["ilga_rank"] == 2
    assert "DD" not in by_iso


def test_ranking_positions_reverse_for_favourable_values_and_reject_unknown() -> None:
    rows = [
        {"country": "A", "iso": "AA", "fra_value": 10, "ilga_value": 90},
        {"country": "B", "iso": "BB", "fra_value": 60, "ilga_value": 80},
    ]
    favourable = ranking_position_rows(rows, "favourable")
    by_iso = {row["iso"]: row for row in favourable["rows"]}

    assert by_iso["BB"]["fra_rank"] == 1
    assert ranking_position_rows(rows, "unknown")["available"] is False


def test_ranking_positions_keep_the_complete_european_sample() -> None:
    rows = [
        {
            "country": f"Country {index:02d}",
            "iso": f"X{index:02d}",
            "fra_value": float(index),
            "ilga_value": float(100 - index),
        }
        for index in range(1, 36)
    ]

    comparison = ranking_position_rows(rows, "favourable")
    figure = build_ranking_position_gap_chart(comparison, "en", answer="Yes")

    assert comparison["available"] is True
    assert len(comparison["rows"]) == 35
    assert len(cast(Any, figure.data[1]).x) == 35
    assert figure.layout.height >= 34 * 35 + 150


def test_combination_starts_from_fra_and_only_drops_countries_without_ilga() -> None:
    analysis = build_combined_analysis(
        {
            "year": 2023,
            "indicator": "Feels safe",
            "answer": "Yes",
            "ranking": [
                {"country": "A", "iso": "AA", "value": 10},
                {"country": "B", "iso": "BB", "value": 20},
                {"country": "C", "iso": "CC", "value": 30},
            ],
        },
        {
            "year": 2023,
            "ranking": [
                {"country": "A", "iso": "AA", "value": 80},
                {"country": "C", "iso": "CC", "value": 60},
            ],
        },
    )

    assert [row["iso"] for row in analysis["rows"]] == ["AA", "CC"]


def test_compatibility_hides_often_and_builds_dynamic_messages() -> None:
    rows = _rows(8)
    support = get_supported_combined_analyses(
        question="conduct at school due to being LGBTIQ",
        answer="Often",
        rows=rows,
    )
    analysis = {
        "indicator": "conduct at school due to being LGBTIQ",
        "answer": "Often",
        "rows": rows,
        "semantics": infer_indicator_semantics("conduct at school due to being LGBTIQ", "Often"),
        "quadrant_eligibility": quadrant_eligibility(
            "conduct at school due to being LGBTIQ", "Often"
        ),
        "supported_analyses": support,
    }
    message = _component_text(_combined_compatibility_messages(analysis, "es"))

    assert support["quadrants"] is False
    assert support["ranking_gap"] is False
    assert support["any_visualization"] is False
    assert support["download"] is False
    assert '"Often"' in message
    assert '"conduct at school due to being LGBTIQ"' in message


def test_age_bucket_has_only_two_methodological_messages_and_no_analysis() -> None:
    indicator = "Age when first realised having variation in sex characteristics"
    answer = "10-14y.o."
    rows = _rows(8)
    support = get_supported_combined_analyses(
        question=indicator,
        answer=answer,
        rows=rows,
    )
    messages = _combined_compatibility_messages(
        {
            "indicator": indicator,
            "answer": answer,
            "rows": rows,
            "supported_analyses": support,
        },
        "es",
    )

    assert support["any_visualization"] is False
    assert support["download"] is False
    assert len(messages) == 2
    rendered = _component_text(messages)
    assert '"10-14y.o."' in rendered
    assert f'"{indicator}"' in rendered


def test_combined_service_uses_nearest_legal_year_in_one_shared_payload(monkeypatch) -> None:
    requested_years: list[int | None] = []
    monkeypatch.setattr("app.modules.statistics.service.get_ilga_years", lambda: [2019, 2023, 2026])

    def fake_ilga(query, *, include_history):
        requested_years.append(query.year)
        assert include_history is False
        return {
            "status": "ok",
            "year": query.year,
            "ranking": [{"country": "Spain", "iso": "ES", "value": 70}],
            "normalization": {"applied": False},
        }

    monkeypatch.setattr("app.modules.statistics.service.get_ilga_statistics", fake_ilga)
    result = get_combined_statistics_analysis(
        FraStatisticsQuery(
            year=2023,
            category="Discrimination",
            question_code="D1",
            answer="Yes",
        ),
        fra_result={
            "status": "ok",
            "year": 2023,
            "indicator": "Felt discriminated",
            "answer": "Yes",
            "ranking": [{"country": "Spain", "iso": "ES", "value": 30}],
        },
    )

    assert requested_years == [2023]
    assert result["ilga_year"] == 2023
    assert result["rows"][0]["fra_value"] == 30.0


def test_statistics_layout_separates_fra_and_combined_without_redundant_charts(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.statistics.page.assert_analytics_databases_available", lambda: None
    )
    monkeypatch.setattr("app.modules.statistics.page.build_navbar", lambda **_kwargs: "")
    layout = build_statistics_layout()
    combined = _component_by_id(layout, "stats-combined-block")

    assert _component_by_id(layout, "stats-fra-conclusion") is None
    assert _component_by_id(layout, "stats-combined-intro") is not None
    assert _component_by_id(layout, "stats-combined-download-action") is not None
    assert _component_by_id(layout, "stats-combined-download-button") is None
    assert _component_by_id(combined, "stats-scatter-graph-slot") is None
    assert _component_by_id(combined, "stats-quadrant-graph-slot") is not None
    assert _component_by_id(combined, "stats-quadrant-panel") is not None
    assert _component_by_id(combined, "stats-ranking-gap-graph-slot") is not None
    assert _component_by_id(combined, "stats-median-difference-graph-slot") is None
    assert _component_by_id(combined, "stats-availability-graph-slot") is None
    assert _component_by_id(combined, "stats-experience-legal-radar-panel") is None
    assert _component_by_id(combined, "stats-combined-interpretation") is None
    assert _component_by_id(layout, "stats-gap-graph-slot") is None
    assert _component_by_id(layout, "stats-combined-heatmap-slot") is None


def test_combined_csv_contains_only_analytical_values_not_interpretation() -> None:
    exported = export_summary_table(
        [
            {
                "country": "Spain",
                "country_code": "ES",
                "fra_value": 30.0,
                "ilga_score": 70.0,
                "legal_rank": 3,
                "social_rank": 17,
                "ranking_position_difference": 14,
            }
        ],
        [
            {"field": "country", "headerName": "Country"},
            {"field": "country_code", "headerName": "Country code"},
            {"field": "fra_value", "headerName": "FRA value (%)"},
            {"field": "ilga_score", "headerName": "ILGA-Europe score"},
            {
                "field": "ranking_position_difference",
                "headerName": "Difference in positions",
            },
        ],
        language="en",
        metadata={"source": "FRA + ILGA-Europe", "year": "FRA 2023 / ILGA 2023"},
    )

    assert "FRA value (%)" in exported.content
    assert "ILGA-Europe score" in exported.content
    assert "30.0;70.0;14" in exported.content
    assert "caus" not in exported.content.lower()
