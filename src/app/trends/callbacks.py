from __future__ import annotations

import logging
from typing import Any

from dash import Dash, Input, Output, dcc, html
from dash.development.base_component import Component

from app.analytics.statistics_exports import chart_graph_config
from app.dash.components.empty_state import build_empty_state
from app.dash.components.ilga_methodology import build_ilga_series_normalization_note
from app.dash.components.source_attribution import build_source_attribution
from app.dash.i18n import country_labels, text, ui_text
from app.trends.charts import build_trend_figure
from app.trends.data import RANKING_CATEGORY
from app.trends.models import TrendAnalysis, TrendDirection, TrendFilters, TrendSource
from app.trends.service import (
    generate_trend_analysis,
    get_historical_series,
    get_indicator_options,
    get_trend_scope,
)
from app.trends.validation import max_forecast_horizon

logger = logging.getLogger(__name__)


def register_trend_callbacks(app: Dash) -> None:
    @app.callback(
        Output("trend-category-select", "options"),
        Output("trend-category-select", "value"),
        Output("trend-category-select", "disabled"),
        Input("trend-source-select", "value"),
        Input("app-language-store", "data"),
    )
    def update_trend_categories(source: str | None, language: str | None):
        if source != TrendSource.ILGA.value:
            return [], None, True
        return (
            [
                {
                    "label": ui_text("trends_total_ranking", _language(language)),
                    "value": RANKING_CATEGORY,
                }
            ],
            RANKING_CATEGORY,
            True,
        )

    @app.callback(
        Output("trend-indicator-select", "options"),
        Output("trend-indicator-select", "value"),
        Output("trend-indicator-select", "disabled"),
        Input("trend-source-select", "value"),
        Input("trend-category-select", "value"),
        Input("app-language-store", "data"),
    )
    def update_trend_indicators(
        source: str | None,
        category: str | None,
        language: str | None,
    ):
        if source != TrendSource.ILGA.value or category != RANKING_CATEGORY:
            return [], None, True
        try:
            indicators = get_indicator_options(source, category)
        except Exception:
            logger.exception(
                "trend_indicators_load_failed",
                extra={"source": source, "category": category},
            )
            return [], None, True
        options = [
            {
                "label": ui_text("trends_total_ranking", _language(language)),
                "value": indicator.to_token(),
            }
            for indicator in indicators
        ]
        value = options[0]["value"] if options else None
        return options, value, True

    @app.callback(
        Output("trend-series-select", "options"),
        Output("trend-series-select", "value"),
        Output("trend-series-select", "disabled"),
        Output("trend-series-field", "className"),
        Input("trend-source-select", "value"),
        Input("trend-indicator-select", "value"),
        Input("app-language-store", "data"),
    )
    def update_trend_variants(
        source: str | None,
        indicator_token: str | None,
        language: str | None,
    ):
        if source == TrendSource.ILGA.value and indicator_token:
            return (
                [{"label": ui_text("trends_source_ilga", _language(language)), "value": "default"}],
                "default",
                True,
                ("trend-field is-hidden"),
            )
        return [], None, True, "trend-field is-hidden"

    @app.callback(
        Output("trend-country-select", "options"),
        Output("trend-country-select", "value"),
        Output("trend-country-select", "disabled"),
        Input("trend-indicator-select", "value"),
        Input("trend-series-select", "value"),
    )
    def update_trend_countries(indicator_token: str | None, series_key: str | None):
        if not indicator_token or not series_key:
            return [], None, True
        try:
            scope = get_trend_scope(indicator_token, series_key)
        except Exception:
            logger.exception("trend_countries_load_failed")
            return [], None, True
        options = [
            {
                "label": text(*country_labels(code, name)),
                "value": code,
            }
            for code, name in scope.countries
        ]
        return options, None, not bool(options)

    @app.callback(
        Output("trend-year-range", "min"),
        Output("trend-year-range", "max"),
        Output("trend-year-range", "value"),
        Output("trend-year-range", "marks"),
        Output("trend-year-range", "disabled"),
        Input("trend-source-select", "value"),
        Input("trend-indicator-select", "value"),
        Input("trend-series-select", "value"),
        Input("trend-country-select", "value"),
    )
    def update_trend_range(
        source: str | None,
        indicator_token: str | None,
        series_key: str | None,
        country_code: str | None,
    ):
        if not source or not indicator_token or not series_key or not country_code:
            return 0, 1, [0, 1], {}, True
        try:
            points = get_historical_series(
                source,
                indicator_token,
                country_code,
                TrendFilters(series_key=series_key),
            )
        except Exception:
            logger.exception(
                "trend_range_load_failed",
                extra={"source": source, "country": country_code},
            )
            return 0, 1, [0, 1], {}, True
        years = sorted(
            {
                int(point.year)
                for point in points
                if point.year is not None and point.value is not None
            }
        )
        if not years:
            return 0, 1, [0, 1], {}, True
        minimum = years[0]
        maximum = years[-1]
        range_max = maximum if maximum > minimum else minimum + 1
        return (
            minimum,
            range_max,
            [minimum, maximum],
            {year: str(year) for year in years},
            len(years) < 2,
        )

    @app.callback(
        Output("trend-horizon-select", "options"),
        Output("trend-horizon-select", "value"),
        Output("trend-horizon-select", "disabled"),
        Input("trend-source-select", "value"),
        Input("trend-indicator-select", "value"),
        Input("trend-series-select", "value"),
        Input("trend-country-select", "value"),
        Input("trend-year-range", "value"),
        Input("app-language-store", "data"),
    )
    def update_trend_horizon(
        source: str | None,
        indicator_token: str | None,
        series_key: str | None,
        country_code: str | None,
        year_range: list[int] | None,
        language: str | None,
    ):
        if not source or not indicator_token or not series_key or not country_code:
            return [], None, True
        start_year, end_year = _year_bounds(year_range)
        try:
            points = get_historical_series(
                source,
                indicator_token,
                country_code,
                TrendFilters(
                    start_year=start_year,
                    end_year=end_year,
                    series_key=series_key,
                ),
            )
        except Exception:
            logger.exception(
                "trend_horizon_load_failed",
                extra={"source": source, "country": country_code},
            )
            return [], None, True
        years = {
            point.year for point in points if point.year is not None and point.value is not None
        }
        allowed = max_forecast_horizon(len(years))
        return (
            _horizon_options(allowed, _language(language)),
            1 if allowed else None,
            allowed == 0,
        )

    @app.callback(
        Output("trend-result", "children"),
        Input("trend-source-select", "value"),
        Input("trend-category-select", "value"),
        Input("trend-indicator-select", "value"),
        Input("trend-series-select", "value"),
        Input("trend-country-select", "value"),
        Input("trend-year-range", "value"),
        Input("trend-horizon-select", "value"),
        Input("app-language-store", "data"),
    )
    def render_trend_analysis(
        source: str | None,
        category: str | None,
        indicator_token: str | None,
        series_key: str | None,
        country_code: str | None,
        year_range: list[int] | None,
        horizon: int | None,
        language: str | None,
    ) -> Component:
        clean_language = _language(language)
        if not all((source, category, indicator_token, series_key, country_code)):
            return _state(
                "trends_name",
                "trends_initial_prompt",
                clean_language,
                "trend-state-info",
            )
        start_year, end_year = _year_bounds(year_range)
        try:
            analysis, metadata = generate_trend_analysis(
                str(source),
                str(indicator_token),
                str(country_code),
                TrendFilters(
                    start_year=start_year,
                    end_year=end_year,
                    series_key=str(series_key),
                ),
                forecast_years=int(horizon or 0),
            )
        except Exception:
            logger.exception(
                "trend_analysis_failed",
                extra={"source": source, "country": country_code},
            )
            return _state(
                "trends_error_loading_series",
                "trends_error_analysis",
                clean_language,
                "trend-state-error",
            )
        if analysis.status == "insufficient":
            return _state(
                "trends_not_enough",
                "trends_not_enough_detail",
                clean_language,
                "trend-state-warning",
            )
        if analysis.status == "incomparable":
            return _state(
                "trends_not_enough",
                "trends_incomparable",
                clean_language,
                "trend-state-warning",
            )
        return _result(analysis, metadata, clean_language)

    @app.callback(
        Output("trend-source-select", "placeholder"),
        Output("trend-category-select", "placeholder"),
        Output("trend-indicator-select", "placeholder"),
        Output("trend-series-select", "placeholder"),
        Output("trend-country-select", "placeholder"),
        Input("app-language-store", "data"),
    )
    def translate_trend_placeholders(language: str | None) -> tuple[str, str, str, str, str]:
        clean_language = _language(language)
        return (
            ui_text("trends_select_source", clean_language),
            ui_text("trends_select_category", clean_language),
            ui_text("trends_select_indicator", clean_language),
            ui_text("trends_select_series", clean_language),
            ui_text("trends_select_country", clean_language),
        )


