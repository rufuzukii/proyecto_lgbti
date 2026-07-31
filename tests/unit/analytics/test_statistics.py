from typing import Any, cast

import pandas as pd
import pytest
from flask import Flask

import app.analytics.repository as analytics_repository
from app.analytics import statistics_service
from app.analytics.percentage_display import normalize_percentage_values
from app.analytics.statistics_charts import (
    COUNTRY_COLORS,
    EUROPE_PERCENTAGE_COLORSCALE,
    NO_RESPONSE_COLOR,
    YES_RESPONSE_COLOR,
    _legal_hover_data,
    build_europe_choropleth,
    build_europe_distribution_chart,
    build_fra_response_comparison_chart,
    build_ilga_criteria_heatmap,
    normalize_percentage,
    summarize_response_comparison,
)
from app.analytics.statistics_geodata import merge_statistics_with_geodata
from app.analytics.statistics_models import (
    FRA_FILTER_GROUP_A,
    FRA_FILTER_GROUP_B,
    FraStatisticsQuery,
    IlgaStatisticsQuery,
    validate_fra_query,
)
from app.analytics.statistics_normalizers import (
    normalize_country_code,
    normalize_filter_value,
    repair_text_encoding,
)
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
from app.cache import cache, init_cache
from app.dash.pages.statistics import (
    DATA_TYPE_OPTIONS,
    _category_options,
    _control_group,
    _controls,
    _detail_summary,
    _effective_query_mode,
    _fra_controls_are_ready,
    _fra_segmentation_card_class,
    _has_valid_fra_selection,
    _methodology_text,
    _segmentation_catalog_options,
    build_statistics_layout,
)


def _trace(figure: Any, index: int = 0) -> Any:
    return figure.data[index]


def _traces(figure: Any) -> list[Any]:
    return list(figure.data)


def _layout(figure: Any) -> Any:
    return figure.layout


def test_distribution_chart_highlights_selected_country_without_invalid_box_colors() -> None:
    figure = build_europe_distribution_chart(
        [
            {"country": "Spain", "iso": "ES", "value": 63.0},
            {"country": "France", "iso": "FR", "value": 58.0},
        ],
        ["ES"],
    )

    traces = _traces(figure)
    assert [trace.type for trace in traces] == ["histogram", "box", "scatter", "scatter"]
    assert list(traces[2].text) == ["Spain", "France"]
    assert list(traces[3].text) == ["Spain"]


@pytest.fixture(autouse=True)
def _isolate_statistics_cache():
    previous_app = getattr(cache, "app", None)
    if previous_app is not None:
        cache.clear()
    try:
        yield
    finally:
        if getattr(cache, "app", None) is not None:
            cache.clear()
        cast(Any, cache).app = previous_app


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


def test_legal_source_hides_sociodemographic_segmentation() -> None:
    fra_classes = _fra_segmentation_card_class("fra").split()
    legal_classes = _fra_segmentation_card_class("ilga").split()

    assert "stats-segmentation-card" in fra_classes
    assert "is-hidden" not in fra_classes
    assert "stats-segmentation-card" in legal_classes
    assert "is-hidden" in legal_classes


def test_statistics_category_options_exclude_hidden_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_fra_categories_are_loaded_from_mongo_without_postgres(monkeypatch) -> None:
    class FakeCollection:
        def distinct(self, field, query):
            assert field == "category"
            assert query == {"code": {"$exists": True, "$ne": ""}}
            return ["Everyday life", "Discrimination", "", None, "Discrimination"]

    monkeypatch.setattr(analytics_repository, "_mongo_collection", lambda _name: FakeCollection())

    categories = analytics_repository.get_fra_categories.uncached()

    assert categories == ["Discrimination", "Everyday life"]


