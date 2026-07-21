from __future__ import annotations

import logging
import re
import time
from typing import Any, cast

from dash import Dash, Input, Output, State, ctx, dcc, html
from dash.development.base_component import Component
import plotly.graph_objects as go

from app.analytics.repository import (
    get_felgtbi_document_options,
    get_felgtbi_document_years,
    get_felgtbi_indicator_answers,
    get_felgtbi_indicators_by_document,
    get_spain_collection_options,
)
from app.dash.i18n import dash_attrs, text, text_attrs
from app.dash.layouts.navigation import build_navbar
from app.storage import supabase_public_image_url

logger = logging.getLogger(__name__)
PERCENT_TEXT_PATTERN = re.compile(r"(\d{1,3}(?:[,.]\d{1,2})?\s*%)")

TEXT_EN = {
    "Contenido": "Content",
    "Detalle": "Detail",
    "No hay información disponible": "No information available",
    "Todavía no hay información estatal para mostrar.": "There is no national information to show yet.",
    "Sin categoría": "No category selected",
    "Selecciona una categoría para empezar.": "Select a category to begin.",
    "Sin año": "No year selected",
    "Selecciona un año para continuar.": "Select a year to continue.",
    "Datos no disponibles": "Data unavailable",
    "Todavía no hay información disponible para esta categoría y año.": "There is no information available for this category and year yet.",
    "Sin resumen": "No summary",
    "Selecciona una sección para ver sus resultados.": "Select a section to view its results.",
    "Sin contenido": "No content",
    "No hay contenido disponible para este indicador.": "No content is available for this indicator.",
    "Sin indicador": "No indicator selected",
    "Selecciona un indicador para ver sus datos.": "Select an indicator to view its data.",
    "Documento": "Document",
    "Selecciona un documento": "Select a document",
    "Selecciona un documento para cargar sus indicadores.": "Select a document to load its indicators.",
    "No hay documentos disponibles": "No documents available",
    "El documento seleccionado ya no está disponible": "The selected document is no longer available",
    "No hay fuentes de datos": "No data sources",
    "No se han encontrado colecciones españolas disponibles.": "No Spanish collections were found.",
    "No hay secciones disponibles": "No sections available",
    "La sección seleccionada ya no está disponible": "The selected section is no longer available",
    "Anterior": "Previous",
    "Siguiente": "Next",
}

SPAIN_SLOT_CLASS = "spain-content-slot"
SPAIN_SLOT_HIDDEN_CLASS = "spain-content-slot is-hidden"
SPAIN_IMAGE_CLASS = "spain-pdf-figure spain-content-slot"
SPAIN_IMAGE_HIDDEN_CLASS = "spain-pdf-figure spain-content-slot is-hidden"
SPAIN_GRAPH_CLASS = "spain-section-graph spain-content-slot"
SPAIN_GRAPH_HIDDEN_CLASS = "spain-section-graph spain-content-slot is-hidden"


