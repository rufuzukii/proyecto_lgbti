from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.analytics.statistics_geodata import merge_statistics_with_geodata
from app.analytics.statistics_charts import (
    _legal_hover_data,
    _response_color,
    build_europe_choropleth,
    build_fra_response_comparison_chart,
    build_ilga_criteria_heatmap,
    normalize_percentage,
    summarize_response_comparison,
)
from app.analytics.statistics_models import FraStatisticsQuery, IlgaStatisticsQuery, validate_fra_query
from app.analytics.statistics_normalizers import normalize_country_code, normalize_filter_value, repair_text_encoding
from app.analytics.statistics_service import (
    aggregate_fra_data,
    build_fra_default_filter_types,
    build_fra_filter_type_options,
    build_fra_filter_value_options,
    classify_external_data_error,
    filter_fra_dataframe,
    filter_fra_detail_dataframe,
    filter_ilga_dataframe,
    fra_document_to_dataframe,
    get_fra_statistics,
    ilga_document_to_dataframe,
)
from app.dash.pages.statistics import (
    DATA_TYPE_OPTIONS,
    _category_options,
    _control_group,
    _detail_summary,
    _effective_query_mode,
)


def test_normalizes_country_codes_and_filter_values() -> None:
    assert normalize_country_code("UK") == "GB"
    assert normalize_country_code("", "Czechia") == "CZ"
    assert normalize_country_code("", "Kosovo") == "XK"
    assert normalize_filter_value("Rairly open") == "Fairly open"
    assert normalize_filter_value("Heterosexual/Straighy") == "Heterosexual/Straight"
    assert normalize_filter_value("Not limited al all") == "Not limited at all"


def test_repairs_common_mojibake_from_database_values() -> None:
    assert repair_text_encoding("Espa\u00c3\u00b1a") == "España"
    assert repair_text_encoding("Distribuci\u00c3\u00b3n") == "Distribución"
    assert repair_text_encoding("pa\u00c3\u0192\u00c2\u00adses") == "países"
    assert repair_text_encoding("It\u00e2\u20ac\u2122s quoted") == "It’s quoted"


def test_statistics_data_type_options_keep_internal_source_values() -> None:
    assert [option["value"] for option in DATA_TYPE_OPTIONS] == ["fra", "ilga"]
    labels = [option["label"].to_plotly_json()["props"] for option in DATA_TYPE_OPTIONS]
    assert labels[0]["children"] == "Sociodemográficos"
    assert labels[0]["data-i18n-en"] == "Sociodemographic"
    assert labels[1]["children"] == "Legales"
    assert labels[1]["data-i18n-en"] == "Legal"


def test_statistics_category_options_exclude_hidden_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.dash.pages.statistics.get_fra_categories",
        lambda: ["Discrimination", "Spanish LGBTIQ+ indicators", "Everyday life"],
    )
    monkeypatch.setattr(
        "app.dash.pages.statistics.get_ilga_criteria_categories_by_year",
        lambda _year: ["Equality", "Political Participation", "Family"],
    )

    fra_values = [option["value"] for option in _category_options("fra", 2026)]
    ilga_values = [option["value"] for option in _category_options("ilga", 2026)]

    assert fra_values == ["Discrimination", "Everyday life"]
    assert ilga_values == ["Ranking total", "Equality", "Family"]


def test_fra_query_rejects_two_group_a_filters_represented_as_group_b() -> None:
    query = FraStatisticsQuery(
        filter_a_name="Age",
        filter_a_value="18-24",
        filter_b_name="Education",
        filter_b_value="Tertiary education",
    )

    result = validate_fra_query(query)

    assert not result.ok
    assert "grupo B" in result.message


def test_fra_dataframe_keeps_one_filter_a_and_one_filter_b() -> None:
    document = {
        "code": "D1",
        "category": "Discrimination",
        "specific_category": "Work",
        "question": "Felt discriminated",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 21.0,
                "date": "2023",
                "filters": [
                    {"type": "Age", "value": "18-24"},
                    {"type": "Gender Expression", "value": "Trans women"},
                ],
            }
        ],
    }

    dataframe = fra_document_to_dataframe(document)

    assert dataframe.iloc[0]["filter_a"] == "18-24"
    assert dataframe.iloc[0]["filter_b"] == "Trans women"
    assert dataframe.iloc[0]["year"] == 2023