def test_statistics_fra_selectors_start_empty() -> None:
    controls = _controls(
        [{"label": "2024", "value": 2024}],
        2024,
        [{"label": "Discrimination", "value": "Discrimination"}],
    )

    category = _component_by_id(controls, "stats-category-select")
    indicator = _component_by_id(controls, "fra-indicator-select")

    category_props = category.to_plotly_json()["props"]
    indicator_props = indicator.to_plotly_json()["props"]
    assert category_props["value"] is None
    assert category_props["placeholder"] == "Selecciona una categoría"
    assert indicator_props["value"] is None
    assert indicator_props["placeholder"] == "Selecciona primero una categoría"
    assert indicator_props["disabled"] is True
    assert not _has_valid_fra_selection(None, None)
    assert not _has_valid_fra_selection("Discrimination", None)
    assert _has_valid_fra_selection("Discrimination", "D1")
    payload = {"code": "D1", "category": "Discrimination"}
    assert _fra_controls_are_ready(
        "Discrimination", "D1", payload, "Yes", "All", "All", "All", "All"
    )
    assert not _fra_controls_are_ready(
        "Everyday life", "D1", payload, "Yes", "All", "All", "All", "All"
    )
    assert not _fra_controls_are_ready(
        "Discrimination", "D2", payload, "Yes", "All", "All", "All", "All"
    )
    assert not _fra_controls_are_ready(
        "Discrimination", "D1", payload, None, "All", "All", "All", "All"
    )


def test_statistics_separates_demographic_and_identity_filters() -> None:
    controls = _controls(
        [{"label": "2024", "value": 2024}],
        2024,
        [{"label": "Discrimination", "value": "Discrimination"}],
    )

    demographic_type = _component_by_id(controls, "fra-demographic-type")
    demographic_value = _component_by_id(controls, "fra-demographic-value")
    identity_type = _component_by_id(controls, "fra-identity-type")
    identity_value = _component_by_id(controls, "fra-identity-value")

    assert demographic_type is not None
    assert demographic_value is not None
    assert identity_type is not None
    assert identity_value is not None
    assert demographic_type.to_plotly_json()["props"]["value"] is None
    assert demographic_value.to_plotly_json()["props"]["value"] is None
    assert identity_type.to_plotly_json()["props"]["value"] is None
    assert identity_value.to_plotly_json()["props"]["value"] is None

    demographic_options = demographic_type.to_plotly_json()["props"]["options"]
    identity_options = identity_type.to_plotly_json()["props"]["options"]
    assert [option["value"] for option in demographic_options] == list(FRA_FILTER_GROUP_A)
    assert [option["value"] for option in identity_options] == list(FRA_FILTER_GROUP_B)
    assert all(option["disabled"] for option in demographic_options)
    assert all(option["disabled"] for option in identity_options)


def test_fra_segmentation_catalog_keeps_missing_options_disabled() -> None:
    options = _segmentation_catalog_options(
        FRA_FILTER_GROUP_A,
        [{"label": "All", "value": "All"}, {"label": "Age", "value": "Age"}],
    )

    by_value = {option["value"]: option for option in options}
    assert not by_value["All"]["disabled"]
    assert not by_value["Age"]["disabled"]
    assert by_value["Education"]["disabled"]
    assert by_value["Employment status"]["disabled"]
    age_label = by_value["Age"]["label"].to_plotly_json()["props"]
    assert age_label["children"] == "Edad"
    assert age_label["data-i18n-en"] == "Age"


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


