from __future__ import annotations

import logging
from typing import Any

from dash import Dash, Input, Output, State, dcc, html
from dash.development.base_component import Component

from app.analytics.statistics_exports import chart_graph_config
from app.dash.components.dropdown_options import build_dropdown_options, option_value_or_none
from app.dash.components.empty_state import build_empty_state
from app.dash.components.ilga_methodology import build_ilga_series_normalization_note
from app.dash.i18n import country_labels, ui_text
from app.trends.charts import build_trend_figure
from app.trends.forecasting_service import forecast_horizon_limit
from app.trends.models import (
    ForecastModelName,
    ForecastResult,
    ModelValidation,
    TrendDirection,
    TrendFilters,
)
from app.trends.service import generate_trend_analysis, get_historical_series, get_trend_scope

logger = logging.getLogger(__name__)


def register_trend_callbacks(app: Dash) -> None:
    @app.callback(
        Output("trend-country-select", "options"),
        Output("trend-country-select", "value"),
        Output("trend-country-select", "disabled"),
        Output("trend-country-select", "placeholder"),
        Input("app-language-store", "data"),
        State("trend-country-select", "value"),
    )
    def update_trend_countries(language: str | None, current: str | None):
        clean_language = _language(language)
        try:
            countries = get_trend_scope().countries
        except Exception:
            logger.exception("trend_country_catalog_load_failed")
            return [], None, True, ui_text("trends_select_country", clean_language)
        options = build_dropdown_options(
            (
                {
                    "label": country_labels(code, name)[1 if clean_language == "en" else 0],
                    "value": code,
                }
                for code, name in countries
            ),
            context="trends-country",
        )
        selected = option_value_or_none(options, current)
        return (
            options,
            selected,
            not bool(options),
            ui_text("trends_select_country", clean_language),
        )

    @app.callback(
        Output("trend-year-range", "min"),
        Output("trend-year-range", "max"),
        Output("trend-year-range", "value"),
        Output("trend-year-range", "marks"),
        Output("trend-year-range", "disabled"),
        Input("trend-country-select", "value"),
    )
    def update_trend_range(country_code: str | None):
        if not country_code:
            return 2011, 2012, [2011, 2012], {2011: "2011", 2012: "2012"}, True
        try:
            points = get_historical_series(country_code)
        except Exception:
            logger.exception("trend_control_series_load_failed", extra={"country": country_code})
            return 2011, 2012, [2011, 2012], {2011: "2011", 2012: "2012"}, True
        years = sorted({int(point.year) for point in points if point.year is not None})
        if not years:
            return 2011, 2012, [2011, 2012], {2011: "2011", 2012: "2012"}, True
        minimum, maximum = years[0], years[-1]
        return minimum, maximum, [minimum, maximum], _year_marks(years), len(years) < 2

    @app.callback(
        Output("trend-horizon-select", "options"),
        Output("trend-horizon-select", "value"),
        Output("trend-horizon-select", "disabled"),
        Input("trend-country-select", "value"),
        Input("trend-year-range", "value"),
        Input("app-language-store", "data"),
        State("trend-horizon-select", "value"),
    )
    def update_trend_horizon(
        country_code: str | None,
        year_range: list[int] | None,
        language: str | None,
        current_horizon: int | None,
    ):
        if not country_code:
            return [], None, True
        clean_language = _language(language)
        start_year, end_year = _selected_range(year_range)
        try:
            points = get_historical_series(
                country_code,
                TrendFilters(start_year=start_year, end_year=end_year),
            )
        except Exception:
            logger.exception("trend_horizon_load_failed", extra={"country": country_code})
            return [], None, True
        limit = forecast_horizon_limit(len(points))
        horizon_options = [
            {"label": _horizon_label(value, clean_language), "value": value}
            for value in range(1, limit + 1)
        ]
        selected_horizon = option_value_or_none(horizon_options, current_horizon) or (
            1 if horizon_options else None
        )
        return horizon_options, selected_horizon, not bool(horizon_options)

    @app.callback(
        Output("trend-result", "children"),
        Input("trend-country-select", "value"),
        Input("trend-year-range", "value"),
        Input("trend-year-range", "disabled"),
        Input("trend-horizon-select", "value"),
        Input("app-language-store", "data"),
    )
    def render_trend_analysis(
        country_code: str | None,
        year_range: list[int] | None,
        range_disabled: bool | None,
        horizon: int | None,
        language: str | None,
    ) -> Component:
        clean_language = _language(language)
        if not country_code:
            return _state(
                "trends_name",
                "trends_initial_prompt",
                clean_language,
                "trend-state-info",
            )
        start_year, end_year = (None, None) if range_disabled else _selected_range(year_range)
        try:
            result = generate_trend_analysis(
                country_code,
                TrendFilters(start_year=start_year, end_year=end_year),
                forecast_years=int(horizon or 1),
            )
        except Exception:
            logger.exception("trend_analysis_failed", extra={"country": country_code})
            return _state(
                "trends_error_loading_series",
                "trends_error_analysis",
                clean_language,
                "trend-state-error",
            )
        return _render_result(result, clean_language)


