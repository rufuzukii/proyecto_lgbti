from __future__ import annotations

import math
from typing import Any, cast

from dash import Dash, html

from app.modules.statistics.figures import (
    COUNTRY_COLORS,
    build_combined_scatter,
    build_comparative_ranking_chart,
    build_eu_average_comparison_chart,
    build_experience_legal_radar,
    build_fra_response_comparison_chart,
    build_response_country_comparison_chart,
    country_color,
)
from app.modules.statistics.models import FraStatisticsQuery, IlgaStatisticsQuery
from app.modules.statistics.page import _table_rows, register_statistics_callbacks
from app.modules.statistics.service import get_fra_statistics, get_ilga_statistics


def _trace(figure: Any, index: int = 0) -> Any:
    return figure.data[index]


def _traces(figure: Any) -> list[Any]:
    return list(figure.data)


def _layout(figure: Any) -> Any:
    return figure.layout


def test_country_palette_matches_the_approved_european_colours() -> None:
    assert len(COUNTRY_COLORS) == 50
    assert len(set(COUNTRY_COLORS.values())) == 50
    assert {iso: country_color(iso) for iso in COUNTRY_COLORS} == COUNTRY_COLORS
    assert country_color(country="France") == COUNTRY_COLORS["FR"]
    assert country_color(country="España") == COUNTRY_COLORS["ES"]
    assert country_color("EL") == COUNTRY_COLORS["GR"]
    assert country_color("ESP", "Spain") == COUNTRY_COLORS["ES"]
    assert country_color(math.nan, "Spain") == COUNTRY_COLORS["ES"]
    assert country_color("Spain") == COUNTRY_COLORS["ES"]
    assert country_color("XX", "Unknown") == "#2F6BDE"


def test_ranking_uses_all_europe_without_selection_and_only_selected_with_selection() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "value": 62.0},
        {"country": "France", "iso": "FR", "value": 58.0},
        {"country": "Portugal", "iso": "PT", "value": None},
    ]

    europe = build_comparative_ranking_chart(rows)
    selected = build_comparative_ranking_chart(rows, ["ES", "PT"])

    assert set(_trace(europe).y) == {"España", "Francia", "Portugal"}
    assert set(_trace(selected).y) == {"España", "Portugal"}
    assert "Sin datos" in set(_trace(selected).text)
    selected_values = dict(zip(_trace(selected).y, _trace(selected).x, strict=True))
    assert selected_values == {"Portugal": None, "España": 62.0}
    missing_trace = _traces(selected)[1]
    assert missing_trace.type == "scatter"
    assert list(missing_trace.y) == ["Portugal"]
    assert missing_trace.customdata[0][2] == "Sin datos"


def test_ranking_distinguishes_a_real_zero_from_missing_data() -> None:
    figure = build_comparative_ranking_chart(
        [
            {"country": "Spain", "iso": "ES", "value": 0.0},
            {"country": "Portugal", "iso": "PT", "value": None},
        ]
    )

    values = dict(zip(_trace(figure).y, _trace(figure).x, strict=True))
    assert values["España"] == 0.0
    assert values["Portugal"] is None
    assert list(_traces(figure)[1].y) == ["Portugal"]


def test_ranking_scales_for_all_countries_and_exposes_complete_hover_context() -> None:
    rows = [
        {"country": f"European country {index:02d}", "iso": f"X{index:02d}", "value": index}
        for index in range(1, 47)
    ]

    figure = build_comparative_ranking_chart(
        rows,
        language="en",
        indicator="Equal treatment",
        year=2024,
    )
    trace = _trace(figure)

    assert len(trace.y) == 46
    assert _layout(figure).height == 1500
    assert _layout(figure).autosize is True
    assert _layout(figure).xaxis.automargin is True
    assert _layout(figure).yaxis.automargin is True
    assert "Position" in trace.hovertemplate
    assert "Year" in trace.hovertemplate
    assert "Indicator" in trace.hovertemplate
    assert set(row[3] for row in trace.customdata) == {"2024"}
    assert set(row[4] for row in trace.customdata) == {"Equal treatment"}


def test_response_comparison_groups_dynamic_answers_for_selected_countries() -> None:
    details = [
        {"country": country, "iso": iso, "answer": answer, "percentage": value}
        for country, iso, values in (
            ("Spain", "ES", (60.0, 30.0, 10.0)),
            ("France", "FR", (50.0, 35.0, 15.0)),
        )
        for answer, value in zip(("Yes", "No", "Unknown"), values, strict=True)
    ]

    figure = build_response_country_comparison_chart(details, ["ES"])

    assert _layout(figure).barmode == "group"
    assert {trace.name for trace in _traces(figure)} == {"España"}
    assert list(_trace(figure).x) == ["Yes", "No", "Unknown"]
    assert list(_trace(figure).y) == [60.0, 30.0, 10.0]
    assert _trace(figure).orientation in (None, "v")