def test_fra_dataframe_preserves_missing_percentage_rows_and_warns_invalid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document = {
        "code": "D1",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": None,
                "filters": [],
            },
            {"country": "Portugal", "country_code": "PT", "answer": "Yes", "filters": []},
            {
                "country": "France",
                "country_code": "FR",
                "answer": "Yes",
                "percentage": "not-a-number",
                "filters": [],
            },
        ],
    }

    dataframe = fra_document_to_dataframe(document)

    assert dataframe["country"].tolist() == ["Spain", "Portugal", "France"]
    assert dataframe["percentage"].isna().tolist() == [True, True, True]
    warnings = [
        record for record in caplog.records if "invalid_percentage_values" in record.message
    ]
    assert len(warnings) == 1
    assert "count=1" in warnings[0].message
    assert "'not-a-number'" in warnings[0].message
    assert "indicator='D1'" in warnings[0].message
    assert "countries=['ES', 'FR', 'PT']" in warnings[0].message


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
    assert (
        next(option for option in filter_b_options if option["value"] == "All")["disabled"] is True
    )


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (42, 42.0),
        (42.5, 42.5),
        ("42.5", 42.5),
        ("42,5", 42.5),
        ("42.5%", 42.5),
        (" 42,5 % ", 42.5),
        (0.42, 0.42),
        (None, None),
        ("", None),
        ("N/A", None),
        ("NA", None),
        ("null", None),
        (float("nan"), None),
        (float("inf"), None),
        (-1, None),
        (101, None),
        ({}, None),
        ([], None),
        (True, None),
    ],
)
def test_normalize_percentage_handles_supported_and_invalid_values(
    value: object, expected: float | None
) -> None:
    assert normalize_percentage(value) == expected


def test_percentage_batch_logs_invalid_values_once_and_ignores_missing_markers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    values = [None, "", "N/A", "NA", "null", float("nan"), {}, {}, "bad"]

    normalized = normalize_percentage_values(
        values,
        logger=statistics_service.logger,
        context={"indicator": "D1", "year": 2024},
    )

    assert normalized == [None] * len(values)
    warnings = [
        record for record in caplog.records if "invalid_percentage_values" in record.message
    ]
    assert len(warnings) == 1
    assert "count=3" in warnings[0].message
    assert "indicator='D1'" in warnings[0].message
    assert "year=2024" in warnings[0].message


def test_europe_choropleth_uses_percentage_values_with_a_uniform_blue_scale() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": 63},
            {"country": "Portugal", "iso": "PT", "value": 37.0},
        ],
        source="FRA",
    )
    trace = _trace(figure, 0)

    assert trace.locationmode == "ISO-3"
    assert list(trace.locations) == ["ESP", "PRT"]
    assert list(trace.z) == [63.0, 37.0]
    assert trace.zmin == 0
    assert trace.zmax == 100
    assert trace.colorscale == tuple(
        (position, color) for position, color in EUROPE_PERCENTAGE_COLORSCALE
    )
    assert trace.customdata.tolist() == [["ES", "Valor", "63%"], ["PT", "Valor", "37%"]]
    assert (
        trace.hovertemplate == "<b>%{text}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>"
    )


def test_europe_choropleth_preserves_real_decimals_and_numeric_strings() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": "63.5"},
            {"country": "Portugal", "iso": "PT", "value": "36,5%"},
        ],
        source="FRA",
    )
    trace = _trace(figure, 0)

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
    valid_trace = _trace(figure, 0)
    missing_trace = _trace(figure, 1)

    assert list(valid_trace.z) == [10.0, 30.0]
    assert valid_trace.customdata.tolist() == [["ES", "Valor", "10%"], ["PT", "Valor", "30%"]]
    assert list(missing_trace.locations) == ["FRA"]
    assert missing_trace.customdata.tolist() == [["FR", "No hay suficiente información"]]


def test_europe_choropleth_marks_null_missing_absent_and_invalid_values_grey(
    caplog: pytest.LogCaptureFixture,
) -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": None},
            {"country": "Portugal", "iso": "PT"},
            {"country": "France", "iso": "FR", "value": "not-a-number"},
        ],
        source="FRA",
    )
    missing_trace = _trace(figure, 0)

    assert list(missing_trace.locations) == ["ESP", "PRT", "FRA"]
    assert missing_trace.colorscale == ((0.0, "#9ca3af"), (1.0, "#9ca3af"))
    assert missing_trace.customdata.tolist() == [
        ["ES", "No hay suficiente información"],
        ["PT", "No hay suficiente información"],
        ["FR", "No hay suficiente información"],
    ]
    assert caplog.text.count("invalid_percentage_values") == 1
    assert "count=1" in caplog.text
    assert "value='not-a-number'" not in caplog.text
    assert "'not-a-number'" in caplog.text


