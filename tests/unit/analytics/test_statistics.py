from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import pytest
from flask import Flask

import app.analytics.repository as analytics_repository
import app.dash.pages.statistics as statistics_page
from app.analytics import statistics_service
from app.analytics.percentage_display import normalize_percentage_values
from app.analytics.statistics_charts import (
    COUNTRY_COLORS,
    EUROPE_MAP_COLORSCALE,
    NO_RESPONSE_COLOR,
    YES_RESPONSE_COLOR,
    _legal_hover_data,
    build_comparative_ranking_chart,
    build_europe_choropleth,
    build_fra_response_comparison_chart,
    build_ilga_criteria_heatmap,
    build_response_country_comparison_chart,
    build_statistics_hover,
    normalize_percentage,
    summarize_response_comparison,
)
from app.analytics.statistics_models import (
    FRA_FILTER_GROUP_A,
    FRA_FILTER_GROUP_B,
    FraStatisticsQuery,
    IlgaStatisticsQuery,
    StatisticsFilters,
    validate_fra_query,
    validate_statistics_filter_combination,
)
from app.analytics.statistics_normalizers import (
    normalize_country_code,
    normalize_filter_value,
    repair_text_encoding,
)
from app.analytics.statistics_service import (
    aggregate_fra_data,
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
    FRA_SURVEY_OPTIONS,
    _category_options,
    _control_group,
    _controls,
    _detail_summary,
    _effective_query_mode,
    _explicit_filter_value,
    _fra_controls_are_ready,
    _fra_segmentation_card_class,
    _has_valid_fra_selection,
    _methodology_text,
    _ranking_graph_style,
    _resolved_ui_filters,
    _response_comparison_component,
    _response_comparison_graph_style,
    _response_detail_graph_style,
    _segmentation_catalog_options,
    _selected_category_value,
    build_statistics_layout,
)


def _trace(figure: Any, index: int = 0) -> Any:
    return figure.data[index]


def _traces(figure: Any) -> list[Any]:
    return list(figure.data)


def _layout(figure: Any) -> Any:
    return figure.layout


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


def test_statistics_survey_options_keep_stable_internal_ids() -> None:
    assert [option["value"] for option in FRA_SURVEY_OPTIONS] == [
        "fra_survey_iii",
        "fra_survey_ii",
    ]
    assert all("Indicator_fra" not in str(option["label"]) for option in FRA_SURVEY_OPTIONS)
    assert [option["label"].children[0].children for option in FRA_SURVEY_OPTIONS] == [
        "Encuesta 2023",
        "Encuesta 2019",
    ]
    assert [
        option["label"].children[0].to_plotly_json()["props"]["data-i18n-en"]
        for option in FRA_SURVEY_OPTIONS
    ] == ["2023 Survey", "2019 Survey"]


def test_statistics_social_data_heading_replaces_the_old_survey_heading() -> None:
    controls = _controls([{"label": "Discrimination", "value": "Discrimination"}])
    control_children = cast(list[Any], controls.children)
    social_data_card = cast(Any, control_children[0])
    heading = social_data_card.children[0]

    assert heading.children == "Datos Sociales"
    assert heading.to_plotly_json()["props"]["data-i18n-en"] == "Social Data"
    survey = _component_by_id(controls, "stats-survey-select")
    assert survey is not None
    assert survey.value == "fra_survey_iii"
    assert len(survey.options) == 2


def test_spanish_ui_localizes_only_fra_category_labels(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.dash.pages.statistics.get_fra_categories",
        lambda _year: ["Education", "Health and mental health"],
    )

    spanish = _category_options(2023, "es")
    english = _category_options(2023, "en")

    assert spanish == [
        {"label": "Educación", "value": "Education"},
        {"label": "Salud y salud mental", "value": "Health and mental health"},
    ]
    assert english == [
        {"label": "Education", "value": "Education"},
        {"label": "Health and mental health", "value": "Health and mental health"},
    ]


def test_fra_segmentation_is_always_available_in_statistics() -> None:
    classes = _fra_segmentation_card_class().split()
    assert "stats-segmentation-card" in classes
    assert "is-hidden" not in classes


