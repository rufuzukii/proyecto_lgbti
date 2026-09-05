from __future__ import annotations

from dash import dcc, html
from dash.development.base_component import Component

from app.shared.components.empty_state import build_empty_state
from app.shared.components.loading import contextual_loading
from app.shared.components.page_structure import build_page_header
from app.web.i18n import dash_attrs, text, ui_text
from app.web.navigation import build_navbar


def build_trends_layout() -> Component:
    return html.Div(
        [
            build_navbar(active="trends"),
            html.Main(
                [
                    _header(),
                    _controls(),
                    contextual_loading(
                        html.Div(
                            _initial_state(),
                            id="trend-result",
                            className="trend-result",
                            role="status",
                            **dash_attrs({"aria-live": "polite"}),
                        ),
                        "loading_trends",
                        element_id="trends-result-loading",
                        target_components={"trend-result": "children"},
                        hide_content_while_loading=True,
                        message_id="trends-loading-message",
                    ),
                ],
                className="trend-shell app-page app-page-container",
            ),
        ]
    )


def _header() -> Component:
    return build_page_header(
        eyebrow=text(ui_text("trends_eyebrow", "es"), ui_text("trends_eyebrow", "en")),
        title=text(ui_text("trends_title", "es"), ui_text("trends_title", "en")),
        description=text(ui_text("trends_lead", "es"), ui_text("trends_lead", "en")),
        meta=html.P(
            text(
                ui_text("trends_historical_source", "es"),
                ui_text("trends_historical_source", "en"),
            ),
            className="trend-source-note",
        ),
        class_name="trend-header",
    )


def _controls() -> Component:
    return html.Section(
        [
            _field(
                "trends_country",
                dcc.Dropdown(
                    id="trend-country-select",
                    options=[],
                    value=None,
                    clearable=False,
                    searchable=True,
                    placeholder=ui_text("trends_select_country", "es"),
                ),
            ),
            _field(
                "trends_forecast_horizon",
                dcc.Dropdown(
                    id="trend-horizon-select",
                    options=[
                        {
                            "label": text(
                                ui_text("trends_year_singular", "es"),
                                ui_text("trends_year_singular", "en"),
                            ),
                            "value": 1,
                        },
                        {
                            "label": text(
                                ui_text("trends_years_two", "es"),
                                ui_text("trends_years_two", "en"),
                            ),
                            "value": 2,
                        },
                        {
                            "label": text(
                                ui_text("trends_years_three", "es"),
                                ui_text("trends_years_three", "en"),
                            ),
                            "value": 3,
                        },
                    ],
                    value=1,
                    clearable=False,
                    disabled=True,
                ),
            ),
            _field(
                "trends_historical_range",
                dcc.RangeSlider(
                    id="trend-year-range",
                    className="trend-range-control",
                    min=2011,
                    max=2012,
                    value=[2011, 2012],
                    marks={2011: "2011", 2012: "2012"},
                    step=1,
                    allowCross=False,
                    disabled=True,
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
                class_name="trend-field trend-field-wide trend-range-field",
            ),
        ],
        className="trend-controls",
        **dash_attrs({"aria-label": "Configuración de tendencias / Trends configuration"}),
    )


def _field(label_key: str, control: Component, *, class_name: str = "trend-field") -> Component:
    control_id = getattr(control, "id", None)
    label_id = f"{control_id}-label" if control_id else None
    label = text(ui_text(label_key, "es"), ui_text(label_key, "en"))
    is_native_form_control = control.__class__.__name__ in {"Input", "Textarea"}
    if control_id and not is_native_form_control:
        label_node = html.Span(label, id=label_id, className="trend-field-label")
        return html.Div(
            [label_node, control],
            className=class_name,
            role="group",
            **dash_attrs({"aria-labelledby": label_id}),
        )
    return html.Div(
        [html.Label(label, htmlFor=control_id, className="trend-field-label"), control],
        className=class_name,
    )


def _initial_state() -> Component:
    return build_empty_state(
        text(ui_text("trends_name", "es"), ui_text("trends_name", "en")),
        text(
            ui_text("trends_initial_prompt", "es"),
            ui_text("trends_initial_prompt", "en"),
        ),
        class_name="trend-state trend-state-info",
    )