def test_europe_choropleth_translates_value_and_missing_hover_texts() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": 63},
            {"country": "Portugal", "iso": "PT", "value": None},
        ],
        source="ILGA-Europe",
        language="en",
    )

    assert _trace(figure, 0).customdata.tolist() == [["ES", "Value", "63%"]]
    assert _trace(figure, 1).customdata.tolist() == [["PT", "There is not enough information"]]


def test_ilga_filter_applies_countries_even_when_mode_is_all() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "country": "Spain",
                "iso": "ES",
                "category": "Ranking total",
                "criterion": "",
                "ranking": 77.0,
            },
            {
                "country": "Portugal",
                "iso": "PT",
                "category": "Ranking total",
                "criterion": "",
                "ranking": 68.0,
            },
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
            {
                "country": "Spain",
                "iso": "ES",
                "answer": "Yes",
                "percentage": 20.0,
                "filters": {"All": "All"},
                "year": 2023,
            },
            {
                "country": "Spain",
                "iso": "ES",
                "answer": "No",
                "percentage": 80.0,
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
            {
                "country": "Portugal",
                "iso": "PT",
                "answer": "No",
                "percentage": 70.0,
                "filters": {"All": "All"},
                "year": 2023,
            },
        ]
    )
    query = FraStatisticsQuery(countries=["ES"], answer="Yes", year=2023)

    filtered = filter_fra_detail_dataframe(dataframe, query)

    assert filtered["country"].tolist() == ["Spain", "Spain", "Portugal", "Portugal"]
    assert filtered["answer"].tolist() == ["Yes", "No", "Yes", "No"]


def test_get_fra_statistics_exposes_detail_data_without_country_or_answer_filter(
    monkeypatch,
) -> None:
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
                "percentage": 20.0,
                "date": "2023",
                "filters": [],
            },
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "No",
                "percentage": 80.0,
                "date": "2023",
                "filters": [],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "Yes",
                "percentage": 30.0,
                "date": "2023",
                "filters": [],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "No",
                "percentage": 70.0,
                "date": "2023",
                "filters": [],
            },
        ],
    }
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_fra_indicator_answers", lambda _code: document
    )

    result = get_fra_statistics(
        FraStatisticsQuery(question_code="D1", countries=["ES"], answer="Yes", year=2023)
    )

    assert result["status"] == "ok"
    assert [row["country"] for row in result["ranking"]] == ["Spain"]
    assert {(row["country"], row["answer"]) for row in result["detail_data"]} == {
        ("Spain", "Yes"),
        ("Spain", "No"),
        ("Portugal", "Yes"),
        ("Portugal", "No"),
    }
    assert {row["iso"] for row in result["country_universe"]} == {"ES", "PT"}


def test_get_fra_statistics_uses_exact_all_filter_rows_for_map_ranking(monkeypatch) -> None:
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
                "percentage": 63.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 3.0,
                "date": "2023",
                "filters": [
                    {"type": "Age", "value": "18-24"},
                    {"type": "Sexual Orientation", "value": "Gay"},
                ],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "Yes",
                "percentage": 37.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "Yes",
                "percentage": 4.0,
                "date": "2023",
                "filters": [
                    {"type": "Age", "value": "18-24"},
                    {"type": "Sexual Orientation", "value": "Gay"},
                ],
            },
        ],
    }
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_fra_indicator_answers", lambda _code: document
    )

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1", answer="Yes", year=2023))

    assert result["status"] == "ok"
    assert [(row["country"], row["value"]) for row in result["ranking"]] == [
        ("Spain", 63.0),
        ("Portugal", 37.0),
    ]