def test_statistics_category_options_exclude_hidden_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.dash.pages.statistics.get_fra_categories",
        lambda _year=None: ["Discrimination", "Spanish LGBTIQ+ indicators", "Everyday life"],
    )
    values = [option["value"] for option in _category_options(2023)]
    assert values == ["Discrimination", "Everyday life"]


def test_selected_category_is_preserved_only_when_available() -> None:
    options = [
        {"label": "Ranking total", "value": "Ranking total"},
        {"label": "Equality", "value": "Equality"},
    ]

    assert _selected_category_value(options, None) is None
    assert _selected_category_value(options, "Equality") == "Equality"
    assert _selected_category_value(options, "Family") is None


def test_fra_categories_are_loaded_from_mongo_without_postgres(monkeypatch) -> None:
    class FakeCollection:
        def distinct(self, field, query):
            assert field == "category"
            assert query["code"] == {"$exists": True, "$nin": [None, ""]}
            assert "$elemMatch" in query["answers"]
            assert "Date:" in query["category"]["$nin"]
            return [
                "Everyday life",
                "Discrimination",
                "Date:",
                "‡",
                "",
                None,
                "Discrimination",
            ]

    monkeypatch.setattr(analytics_repository, "_mongo_collection", lambda _name: FakeCollection())

    categories = analytics_repository.get_fra_categories.uncached()

    assert categories == ["Discrimination", "Everyday life"]


def test_statistics_fra_selectors_start_empty() -> None:
    controls = _controls([{"label": "Discrimination", "value": "Discrimination"}])

    category = _component_by_id(controls, "stats-category-select")
    indicator = _component_by_id(controls, "fra-indicator-select")
    answer = _component_by_id(controls, "fra-answer-select")
    segmentation_card = _component_by_id(controls, "stats-fra-segmentation-card")
    demographic_row = _component_by_id(controls, "stats-demographic-segmentation")
    identity_row = _component_by_id(controls, "stats-identity-segmentation")
    assert category is not None
    assert indicator is not None
    assert answer is not None
    assert segmentation_card is not None
    assert demographic_row is not None
    assert identity_row is not None

    category_props = category.to_plotly_json()["props"]
    indicator_props = indicator.to_plotly_json()["props"]
    answer_props = answer.to_plotly_json()["props"]
    assert category_props["value"] is None
    assert category_props["placeholder"] == "Selecciona una categoría"
    assert indicator_props["value"] is None
    assert indicator_props["placeholder"] == "Selecciona primero una categoría"
    assert indicator_props["disabled"] is True
    assert answer_props["disabled"] is True
    assert "is-hidden" not in cast(Any, segmentation_card).className.split()
    assert "is-disabled" in cast(Any, segmentation_card).className.split()
    assert "is-disabled" in cast(Any, demographic_row).className.split()
    assert "is-hidden" not in cast(Any, identity_row).className.split()
    assert "is-disabled" in cast(Any, identity_row).className.split()
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
    controls = _controls([{"label": "Discrimination", "value": "Discrimination"}])

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
    assert by_value["Age"]["label"] == "Edad"
    assert (
        _segmentation_catalog_options(
            FRA_FILTER_GROUP_A,
            [{"label": "All", "value": "All"}, {"label": "Age", "value": "Age"}],
            "en",
        )[1]["label"]
        == "Age"
    )


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
                "survey_year": 2023,
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
                "survey_year": 2023,
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
                "survey_year": 2023,
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