def build_spain_layout() -> Component:
    sources = _source_options()
    initial_source = sources[0]["value"] if sources else None
    documents = _document_options(initial_source)
    initial_document = documents[0]["value"] if documents else None
    years = _year_options(initial_source, initial_document)
    initial_year = years[0]["value"] if years else None

    return html.Div(
        [
            build_navbar(active="spain"),
            html.Main(
                [
                    html.Header(
                        [
                            html.P("España", className="stats-eyebrow", **text_attrs("España", "Spain")),
                            html.H1(text("Indicadores estatales LGBTIQ+", "National LGBTIQ+ indicators")),
                            html.P(
                                text(
                                    "Explora información estatal sobre derechos, percepción social y experiencias de las personas LGBTIQ+.",
                                    "Explore national information on rights, social perception, and experiences of LGBTIQ+ people.",
                                ),
                                className="stats-lead",
                            ),
                        ],
                        className="stats-header",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        "Fuente de datos",
                                        htmlFor="spain-source-select",
                                        **text_attrs("Fuente de datos", "Data source"),
                                    ),
                                    dcc.Dropdown(
                                        id="spain-source-select",
                                        options=sources,
                                        value=initial_source,
                                        clearable=False,
                                        className="spain-dropdown",
                                        disabled=not bool(sources),
                                        placeholder="Selecciona una fuente",
                                    ),
                                ],
                                className="stats-control-field spain-control-field spain-control-field-wide",
                            ),
                            html.Div(
                                [
                                    html.Label("Documento", htmlFor="spain-category-select", **text_attrs("Documento", "Document")),
                                    dcc.Dropdown(
                                        id="spain-category-select",
                                        options=documents,
                                        value=initial_document,
                                        clearable=False,
                                        className="spain-dropdown",
                                        disabled=not bool(documents),
                                        placeholder="Selecciona un documento",
                                    ),
                                ],
                                className="stats-control-field spain-control-field",
                            ),
                            html.Div(
                                [
                                    html.Label("Año", htmlFor="spain-year-select", **text_attrs("Año", "Year")),
                                    dcc.Dropdown(
                                        id="spain-year-select",
                                        options=years,
                                        value=initial_year,
                                        clearable=False,
                                        className="spain-dropdown",
                                        disabled=not bool(years),
                                        placeholder="Selecciona un año",
                                    ),
                                ],
                                className="stats-control-field spain-control-field spain-year-field",
                            ),
                            html.Div(
                                [
                                    html.Label("Indicador", htmlFor="spain-topic-select", **text_attrs("Indicador", "Indicator")),
                                    html.Div(
                                        [
                                            dcc.Dropdown(
                                                id="spain-topic-select",
                                                options=[],
                                                value=None,
                                                clearable=False,
                                                className="spain-dropdown spain-topic-dropdown",
                                                disabled=not bool(initial_source and initial_document and initial_year),
                                                placeholder="Selecciona un indicador",
                                            ),
                                            html.Div(
                                                [
                                                    html.Button(
                                                        text("Anterior", "Previous"),
                                                        id="spain-topic-prev",
                                                        n_clicks=0,
                                                        disabled=True,
                                                        className="spain-nav-button",
                                                        type="button",
                                                    ),
                                                    html.Button(
                                                        text("Siguiente", "Next"),
                                                        id="spain-topic-next",
                                                        n_clicks=0,
                                                        disabled=True,
                                                        className="spain-nav-button",
                                                        type="button",
                                                    ),
                                                ],
                                                className="spain-section-navigation",
                                            ),
                                        ],
                                        className="spain-topic-selector-row",
                                    ),
                                ],
                                className="stats-control-field spain-control-field spain-topic-field",
                            ),
                            html.P(
                                "Selecciona un documento para cargar sus indicadores.",
                                id="spain-indicator-summary",
                                className="stats-control-summary",
                                **text_attrs(
                                    "Selecciona un documento para cargar sus indicadores.",
                                    "Select a document to load its indicators.",
                                ),
                            ),
                        ],
                        className="stats-controls spain-controls",
                    ),
                    html.Section(
                        id="spain-visualization-grid",
                        className="stats-grid",
                        children=_spain_visualization_shell(),
                    ),
                ],
                className="stats-shell",
            ),
        ]
    )