def test_fra_dataframe_repairs_mojibake_from_source_document() -> None:
    document = {
        "code": "D1",
        "category": "Situaci\u00c3\u00b3n social",
        "specific_category": "Informaci\u00c3\u00b3n",
        "question": "Comparaci\u00c3\u00b3n por pa\u00c3\u00adses",
        "answers": [
            {
                "country": "Espa\u00c3\u00b1a",
                "country_code": "ES",
                "answer": "S\u00c3\u00ad",
                "percentage": 21.0,
                "date": "2023",
                "filters": [{"type": "Age", "value": "18-24"}],
            }
        ],
    }

    dataframe = fra_document_to_dataframe(document)
    row = dataframe.iloc[0]

    assert row["category"] == "Situación social"
    assert row["specific_category"] == "Información"
    assert row["question"] == "Comparación por países"
    assert row["country"] == "España"
    assert row["answer"] == "Sí"


def test_fra_dataframe_accepts_string_percentages() -> None:
    document = {
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": "67,5%",
                "date": "2023",
                "filters": [],
            }
        ],
    }

    dataframe = fra_document_to_dataframe(document)

    assert dataframe.iloc[0]["percentage"] == 67.5


def test_fra_dataframe_preserves_missing_percentage_rows_and_warns_invalid(caplog: pytest.LogCaptureFixture) -> None:
    document = {
        "code": "D1",
        "answers": [
            {"country": "Spain", "country_code": "ES", "answer": "Yes", "percentage": None, "filters": []},
            {"country": "Portugal", "country_code": "PT", "answer": "Yes", "filters": []},
            {"country": "France", "country_code": "FR", "answer": "Yes", "percentage": "not-a-number", "filters": []},
        ],
    }

    dataframe = fra_document_to_dataframe(document)

    assert dataframe["country"].tolist() == ["Spain", "Portugal", "France"]
    assert dataframe["percentage"].isna().tolist() == [True, True, True]
    assert "invalid_percentage_value" in caplog.text


def test_filter_value_options_show_normalized_label_but_keep_raw_value() -> None:
    document = {
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 21.0,
                "filters": [{"type": "Openness about being LGBTIQ", "value": "Rairly open"}],
            }
        ],
    }

    options = build_fra_filter_value_options(document, "Openness about being LGBTIQ+")

    assert options == [{"label": "Fairly open", "value": "Rairly open"}]


def test_fra_default_filters_use_available_scope_when_all_all_is_missing() -> None:
    document = {
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 63,
                "filters": [{"type": "Sexual Orientation", "value": "Gay"}],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "Yes",
                "percentage": 37,
                "filters": [{"type": "Sexual Orientation", "value": "Gay"}],
            },
        ]
    }

    filter_a, filter_b = build_fra_default_filter_types(document)
    filter_b_options = build_fra_filter_type_options(document, "b")

    assert (filter_a, filter_b) == ("All", "Sexual Orientation")
    assert next(option for option in filter_b_options if option["value"] == "All")["disabled"] is True


def test_classifies_fra_no_data_payload_without_exposing_500() -> None:
    payload = {
        "error": ["500 - Internal server error"],
        "message": ["Error in getFilteredIndicatorEnrichedData(req): No data for this query.\n"],
    }

    assert classify_external_data_error(payload) == "empty"


def test_aggregate_fra_data_rejects_summing_percentages() -> None:
    dataframe = pd.DataFrame(
        [
            {"country": "Spain", "percentage": 20.0},
            {"country": "Spain", "percentage": 30.0},
        ]
    )

    with pytest.raises(ValueError, match="cannot_sum_percentages"):
        aggregate_fra_data(dataframe, ["country"], "percentage", "sum")


def test_aggregate_fra_data_computes_mean() -> None:
    dataframe = pd.DataFrame(
        [
            {"country": "Spain", "percentage": 20.0},
            {"country": "Spain", "percentage": 30.0},
        ]
    )

    result = aggregate_fra_data(dataframe, ["country"], "percentage", "mean")

    assert result.iloc[0]["percentage"] == 25.0