def test_fra_filters_never_replace_missing_all_with_an_available_identity() -> None:
    filters = StatisticsFilters.from_raw(None, None, None, None)

    validation = validate_statistics_filter_combination(
        filters,
        available_values={"All": set(), "Sexual Orientation": {"Asexual"}},
    )

    assert filters == StatisticsFilters()
    assert validation.ok is False


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

    values = dict(zip(trace.locations, trace.z, strict=True))
    assert trace.locationmode is None
    assert trace.featureidkey == "properties.country_code"
    assert len(trace.locations) == 49
    assert values["ES"] == 63.0
    assert values["PT"] == 37.0
    assert values["FR"] == -1.0
    assert trace.zmin == -1
    assert trace.zmax == 100
    assert trace.colorscale == tuple((position, color) for position, color in EUROPE_MAP_COLORSCALE)
    customdata = {row[0]: row[1] for row in trace.customdata.tolist()}
    assert customdata["ES"] == "63%"
    assert customdata["PT"] == "37%"
    assert trace.hovertemplate == "%{hovertext}<extra></extra>"
    assert len(trace.geojson["features"]) == 49
    assert figure.layout.dragmode is False


def test_europe_choropleth_preserves_real_decimals_and_numeric_strings() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": "63.5"},
            {"country": "Portugal", "iso": "PT", "value": "36,5%"},
        ],
        source="FRA",
    )
    trace = _trace(figure, 0)

    values = dict(zip(trace.locations, trace.z, strict=True))
    customdata = {row[0]: row[1] for row in trace.customdata.tolist()}
    assert values["ES"] == 63.5
    assert values["PT"] == 36.5
    assert customdata["ES"] == "63.5%"
    assert customdata["PT"] == "36.5%"


def test_europe_choropleth_preserves_country_percentages_when_total_is_not_100() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": 10},
            {"country": "Portugal", "iso": "PT", "value": 30},
            {"country": "France", "iso": "FR", "value": None},
        ],
        source="FRA",
    )
    trace = _trace(figure, 0)
    values = dict(zip(trace.locations, trace.z, strict=True))
    customdata = {row[0]: row[1] for row in trace.customdata.tolist()}

    assert values["ES"] == 10.0
    assert values["PT"] == 30.0
    assert values["FR"] == -1.0
    assert customdata["ES"] == "10%"
    assert customdata["PT"] == "30%"
    assert customdata["FR"] == ""


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
    trace = _trace(figure, 0)
    values = dict(zip(trace.locations, trace.z, strict=True))
    hover = dict(zip(trace.locations, trace.hovertext, strict=True))

    assert len(values) == 49
    assert values["ES"] == values["PT"] == values["FR"] == -1.0
    assert all(value == -1.0 for value in values.values())
    assert trace.colorscale[0] == (0.0, "#9ca3af")
    assert "No hay suficiente información" in hover["ES"]
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

    trace = _trace(figure, 0)
    hover = dict(zip(trace.locations, trace.hovertext, strict=True))
    assert "Value: 63%" in hover["ES"]
    assert "There is not enough information" in hover["PT"]


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
        "app.analytics.statistics_service.get_fra_indicator_answers",
        lambda *_args, **_kwargs: document,
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
        "app.analytics.statistics_service.get_fra_indicator_answers",
        lambda *_args, **_kwargs: document,
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
        "app.analytics.statistics_service.get_fra_indicator_answers",
        lambda *_args, **_kwargs: document,
    )

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1", answer=None, year=2023))

    assert result["status"] == "ok"
    assert result["answer"] == "Yes"
    assert [(row["country"], row["value"]) for row in result["ranking"]] == [
        ("Spain", 40.0),
        ("Portugal", 30.0),
    ]


def test_education_bathroom_indicator_default_uses_an_answer_published_for_all_all() -> None:
    question = "Problems when going to bathroom and changing rooms at school"
    document = {
        "code": "C9_E",
        "category": "Education",
        "specific_category": "Education",
        "question": question,
        "answers": [
            {
                "country": "Spain",
                "answer": "Always",
                "percentage": 12.0,
                "filters": [{"type": "Gender Expression", "value": "Cisgender men"}],
            },
            *[
                {
                    "country": "Spain",
                    "answer": answer,
                    "percentage": percentage,
                    "filters": [{"type": "All", "value": "All"}],
                }
                for answer, percentage in (("Never", 50.0), ("Often", 20.0), ("Rarely", 18.0))
            ],
        ],
    }

    payload = statistics_service.build_fra_control_payload(document)

    assert payload["global_answers"] == ["Never", "Often", "Rarely"]
    assert payload["default_answer"] == "Often"
    assert payload["default_answer"] != "Always"