def _result(analysis: TrendAnalysis, metadata: Any, language: str) -> Component:
    summary = analysis.summary
    metrics = analysis.metrics
    if summary is None or metrics is None:
        return _state("trends_not_enough", "trends_not_enough_detail", language)
    cards = [
        _metric_card(
            "trends_trend",
            _direction_label(summary.direction, language),
            language,
        ),
        _metric_card("trends_total_change", _change_label(summary), language),
        _metric_card("trends_historical_mean", _number(summary.mean), language),
        _metric_card("trends_years_analyzed", str(summary.observations), language),
        _metric_card("trends_last_value", _number(summary.final_value), language),
    ]
    if analysis.forecast:
        cards.append(
            _metric_card(
                "trends_projected_value",
                _number(analysis.forecast[-1].value),
                language,
            )
        )
    metric_items: list[Component] = []
    metric_items.extend(_quality_item("trends_observations", str(metrics.observations), language))
    metric_items.extend(_quality_item("trends_mae", _number(metrics.mae), language))
    metric_items.extend(_quality_item("trends_rmse", _number(metrics.rmse), language))
    metric_items.extend(_quality_item("trends_slope", _number(metrics.slope), language))
    if metrics.r_squared is not None:
        metric_items.extend(_quality_item("trends_r_squared", _number(metrics.r_squared), language))
    notes: list[Component] = [
        html.P(ui_text("trends_ilga_context", language)),
        html.P(ui_text("trends_method_warning", language)),
        html.P(ui_text("trends_ilga_warning", language)),
    ]
    if analysis.exploratory:
        notes.append(html.P(ui_text("trends_exploratory", language), className="trend-exploratory"))
    normalization_note = build_ilga_series_normalization_note(
        analysis.points,
        language=language,
        class_name="trend-normalization-note",
    )
    return html.Div(
        [
            html.Section(cards, className="trend-metric-grid"),
            html.Section(
                [
                    dcc.Graph(
                        id="trend-history-graph",
                        figure=build_trend_figure(analysis, metadata, language=language),
                        responsive=True,
                        config=chart_graph_config(),
                        className="trend-graph",
                        style={"width": "100%"},
                    ),
                    build_source_attribution(
                        metadata.source.value,
                        year=summary.end_year,
                        compact=True,
                        language=language,
                        class_name="trend-source-attribution",
                    ),
                ],
                className="trend-chart-card",
            ),
            html.Section(
                [
                    html.H2(ui_text("trends_model_metrics", language)),
                    html.Dl(metric_items, className="trend-quality-grid"),
                ],
                className="trend-quality-card",
            ),
            html.Aside(notes, className="trend-methodology"),
            normalization_note,
        ],
        className="trend-analysis",
    )