def test_response_details_can_limit_rendering_without_changing_selection_semantics() -> None:
    details = [
        {"country": country, "iso": iso, "answer": answer, "percentage": value}
        for country, iso, values in (
            ("Spain", "ES", (60.0, 40.0)),
            ("France", "FR", (55.0, 45.0)),
            ("Germany", "DE", (50.0, 50.0)),
        )
        for answer, value in zip(("Yes", "No"), values, strict=True)
    ]

    figure = build_fra_response_comparison_chart(
        details,
        selected_countries=["ES", "DE"],
        visible_countries=["ES", "DE"],
    )

    assert {country for trace in figure.data for country in (cast(Any, trace).y or [])} == {
        "España",
        "Alemania",
    }


def test_response_comparison_keeps_all_46_countries_without_map_selection(
    caplog,
) -> None:
    details = [
        {
            "country": f"Country {index:02d}",
            "iso": f"X{index:02d}",
            "answer": answer,
            "percentage": None if index in {7, 19} and answer == "No" else float(index),
            "question": "Equal treatment",
            "year": 2024,
            "source": "FRA",
        }
        for index in range(46)
        for answer in ("Yes", "No")
    ]
    caplog.set_level("INFO")

    figure = build_response_country_comparison_chart(
        details,
        [],
        language="en",
        indicator="Legal protection",
        year=2024,
    )

    assert len(_traces(figure)) == 46
    assert {trace.name for trace in _traces(figure)} == {
        f"Country {index:02d}" for index in range(46)
    }
    assert _layout(figure).height == 610
    assert _layout(figure).autosize is True
    assert _layout(figure).xaxis.automargin is True
    assert _layout(figure).yaxis.automargin is True
    assert _layout(figure).showlegend is False
    assert _layout(figure).margin.b == 96
    assert "Indicator" in _trace(figure).hovertemplate
    assert _layout(figure).meta["minimum_width"] > 2000
    assert "countries_rendered=46 responses=2 missing_values=2" in caplog.text


def test_average_chart_renders_selected_countries_and_a_distinct_european_average() -> None:
    figure = build_eu_average_comparison_chart(
        [
            {"country": "Spain", "iso": "ES", "value": 60.0},
            {"country": "France", "iso": "FR", "value": 40.0},
            {"country": "Portugal", "iso": "PT", "value": None},
        ],
        ["ES", "PT"],
    )

    countries_trace, mean_trace, missing_trace = _traces(figure)
    spain = list(countries_trace.y).index("España")
    portugal = list(countries_trace.y).index("Portugal")
    assert countries_trace.customdata[spain].tolist() == [
        "60 %",
        "+10 puntos porcentuales respecto a la media europea",
    ]
    assert countries_trace.customdata[portugal].tolist() == ["Sin datos", "Sin datos"]
    assert "+10 pp" in countries_trace.text[spain]
    values = dict(zip(countries_trace.y, countries_trace.x, strict=True))
    assert values["Portugal"] is None
    assert list(mean_trace.y) == ["Media europea"]
    assert list(mean_trace.x) == [50.0]
    assert mean_trace.marker.pattern.shape == "/"
    assert list(missing_trace.y) == ["Portugal"]


def test_average_chart_supports_multiple_countries_and_keeps_real_zero_in_mean() -> None:
    figure = build_eu_average_comparison_chart(
        [
            {"country": "Spain", "iso": "ES", "value": 60.0},
            {"country": "France", "iso": "FR", "value": 40.0},
            {"country": "Germany", "iso": "DE", "value": 0.0},
            {"country": "Portugal", "iso": "PT", "value": None},
        ],
        ["ES", "FR"],
        "en",
    )

    countries_trace, mean_trace = _traces(figure)
    assert set(countries_trace.y) == {"Spain", "France"}
    assert list(mean_trace.x) == [100 / 3]
    assert any(
        "percentage points compared with the European average" in row[1]
        for row in countries_trace.customdata
    )


def test_combined_scatter_avoids_numpy_warning_for_one_pair() -> None:
    figure = build_combined_scatter(
        [{"country": "Spain", "iso": "ES", "ilga_value": 75.0, "fra_value": 62.0}],
        "en",
    )

    assert "Correlation unavailable" in _layout(figure).annotations[0].text