def test_get_fra_statistics_does_not_fall_back_to_available_scope(monkeypatch) -> None:
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
        "app.analytics.statistics_service.get_fra_indicator_answers",
        lambda *_args, **_kwargs: document,
    )

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1", answer="Yes"))

    assert result["status"] == "empty"
    assert result["ranking"] == []


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
        "app.analytics.statistics_service.get_fra_indicator_answers",
        lambda *_args, **_kwargs: document,
    )

    result = get_fra_statistics(FraStatisticsQuery(question_code="D1_8", answer="No", year=2023))

    assert result["status"] == "ok"
    assert {row["answer"] for row in result["detail_data"]} == {"Yes", "No"}
    assert "response_ranking" not in result
    assert "segmentation_data" not in result
    figure = build_fra_response_comparison_chart(result["detail_data"])
    assert {trace.name for trace in _traces(figure)} == {"Yes", "No"}


def test_response_details_uses_filtered_dynamic_country_universe_and_canonical_columns(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def answer(
        country: str,
        code: str,
        response: str,
        percentage: float | None,
        filter_type: str,
        filter_value: str,
    ) -> dict[str, Any]:
        return {
            "country": country,
            "country_code": code,
            "answer": response,
            "percentage": percentage,
            "date": "2023",
            "filters": [{"type": filter_type, "value": filter_value}],
        }

    document = {
        "code": "FILTERED_EU",
        "category": "Discrimination",
        "question": "Filtered coverage",
        "answers": [
            answer("Spain", "ESP", "Yes", 60, "Age", "25-39"),
            answer("Spain", "ES", "No", 40, "Age", "25-39"),
            answer("Portugal", "PT", "Yes", None, "Age", "25-39"),
            answer("Portugal", "PT", "No", 70, "Age", "25-39"),
            answer("Germany", "DE", "Yes", 55, "All", "All"),
        ],
    }
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_fra_indicator_answers",
        lambda *_args, **_kwargs: document,
    )
    caplog.set_level("INFO")

    result = get_fra_statistics(
        FraStatisticsQuery(
            question_code="FILTERED_EU",
            answer="Yes",
            year=2023,
            filter_a_name="Age",
            filter_a_value="25-39",
            filter_b_name="All",
            filter_b_value="All",
        )
    )

    assert result["status"] == "ok"
    assert {row["country_code"] for row in result["country_universe"]} == {"ES", "PT"}
    assert all(
        {
            "country_code",
            "country_name",
            "response",
            "percentage",
            "year",
            "indicator_id",
        }.issubset(row)
        for row in result["detail_data"]
    )
    assert result["response_details_diagnostics"]["countries_loaded"] == 2
    assert result["response_details_diagnostics"]["countries_rendered"] == 1
    assert result["response_details_diagnostics"]["countries_without_data"] == 1
    assert (
        "response_details countries_loaded=2 countries_rendered=1 countries_without_data=1"
        in caplog.text
    )


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

    def load_document(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return document

    monkeypatch.setattr(statistics_service, "get_fra_indicator_answers", load_document)
    monkeypatch.setattr(statistics_service, "get_fra_indicator_control_document", load_document)
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
    assert set(missing_trace.y) == {"Espa\u00f1a", "Portugal"}
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
    rendered_countries = {str(country) for trace in _traces(figure) for country in trace.y}

    assert rendered_countries == {f"Country {index:02d}" for index in range(27)}
    assert _layout(figure).height == 1069
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
    rendered_countries = {str(country) for trace in _traces(figure) for country in trace.y}
    missing_trace = next(
        trace for trace in _traces(figure) if trace.name == "No hay suficiente información"
    )

    assert rendered_countries == {f"Country {index:02d}" for index in range(30)}
    assert set(missing_trace.y) == {f"Country {index:02d}" for index in range(24, 30)}
    assert summary["countries"] == 30
    assert _layout(figure).height == 1165


def test_fra_response_comparison_keeps_46_countries_and_graph_height_in_sync() -> None:
    rows = [
        {
            "country_name": f"Country {index:02d}",
            "country_code": f"X{index:02d}",
            "response": "Yes",
            "percentage": float(index % 101),
            "year": 2024,
            "indicator_id": "FULL_EUROPE",
            "question": "Full European coverage",
            "source": "FRA",
        }
        for index in range(46)
    ]

    figure = build_fra_response_comparison_chart(rows, language="en")
    rendered = {str(country) for trace in _traces(figure) for country in trace.y}
    graph_style = _response_detail_graph_style(figure)

    assert len(rendered) == 46
    assert _layout(figure).height == 1677
    assert graph_style["height"] == "1677px"
    assert graph_style["width"] == "100%"
    assert "Indicator" in _trace(figure).hovertemplate


def test_fra_response_comparison_groups_country_variants_by_normalized_iso() -> None:
    figure = build_fra_response_comparison_chart(
        [
            {
                "country": " Czech Republic ",
                "iso": "CZE",
                "answer": "Yes",
                "percentage": 60,
            },
            {
                "country": "czechia",
                "iso": "cz",
                "answer": "No",
                "percentage": 40,
            },
        ],
        language="es",
    )

    assert {country for trace in _traces(figure) for country in trace.y} == {"Rep\u00fablica Checa"}
    assert {trace.customdata[0][0] for trace in _traces(figure)} == {"CZ"}


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
    assert list(trace.y) == ["Espa\u00f1a"]
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
        [
            {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 100.0},
        ],
    )
    text_values = _component_text(component)

    assert isinstance(component, list)
    assert len(component) == 3
    assert "Países comparados" in text_values
    assert "1" in text_values
    assert "Respuestas detectadas" not in text_values
    assert "Distribución" in text_values
    assert "1 país" in text_values


