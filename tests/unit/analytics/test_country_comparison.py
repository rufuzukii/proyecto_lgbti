from __future__ import annotations

import math
from typing import Any

from dash import Dash, html

from app.analytics.statistics_charts import (
    build_combined_heatmap,
    build_comparative_ranking_chart,
    build_country_comparison_chart,
    build_eu_average_comparison_chart,
    build_indicator_radar,
    country_color,
)
from app.analytics.statistics_models import FraStatisticsQuery, IlgaStatisticsQuery
from app.analytics.statistics_service import get_fra_statistics, get_ilga_statistics
from app.dash.pages.statistics import _table_rows, register_statistics_callbacks


def _trace(figure: Any, index: int = 0) -> Any:
    return figure.data[index]


def _traces(figure: Any) -> list[Any]:
    return list(figure.data)


def test_country_palette_matches_the_approved_european_colours() -> None:
    expected = {
        "FR": "#2F6BDE",
        "DE": "#2B2B2B",
        "BE": "#E3B505",
        "NL": "#E85D5D",
        "LU": "#5AA9E6",
        "IT": "#2E8B57",
        "DK": "#B22234",
        "ES": "#C62828",
        "PT": "#2F855A",
        "IE": "#F28C28",
        "GR": "#3A86D1",
        "SE": "#4A90E2",
        "FI": "#6FA8DC",
        "AT": "#8E2430",
        "EE": "#2C7DA0",
        "LV": "#7A1F2B",
        "LT": "#6B8E23",
        "PL": "#D45A7A",
        "CZ": "#1E5AA8",
        "SK": "#4361EE",
        "SI": "#3D5AFE",
        "HU": "#009B77",
        "RO": "#F4B400",
        "BG": "#5A8F29",
        "MT": "#D7265E",
        "CY": "#52B788",
        "HR": "#277DA1",
    }

    assert {iso: country_color(iso) for iso in expected} == expected
    assert country_color(country="France") == expected["FR"]
    assert country_color(country="España") == expected["ES"]
    assert country_color("EL") == expected["GR"]
    assert country_color("ESP", "Spain") == expected["ES"]
    assert country_color(math.nan, "Spain") == expected["ES"]
    assert country_color("Spain") == expected["ES"]
    assert country_color("XX", "Unknown") == "#2F6BDE"


def test_ranking_uses_all_europe_without_selection_and_only_selected_with_selection() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "value": 62.0},
        {"country": "France", "iso": "FR", "value": 58.0},
        {"country": "Portugal", "iso": "PT", "value": None},
    ]

    europe = build_comparative_ranking_chart(rows)
    selected = build_comparative_ranking_chart(rows, ["ES", "PT"])

    assert set(_trace(europe).y) == {"Spain", "France", "Portugal"}
    assert set(_trace(selected).y) == {"Spain", "Portugal"}
    assert "Sin datos" in set(_trace(selected).text)


def test_direct_fra_comparison_groups_binary_and_multiple_answers_by_country() -> None:
    ranking = [
        {"country": "Spain", "iso": "ES", "value": 60.0},
        {"country": "France", "iso": "FR", "value": 50.0},
    ]
    details = [
        {"country": country, "iso": iso, "answer": answer, "percentage": value}
        for country, iso, values in (
            ("Spain", "ES", (60.0, 30.0, 10.0)),
            ("France", "FR", (50.0, 35.0, 15.0)),
        )
        for answer, value in zip(("Yes", "No", "Unknown"), values, strict=True)
    ]

    figure = build_country_comparison_chart(
        ranking,
        ["ES", "FR"],
        detail_rows=details,
        source="FRA",
    )

    assert figure.layout.barmode == "group"
    assert {trace.name for trace in _traces(figure)} == {"Spain", "France"}
    assert all(list(trace.x) == ["Yes", "No", "Unknown"] for trace in _traces(figure))
    assert {trace.name: trace.marker.color for trace in _traces(figure)} == {
        "Spain": country_color("ES", "Spain"),
        "France": country_color("FR", "France"),
    }


def test_combined_heatmap_renders_one_complete_percentage_matrix() -> None:
    figure = build_combined_heatmap(
        [
            {
                "country": "Spain",
                "iso": "ES",
                "ilga_value": 75.0,
                "fra_value": 62.0,
            },
            {
                "country": "France",
                "iso": "FR",
                "ilga_value": 70.0,
                "fra_value": 58.0,
            },
        ]
    )

    assert len(_traces(figure)) == 1
    trace = _trace(figure)
    assert list(trace.y) == ["France", "Spain"]
    assert trace.z.tolist() == [[70.0, 58.0], [75.0, 62.0]]
    assert trace.zmin == 0
    assert trace.zmax == 100