def test_effective_query_mode_follows_country_selection() -> None:
    assert _effective_query_mode("all", []) == "all"
    assert _effective_query_mode("all", ["ES"]) == "one"
    assert _effective_query_mode("all", ["ES", "PT"]) == "compare"


def test_normalize_percentage_handles_strings_and_invalid_values() -> None:
    assert normalize_percentage("78%") == 78.0
    assert normalize_percentage("67,5") == 67.5
    assert normalize_percentage(None) is None
    assert normalize_percentage("not-a-number") is None


def test_europe_choropleth_preserves_stored_percentages_when_total_is_100() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": 63},
            {"country": "Portugal", "iso": "PT", "value": 37.0},
        ],
        source="FRA",
    )
    trace = figure.data[0]

    assert trace.locationmode == "ISO-3"
    assert list(trace.locations) == ["ESP", "PRT"]
    assert list(trace.z) == [63.0, 37.0]
    assert trace.customdata.tolist() == [["ES", "Valor", "63%"], ["PT", "Valor", "37%"]]
    assert trace.hovertemplate == "<b>%{text}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>"


def test_europe_choropleth_preserves_real_decimals_and_numeric_strings() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": "63.5"},
            {"country": "Portugal", "iso": "PT", "value": "36,5%"},
        ],
        source="FRA",
    )
    trace = figure.data[0]

    assert list(trace.z) == [63.5, 36.5]
    assert trace.customdata.tolist() == [["ES", "Valor", "63.5%"], ["PT", "Valor", "36.5%"]]


def test_europe_choropleth_preserves_country_percentages_when_total_is_not_100() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": 10},
            {"country": "Portugal", "iso": "PT", "value": 30},
            {"country": "France", "iso": "FR", "value": None},
        ],
        source="FRA",
    )
    valid_trace = figure.data[0]
    missing_trace = figure.data[1]

    assert list(valid_trace.z) == [10.0, 30.0]
    assert valid_trace.customdata.tolist() == [["ES", "Valor", "10%"], ["PT", "Valor", "30%"]]
    assert list(missing_trace.locations) == ["FRA"]
    assert missing_trace.customdata.tolist() == [["FR", "No hay suficiente información"]]


def test_europe_choropleth_marks_null_missing_absent_and_invalid_values_grey(caplog: pytest.LogCaptureFixture) -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": None},
            {"country": "Portugal", "iso": "PT"},
            {"country": "France", "iso": "FR", "value": "not-a-number"},
        ],
        source="FRA",
    )
    missing_trace = figure.data[0]

    assert list(missing_trace.locations) == ["ESP", "PRT", "FRA"]
    assert missing_trace.colorscale == ((0.0, "#9ca3af"), (1.0, "#9ca3af"))
    assert missing_trace.customdata.tolist() == [
        ["ES", "No hay suficiente información"],
        ["PT", "No hay suficiente información"],
        ["FR", "No hay suficiente información"],
    ]
    assert "invalid_percentage_value" in caplog.text


def test_europe_choropleth_translates_value_and_missing_hover_texts() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": 63},
            {"country": "Portugal", "iso": "PT", "value": None},
        ],
        source="ILGA-Europe",
        language="en",
    )

    assert figure.data[0].customdata.tolist() == [["ES", "Value", "63%"]]
    assert figure.data[1].customdata.tolist() == [["PT", "There is not enough information"]]


def test_ilga_filter_applies_countries_even_when_mode_is_all() -> None:
    dataframe = pd.DataFrame(
        [
            {"country": "Spain", "iso": "ES", "category": "Ranking total", "criterion": "", "ranking": 77.0},
            {"country": "Portugal", "iso": "PT", "category": "Ranking total", "criterion": "", "ranking": 68.0},
        ]
    )
    query = IlgaStatisticsQuery(countries=["ES"], mode="all", category="Ranking total")

    filtered = filter_ilga_dataframe(dataframe, query)

    assert filtered["country"].tolist() == ["Spain"]