def test_detail_summary_wraps_long_answers_and_calculates_valid_european_mean() -> None:
    long_answer = "I am currently in the process of changing my legal gender"
    component = _detail_summary(
        [
            {"country": "Spain", "iso": "ES", "answer": long_answer, "percentage": 40.0},
            {"country": "France", "iso": "FR", "answer": long_answer, "percentage": 0.0},
        ],
        ranking=[
            {"country": "Spain", "iso": "ES", "value": 40.0},
            {"country": "France", "iso": "FR", "value": 0.0},
            {"country": "Portugal", "iso": "PT", "value": None},
        ],
        selected_response=long_answer,
    )

    rendered = str(component)
    assert "stats-response-distribution-item" in rendered
    assert "stats-response-distribution-value" in rendered
    assert long_answer in rendered
    assert "Media europea" in rendered
    assert "20 %" in rendered


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
    assert trace.z[0][0] == pytest.approx(0.05882352941)
    assert trace.colorscale == ((0.0, COUNTRY_COLORS["ES"]), (1.0, COUNTRY_COLORS["ES"]))
    assert trace.customdata[0][0][0] == "Protección constitucional por orientación sexual"
    assert "discriminación por orientación sexual" in trace.customdata[0][0][1]
    assert trace.customdata[0][0][3] == "Cumplimiento parcial"
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


def test_statistics_control_group_omits_empty_id() -> None:
    component = _control_group("Tipo de datos", [])

    assert "id" not in component.to_plotly_json()["props"]


def test_fra_repository_merges_every_document_for_indicator_in_one_find(monkeypatch) -> None:
    calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    class Collection:
        def find(self, query, projection):
            calls.append((query, projection))
            return [
                {
                    "code": "DUPLICATED",
                    "category": "Category",
                    "question": "Question",
                    "answers": [{"country_code": "ES"}],
                },
                {
                    "code": "DUPLICATED",
                    "category": "Category",
                    "question": "Question",
                    "answers": [{"country_code": "PT"}],
                },
            ]

    monkeypatch.setattr(analytics_repository, "_mongo_collection", lambda _name: Collection())

    document = analytics_repository.get_fra_indicator_answers.__wrapped__(
        " DUPLICATED ", " Category "
    )

    assert calls == [
        (
            {"code": "DUPLICATED", "category": "Category"},
            {
                "_id": 0,
                "code": 1,
                "category": 1,
                "specific_category": 1,
                "question": 1,
                "survey_year": 1,
                "answers": 1,
            },
        )
    ]
    assert [row["country_code"] for row in document["answers"]] == ["ES", "PT"]