def test_average_chart_exposes_value_mean_absolute_and_percentage_differences() -> None:
    figure = build_eu_average_comparison_chart(
        [
            {"country": "Spain", "iso": "ES", "value": 60.0},
            {"country": "France", "iso": "FR", "value": 40.0},
            {"country": "Portugal", "iso": "PT", "value": None},
        ],
        ["ES", "PT"],
    )

    trace = _trace(figure)
    spain = list(trace.y).index("Spain")
    portugal = list(trace.y).index("Portugal")
    assert trace.customdata[spain].tolist() == ["60.00%", "10.00 pp", "+20.00%"]
    assert trace.customdata[portugal].tolist() == ["Sin datos", "Sin datos", "Sin datos"]


def test_radar_is_hidden_for_binary_fra_and_available_for_multidimensional_ilga() -> None:
    binary = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 60.0},
        {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 40.0},
    ]
    binary_figure, binary_compatible = build_indicator_radar(
        binary,
        source="FRA",
        selected_countries=["ES"],
    )
    legal = [
        {
            "country": country,
            "iso": iso,
            "category": category,
            "criterion": f"{category} criterion",
            "criterion_value": value,
            "criterion_weight": 1.0,
        }
        for country, iso, value in (("Spain", "ES", 0.8), ("France", "FR", 0.6))
        for category in ("Equality", "Family", "Asylum")
    ]
    legal_figure, legal_compatible = build_indicator_radar(
        legal,
        source="ILGA-Europe",
        selected_countries=["ES", "FR"],
    )
    legal_default_figure, legal_default_compatible = build_indicator_radar(
        legal,
        source="ILGA-Europe",
    )

    assert binary_compatible is False
    assert not _traces(binary_figure)
    assert legal_compatible is True
    assert {trace.name for trace in _traces(legal_figure)} == {"Spain", "France"}
    assert legal_default_compatible is True
    assert {trace.name for trace in _traces(legal_default_figure)} == {"Spain", "France"}


def test_fra_result_keeps_country_without_selected_answer_as_missing(monkeypatch) -> None:
    document = {
        "code": "COMPARE_MISSING",
        "category": "Discrimination",
        "question": "Example",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 60,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "No",
                "percentage": 70,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
        ],
    }
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_fra_indicator_answers",
        lambda _code: document,
    )

    result = get_fra_statistics(
        FraStatisticsQuery(
            question_code="COMPARE_MISSING",
            answer="Yes",
            year=2023,
        )
    )
    rows = {row["iso"]: row for row in result["ranking"]}

    assert rows["ES"]["value"] == 60.0
    assert rows["ES"]["position"] == 1
    assert rows["PT"]["value"] is None
    assert rows["PT"]["position"] is None


def test_ilga_result_keeps_country_without_selected_criterion_as_missing(monkeypatch) -> None:
    document = {
        "year": 2026,
        "countries": [
            {
                "country": "Spain",
                "country_code": "ES",
                "ranking": 75,
                "criteria": [
                    {
                        "category": "Family",
                        "indicator": "Marriage equality",
                        "value": 1,
                        "weight": 1,
                    }
                ],
            },
            {
                "country": "France",
                "country_code": "FR",
                "ranking": 70,
                "criteria": [],
            },
        ],
    }
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_ilga_document_by_year",
        lambda _year: document,
    )

    result = get_ilga_statistics(
        IlgaStatisticsQuery(
            year=2026,
            category="Family",
            criterion="Marriage equality",
        ),
        include_history=False,
    )
    rows = {row["iso"]: row for row in result["ranking"]}

    assert rows["ES"]["value"] == 100.0
    assert rows["FR"]["value"] is None


def test_comparison_table_uses_shared_selection_and_marks_missing_data() -> None:
    result = {
        "source": "FRA",
        "year": 2023,
        "indicator": "Example question",
        "answer": "Yes",
        "ranking": [
            {
                "country": "Spain",
                "iso": "ES",
                "value": 60.0,
                "position": 1,
                "difference": 10.0,
                "percentage_difference": 20.0,
            },
            {
                "country": "Portugal",
                "iso": "PT",
                "value": None,
                "position": None,
                "difference": None,
                "percentage_difference": None,
            },
        ],
    }

    rows = _table_rows(result, ["PT", "ES"])

    assert [row["country"] for row in rows] == ["Portugal", "Spain"]
    assert rows[0]["status"] == "Sin datos"
    assert rows[0]["value"] is None
    assert rows[1]["indicator"] == "Example question · Yes"


def test_country_selection_never_triggers_the_data_query_callback() -> None:
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = html.Div()
    register_statistics_callbacks(app)

    data_callback = app.callback_map["stats-data-store.data"]
    input_ids = {item["id"] for item in data_callback["inputs"]}

    assert "stats-selected-countries" not in input_ids
    assert "stats-map-graph" not in input_ids