def test_get_fra_statistics_uses_default_answer_instead_of_averaging_all_answers(
    monkeypatch,
) -> None:
    document = {
        "code": "D1",
        "category": "Discrimination",
        "specific_category": "Work",
        "question": "Felt discriminated",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "No",
                "percentage": 60.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 40.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "No",
                "percentage": 70.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "Yes",
                "percentage": 30.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
        ],
    }
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_fra_indicator_answers", lambda _code: document
    )

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
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "No",
                "percentage": 63.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "No",
                "percentage": 62.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 14.0,
                "date": "2023",
                "filters": [{"type": "Sexual Orientation", "value": "Asexual"}],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "Yes",
                "percentage": 10.0,
                "date": "2023",
                "filters": [{"type": "Sexual Orientation", "value": "Asexual"}],
            },
        ],
    }
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_fra_indicator_answers", lambda _code: document
    )

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1", answer="Yes"))

    assert result["status"] == "ok"
    assert [(row["country"], row["value"]) for row in result["ranking"]] == [
        ("Spain", 14.0),
        ("Portugal", 10.0),
    ]
    assert {(row["country"], row["answer"]) for row in result["detail_data"]} == {
        ("Spain", "Yes"),
        ("Portugal", "Yes"),
        ("Spain", "No"),
        ("Portugal", "No"),
    }


def test_response_details_compare_all_answers_when_no_is_selected(monkeypatch) -> None:
    document = {
        "code": "D1_8",
        "category": "Discrimination",
        "specific_category": "Discrimination in areas of life",
        "question": "Felt discriminated in the 12 months before the survey in any of 8 areas of life",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "No",
                "percentage": 63.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 37.0,
                "date": "2023",
                "filters": [{"type": "Sexual Orientation", "value": "All"}],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "No",
                "percentage": 70.0,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Portugal",
                "country_code": "PT",
                "answer": "Yes",
                "percentage": 30.0,
                "date": "2023",
                "filters": [{"type": "Sexual Orientation", "value": "All"}],
            },
        ],
    }
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_fra_indicator_answers", lambda _code: document
    )

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1_8", answer="No", year=2023))

    assert result["status"] == "ok"
    assert {row["answer"] for row in result["detail_data"]} == {"Yes", "No"}
    assert "response_ranking" not in result
    assert "segmentation_data" not in result
    figure = build_fra_response_comparison_chart(result["detail_data"])
    assert {trace.name for trace in _traces(figure)} == {"Yes", "No"}


def test_fra_controls_dataframe_and_query_results_are_reused_from_server_cache(monkeypatch) -> None:
    document = {
        "code": "CACHE_1",
        "category": "Discrimination",
        "specific_category": "Everyday life",
        "question": "Example question",
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
                "country": "Spain",
                "country_code": "ES",
                "answer": "No",
                "percentage": 40,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
        ],
    }
    calls = 0

    def load_document(_code):
        nonlocal calls
        calls += 1
        return document

    monkeypatch.setattr(statistics_service, "get_fra_indicator_answers", load_document)
    app = Flask("statistics-cache-test")
    init_cache(app)
    with app.app_context():
        cache.clear()
        first_controls = statistics_service.get_fra_control_payload("CACHE_1")
        second_controls = statistics_service.get_fra_control_payload("CACHE_1")
        assert first_controls == second_controls
        assert first_controls["category"] == "Discrimination"
        assert calls == 1

        cache.clear()
        calls = 0
        yes_query = FraStatisticsQuery(question_code="CACHE_1", answer="Yes", year=2023)
        first_result = get_fra_statistics(yes_query)
        second_result = get_fra_statistics(yes_query)
        no_result = get_fra_statistics(
            FraStatisticsQuery(question_code="CACHE_1", answer="No", year=2023)
        )
        first_result["ranking"] = []
        cached_result = get_fra_statistics(yes_query)
        cache.clear()

    assert second_result["status"] == "ok"
    assert no_result["status"] == "ok"
    assert cached_result["ranking"] != []
    assert calls == 1


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

    assert _layout(figure).barmode == "stack"
    assert len(_traces(figure)) == 3
    assert {trace.name for trace in _traces(figure)} == {"Yes", "No", "Don't know"}
    colors = {trace.name: trace.marker.color for trace in _traces(figure)}
    assert colors["Yes"] == YES_RESPONSE_COLOR
    assert colors["No"] == NO_RESPONSE_COLOR
    assert colors["Don't know"] not in {YES_RESPONSE_COLOR, NO_RESPONSE_COLOR}
    assert all(not trace.marker.pattern.shape for trace in _traces(figure))
    assert summary["countries"] == 2
    assert summary["responses"] == 3
    assert len(summary["distribution"]) == 3
    assert any(annotation.text == "Seleccionado" for annotation in _layout(figure).annotations)