def test_statistics_layout_keeps_response_details_without_duplicate_panels(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.dash.pages.statistics.assert_analytics_databases_available", lambda: None
    )
    monkeypatch.setattr("app.dash.pages.statistics._category_options", lambda _year: [])
    monkeypatch.setattr("app.dash.pages.statistics.build_navbar", lambda **_kwargs: "")

    layout = build_statistics_layout()

    assert _component_by_id(layout, "stats-response-detail-graph") is None
    assert _component_by_id(layout, "stats-response-detail-graph-slot") is not None
    response_panel = _component_by_id(layout, "stats-response-panel")
    assert response_panel is not None
    response_classes = str(response_panel.to_plotly_json()["props"]["className"]).split()
    assert "stats-panel-wide" in response_classes
    assert "stats-response-panel" in response_classes
    response_figure = go.Figure()
    response_graph = cast(
        Any,
        statistics_page._graph_component(
            "stats-response-detail-graph",
            response_figure,
            style=statistics_page._response_detail_graph_style(response_figure),
        ),
    )
    graph_props = response_graph.to_plotly_json()["props"]
    assert graph_props["responsive"] is True
    assert graph_props["style"] == {
        "width": "100%",
        "height": "520px",
        "minHeight": "520px",
    }
    assert _component_by_id(layout, "stats-ranking-graph") is None
    assert _component_by_id(layout, "stats-ranking-graph-slot") is not None
    ranking_graph = cast(
        Any, statistics_page._graph_component("stats-ranking-graph", go.Figure())
    )
    ranking_graph_props = ranking_graph.to_plotly_json()["props"]
    assert ranking_graph_props["responsive"] is True
    assert ranking_graph_props["style"] == {"width": "100%"}
    assert ranking_graph_props["className"] == "stats-chart-graph"
    ranking_panel = cast(Any, _component_by_id(layout, "stats-ranking-panel"))
    assert "stats-panel-wide" in ranking_panel.className.split()
    table = cast(Any, _component_by_id(layout, "stats-results-table"))
    assert table.to_plotly_json()["props"]["style"] == {"width": "100%"}
    assert table.to_plotly_json()["type"] == "AgGrid"
    table_wrapper = cast(Any, _component_by_id(layout, "stats-results-table-wrapper"))
    assert table_wrapper is not None
    assert table_wrapper.className == "stats-results-table-scroll"
    assert table_wrapper.to_plotly_json()["props"]["tabIndex"] == 0
    assert _component_by_id(layout, "stats-response-comparison-graph") is None
    assert _component_by_id(layout, "stats-response-comparison-graph-slot") is not None
    comparison_panel = cast(Any, _component_by_id(layout, "stats-response-comparison-panel"))
    assert "stats-panel-wide" in comparison_panel.className.split()
    table_download = cast(Any, _component_by_id(layout, "stats-table-download-button"))
    assert table_download.disabled is True
    assert _component_by_id(layout, "stats-summary-table-download") is not None
    assert _component_by_id(layout, "stats-experience-legal-radar-graph") is None
    assert _component_by_id(layout, "stats-experience-legal-radar-graph-slot") is None
    assert _component_by_id(layout, "stats-experience-legal-country-select") is None
    assert _component_by_id(layout, "stats-filter-analysis-graph") is None