def register_spain_callbacks(app: Dash) -> None:
    @app.callback(
        Output("spain-category-select", "options"),
        Output("spain-category-select", "value"),
        Output("spain-category-select", "disabled"),
        Input("spain-source-select", "value"),
        State("spain-category-select", "value"),
    )
    def update_category_selector(collection_name: str | None, current_document: str | None):
        documents = _document_options(collection_name)
        if not documents:
            return [], None, True
        values = {option["value"] for option in documents}
        value = current_document if current_document in values else documents[0]["value"]
        return documents, value, False

    @app.callback(
        Output("spain-year-select", "options"),
        Output("spain-year-select", "value"),
        Output("spain-year-select", "disabled"),
        Input("spain-source-select", "value"),
        Input("spain-category-select", "value"),
        State("spain-year-select", "value"),
    )
    def update_year_selector(collection_name: str | None, document_id: str | None, current_year: int | str | None):
        years = _year_options(collection_name, document_id)
        if not years:
            return [], None, True
        values = {option["value"] for option in years}
        clean_current_year = _int_or_original(current_year)
        value = clean_current_year if clean_current_year in values else years[0]["value"]
        return years, value, False

    @app.callback(
        Output("spain-topic-select", "options"),
        Output("spain-topic-select", "value"),
        Output("spain-topic-select", "disabled"),
        Output("spain-indicator-summary", "children"),
        Output("spain-topic-prev", "disabled"),
        Output("spain-topic-next", "disabled"),
        Input("spain-source-select", "value"),
        Input("spain-category-select", "value"),
        Input("spain-year-select", "value"),
        Input("spain-topic-prev", "n_clicks"),
        Input("spain-topic-next", "n_clicks"),
        State("spain-topic-select", "value"),
    )
    def update_topic_selector(
        collection_name: str | None,
        document_id: str | None,
        year: int | str | None,
        _previous_clicks: int | None,
        _next_clicks: int | None,
        current_code: str | None,
    ):
        if not collection_name:
            return [], None, True, text("No hay fuentes de datos disponibles.", "No data sources are available."), True, True
        document_options = _document_options(collection_name)
        if not document_options:
            return [], None, True, text("No hay documentos disponibles", "No documents available"), True, True
        if not document_id:
            return [], None, True, text("Selecciona un documento para cargar sus indicadores.", "Select a document to load its indicators."), True, True
        if document_id not in {option["value"] for option in document_options}:
            return [], None, True, text("El documento seleccionado ya no está disponible", "The selected document is no longer available"), True, True
        if not year:
            return [], None, True, text("Selecciona un año para cargar sus indicadores.", "Select a year to load its indicators."), True, True

        indicators = get_felgtbi_indicators_by_document(document_id, year, collection_name)
        options = _indicator_options(indicators)
        selected_code, selection_status = _resolve_topic_selection(
            options,
            current_code,
            trigger_id=ctx.triggered_id,
        )
        if not options:
            return (
                [],
                None,
                True,
                text("No hay secciones disponibles", "No sections available"),
                True,
                True,
            )
        selected_index = _selected_option_index(options, selected_code)
        previous_disabled = selected_index <= 0
        next_disabled = selected_index >= len(options) - 1
        summary = _topic_summary(document_id, year, len(options), selection_status)
        return options, selected_code, False, summary, previous_disabled, next_disabled

    @app.callback(
        Output("spain-content-empty", "children"),
        Output("spain-content-empty", "className"),
        Output("spain-report-content", "children"),
        Output("spain-report-content", "className"),
        Output("spain-section-image", "src"),
        Output("spain-section-image", "alt"),
        Output("spain-section-image", "className"),
        Output("spain-section-graph", "figure"),
        Output("spain-section-graph", "className"),
        Output("spain-detail-content", "children"),
        Input("spain-source-select", "value"),
        Input("spain-category-select", "value"),
        Input("spain-year-select", "value"),
        Input("spain-topic-select", "value"),
    )
    def update_spain_grid(
        collection_name: str | None,
        document_id: str | None,
        year: int | str | None,
        code: str | None,
    ):
        navigation_started_at = time.perf_counter()
        if not collection_name:
            return _spain_view_state(
                empty=_empty_state("No hay fuentes de datos", "No se han encontrado colecciones españolas disponibles."),
                detail=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
            )
        document_options = _document_options(collection_name)
        if not document_options:
            return _spain_view_state(
                empty=_empty_state("No hay documentos disponibles", "No hay documentos disponibles"),
                detail=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
            )
        if not document_id:
            return _spain_view_state(
                empty=_empty_state("No hay documentos disponibles", "Selecciona un documento para cargar sus indicadores."),
                detail=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
            )
        if document_id not in {option["value"] for option in document_options}:
            return _spain_view_state(
                empty=_empty_state(
                    "El documento seleccionado ya no está disponible",
                    "El documento seleccionado ya no está disponible",
                ),
                detail=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
            )
        if not year:
            return _spain_view_state(
                empty=_empty_state("Sin año", "Selecciona un año para continuar."),
                detail=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
            )

        indicators = get_felgtbi_indicators_by_document(document_id, year, collection_name)
        if not indicators:
            return _spain_view_state(
                empty=_empty_state("No hay secciones disponibles", "No hay secciones disponibles"),
                detail=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
            )

        indicator_codes = {indicator.code for indicator in indicators}
        if code not in indicator_codes:
            return _spain_view_state(
                empty=_empty_state(
                    "La sección seleccionada ya no está disponible",
                    "La sección seleccionada ya no está disponible",
                ),
                detail=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
            )

        document = get_felgtbi_indicator_answers(code or "", collection_name, document_id=document_id)
        render_started_at = time.perf_counter()
        view_state = _spain_document_view_state(document)
        render_ms = (time.perf_counter() - render_started_at) * 1000
        logger.debug(
            "spain_section_navigation_rendered",
            extra={
                "collection": collection_name,
                "document": document_id,
                "code": code,
                "render_ms": round(render_ms, 2),
                "total_navigation_ms": round(
                    (time.perf_counter() - navigation_started_at) * 1000,
                    2,
                ),
            },
        )
        return view_state