def test_fra_response_comparison_rejects_out_of_range_values_without_zero_bars(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 140.0},
        {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 35.0},
        {"country": "Spain", "iso": "ES", "answer": "Don't know", "percentage": -5.0},
        {"country": "Portugal", "iso": "PT", "answer": "Yes", "percentage": 0.0},
        {"country": "Portugal", "iso": "PT", "answer": "No", "percentage": 0.0},
        {"country": "Portugal", "iso": "PT", "answer": "Don't know", "percentage": 0.0},
    ]

    figure = build_fra_response_comparison_chart(rows)

    for trace in _traces(figure):
        assert all(0 <= value <= 100 for value in trace.x)
    missing_trace = next(
        trace for trace in _traces(figure) if trace.name == "No hay suficiente información"
    )
    assert set(missing_trace.y) == {"Spain", "Portugal"}
    assert all(
        "Spain" not in trace.y
        for trace in _traces(figure)
        if trace.name != "No hay suficiente información"
    )
    assert caplog.text.count("invalid_percentage_values") == 1
    assert "count=2" in caplog.text


def test_fra_response_comparison_keeps_original_decimals_when_country_total_is_100() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 63.5},
        {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 36.5},
    ]

    figure = build_fra_response_comparison_chart(rows, language="en")

    assert [trace.x[0] for trace in _traces(figure)] == [36.5, 63.5]
    assert [trace.customdata[0][1:] for trace in _traces(figure)] == [
        ["No", "36.5%", "", ""],
        ["Yes", "63.5%", "", ""],
    ]
    assert [trace.marker.color for trace in _traces(figure)] == [
        NO_RESPONSE_COLOR,
        YES_RESPONSE_COLOR,
    ]


def test_fra_response_comparison_numeric_chart_shows_response_color_legend() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 14.0},
        {"country": "Portugal", "iso": "PT", "answer": "Yes", "percentage": 10.0},
    ]

    figure = build_fra_response_comparison_chart(rows)

    assert _layout(figure).showlegend is True
    assert _layout(figure).legend.title.text == "Respuesta"
    assert _trace(figure, 0).showlegend is True
    assert _trace(figure, 0).name == "Yes"
    assert _trace(figure, 0).marker.color == YES_RESPONSE_COLOR


def test_fra_response_comparison_marks_country_without_numeric_information_grey() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 60.0},
        {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 40.0},
        {"country": "Portugal", "iso": "PT", "answer": "Yes", "percentage": None},
        {"country": "Portugal", "iso": "PT", "answer": "No", "percentage": None},
    ]

    figure = build_fra_response_comparison_chart(rows)
    missing_trace = next(
        trace for trace in _traces(figure) if trace.name == "No hay suficiente información"
    )

    assert list(missing_trace.y) == ["Portugal"]
    assert list(missing_trace.x) == [100]
    assert missing_trace.marker.color == "#9ca3af"
    assert missing_trace.customdata == (["PT", "No hay suficiente información", "", ""],)