def test_fra_filter_applies_countries_even_when_mode_is_all() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "country": "Spain",
                "iso": "ES",
                "answer": "Yes",
                "percentage": 20.0,
                "filters": {"All": "All"},
                "year": 2023,
            },
            {
                "country": "Portugal",
                "iso": "PT",
                "answer": "Yes",
                "percentage": 30.0,
                "filters": {"All": "All"},
                "year": 2023,
            },
        ]
    )
    query = FraStatisticsQuery(countries=["PT"], mode="all", answer="Yes")

    filtered = filter_fra_dataframe(dataframe, query)

    assert filtered["country"].tolist() == ["Portugal"]


def test_fra_detail_filter_keeps_all_countries_and_answers() -> None:
    dataframe = pd.DataFrame(
        [
            {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 20.0, "filters": {"All": "All"}, "year": 2023},
            {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 80.0, "filters": {"All": "All"}, "year": 2023},
            {"country": "Portugal", "iso": "PT", "answer": "Yes", "percentage": 30.0, "filters": {"All": "All"}, "year": 2023},
            {"country": "Portugal", "iso": "PT", "answer": "No", "percentage": 70.0, "filters": {"All": "All"}, "year": 2023},
        ]
    )
    query = FraStatisticsQuery(countries=["ES"], answer="Yes", year=2023)

    filtered = filter_fra_detail_dataframe(dataframe, query)

    assert filtered["country"].tolist() == ["Spain", "Spain", "Portugal", "Portugal"]
    assert filtered["answer"].tolist() == ["Yes", "No", "Yes", "No"]


def test_get_fra_statistics_exposes_detail_data_without_country_or_answer_filter(monkeypatch) -> None:
    document = {
        "code": "D1",
        "category": "Discrimination",
        "specific_category": "Work",
        "question": "Felt discriminated",
        "answers": [
            {"country": "Spain", "country_code": "ES", "answer": "Yes", "percentage": 20.0, "date": "2023", "filters": []},
            {"country": "Spain", "country_code": "ES", "answer": "No", "percentage": 80.0, "date": "2023", "filters": []},
            {"country": "Portugal", "country_code": "PT", "answer": "Yes", "percentage": 30.0, "date": "2023", "filters": []},
            {"country": "Portugal", "country_code": "PT", "answer": "No", "percentage": 70.0, "date": "2023", "filters": []},
        ],
    }
    monkeypatch.setattr("app.analytics.statistics_service.get_fra_indicator_answers", lambda _code: document)

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1", countries=["ES"], answer="Yes", year=2023))

    assert result["status"] == "ok"
    assert [row["country"] for row in result["ranking"]] == ["Spain"]
    assert {(row["country"], row["answer"]) for row in result["detail_data"]} == {
        ("Spain", "Yes"),
        ("Spain", "No"),
        ("Portugal", "Yes"),
        ("Portugal", "No"),
    }


def test_get_fra_statistics_uses_exact_all_filter_rows_for_map_ranking(monkeypatch) -> None:
    document = {
        "code": "D1",
        "category": "Discrimination",
        "specific_category": "Work",
        "question": "Felt discriminated",
        "answers": [
            {"country": "Spain", "country_code": "ES", "answer": "Yes", "percentage": 63.0, "date": "2023", "filters": [{"type": "All", "value": "All"}]},
            {"country": "Spain", "country_code": "ES", "answer": "Yes", "percentage": 3.0, "date": "2023", "filters": [{"type": "Age", "value": "18-24"}, {"type": "Sexual Orientation", "value": "Gay"}]},
            {"country": "Portugal", "country_code": "PT", "answer": "Yes", "percentage": 37.0, "date": "2023", "filters": [{"type": "All", "value": "All"}]},
            {"country": "Portugal", "country_code": "PT", "answer": "Yes", "percentage": 4.0, "date": "2023", "filters": [{"type": "Age", "value": "18-24"}, {"type": "Sexual Orientation", "value": "Gay"}]},
        ],
    }
    monkeypatch.setattr("app.analytics.statistics_service.get_fra_indicator_answers", lambda _code: document)

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1", answer="Yes", year=2023))

    assert result["status"] == "ok"
    assert [(row["country"], row["value"]) for row in result["ranking"]] == [
        ("Spain", 63.0),
        ("Portugal", 37.0),
    ]