def _state(
    title_key: str,
    detail_key: str,
    language: str,
    class_name: str = "trend-state-warning",
) -> Component:
    return build_empty_state(
        ui_text(title_key, language),
        ui_text(detail_key, language),
        class_name=f"trend-state {class_name}",
    )


def _metric_card(label_key: str, value: str, language: str) -> Component:
    return html.Article(
        [html.Span(ui_text(label_key, language)), html.Strong(value)],
        className="trend-metric-card",
    )


def _quality_item(label_key: str, value: str, language: str) -> list[Component]:
    return [html.Dt(ui_text(label_key, language)), html.Dd(value)]


def _horizon_options(limit: int, language: str) -> list[dict[str, Any]]:
    keys = {1: "trends_year_singular", 2: "trends_years_two", 3: "trends_years_three"}
    return [
        {"label": ui_text(keys[value], language), "value": value} for value in range(1, limit + 1)
    ]


def _direction_label(direction: TrendDirection, language: str) -> str:
    return ui_text(
        {
            TrendDirection.UPWARD: "trends_upward",
            TrendDirection.DOWNWARD: "trends_downward",
            TrendDirection.STABLE: "trends_stable",
        }[direction],
        language,
    )


def _change_label(summary: Any) -> str:
    absolute = f"{summary.absolute_change:+.2f}"
    if summary.percentage_change is None:
        return absolute
    return f"{absolute} ({summary.percentage_change:+.2f} %)"


def _number(value: float) -> str:
    return f"{value:.2f}"


def _year_bounds(value: list[int] | None) -> tuple[int | None, int | None]:
    if not value or len(value) != 2:
        return None, None
    return int(min(value)), int(max(value))


def _language(value: str | None) -> str:
    return "en" if value == "en" else "es"