def test_fra_response_comparison_marks_entire_country_grey_when_one_answer_is_missing() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 60.0},
        {"country": "Spain", "iso": "ES", "answer": "No", "percentage": 40.0},
        {"country": "Albania", "iso": "AL", "answer": "No", "percentage": 70.0},
        {"country": "Albania", "iso": "AL", "answer": "Yes", "percentage": None},
    ]

    figure = build_fra_response_comparison_chart(rows)
    summary = summarize_response_comparison(rows)
    missing_trace = next(
        trace for trace in _traces(figure) if trace.name == "No hay suficiente información"
    )
    response_traces = [
        trace for trace in _traces(figure) if trace.name != "No hay suficiente información"
    ]

    assert all("Albania" not in list(trace.y) for trace in response_traces)
    assert list(missing_trace.y) == ["Albania"]
    assert list(missing_trace.x) == [100]
    assert missing_trace.marker.color == "#9ca3af"
    assert next(iter(_layout(figure).yaxis.categoryarray)) == "Albania"
    assert {item["label"]: item["value"] for item in summary["distribution"]} == {
        "Yes": 60.0,
        "No": 40.0,
    }


def test_fra_response_comparison_marks_all_missing_numeric_countries_grey_in_english() -> None:
    figure = build_fra_response_comparison_chart(
        [
            {"country": "Portugal", "iso": "PT", "answer": "Yes", "percentage": None},
        ],
        language="en",
    )

    trace = _trace(figure)
    assert trace.name == "There is not enough information"
    assert trace.marker.color == "#9ca3af"
    assert list(trace.y) == ["Portugal"]


def test_fra_response_comparison_keeps_all_database_countries_when_map_selects_one() -> None:
    rows = [
        {
            "country": f"Country {index:02d}",
            "iso": f"X{index:02d}",
            "answer": "Yes",
            "percentage": None if index == 26 else float(index + 1),
            "year": 2024,
            "source": "FRA",
        }
        for index in range(27)
    ]

    figure = build_fra_response_comparison_chart(rows, selected_countries=["X00"])
    rendered_countries = {
        str(country)
        for trace in _traces(figure)
        for country in trace.y
    }

    assert rendered_countries == {f"Country {index:02d}" for index in range(27)}
    assert _layout(figure).height == 946
    assert _layout(figure).paper_bgcolor == "rgba(0,0,0,0)"


def test_fra_response_comparison_adds_all_30_countries_from_indicator_universe() -> None:
    universe = [
        {
            "country": f"Country {index:02d}",
            "iso": f"X{index:02d}",
            "year": 2024,
            "source": "FRA",
        }
        for index in range(30)
    ]
    rows = [
        {
            **universe[index],
            "answer": "Yes",
            "percentage": float(index + 1),
        }
        for index in range(24)
    ]

    figure = build_fra_response_comparison_chart(
        rows,
        available_countries=universe,
        selected_countries=["X00"],
    )
    summary = summarize_response_comparison(rows, available_countries=universe)
    rendered_countries = {
        str(country)
        for trace in _traces(figure)
        for country in trace.y
    }
    missing_trace = next(
        trace for trace in _traces(figure) if trace.name == "No hay suficiente información"
    )

    assert rendered_countries == {f"Country {index:02d}" for index in range(30)}
    assert set(missing_trace.y) == {f"Country {index:02d}" for index in range(24, 30)}
    assert summary["countries"] == 30
    assert _layout(figure).height == 1030


def test_fra_response_hover_includes_answer_percentage_year_and_source() -> None:
    figure = build_fra_response_comparison_chart(
        [
            {
                "country": "Spain",
                "iso": "ES",
                "answer": "Yes",
                "percentage": "42,5%",
                "year": 2024,
                "source": "FRA",
            }
        ]
    )
    trace = _trace(figure)

    assert list(trace.customdata[0]) == ["ES", "Yes", "42.5%", 2024, "FRA"]
    assert "Respuesta" in trace.hovertemplate
    assert "Porcentaje" in trace.hovertemplate
    assert "Año" in trace.hovertemplate
    assert "Fuente" in trace.hovertemplate