def test_get_fra_statistics_uses_default_answer_instead_of_averaging_all_answers(monkeypatch) -> None:
    document = {
        "code": "D1",
        "category": "Discrimination",
        "specific_category": "Work",
        "question": "Felt discriminated",
        "answers": [
            {"country": "Spain", "country_code": "ES", "answer": "No", "percentage": 60.0, "date": "2023", "filters": [{"type": "All", "value": "All"}]},
            {"country": "Spain", "country_code": "ES", "answer": "Yes", "percentage": 40.0, "date": "2023", "filters": [{"type": "All", "value": "All"}]},
            {"country": "Portugal", "country_code": "PT", "answer": "No", "percentage": 70.0, "date": "2023", "filters": [{"type": "All", "value": "All"}]},
            {"country": "Portugal", "country_code": "PT", "answer": "Yes", "percentage": 30.0, "date": "2023", "filters": [{"type": "All", "value": "All"}]},
        ],
    }
    monkeypatch.setattr("app.analytics.statistics_service.get_fra_indicator_answers", lambda _code: document)

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1", answer=None, year=2023))

    assert result["status"] == "ok"
    assert [(row["country"], row["value"]) for row in result["ranking"]] == [
        ("Portugal", 70.0),
        ("Spain", 60.0),
    ]


def test_get_fra_statistics_falls_back_to_available_scope_for_selected_answer(monkeypatch) -> None:
    document = {
        "code": "D1",
        "category": "Discrimination",
        "specific_category": "Areas of life",
        "question": "Felt discriminated",
        "answers": [
            {"country": "Spain", "country_code": "ES", "answer": "No", "percentage": 63.0, "date": "2023", "filters": [{"type": "All", "value": "All"}]},
            {"country": "Portugal", "country_code": "PT", "answer": "No", "percentage": 62.0, "date": "2023", "filters": [{"type": "All", "value": "All"}]},
            {"country": "Spain", "country_code": "ES", "answer": "Yes", "percentage": 14.0, "date": "2023", "filters": [{"type": "Sexual Orientation", "value": "Asexual"}]},
            {"country": "Portugal", "country_code": "PT", "answer": "Yes", "percentage": 10.0, "date": "2023", "filters": [{"type": "Sexual Orientation", "value": "Asexual"}]},
        ],
    }
    monkeypatch.setattr("app.analytics.statistics_service.get_fra_indicator_answers", lambda _code: document)

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1", answer="Yes"))

    assert result["status"] == "ok"
    assert [(row["country"], row["value"]) for row in result["ranking"]] == [
        ("Spain", 14.0),
        ("Portugal", 10.0),
    ]
    assert {(row["country"], row["answer"]) for row in result["detail_data"]} == {
        ("Spain", "Yes"),
        ("Portugal", "Yes"),
    }


def test_fra_response_comparison_builds_stacked_chart_for_three_answers() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 55.0},
        {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 35.0},
        {"country": "Spain", "iso": "ES", "answer": "Don't know", "percentage": 10.0},
        {"country": "Portugal", "iso": "PT", "answer": "YES", "percentage": 40.0},
        {"country": "Portugal", "iso": "PT", "answer": "No", "percentage": 45.0},
        {"country": "Portugal", "iso": "PT", "answer": "Don't know", "percentage": 15.0},
    ]

    figure = build_fra_response_comparison_chart(rows, selected_countries=["ES"])
    summary = summarize_response_comparison(rows)

    assert figure.layout.barmode == "stack"
    assert len(figure.data) == 3
    assert {trace.name for trace in figure.data} == {"Yes", "No", "Don't know"}
    assert summary["countries"] == 2
    assert summary["responses"] == 3
    assert len(summary["distribution"]) == 3
    assert any(annotation.text == "Seleccionado" for annotation in figure.layout.annotations)