def _spain_visualization_shell() -> list[Any]:
    return [
        _panel(
            "Contenido",
            html.Div(
                [
                    html.Div(
                        _empty_state(
                            "No hay información disponible",
                            "Todavía no hay información estatal para mostrar.",
                        ),
                        id="spain-content-empty",
                        className=SPAIN_SLOT_CLASS,
                    ),
                    html.Div(
                        id="spain-report-content",
                        className=SPAIN_SLOT_HIDDEN_CLASS,
                    ),
                    html.Img(
                        id="spain-section-image",
                        src=None,
                        alt="",
                        className=SPAIN_IMAGE_HIDDEN_CLASS,
                    ),
                    dcc.Graph(
                        id="spain-section-graph",
                        figure=_value_figure(None),
                        config={"displaylogo": False},
                        className=SPAIN_GRAPH_HIDDEN_CLASS,
                    ),
                ],
                className="spain-content-frame",
            ),
            "stats-panel stats-panel-wide",
        ),
        _panel(
            "Detalle",
            html.Div(
                _empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
                id="spain-detail-content",
                className="spain-detail-content",
            ),
        ),
    ]


def _spain_view_state(
    *,
    empty: Any | None = None,
    report: Any | None = None,
    image_src: str | None = None,
    image_alt: str = "",
    figure: go.Figure | None = None,
    detail: Any | None = None,
) -> tuple[Any, str, Any, str, str | None, str, str, go.Figure, str, Any]:
    has_empty = empty is not None
    has_report = report is not None
    has_image = bool(image_src)
    has_graph = figure is not None

    return (
        empty or [],
        SPAIN_SLOT_CLASS if has_empty else SPAIN_SLOT_HIDDEN_CLASS,
        report or [],
        SPAIN_SLOT_CLASS if has_report else SPAIN_SLOT_HIDDEN_CLASS,
        image_src if has_image else None,
        image_alt if has_image else "",
        SPAIN_IMAGE_CLASS if has_image else SPAIN_IMAGE_HIDDEN_CLASS,
        figure or _value_figure(None),
        SPAIN_GRAPH_CLASS if has_graph else SPAIN_GRAPH_HIDDEN_CLASS,
        detail or _empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
    )


def _spain_document_view_state(document: dict[str, Any] | None) -> tuple[Any, str, Any, str, str | None, str, str, go.Figure, str, Any]:
    if not document:
        return _spain_view_state(
            empty=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
            detail=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
        )

    detail = _detail_panel_content(document)
    if _content_html(document) or _has_structured_report_content(document):
        return _spain_view_state(report=_html_content_panel(document), detail=detail)

    image_src = _figure_url(document)
    if image_src:
        return _spain_view_state(
            image_src=image_src,
            image_alt=_figure_alt_text(document),
            detail=detail,
        )

    return _spain_view_state(figure=_value_figure(document), detail=detail)


def _source_options() -> list[dict[str, str]]:
    return get_spain_collection_options()


def _document_options(collection_name: str | None = None) -> list[dict[str, str]]:
    return get_felgtbi_document_options(collection_name)


def _year_options(collection_name: str | None = None, document_id: str | None = None) -> list[dict[str, Any]]:
    return [{"label": str(year), "value": year} for year in get_felgtbi_document_years(document_id, collection_name)]