def test_all_statistics_graphs_are_responsive_without_fixed_widths(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.dash.pages.statistics.assert_analytics_databases_available", lambda: None
    )
    monkeypatch.setattr("app.dash.pages.statistics._category_options", lambda _year: [])
    monkeypatch.setattr("app.dash.pages.statistics.build_navbar", lambda **_kwargs: "")

    graph_ids = (
        "stats-map-graph",
        "stats-temporal-graph",
        "stats-ranking-graph",
        "stats-average-graph",
        "stats-response-comparison-graph",
        "stats-response-detail-graph",
        "stats-quadrant-graph",
        "stats-ranking-gap-graph",
    )

    layout = build_statistics_layout()
    for graph_id in graph_ids:
        graph = cast(
            Any,
            (
                _component_by_id(layout, "stats-map-graph")
                if graph_id == "stats-map-graph"
                else statistics_page._graph_component(graph_id, go.Figure())
            ),
        )
        props = graph.to_plotly_json()["props"]
        assert props["responsive"] is True
        assert props["config"]["responsive"] is True
        assert props["style"]["width"] == "100%"

    map_config = cast(Any, _component_by_id(layout, "stats-map-graph")).to_plotly_json()["props"][
        "config"
    ]
    assert map_config["scrollZoom"] is False
    assert map_config["doubleClick"] is False
    assert {"zoomInGeo", "zoomOutGeo", "resetGeo", "toImage"}.issubset(
        map_config["modeBarButtonsToRemove"]
    )


def test_ranking_graph_style_tracks_plotly_dynamic_height() -> None:
    figure = build_comparative_ranking_chart(
        [{"country": f"Country {index}", "iso": f"X{index}", "value": index} for index in range(46)]
    )

    assert _ranking_graph_style(figure) == {
        "width": "100%",
        "height": "1500px",
        "minHeight": "500px",
    }


def test_response_comparison_graph_style_tracks_local_horizontal_width() -> None:
    figure = build_response_country_comparison_chart(
        [
            {
                "country": f"Country {index}",
                "iso": f"X{index}",
                "answer": answer,
                "percentage": index,
            }
            for index in range(46)
            for answer in ("Yes", "No")
        ],
    )

    assert _response_comparison_graph_style(figure) == {
        "width": "100%",
        "height": "610px",
        "minHeight": "560px",
        "minWidth": "2358px",
    }


def test_response_comparison_uses_an_external_country_legend() -> None:
    figure = build_response_country_comparison_chart(
        [
            {"country": "Spain", "iso": "ES", "answer": "Yes", "percentage": 60.0},
            {"country": "France", "iso": "FR", "answer": "Yes", "percentage": 55.0},
        ]
    )

    component = _response_comparison_component(
        figure,
        _response_comparison_graph_style(figure),
    )
    graph = cast(Any, _component_by_id(component, "stats-response-comparison-graph"))

    assert graph.figure.layout.showlegend is False
    assert "stats-country-legend" in str(component)
    assert "España" in str(component)
    assert "Francia" in str(component)