def test_experience_legal_radar_renders_country_and_european_means() -> None:
    dimensions = ["equality", "education", "health"]
    payload = {
        "fra_year": 2024,
        "ilga_year": 2026,
        "dimensions": [
            {"key": key, "label_es": key.title(), "label_en": key.title()} for key in dimensions
        ],
        "rows": [
            {
                "country": country,
                "iso": iso,
                "dimension": dimension,
                "experience_score": experience,
                "legal_score": legal,
            }
            for country, iso, experience, legal in (
                ("Spain", "ES", 60.0, 80.0),
                ("France", "FR", 55.0, 70.0),
            )
            for dimension in dimensions
        ],
    }

    figure, compatible, metadata, interpretation = build_experience_legal_radar(payload, "ES", "en")

    assert compatible is True
    assert len(_traces(figure)) == 4
    assert {trace.name for trace in _traces(figure)} == {
        "Real-life experience · Spain",
        "Legal protection · Spain",
        "European average · Real-life experience",
        "European average · Legal protection",
    }
    assert "FRA 2024" in metadata
    assert "ILGA-Europe 2026" in metadata
    assert "causal" in interpretation


def test_experience_legal_radar_hides_incomplete_country() -> None:
    payload = {
        "dimensions": [
            {"key": "equality", "label_es": "Igualdad", "label_en": "Equality"},
            {"key": "health", "label_es": "Salud", "label_en": "Health"},
        ],
        "rows": [
            {
                "country": "Spain",
                "iso": "ES",
                "dimension": dimension,
                "experience_score": 60.0,
                "legal_score": 70.0,
            }
            for dimension in ("equality", "health")
        ],
    }

    figure, compatible, _metadata, message = build_experience_legal_radar(payload, "ES")

    assert compatible is False
    assert not _traces(figure)
    assert "No hay suficientes datos comparables" in message


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
        "app.modules.statistics.service.get_fra_indicator_answers",
        lambda *_args, **_kwargs: document,
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
    assert result["metrics"]["mean"] == 60.0


def test_ilga_result_keeps_country_without_selected_criterion_as_missing(monkeypatch) -> None:
    rows = [
        {
            "document_id": "2",
            "year": 2026,
            "country_index": 0,
            "country_name": "Spain",
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
            "document_id": "2",
            "year": 2026,
            "country_index": 1,
            "country_name": "France",
            "country_code": "FR",
            "ranking": 70,
            "criteria": [],
        },
    ]
    monkeypatch.setattr(
        "app.modules.statistics.service.get_ilga_analysis_rows",
        lambda _category, _criterion: rows,
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
    assert rows[0]["country_code"] == "PT"
    assert rows[0]["response"] == "Yes"
    assert rows[0]["source"] == "FRA"
    assert rows[1]["indicator"] == "Example question · Yes"


def test_country_selection_never_triggers_the_data_query_callback() -> None:
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = html.Div()
    register_statistics_callbacks(app)

    data_callback = app.callback_map["stats-data-store.data"]
    input_ids = {item["id"] for item in data_callback["inputs"]}

    assert "stats-selected-countries" not in input_ids
    assert "stats-map-graph" not in input_ids

    download_callback = app.callback_map["stats-summary-table-download.data"]
    assert download_callback["inputs"] == [
        {"id": "stats-table-download-button", "property": "n_clicks"}
    ]
    download_state_ids = {item["id"] for item in download_callback["state"]}
    assert {
        "stats-results-table",
        "stats-data-store",
        "stats-selected-countries",
        "app-language-store",
    }.issubset(download_state_ids)


def test_summary_table_callback_reuses_visible_rows_for_consecutive_downloads() -> None:
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = html.Div()
    register_statistics_callbacks(app)
    callback = app.callback_map["stats-summary-table-download.data"]["callback"].__wrapped__
    visible_rows = [
        {"country": "Portugal", "value": 48.0},
        {"country": "Spain", "value": 63.0},
    ]
    raw_rows = list(reversed(visible_rows))
    columns = [
        {"field": "country", "headerName": "Country"},
        {"field": "value", "headerName": "Value (%)"},
    ]
    result = {
        "ranking": [
            {"country": "Spain", "iso": "ES", "value": 63.0},
            {"country": "Portugal", "iso": "PT", "value": 48.0},
        ],
        "indicator": "Discrimination",
        "answer": "Yes",
        "source": "FRA",
        "year": 2024,
    }

    first = callback(1, visible_rows, raw_rows, columns, result, [], "en")
    second = callback(2, visible_rows, raw_rows, columns, result, [], "en")

    assert first == second
    assert first["content"].index("Portugal;48.0") < first["content"].index("Spain;63.0")
    assert first["filename"].endswith("_europa_2024.csv")