def test_fra_response_comparison_never_displays_normalized_segments_above_100() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 140.0},
        {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 35.0},
        {"country": "Spain", "iso": "ES", "answer": "Don't know", "percentage": -5.0},
        {"country": "Portugal", "iso": "PT", "answer": "Yes", "percentage": 0.0},
        {"country": "Portugal", "iso": "PT", "answer": "No", "percentage": 0.0},
        {"country": "Portugal", "iso": "PT", "answer": "Don't know", "percentage": 0.0},
    ]

    figure = build_fra_response_comparison_chart(rows)

    for trace in figure.data:
        assert all(0 <= value <= 100 for value in trace.x)
    assert all("Porcentaje dentro del país" not in trace.hovertemplate for trace in figure.data)
    assert all("Valor original" not in trace.hovertemplate for trace in figure.data)
    assert all(
        trace.hovertemplate == "<b>%{y}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>"
        for trace in figure.data
    )
    spain_index = list(figure.data[0].y).index("Spain")
    assert sum(trace.x[spain_index] for trace in figure.data) == 100


def test_fra_response_comparison_keeps_original_decimals_when_country_total_is_100() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 63.5},
        {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 36.5},
    ]

    figure = build_fra_response_comparison_chart(rows, language="en")

    assert [trace.x[0] for trace in figure.data] == [36.5, 63.5]
    assert [trace.customdata[0][1:] for trace in figure.data] == [["Value", "36.5%"], ["Value", "63.5%"]]


def test_fra_response_comparison_numeric_chart_shows_response_color_legend() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 14.0},
        {"country": "Portugal", "iso": "PT", "answer": "Yes", "percentage": 10.0},
    ]

    figure = build_fra_response_comparison_chart(rows)

    assert figure.layout.showlegend is True
    assert figure.layout.legend.title.text == "Respuesta"
    assert figure.data[0].showlegend is True
    assert figure.data[0].name == "Yes"


def test_fra_response_comparison_replaces_orange_and_grey_response_colors() -> None:
    assert _response_color("no") == "#c62828"
    assert _response_color("yes") == "#2e7d32"


def test_fra_response_comparison_keeps_distinct_answer_meanings() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 60.0},
        {"country": "Spain", "iso": "ES", "answer": "No answer", "percentage": 5.0},
        {"country": "Spain", "iso": "ES", "answer": "yes", "percentage": 35.0},
    ]

    summary = summarize_response_comparison(rows)

    assert summary["responses"] == 3
    assert {item["label"] for item in summary["distribution"]} == {"No", "No answer", "yes"}


def test_detail_summary_uses_separate_readable_blocks_and_pluralization() -> None:
    component = _detail_summary(
        "FRA",
        [
            {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 100.0},
        ],
    )
    text_values = _component_text(component)

    assert "Países comparados" in text_values
    assert "1" in text_values
    assert "Respuestas detectadas" in text_values
    assert "1 respuesta" in text_values
    assert "Distribución" in text_values
    assert "1 país" in text_values


def test_ilga_dataframe_preserves_partial_criteria_values() -> None:
    document = {
        "year": 2026,
        "countries": [
            {
                "country": "Spain",
                "country_code": "ES",
                "ranking": 77.97,
                "criteria": [
                    {
                        "category": "Equality & non-discrimination",
                        "indicator": "Constitutional protection",
                        "weight": 1.0,
                        "value": 0.05882352941,
                    }
                ],
            }
        ],
    }

    dataframe = ilga_document_to_dataframe(document)
    criterion_row = dataframe[dataframe["criterion"] == "Constitutional protection"].iloc[0]

    assert criterion_row["criterion_value"] == 0.05882352941