def test_fra_methodology_uses_exact_localized_copy() -> None:
    assert _methodology_text("es") == (
        "FRA refleja respuestas de personas encuestadas. "
        "La puntuación ILGA mide leyes y políticas. "
        "Las fuentes no son directamente equivalentes."
    )
    assert _methodology_text("en") == (
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


def test_filter_contract_canonicalizes_all_without_using_the_first_option() -> None:
    filters = StatisticsFilters.from_raw(None, "", "ALL", None)
    options = [
        {"label": "Asexual", "value": "Asexual"},
        {"label": "Gay", "value": "Gay"},
    ]

    assert filters == StatisticsFilters()
    assert _explicit_filter_value("Sexual Orientation", options, None) is None


def test_demographic_filter_resets_incompatible_identity_to_all() -> None:
    filters = _resolved_ui_filters(
        "Age",
        "25-39",
        "Sexual Orientation",
        "Asexual",
    )

    assert filters == StatisticsFilters(
        demographic_type="Age",
        demographic_value="25-39",
        identity_type="All",
        identity_value="All",
    )


@pytest.mark.parametrize(
    ("filter_a_name", "filter_a_value", "filter_b_name", "filter_b_value", "expected"),
    [
        ("All", "All", "All", "All", "Segmentación: Población total"),
        ("Age", "25-39", "All", "All", "Filtro: Edad — 25\u201339"),
        (
            "All",
            "All",
            "Sexual Orientation",
            "Asexual",
            "Filtro: Orientación sexual — Asexual",
        ),
    ],
)
def test_statistics_map_hover_prioritizes_selected_segmentation(
    filter_a_name: str,
    filter_a_value: str,
    filter_b_name: str,
    filter_b_value: str,
    expected: str,
) -> None:
    hover = build_statistics_hover(
        country="España",
        value=42,
        filter_a_name=filter_a_name,
        filter_a_value=filter_a_value,
        filter_b_name=filter_b_name,
        filter_b_value=filter_b_value,
        response="Yes",
        language="es",
    )

    assert "Valor: 42%" in hover
    assert expected in hover
    assert "Respuesta" not in hover


def test_percentage_choropleth_distinguishes_zero_low_values_and_null() -> None:
    samples = [0, 1, 5, 10, 25, 50, 75, 100, None]
    codes = ["ES", "PT", "FR", "DE", "IT", "BE", "NL", "LU", "AT"]
    figure = build_europe_choropleth(
        [
            {"country": code, "iso": code, "value": value}
            for code, value in zip(codes, samples, strict=True)
        ],
        source="FRA",
    )
    trace = _trace(figure)
    values = dict(zip(trace.locations, trace.z, strict=True))

    assert [values[code] for code in codes] == [0, 1, 5, 10, 25, 50, 75, 100, -1]
    assert trace.colorscale[0][1] == "#9ca3af"
    assert trace.colorscale[2][1] == "#A9C8F0"
    assert trace.colorscale[0][1] != trace.colorscale[2][1]
    assert trace.marker.line.color == "#334155"
    assert trace.marker.line.width >= 0.85
    assert list(trace.colorbar.tickvals) == [0, 20, 40, 60, 80, 100]
    assert trace.colorbar.x == pytest.approx(-0.035)
    assert trace.colorbar.xanchor == "right"
    assert figure.layout.margin.l == 88


def test_choropleth_uses_home_map_framing_and_keeps_country_selection() -> None:
    rows = [
        {"country": "Spain", "iso": "ES", "value": 42.0},
        {"country": "France", "iso": "FR", "value": 38.0},
    ]
    europe = build_europe_choropleth(rows, source="FRA")
    focused = build_europe_choropleth(rows, source="FRA", selected_isos=["ES"])
    reset = build_europe_choropleth(rows, source="FRA", selected_isos=[])

    assert europe.layout.geo.center.lon == 20
    assert europe.layout.geo.center.lat == 54
    assert europe.layout.geo.projection.scale == 1.18
    assert europe.layout.margin.b == 0
    assert europe.layout.margin.t == 0
    assert focused.layout.geo.projection.scale == europe.layout.geo.projection.scale
    assert focused.layout.geo.lonaxis.range is None
    assert _trace(focused, 1).customdata[0][0] == "ES"
    assert reset.layout.geo.projection.scale == 1.18
    assert reset.layout.uirevision.endswith("-europe")


def test_social_attitudes_email_regression_keeps_all_all(monkeypatch) -> None:
    selected_answer = "I received an email from any other organisation or online network"
    document = {
        "code": "I1",
        "category": "Social attitudes and government response",
        "question": "How did you come to know about this survey?",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": selected_answer,
                "percentage": 2,
                "date": "2023",
                "filters": [{"type": "All", "value": "All"}],
            },
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": selected_answer,
                "percentage": 1,
                "date": "2023",
                "filters": [{"type": "Sexual Orientation", "value": "Asexual"}],
            },
        ],
    }
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_fra_indicator_answers",
        lambda *_args: document,
    )

    result = get_fra_statistics(
        FraStatisticsQuery(
            year=2023,
            category="Social attitudes and government response",
            question_code="I1",
            answer=selected_answer,
            filter_a_name="All",
            filter_a_value="All",
            filter_b_name="All",
            filter_b_value="All",
        )
    )

    assert result["status"] == "ok"
    assert result["filters"] == {
        "filter_a_name": "All",
        "filter_a_value": "All",
        "filter_b_name": "All",
        "filter_b_value": "All",
    }
    assert {(row["filter_a"], row["filter_b"]) for row in result["data"]} == {("All", "All")}
    assert result["ranking"][0]["value"] == 2
