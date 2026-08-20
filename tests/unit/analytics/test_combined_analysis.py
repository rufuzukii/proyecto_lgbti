from __future__ import annotations

import math
from typing import Any, cast

import pytest

from app.analytics.combined_analysis import (
    AVAILABLE,
    FRA_MISSING,
    ILGA_MISSING,
    NOT_COMPARABLE,
    NOT_PARTICIPATING,
    build_availability_rows,
    build_combined_analysis,
    classify_quadrant,
    combined_metrics,
    correlation_strength,
    infer_indicator_semantics,
    median_difference_rows,
    nearest_ilga_year,
    quadrant_eligibility,
)
from app.analytics.statistics_charts import (
    build_combined_quadrant_chart,
    build_combined_scatter,
    build_data_availability_matrix,
    build_fra_median_difference_chart,
)
from app.analytics.statistics_exports import export_summary_table
from app.analytics.statistics_models import FraStatisticsQuery
from app.analytics.statistics_service import get_combined_statistics_analysis
from app.dash.pages.statistics import (
    _combined_interpretation,
    _combined_intro,
    _fra_conclusion,
    build_statistics_layout,
)


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
    assert infer_indicator_semantics("Felt discriminated in the last 12 months", "Yes")[
        "direction"
    ] == "adverse"
    assert infer_indicator_semantics("Felt discriminated in the last 12 months", "No")[
        "direction"
    ] == "favourable"
    assert infer_indicator_semantics("Feels safe holding hands", "Yes")["direction"] == (
        "favourable"
    )
    assert infer_indicator_semantics("Unclassified response", "Sometimes")["direction"] == (
        "unknown"
    )


def test_interpretation_is_prudent_for_small_and_clear_samples() -> None:
    small = _component_text(
        _combined_interpretation(
            {
                "indicator": "Felt discriminated",
                "answer": "Yes",
                "metrics": combined_metrics(_rows(4)),
                "semantics": {"direction": "adverse"},
            },
            "es",
        )
    )
    strong = _component_text(
        _combined_interpretation(
            {
                "metrics": combined_metrics(_rows(10, inverse=True)),
                "semantics": {"direction": "adverse"},
                "indicator": "Felt discriminated",
                "answer": "Yes",
            },
            "es",
        )
    )

    assert "No hay suficientes países" in small
    assert "no significa que uno sea la causa" in small
    assert "vista por cuadrantes" in strong
    assert "no significa que uno sea la causa" in strong


def test_combined_methodology_and_interpretation_are_localized_in_english() -> None:
    analysis = {
        "indicator": "Felt discriminated",
        "answer": "Yes",
        "fra_year": 2019,
        "ilga_year": 2020,
        "semantics": {"direction": "adverse"},
        "metrics": combined_metrics(_rows(7, inverse=True)),
    }
    intro = _component_text(_combined_intro(analysis, "en"))
    interpretation = _component_text(_combined_interpretation(analysis, "en"))

    assert "does not show that one variable causes" in intro
    assert "FRA 2019 and ILGA-Europe 2020" in intro
    assert "different years" in intro
    assert "European Union Agency for Fundamental Rights" in intro
    assert "exploratory" in interpretation
    assert "does not mean that one causes the other" in interpretation


def test_quadrants_only_accept_yes_no_or_quantitative_answers() -> None:
    assert quadrant_eligibility("Felt discriminated", "Yes")["eligible"] is True
    assert quadrant_eligibility("Felt discriminated", "No")["eligible"] is True
    assert quadrant_eligibility("Felt discriminated", "Sí")["eligible"] is True
    assert quadrant_eligibility("Number of incidents", "5")["eligible"] is True
    assert quadrant_eligibility("Age range", "25-39")["eligible"] is True
    assert quadrant_eligibility("Felt discriminated", "Sometimes")["eligible"] is False
    assert quadrant_eligibility("Unclassified question", "Yes")["eligible"] is False


def test_fra_conclusion_uses_valid_values_and_keeps_zero() -> None:
    conclusion = _fra_conclusion(
        {
            "ranking": [
                {"country": "Spain", "value": 0},
                {"country": "France", "value": 20},
                {"country": "Germany", "value": None},
            ]
        },
        "es",
    )

    assert "2 países con datos válidos" in conclusion
    assert "entre 0.0% y 20.0%" in conclusion
    assert "media de 10.0%" in conclusion


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
    differences = median_difference_rows(rows)
    divergent = build_fra_median_difference_chart(
        differences, "es", semantic_direction="adverse", answer="Yes"
    )

    assert list(scatter.layout.xaxis.range) == [0, 100]
    assert list(scatter.layout.yaxis.range) == [0, 100]
    scatter_data = cast(Any, scatter.data)
    quadrant_data = cast(Any, quadrants.data)
    divergent_data = cast(Any, divergent.data)
    assert len(scatter_data) == 2
    assert "País" in scatter_data[0].hovertemplate
    assert "Encuesta FRA" in scatter_data[0].hovertemplate
    assert len(quadrant_data) == 1
    assert len(cast(Any, quadrants.layout.shapes)) == 2
    assert "Situación" in quadrant_data[0].hovertemplate
    assert divergent_data[0].orientation == "h"
    assert "puntos porcentuales" in divergent_data[0].hovertemplate