def _render_result(result: ForecastResult, language: str) -> Component:
    if result.status == "invalid":
        return _state(
            "trends_error_loading_series",
            "trends_error_analysis",
            language,
            "trend-state-error",
        )
    if not result.historical:
        return _state(
            "trends_not_enough",
            "trends_not_enough_projection",
            language,
            "trend-state-warning",
        )
    graph = dcc.Graph(
        id="trend-history-graph",
        figure=build_trend_figure(result, language=language),
        responsive=True,
        config=chart_graph_config(),
        className="trend-graph",
    )
    normalization_note = build_ilga_series_normalization_note(
        result.historical,
        language=language,
        class_name="trend-normalization-note",
    )
    if result.status != "ok":
        return html.Div(
            [
                _state(
                    "trends_not_enough",
                    "trends_not_enough_projection",
                    language,
                    "trend-state-warning",
                ),
                html.Section(graph, className="trend-chart-card"),
                normalization_note,
                _limitations(language),
            ],
            className="trend-analysis",
        )

    return html.Div(
        [
            _summary_cards(result, language),
            *(
                [
                    html.Aside(
                        ui_text("trends_exploratory_warning", language),
                        className="trend-exploratory-note",
                        role="note",
                    )
                ]
                if result.exploratory
                else []
            ),
            html.Section(
                [
                    html.H2(ui_text("trends_chart_title", language)),
                    graph,
                    _source_distinction(language),
                ],
                className="trend-chart-card",
            ),
            normalization_note,
            _methodology(result, language),
            _limitations(language),
        ],
        className="trend-analysis",
    )


def _summary_cards(result: ForecastResult, language: str) -> Component:
    summary = result.summary
    validation = result.selected_validation
    if summary is None:
        return html.Section(className="trend-metric-grid")
    cards = [
        _metric_card("trends_last_value", f"{summary.final_value:.1f} %", language),
        _metric_card("trends_trend", _direction_label(summary.direction, language), language),
        _metric_card("trends_total_change", _signed_points(summary.absolute_change, language), language),
        _metric_card("trends_selected_model", _model_label(result.selected_model, language), language),
        _metric_card(
            "trends_mean_error",
            f"±{validation.mae:.1f} {ui_text('trends_points', language)}"
            if validation
            else "—",
            language,
        ),
    ]
    return html.Section(cards, className="trend-metric-grid")


def _methodology(result: ForecastResult, language: str) -> Component:
    summary = result.summary
    validation = result.selected_validation
    if summary is None or validation is None:
        return html.Section(className="trend-method-card")
    return html.Section(
        [
            html.H2(ui_text("trends_projection_method", language)),
            html.P(ui_text("trends_method_summary", language), className="trend-method-summary"),
            html.Dl(
                [
                    *_definition(
                        "trends_selected_model",
                        _model_label(result.selected_model, language),
                        language,
                    ),
                    *_definition(
                        "trends_validation_mean_error",
                        f"{validation.mae:.2f} {ui_text('trends_points', language)}",
                        language,
                    ),
                    *_definition(
                        "trends_years_used",
                        f"{summary.start_year}-{summary.end_year}",
                        language,
                    ),
                    *_definition("trends_observations", str(summary.observations), language),
                    *_definition(
                        "trends_forecast_horizon",
                        _horizon_label(result.forecast_horizon, language),
                        language,
                    ),
                ],
                className="trend-method-facts",
            ),
            html.Details(
                [
                    html.Summary(ui_text("trends_how_calculated", language)),
                    html.Div(
                        [
                            _method_step(
                                1,
                                "trends_data_collection",
                                _collection_text(result, language),
                                language,
                            ),
                            _method_step(
                                2,
                                "trends_data_validation",
                                _validation_text(result, language),
                                language,
                            ),
                            _models_step(result, language),
                            _method_step(
                                4,
                                "trends_temporal_validation",
                                ui_text("trends_temporal_validation_detail", language),
                                language,
                            ),
                            _comparison_step(result.validation, language),
                            _method_step(
                                6,
                                "trends_model_selection",
                                _selection_text(result, language),
                                language,
                            ),
                            _method_step(
                                7,
                                "trends_final_training",
                                ui_text("trends_final_training_detail", language),
                                language,
                            ),
                            _method_step(
                                8,
                                "trends_projection",
                                ui_text("trends_projection_detail", language).format(
                                    horizon=result.forecast_horizon
                                ),
                                language,
                            ),
                            _method_step(
                                9,
                                "trends_limits",
                                ui_text("trends_score_limits_detail", language),
                                language,
                            ),
                            _method_step(
                                10,
                                "trends_uncertainty",
                                ui_text(
                                    "trends_uncertainty_detail"
                                    if result.uncertainty_method
                                    else "trends_uncertainty_unavailable",
                                    language,
                                ),
                                language,
                            ),
                        ],
                        className="trend-method-details-body",
                    ),
                ],
                className="trend-method-details",
            ),
        ],
        className="trend-method-card",
    )