def test_ilga_criteria_heatmap_uses_legal_metadata_in_hover() -> None:
    rows = [
        {
            "country": "Spain",
            "iso": "ES",
            "category": "Equality & non-discrimination",
            "criterion": "Constitution (sexual orientation)",
            "criterion_value": 0.05882352941,
            "criterion_weight": 0.05882352941,
        }
    ]
    figure = build_ilga_criteria_heatmap(rows)
    trace = figure.data[0]

    assert list(trace.x) == ["Protección constitucional por orientación sexual"]
    assert trace.z[0][0] == 1.0
    assert trace.customdata[0][0][0] == "Protección constitucional por orientación sexual"
    assert "discriminación por orientación sexual" in trace.customdata[0][0][1]
    assert trace.customdata[0][0][3] == "Cumplimiento completo"
    assert "<extra></extra>" in trace.hovertemplate

    english_trace = build_ilga_criteria_heatmap(rows, language="en").data[0]
    assert list(english_trace.x) == ["Constitutional protection based on sexual orientation"]
    assert english_trace.customdata[0][0][0] == "Constitutional protection based on sexual orientation"
    assert "based on sexual orientation" in english_trace.customdata[0][0][1]


def test_ilga_criteria_hover_data_is_translated_for_required_criteria() -> None:
    examples = [
        (
            "Equality & non-discrimination",
            "Constitution (sexual orientation)",
            "Protección constitucional por orientación sexual",
            "Constitutional protection based on sexual orientation",
        ),
        (
            "Equality & non-discrimination",
            "Employment (sexual orientation)",
            "Protección laboral por orientación sexual",
            "Employment protection based on sexual orientation",
        ),
        ("Family", "Marriage equality", "Matrimonio igualitario", "Marriage equality"),
        ("Family", "Joint adoption", "Adopción conjunta", "Joint adoption"),
        (
            "Hate crime & hate speech",
            "Hate crime law (gender identity)",
            "Delitos de odio por identidad de género",
            "Hate crime law based on gender identity",
        ),
        (
            "Legal gender recognition",
            "Self-determination",
            "Autodeterminación",
            "Self-determination",
        ),
        (
            "Asylum",
            "Asylum law (sex characteristics)",
            "Ley de asilo por características sexuales",
            "Asylum law based on sex characteristics",
        ),
    ]

    for category, source_label, title_es, title_en in examples:
        row = {"category": category, "criterion": source_label}
        hover_es = _legal_hover_data(row, 0.5, 1, language="es")
        hover_en = _legal_hover_data(row, 0.5, 1, language="en")

        assert hover_es[0] == title_es
        assert hover_en[0] == title_en
        assert hover_es[1]
        assert hover_en[1]
        assert hover_es[0] != source_label or source_label == title_es
        assert hover_en[0] != source_label or source_label == title_en
        assert hover_es[3] == "Cumplimiento parcial"
        assert hover_en[3] == "Partially met"


def test_ilga_criteria_hover_fallback_does_not_show_technical_label() -> None:
    hover = _legal_hover_data(
        {"category": "Custom category", "criterion": "Dataset-specific criterion"},
        None,
        1,
        language="en",
    )

    assert hover[0] == "Legal criterion"
    assert hover[0] != "Dataset-specific criterion"
    assert "compliance level" in hover[1]


def test_merge_statistics_with_geodata_flags_missing_geometry_and_duplicates() -> None:
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point

    geodata = gpd.GeoDataFrame(
        [{"iso": "ES", "geometry": Point(0, 0)}],
        geometry="geometry",
        crs="EPSG:4326",
    )
    stats = pd.DataFrame(
        [
            {"iso": "ES", "value": 10.0},
            {"iso": "ES", "value": 11.0},
            {"iso": "XK", "value": 12.0},
        ]
    )

    merged = merge_statistics_with_geodata(geodata, stats, "iso", "iso")

    assert merged.iloc[0]["has_statistics"]
    assert merged.attrs["missing_geometry_iso"] == ["XK"]
    assert merged.attrs["duplicated_statistics_iso"] == ["ES"]


def test_statistics_control_group_omits_empty_id() -> None:
    component = _control_group("Tipo de datos", [])

    assert "id" not in component.to_plotly_json()["props"]


def _component_text(component) -> list[str]:
    if component is None:
        return []
    if isinstance(component, str):
        return [component]
    if isinstance(component, (int, float)):
        return [str(component)]
    if isinstance(component, (list, tuple)):
        values: list[str] = []
        for child in component:
            values.extend(_component_text(child))
        return values
    if hasattr(component, "children"):
        return _component_text(component.children)
    return []