def _int_or_original(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _indicator_options(indicators: list[Any]) -> list[dict[str, str]]:
    options = []
    for indicator in indicators:
        label = _indicator_option_label(
            indicator.question,
            indicator.specific_category,
            indicator.value,
            report_title=indicator.report_title,
        )
        options.append({"label": label, "value": indicator.code, "title": label})
    return options


def _resolve_topic_selection(
    options: list[dict[str, str]],
    current_code: str | None,
    *,
    trigger_id: str | dict[str, Any] | None,
) -> tuple[str | None, str]:
    if not options:
        return None, "empty"

    values = [str(option["value"]) for option in options if option.get("value")]
    if not values:
        return None, "empty"

    current = str(current_code or "").strip()
    selection_removed = bool(current and current not in values)
    if current not in values:
        current = values[0]

    index = values.index(current)
    if trigger_id == "spain-topic-prev":
        index = max(0, index - 1)
    elif trigger_id == "spain-topic-next":
        index = min(len(values) - 1, index + 1)

    return values[index], "removed" if selection_removed else "ok"


def _selected_option_index(options: list[dict[str, str]], selected_code: str | None) -> int:
    values = [str(option["value"]) for option in options if option.get("value")]
    try:
        return values.index(str(selected_code or ""))
    except ValueError:
        return -1


def _topic_summary(_document_id: str, year: int | str, total: int, selection_status: str) -> Any:
    if selection_status == "removed":
        return text(
            "La sección seleccionada ya no está disponible",
            "The selected section is no longer available",
        )
    return text(
        f"{year}: {total} indicadores disponibles.",
        f"{year}: {total} indicators available.",
    )


def _indicator_option_label(
    title: str,
    section: str,
    value: float | None,
    *,
    report_title: str = "",
) -> str:
    clean_section = title or section or "Indicador FELGTBI+"
    report = str(report_title or "").strip()
    value_label = f" - {_format_percent(value)}" if value is not None else ""
    if report and report not in clean_section:
        return f"{report} · {clean_section}{value_label}"
    return f"{clean_section}{value_label}"


def _felgtbi_panels(document: dict[str, Any] | None) -> list[Any]:
    if _content_html(document) or _has_structured_report_content(document):
        return [
            _panel("Contenido", _html_content_panel(document), "stats-panel stats-panel-wide"),
        ]
    return [
        _panel("Contenido", _value_panel_content(document), "stats-panel stats-panel-wide"),
        _panel("Detalle", _detail_panel_content(document)),
    ]


def _detail_panel_content(document: dict[str, Any] | None) -> Any:
    if not document:
        return _empty_state("Sin indicador", "Selecciona un indicador para ver sus datos.")
    return html.Div(
        [
            _summary_content(document),
            _detail_table(document),
        ],
        className="spain-detail-content",
    )


def _summary_content(document: dict[str, Any] | None) -> Component:
    if not document:
        return _empty_state("Sin resumen", "Selecciona una sección para ver sus resultados.")
    paragraphs = _summary_paragraphs(document)
    return html.Div(
        [
            html.H3(str(document.get("report_title") or "Informe FELGTBI+")),
            *[html.P(paragraph) for paragraph in paragraphs],
        ],
        className="spain-summary",
    )


def _summary_paragraphs(document: dict[str, Any]) -> list[str]:
    section = str(document.get("section_title") or document.get("specific_category") or "").strip()
    subsection = str(document.get("subsection_title") or document.get("question") or "").strip()
    intro = " ".join(part for part in [section, subsection] if part)
    paragraphs = document.get("paragraphs")
    summary: list[str] = [intro] if intro else []
    if isinstance(paragraphs, list):
        summary.extend(
            str(paragraph or "").strip()
            for paragraph in paragraphs[:2]
            if str(paragraph or "").strip()
        )
    if len(summary) > 1:
        return summary[:3]
    description = str(document.get("description") or "").strip()
    if description:
        summary.append(description)
    return summary or ["Selecciona una sección para consultar el análisis del informe."]


def _value_panel_content(document: dict[str, Any] | None) -> Any:
    image_source = _figure_url(document)
    if image_source:
        return html.Img(
            src=image_source,
            alt="Gráfica asociada al indicador",
            className="spain-pdf-figure",
        )
    figure_placeholder = _figure_placeholder_component(document)
    if figure_placeholder is not None:
        return figure_placeholder
    return dcc.Graph(
        figure=_value_figure(document),
        config={"displaylogo": False},
    )


def _html_content_panel(document: dict[str, Any] | None) -> Any:
    structured_content = _structured_report_content(document)
    if structured_content is not None:
        return structured_content

    content_html = _content_html(document)
    if not content_html:
        return _empty_state("Sin contenido", "No hay contenido disponible para este indicador.")
    return dcc.Markdown(
        _sanitize_report_html(content_html),
        dangerously_allow_html=True,
        className="spain-report-html",
    )


def _has_structured_report_content(document: dict[str, Any] | None) -> bool:
    if not isinstance(document, dict):
        return False
    return bool(
        document.get("section_title")
        or document.get("subsection_title")
        or document.get("paragraphs")
        or document.get("paragraphs_before_figure")
        or document.get("paragraphs_after_figure")
        or document.get("figure")
        or _figure_url(document)
    )


def _structured_report_content(document: dict[str, Any] | None) -> Any | None:
    if not isinstance(document, dict):
        return None

    section = str(document.get("section_title") or document.get("specific_category") or "").strip()
    subsection = str(document.get("subsection_title") or document.get("question") or "").strip()
    before = _text_list(document.get("paragraphs_before_figure"))
    after = _text_list(document.get("paragraphs_after_figure"))
    paragraphs = _text_list(document.get("paragraphs")) if not before and not after else []
    figure = _figure_component(document)

    if not any([section, subsection, before, after, paragraphs, figure is not None]):
        return None

    article_children: list[Any] = []
    if subsection:
        article_children.append(html.H3(subsection))
    for paragraph in before or paragraphs:
        article_children.append(html.P(_paragraph_children(paragraph)))
    if figure is not None:
        article_children.append(figure)
    for paragraph in after:
        article_children.append(html.P(_paragraph_children(paragraph)))

    section_children: list[Any] = []
    if section:
        section_children.append(html.H2(section))
    section_children.append(html.Article(article_children, className="report-subsection"))
    return html.Div(
        html.Section(section_children, className="report-section"),
        className="spain-report-html",
    )


def _figure_component(document: dict[str, Any]) -> Any | None:
    url = _figure_url(document)
    figure = _dict_or_empty(document.get("figure"))
    caption = str(
        figure.get("caption")
        or document.get("figure_caption")
        or figure.get("title")
        or ""
    ).strip()
    alt_text = str(
        figure.get("alt_text")
        or figure.get("title")
        or caption
        or document.get("subsection_title")
        or "Figura del informe FELGTBI+"
    ).strip()
    source = str(figure.get("source") or "").strip()
    width = _positive_int(figure.get("width"))
    height = _positive_int(figure.get("height"))
    if not url:
        return _figure_placeholder_component(document, caption=caption)

    children: list[Any] = [
        html.Img(
            src=None,
            alt=alt_text,
            width=width,
            height=height,
            className="report-figure-image",
            **dash_attrs({"data-lazy-src": url}),
        ),
        html.Div(
            [
                html.Strong("Imagen no disponible"),
                html.Span("No se ha podido cargar la figura desde el almacenamiento."),
            ],
            className="report-figure-placeholder report-figure-load-error",
            hidden=True,
        )
    ]
    if caption or source:
        caption_children: list[Any] = []
        if caption:
            caption_children.append(html.Span(caption))
        if source:
            caption_children.append(html.Small(source, className="report-figure-source"))
        children.append(html.Figcaption(caption_children))
    return html.Figure(children, className="report-figure")


def _figure_placeholder_component(document: dict[str, Any] | None, *, caption: str = "") -> Any | None:
    if not _has_figure_metadata(document):
        return None
    title = "Imagen no disponible"
    children: list[Any] = [
        html.Div(
            [
                html.Strong(title),
                html.Span("La imagen no está disponible temporalmente."),
            ],
            className="report-figure-placeholder",
        )
    ]
    caption_text = caption or _figure_caption_text(document)
    if caption_text:
        children.append(html.Figcaption(caption_text))
    return html.Figure(children, className="report-figure report-figure-missing")


def _has_figure_metadata(document: dict[str, Any] | None) -> bool:
    if not isinstance(document, dict):
        return False
    figure = _dict_or_empty(document.get("figure"))
    return bool(
        figure
        or document.get("figure_caption")
        or figure.get("storage_path")
    )


def _figure_caption_text(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return ""
    figure = _dict_or_empty(document.get("figure"))
    return str(
        figure.get("caption")
        or document.get("figure_caption")
        or figure.get("title")
        or ""
    ).strip()


def _figure_alt_text(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return "Figura del informe FELGTBI+"
    figure = _dict_or_empty(document.get("figure"))
    return str(
        figure.get("alt_text")
        or figure.get("title")
        or _figure_caption_text(document)
        or document.get("subsection_title")
        or "Figura del informe FELGTBI+"
    ).strip()


def _figure_url(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return ""
    figure = _dict_or_empty(document.get("figure"))
    return supabase_public_image_url(figure.get("storage_path"))


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _paragraph_children(text: str) -> list[Any]:
    children: list[Any] = []
    position = 0
    for match in PERCENT_TEXT_PATTERN.finditer(text):
        if match.start() > position:
            children.append(text[position : match.start()])
        children.append(html.Strong(match.group(0)))
        position = match.end()
    if position < len(text):
        children.append(text[position:])
    return children or [text]


def _sanitize_report_html(content_html: str) -> str:
    try:
        import bleach
    except ImportError:
        return content_html

    allowed_tags = [
        "section",
        "article",
        "header",
        "h1",
        "h2",
        "h3",
        "h4",
        "p",
        "strong",
        "em",
        "figure",
        "img",
        "figcaption",
        "ul",
        "ol",
        "li",
        "div",
        "span",
        "a",
    ]
    allowed_attributes = {
        "*": ["class"],
        "a": ["href", "title", "target", "rel", "class"],
        "img": ["src", "alt", "loading", "width", "height", "class"],
    }
    return bleach.clean(
        content_html,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=["http", "https"],
        strip=True,
    )


def _value_figure(document: dict[str, Any] | None) -> go.Figure:
    rows = [
        answer
        for answer in _answers(document)
        if isinstance(answer.get("percentage", answer.get("value")), (int, float))
    ]
    figure = go.Figure()
    if rows:
        figure.add_trace(
            go.Bar(
                x=[str(row.get("answer") or "Total") for row in rows],
                y=[row.get("percentage", row.get("value")) for row in rows],
                marker={"color": "#155f52"},
                customdata=[row.get("page") or "" for row in rows],
                hovertemplate="<b>%{x}</b><br>%{y:.2f}%<br>Página: %{customdata}<extra></extra>",
            )
        )
    else:
        figure.add_annotation(
            text="No hay valores numéricos para este indicador.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 16, "color": "#5f6672"},
        )
    figure.update_layout(
        margin={"l": 45, "r": 20, "t": 20, "b": 65},
        xaxis={"title": "Respuesta"},
        yaxis={"title": "Porcentaje", "range": [0, 100]},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        showlegend=False,
    )
    return figure


def _detail_table(document: dict[str, Any] | None) -> Component:
    if not document:
        return _empty_state("Sin indicador", "Selecciona un indicador para ver sus datos.")
    rows = [
        ("Categoría", document.get("category")),
        ("Sección", document.get("specific_category")),
        ("Subsección", document.get("subsection_title") or document.get("question")),
        ("Figura", document.get("figure_caption")),
        ("Tipo de informe", document.get("report_type")),
    ]
    table = html.Table(
        [
            html.Tbody(
                [
                    html.Tr([html.Th(str(label)), html.Td(str(value or "-"))])
                    for label, value in rows
                ]
            )
        ],
        className="spain-detail-table",
    )
    return html.Div(table, className="spain-detail-scroll")


def _answers(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    answers = document.get("answers")
    if not isinstance(answers, list):
        return []
    return [answer for answer in answers if isinstance(answer, dict)]


def _format_percent(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}%"
    return "-"


def _content_html(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return ""
    return str(document.get("content_html") or "").strip()


def _panel(title: str, child: Any, class_name: str = "stats-panel") -> Component:
    return html.Section([html.H2(title, **text_attrs(title, TEXT_EN.get(title, title))), child], className=class_name)


def _empty_state(title: str, detail: str) -> Component:
    return html.Div(
        [
            html.H2(title, **text_attrs(title, TEXT_EN.get(title, title))),
            html.P(detail, **text_attrs(detail, TEXT_EN.get(detail, detail))),
        ],
        className="stats-empty-state",
    )