def test_quadrant_classification_respects_semantics_and_median_equality() -> None:
    common = {"fra_median": 50, "ilga_median": 50}
    high_high = classify_quadrant(
        70, 70, semantic_direction="favourable", **common
    )
    high_low = classify_quadrant(30, 70, semantic_direction="favourable", **common)
    low_high = classify_quadrant(70, 30, semantic_direction="adverse", **common)
    low_low = classify_quadrant(30, 30, semantic_direction="adverse", **common)
    equal = classify_quadrant(50, 50, semantic_direction="favourable", **common)

    assert high_low is not None
    assert low_high is not None
    assert low_low is not None
    assert equal is not None

    assert high_high == {
        "legal_level": "high", "fra_level": "high", "experience": "favourable",
        "quadrant": "high_legal_favourable",
    }
    assert high_low["experience"] == "unfavourable"
    assert low_high["experience"] == "unfavourable"
    assert low_low["experience"] == "favourable"
    assert equal["legal_level"] == equal["fra_level"] == "high"


def test_median_difference_keeps_zero_and_drops_null() -> None:
    comparison = median_difference_rows(
        [
            {"country": "A", "fra_value": 0},
            {"country": "B", "fra_value": 20},
            {"country": "C", "fra_value": None},
        ]
    )

    assert comparison["median"] == 10.0
    assert [row["difference_pp"] for row in comparison["rows"]] == [10.0, -10.0]


def test_availability_states_are_explicit_and_never_use_zero_for_missing() -> None:
    rows = build_availability_rows(
        [
            {"country": "Spain", "iso": "ES"},
            {"country": "France", "iso": "FR"},
            {"country": "Norway", "iso": "NO"},
            {"country": "Iceland", "iso": "IS"},
        ],
        fra_values_by_year={2023: {"ES"}, 2019: set()},
        indicator_available_by_year={2023: True, 2019: False},
        participant_codes_by_year={2023: {"ES", "FR", "IS"}, 2019: {"ES", "FR", "IS"}},
        ilga_rows=[
            {"country": "Spain", "iso": "ES", "value": 0},
            {"country": "France", "iso": "FR", "value": 70},
            {"country": "Norway", "iso": "NO", "value": None},
        ],
    )
    by_iso = {row["iso"]: row for row in rows}

    assert by_iso["ES"]["fra"]["2023"] == AVAILABLE
    assert by_iso["FR"]["fra"]["2023"] == FRA_MISSING
    assert by_iso["NO"]["fra"]["2023"] == NOT_PARTICIPATING
    assert by_iso["IS"]["fra"]["2019"] == NOT_COMPARABLE
    assert by_iso["ES"]["ilga"] == AVAILABLE
    assert by_iso["NO"]["ilga"] == ILGA_MISSING

    matrix = build_data_availability_matrix(
        {"rows": rows, "fra_years": [2019, 2023], "ilga_year": 2023}, "es"
    )
    matrix_text = cast(Any, matrix.data)[0].text
    assert "NP" in {value for row in matrix_text for value in row}
    assert "NC" in {value for row in matrix_text for value in row}


def test_combined_service_uses_nearest_legal_year_in_one_shared_payload(monkeypatch) -> None:
    requested_years: list[int | None] = []
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_ilga_years", lambda: [2019, 2023, 2026]
    )

    def fake_ilga(query, *, include_history):
        requested_years.append(query.year)
        assert include_history is False
        return {
            "status": "ok",
            "year": query.year,
            "ranking": [{"country": "Spain", "iso": "ES", "value": 70}],
            "normalization": {"applied": False},
        }

    monkeypatch.setattr("app.analytics.statistics_service.get_ilga_statistics", fake_ilga)
    monkeypatch.setattr(
        "app.analytics.statistics_service._combined_availability",
        lambda *_args: {"rows": [], "fra_years": [2012, 2019, 2023], "ilga_year": 2023},
    )
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
        "app.dash.pages.statistics.assert_analytics_databases_available", lambda: None
    )
    monkeypatch.setattr("app.dash.pages.statistics.build_navbar", lambda **_kwargs: "")
    layout = build_statistics_layout()
    combined = _component_by_id(layout, "stats-combined-block")

    assert _component_by_id(layout, "stats-fra-conclusion") is not None
    assert _component_by_id(layout, "stats-combined-intro") is not None
    assert _component_by_id(combined, "stats-scatter-graph-slot") is None
    assert _component_by_id(combined, "stats-quadrant-graph-slot") is not None
    assert _component_by_id(combined, "stats-quadrant-panel") is not None
    assert _component_by_id(combined, "stats-median-difference-graph-slot") is not None
    assert _component_by_id(combined, "stats-availability-graph-slot") is None
    assert _component_by_id(combined, "stats-experience-legal-radar-panel") is not None
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
                "difference_from_fra_median": -2.0,
            }
        ],
        [
            {"field": "country", "headerName": "Country"},
            {"field": "country_code", "headerName": "Country code"},
            {"field": "fra_value", "headerName": "FRA value (%)"},
            {"field": "ilga_score", "headerName": "ILGA-Europe score"},
            {
                "field": "difference_from_fra_median",
                "headerName": "Difference from FRA median (pp)",
            },
        ],
        language="en",
        metadata={"source": "FRA + ILGA-Europe", "year": "FRA 2023 / ILGA 2023"},
    )

    assert "FRA value (%)" in exported.content
    assert "ILGA-Europe score" in exported.content
    assert "30.0;70.0;-2.0" in exported.content
    assert "caus" not in exported.content.lower()