def _models_step(result: ForecastResult, language: str) -> Component:
    return html.Section(
        [
            html.H3(f"3. {ui_text('trends_models_evaluated', language)}"),
            html.Ul(
                [html.Li(_model_label(item.model, language)) for item in result.validation]
            ),
        ],
        className="trend-method-step",
    )


def _comparison_step(validation: tuple[ModelValidation, ...], language: str) -> Component:
    return html.Section(
        [
            html.H3(f"5. {ui_text('trends_error_comparison', language)}"),
            html.Div(
                html.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th(ui_text("trends_model", language)),
                                    html.Th("MAE"),
                                    html.Th("RMSE"),
                                    html.Th(ui_text("trends_validation_folds", language)),
                                ]
                            )
                        ),
                        html.Tbody(
                            [
                                html.Tr(
                                    [
                                        html.Td(_model_label(item.model, language)),
                                        html.Td(f"{item.mae:.2f}"),
                                        html.Td(f"{item.rmse:.2f}"),
                                        html.Td(str(len(item.folds))),
                                    ]
                                )
                                for item in validation
                            ]
                        ),
                    ],
                    className="trend-model-table",
                ),
                className="trend-table-scroll",
            ),
        ],
        className="trend-method-step",
    )


def _method_step(number: int, title_key: str, body: str, language: str) -> Component:
    return html.Section(
        [html.H3(f"{number}. {ui_text(title_key, language)}"), html.P(body)],
        className="trend-method-step",
    )


def _collection_text(result: ForecastResult, language: str) -> str:
    summary = result.summary
    if summary is None:
        return ""
    return ui_text("trends_data_collection_detail", language).format(
        country=result.country_name,
        start=summary.start_year,
        end=summary.end_year,
        observations=summary.observations,
    )


def _validation_text(result: ForecastResult, language: str) -> str:
    summary = result.summary
    missing = summary.missing_years if summary else ()
    missing_label = ", ".join(str(year) for year in missing) or ui_text(
        "trends_no_missing_years", language
    )
    return ui_text("trends_data_validation_detail", language).format(missing=missing_label)


def _selection_text(result: ForecastResult, language: str) -> str:
    model = _model_label(result.selected_model, language)
    key = (
        "trends_selection_simplicity"
        if result.selection_reason == "simpler_model_with_similar_error"
        else "trends_selection_lowest_error"
    )
    return ui_text(key, language).format(model=model)


def _limitations(language: str) -> Component:
    return html.Aside(
        [
            html.H2(ui_text("trends_limitations", language)),
            html.P(ui_text("trends_limitations_detail", language)),
        ],
        className="trend-limitations",
    )


def _source_distinction(language: str) -> Component:
    return html.Div(
        [
            html.P(ui_text("trends_historical_source", language)),
            html.P(ui_text("trends_projection_source", language)),
        ],
        className="trend-source-distinction",
    )


def _state(title_key: str, detail_key: str, language: str, class_name: str) -> Component:
    return build_empty_state(
        ui_text(title_key, language),
        ui_text(detail_key, language),
        class_name=f"trend-state {class_name}",
    )


def _metric_card(label_key: str, value: str, language: str) -> Component:
    return html.Article(
        [html.P(ui_text(label_key, language)), html.Strong(value)],
        className="trend-metric-card",
    )


def _definition(label_key: str, value: str, language: str) -> list[Component]:
    return [html.Dt(ui_text(label_key, language)), html.Dd(value)]


def _model_label(model: ForecastModelName | None, language: str) -> str:
    if model is None:
        return "—"
    return ui_text(f"trends_model_{model.value}", language)


def _direction_label(direction: TrendDirection, language: str) -> str:
    return ui_text(
        {
            TrendDirection.UPWARD: "trends_upward",
            TrendDirection.DOWNWARD: "trends_downward",
            TrendDirection.STABLE: "trends_stable",
        }[direction],
        language,
    )


def _signed_points(value: float, language: str) -> str:
    return f"{value:+.1f} {ui_text('trends_points', language)}"


def _horizon_label(value: int, language: str) -> str:
    return ui_text(
        {1: "trends_year_singular", 2: "trends_years_two", 3: "trends_years_three"}.get(
            int(value), "trends_years_three"
        ),
        language,
    )


def _year_marks(years: list[int]) -> dict[int, str]:
    if len(years) <= 9:
        return {year: str(year) for year in years}
    return {
        year: str(year)
        for index, year in enumerate(years)
        if index % 2 == 0 or year in {years[0], years[-1]}
    }


def _selected_range(value: list[int] | None) -> tuple[int | None, int | None]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        return None, None
    try:
        start, end = sorted((int(value[0]), int(value[1])))
    except (TypeError, ValueError):
        return None, None
    return start, end


def _language(value: Any) -> str:
    return "en" if value == "en" else "es"
