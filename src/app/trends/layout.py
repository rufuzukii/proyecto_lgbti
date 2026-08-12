from __future__ import annotations

from dash import dcc, html
from dash.development.base_component import Component

from app.dash.components.empty_state import build_empty_state
from app.dash.i18n import dash_attrs, text, ui_text
from app.dash.layouts.navigation import build_navbar


def build_trends_layout() -> Component:
    return html.Div(
        [
            build_navbar(active="trends"),
            html.Main(
                [
                    _header(),
                    _controls(),
                    dcc.Loading(
                        html.Div(
                            _initial_state(),
                            id="trend-result",
                            className="trend-result",
                            role="status",
                        ),
                        type="circle",
                    ),
                ],
                className="trend-shell app-page-container",
            ),
        ]
    )


def _header() -> Component:
    return html.Header(
        [
            html.P(
                text(
                    ui_text("trends_eyebrow", "es"),
                    ui_text("trends_eyebrow", "en"),
                ),
                className="trend-eyebrow",
            ),
            html.H1(text(ui_text("trends_title", "es"), ui_text("trends_title", "en"))),
            html.P(
                text(ui_text("trends_lead", "es"), ui_text("trends_lead", "en")),
                className="trend-lead",
            ),
        ],
        className="trend-header",
    )


def _controls() -> Component:
    return html.Section(
        [
            _field(
                "trends_source",
                dcc.Dropdown(
                    id="trend-source-select",
                    options=[
                        {
                            "label": text(
                                ui_text("trends_source_ilga", "es"),
                                ui_text("trends_source_ilga", "en"),
                            ),
                            "value": "ilga",
                        },
                    ],
                    value="ilga",
                    clearable=False,
                ),
            ),
            _field(
                "trends_category",
                dcc.Dropdown(
                    id="trend-category-select",
                    options=[],
                    value=None,
                    disabled=True,
                    clearable=True,
                ),
            ),
            _field(
                "trends_indicator",
                dcc.Dropdown(
                    id="trend-indicator-select",
                    options=[],
                    value=None,
                    disabled=True,
                    clearable=True,
                ),
            ),
            _field(
                "trends_series_variant",
                dcc.Dropdown(
                    id="trend-series-select",
                    options=[],
                    value=None,
                    disabled=True,
                    clearable=True,
                ),
                element_id="trend-series-field",
                class_name="trend-field is-hidden",
            ),
            _field(
                "trends_country",
                dcc.Dropdown(
                    id="trend-country-select",
                    options=[],
                    value=None,
                    disabled=True,
                    clearable=True,
                ),
            ),
            _field(
                "trends_historical_range",
                dcc.RangeSlider(
                    id="trend-year-range",
                    min=0,
                    max=1,
                    value=[0, 1],
                    marks={},
                    step=1,
                    disabled=True,
                    allowCross=False,
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
                class_name="trend-field trend-field-wide trend-range-field",
            ),
            _field(
                "trends_forecast_horizon",
                dcc.Dropdown(
                    id="trend-horizon-select",
                    options=[],
                    value=None,
                    disabled=True,
                    clearable=False,
                ),
            ),
        ],
        className="trend-controls",
    )


def _field(
    label_key: str,
    control: Component,
    *,
    element_id: str | None = None,
    class_name: str = "trend-field",
) -> Component:
    props = {"className": class_name}
    if element_id:
        props["id"] = element_id
    control_id = getattr(control, "id", None)
    is_group = control.__class__.__name__ in {"RangeSlider", "Slider"}
    label = text(ui_text(label_key, "es"), ui_text(label_key, "en"))
    if is_group and control_id:
        label_id = f"{control_id}-label"
        label_node = html.Span(label, id=label_id, className="trend-field-label")
        props.update({"role": "group", "aria-labelledby": label_id})
    else:
        label_node = html.Label(label, htmlFor=control_id)
    return html.Div(
        [label_node, control],
        **dash_attrs(props),
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