def test_fra_response_comparison_does_not_average_conflicting_duplicates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    figure = build_fra_response_comparison_chart(
        [
            {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 40},
            {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 60},
        ]
    )

    trace = _trace(figure)
    assert trace.name == "No hay suficiente información"
    assert list(trace.y) == ["Spain"]
    assert "conflicting_percentage_values groups=1" in caplog.text


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
    assert "Respuestas detectadas" not in text_values
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
    trace = _trace(figure, 0)

    assert list(trace.x) == ["Protección constitucional por orientación sexual"]
    assert trace.z[0][0] == 1.0
    assert trace.colorscale == ((0.0, COUNTRY_COLORS["ES"]), (1.0, COUNTRY_COLORS["ES"]))
    assert trace.customdata[0][0][0] == "Protección constitucional por orientación sexual"
    assert "discriminación por orientación sexual" in trace.customdata[0][0][1]
    assert trace.customdata[0][0][3] == "Cumplimiento completo"
    assert "<extra></extra>" in trace.hovertemplate

    english_trace = _trace(build_ilga_criteria_heatmap(rows, language="en"))
    assert list(english_trace.x) == ["Constitutional protection based on sexual orientation"]
    assert (
        english_trace.customdata[0][0][0] == "Constitutional protection based on sexual orientation"
    )
    assert "based on sexual orientation" in english_trace.customdata[0][0][1]


def test_ilga_criteria_heatmap_shows_complete_dynamic_country_universe() -> None:
    universe = [
        {
            "country": f"Country {index:02d}",
            "iso": f"X{index:02d}",
            "ranking": 100 - index,
            "year": 2026,
            "source": "ILGA-Europe",
        }
        for index in range(20)
    ]
    rows = [
        {
            **universe[index],
            "category": "Family",
            "criterion": "Marriage equality",
            "criterion_value": 1,
            "criterion_weight": 1,
        }
        for index in range(18)
    ]

    figure = build_ilga_criteria_heatmap(rows, available_countries=universe)

    assert len(_traces(figure)) == 20
    assert {trace.y[0] for trace in _traces(figure)} == {
        f"Country {index:02d}" for index in range(20)
    }
    missing = [trace for trace in _traces(figure) if trace.z[0][0] is None]
    assert {trace.y[0] for trace in missing} == {"Country 18", "Country 19"}
    assert _layout(figure).height == 750
    assert _layout(figure).plot_bgcolor == "rgba(0,0,0,0)"


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


def test_statistics_layout_keeps_response_details_without_duplicate_panels(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.dash.pages.statistics.assert_analytics_databases_available", lambda: None
    )
    monkeypatch.setattr("app.dash.pages.statistics._year_options", lambda _source: [])
    monkeypatch.setattr("app.dash.pages.statistics._category_options", lambda _source, _year: [])
    monkeypatch.setattr("app.dash.pages.statistics.build_navbar", lambda **_kwargs: "")

    layout = build_statistics_layout()

    assert _component_by_id(layout, "stats-response-detail-graph") is not None
    response_panel = _component_by_id(layout, "stats-response-panel")
    assert response_panel is not None
    response_classes = str(response_panel.to_plotly_json()["props"]["className"]).split()
    assert "stats-panel-wide" in response_classes
    assert "stats-response-panel" in response_classes
    assert _component_by_id(layout, "stats-ranking-graph") is not None
    assert _component_by_id(layout, "stats-country-comparison-graph") is not None
    assert _component_by_id(layout, "stats-radar-graph") is not None
    assert _component_by_id(layout, "stats-filter-analysis-graph") is None


def test_fra_methodology_uses_exact_localized_copy() -> None:
    result = {"methodology": "Texto anterior que no debe mostrarse"}

    assert _methodology_text(result, "FRA", "es") == (
        "FRA refleja respuestas de personas encuestadas. "
        "La puntuación ILGA mide leyes y políticas. "
        "Las fuentes no son directamente equivalentes."
    )
    assert _methodology_text(result, "FRA", "en") == (
        "FRA reflects responses from surveyed people. "
        "The ILGA score measures laws and policies. "
        "The sources are not directly equivalent."
    )


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


def _component_by_id(component, component_id: str):
    if hasattr(component, "id") and component.id == component_id:
        return component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            match = _component_by_id(child, component_id)
            if match is not None:
                return match
    elif children is not None:
        return _component_by_id(children, component_id)
    return None
