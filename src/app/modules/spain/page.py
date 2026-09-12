from __future__ import annotations

import logging
import re
import time
from collections import Counter
from html import escape as escape_html
from typing import Any, cast

import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html
from dash.development.base_component import Component

from app.infrastructure.storage import supabase_public_image_url
from app.shared.components.loading import contextual_loading
from app.shared.components.page_structure import build_page_header
from app.shared.components.source_attribution import build_source_attribution
from app.shared.data.felgtbi.document_identity import clean_felgtbi_indicator_label
from app.shared.data.repository import (
    get_felgtbi_document_options,
    get_felgtbi_indicator_answers,
    get_felgtbi_indicators_by_document,
    get_felgtbi_years,
)
from app.web.i18n import dash_attrs, text, text_attrs
from app.web.navigation import build_navbar

logger = logging.getLogger(__name__)
PERCENT_TEXT_PATTERN = re.compile(r"(\d{1,3}(?:[,.]\d{1,2})?\s*%)")

TEXT_EN = {
    "Contenido": "Content",
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

# Derivado del gráfico 4, página 9, del PDF oficial: barras y cifras originales.
# Copia pública: https://observatoriolgtbi.com/wp-content/uploads/2023/12/
# lgtbi-informe-de-estado-socioeconomico-de-felgtbi.pdf
# SHA-256 PDF: 183a089db75066c83a7215fb3a78fc671f9862e71c08926bfe6ded1f4465aabf
# Recorte PDF [0.11, 439.58, 571.0, 772.14], escala 2: conserva las etiquetas
# que la importación anterior cortaba al aplicar un margen fijo de 24 puntos.
# Para evitar solapamientos se trasladan/escalan solo los XObjects de texto
# 418, 420, 424, 430 y 436: 12,50%; 5,70%; 6,30%; 5,90%; 16,70%.
# Escalas respectivas: 0.79365079, 0.77543424, 0.85297767, 0.89174938, 0.69444444;
# x respectivas: 485, 489, 487, 455, 488 pt; misma línea base y glifos originales.
# El XObject 438 (11,10% fuera de la barra Mujer Trans en el original) conserva
# posición y texto, pasando de blanco a negro; no se le deduce una categoría.
# SHA-256 PNG: 25bef484371847322fdf891ea43a520221d09460d40031394f254a614ecdbd30
_CORRECTED_FIGURE_ASSETS = {
    "2023/estado-socioecomico-lgtbi/orientacion-sexual-e-identidad-de-genero/"
    "figura-4-7d6c497ad3.webp": "/assets/img/felgtbi-socioeconomico-2023-figura-4.png",
}


def build_spain_layout(selection: dict[str, Any] | None = None) -> Component:
    available_years = _available_years()
    years = _year_options(available_years)
    initial_year = _resolve_initial_year(available_years)
    selection = selection if isinstance(selection, dict) else {}
    saved_year = _clean_year(selection.get("year"))
    if saved_year in available_years:
        initial_year = saved_year
    documents, initial_document = _document_selector_state(initial_year)
    if selection.get("document") in {option["value"] for option in documents}:
        initial_document = selection["document"]
    topics = (
        _indicator_options(get_felgtbi_indicators_by_document(initial_document, initial_year))
        if initial_document
        else []
    )
    initial_topic, _ = _resolve_topic_selection(topics, selection.get("topic"), trigger_id=None)

    return html.Div(
        [
            build_navbar(active="spain"),
            html.Main(
                [
                    build_page_header(
                        eyebrow=text("España", "Spain"),
                        title=text("Indicadores estatales LGBTIQ+", "National LGBTIQ+ indicators"),
                        description=text(
                            "Explora información estatal sobre derechos, percepción social y experiencias de las personas LGBTIQ+.",
                            "Explore national information on rights, social perception, and experiences of LGBTIQ+ people.",
                        ),
                        class_name="stats-header spain-header",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Span(
                                        "Año",
                                        id="spain-year-select-label",
                                        className="stats-control-label",
                                        **text_attrs("Año", "Year"),
                                    ),
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
                                role="group",
                                **dash_attrs({"aria-labelledby": "spain-year-select-label"}),
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        "Documento",
                                        id="spain-document-select-label",
                                        className="stats-control-label",
                                        **text_attrs("Documento", "Document"),
                                    ),
                                    dcc.RadioItems(
                                        id="spain-document-select",
                                        options=documents,
                                        value=initial_document,
                                        className="spain-document-radio spain-selection-control",
                                        inputClassName="spain-document-radio-input",
                                        labelClassName="spain-document-radio-label",
                                    ),
                                ],
                                className="stats-control-field spain-control-field spain-document-field",
                                role="group",
                                **dash_attrs({"aria-labelledby": "spain-document-select-label"}),
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        "Indicador",
                                        id="spain-topic-select-label",
                                        className="stats-control-label",
                                        **text_attrs("Indicador", "Indicator"),
                                    ),
                                    html.Div(
                                        [
                                            dcc.Dropdown(
                                                id="spain-topic-select",
                                                options=topics,
                                                value=initial_topic,
                                                clearable=False,
                                                className="spain-dropdown spain-topic-dropdown",
                                                disabled=not bool(
                                                    initial_document and initial_year
                                                ),
                                                placeholder="Selecciona un indicador",
                                            ),
                                            html.Fieldset(
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
                                                id="spain-section-navigation",
                                                disabled=False,
                                                className="spain-section-navigation",
                                            ),
                                        ],
                                        className="spain-topic-selector-row",
                                    ),
                                ],
                                className="stats-control-field spain-control-field spain-topic-field",
                                role="group",
                                **dash_attrs({"aria-labelledby": "spain-topic-select-label"}),
                            ),
                            html.P(
                                "Selecciona un documento.",
                                id="spain-indicator-summary",
                                className="stats-control-summary",
                                **text_attrs(
                                    "Selecciona un documento.",
                                    "Select a document.",
                                ),
                            ),
                        ],
                        className="stats-controls spain-controls",
                    ),
                    contextual_loading(
                        html.Section(
                            id="spain-visualization-grid",
                            className="stats-grid",
                            children=_spain_visualization_shell(),
                        ),
                        "processing_document",
                        element_id="spain-content-loading",
                    ),
                ],
                className="stats-shell app-page app-page-container",
            ),
        ]
    )


def register_spain_callbacks(app: Dash) -> None:
    app.clientside_callback(
        """
        function(year, document, topic, options) {
            if (!year || !document || !topic ||
                !(options || []).some(option => option.value === topic)) {
                return window.dash_clientside.no_update;
            }
            return {year: year, document: document, topic: topic};
        }
        """,
        Output("spain-selection", "data"),
        Input("spain-year-select", "value"),
        Input("spain-document-select", "value"),
        Input("spain-topic-select", "value"),
        Input("spain-topic-select", "options"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("spain-year-select", "placeholder"),
        Output("spain-topic-select", "placeholder"),
        Input("app-language-store", "data"),
    )
    def translate_spain_controls(language: str | None) -> tuple[str, str]:
        is_english = language == "en"
        return (
            "Select a year" if is_english else "Selecciona un año",
            "Select an indicator" if is_english else "Selecciona un indicador",
        )

    @app.callback(
        Output("spain-document-select", "options"),
        Output("spain-document-select", "value"),
        Input("spain-year-select", "value"),
        State("spain-document-select", "value"),
    )
    def update_document_selector(
        year: int | str | None,
        current_document: str | None,
    ) -> tuple[list[dict[str, str]], str | None]:
        options, default = _document_selector_state(year)
        selected = (
            current_document
            if current_document in {option["value"] for option in options}
            else default
        )
        return options, selected

    @app.callback(
        Output("spain-topic-select", "options"),
        Output("spain-topic-select", "value"),
        Output("spain-topic-select", "disabled"),
        Output("spain-indicator-summary", "children"),
        Output("spain-topic-prev", "disabled"),
        Output("spain-topic-next", "disabled"),
        Input("spain-document-select", "value"),
        Input("spain-year-select", "value"),
        Input("spain-topic-prev", "n_clicks"),
        Input("spain-topic-next", "n_clicks"),
        Input("spain-topic-select", "value"),
        running=[(Output("spain-section-navigation", "disabled"), True, False)],
    )
    def update_topic_selector(
        document_id: str | None,
        year: int | str | None,
        _previous_clicks: int | None,
        _next_clicks: int | None,
        current_code: str | None,
    ):
        if not year:
            return (
                [],
                None,
                True,
                text("Selecciona un año", "Select a year"),
                True,
                True,
            )
        document_options = _document_options(year)
        if not document_options:
            return (
                [],
                None,
                True,
                text("No hay documentos disponibles", "No documents available"),
                True,
                True,
            )
        if not document_id:
            return (
                [],
                None,
                True,
                text(
                    "Selecciona un documento",
                    "Select a document",
                ),
                True,
                True,
            )
        if document_id not in {option["value"] for option in document_options}:
            return (
                [],
                None,
                True,
                text(
                    "El documento seleccionado ya no está disponible",
                    "The selected document is no longer available",
                ),
                True,
                True,
            )
        indicators = get_felgtbi_indicators_by_document(document_id, year)
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
        next_disabled = selected_index < 0 or selected_index >= len(options) - 1
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
        Output("spain-source-attribution", "children"),
        Input("spain-document-select", "value"),
        Input("spain-year-select", "value"),
        Input("spain-topic-select", "value"),
    )
    def update_spain_grid(
        document_id: str | None,
        year: int | str | None,
        code: str | None,
    ):
        navigation_started_at = time.perf_counter()
        if not year:
            return _spain_view_state(
                empty=_empty_state("Sin año", "Selecciona un año para continuar."),
            )
        document_options = _document_options(year)
        if not document_options:
            return _spain_view_state(
                empty=_empty_state(
                    "No hay documentos disponibles", "No hay documentos disponibles"
                ),
            )
        if not document_id:
            return _spain_view_state(
                empty=_empty_state(
                    "Selecciona un documento",
                    "Selecciona un documento para cargar sus indicadores.",
                ),
            )
        if document_id not in {option["value"] for option in document_options}:
            return _spain_view_state(
                empty=_empty_state(
                    "El documento seleccionado ya no está disponible",
                    "El documento seleccionado ya no está disponible",
                ),
            )
        if not code:
            return _spain_view_state(
                empty=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
            )

        indicators = get_felgtbi_indicators_by_document(document_id, year)
        if not indicators:
            return _spain_view_state(
                empty=_empty_state("No hay secciones disponibles", "No hay secciones disponibles"),
            )

        indicator_codes = {indicator.code for indicator in indicators}
        if code not in indicator_codes:
            return _spain_view_state(
                empty=_empty_state(
                    "La sección seleccionada ya no está disponible",
                    "La sección seleccionada ya no está disponible",
                ),
            )

        document = get_felgtbi_indicator_answers(code or "", document_id=document_id)
        render_started_at = time.perf_counter()
        view_state = _spain_document_view_state(document)
        render_ms = (time.perf_counter() - render_started_at) * 1000
        logger.debug(
            "spain_section_navigation_rendered",
            extra={
                "collection": "Indicator_felgtbi",
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
                    html.Div(id="spain-source-attribution"),
                ],
                className="spain-content-frame",
            ),
            "stats-panel stats-panel-wide",
        ),
    ]


def _spain_view_state(
    *,
    empty: Any | None = None,
    report: Any | None = None,
    image_src: str | None = None,
    image_alt: str = "",
    figure: go.Figure | None = None,
    attribution: Any | None = None,
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
        attribution or [],
    )


def _spain_document_view_state(
    document: dict[str, Any] | None,
) -> tuple[Any, str, Any, str, str | None, str, str, go.Figure, str, Any]:
    if not document:
        return _spain_view_state(
            empty=_empty_state("Sin indicador", "Selecciona un indicador para ver sus datos."),
        )

    attribution = _felgtbi_document_attribution(document)

    if _content_html(document) or _has_structured_report_content(document):
        return _spain_view_state(
            report=_html_content_panel(document),
            attribution=attribution,
        )

    image_src = _figure_url(document)
    if image_src:
        return _spain_view_state(
            image_src=image_src,
            image_alt=_figure_alt_text(document),
            attribution=attribution,
        )

    return _spain_view_state(
        figure=_value_figure(document),
        attribution=attribution,
    )


def _felgtbi_document_attribution(document: dict[str, Any]) -> Component:
    report_title = str(document.get("report_title") or "").strip() or None
    document_name = report_title or str(document.get("original_filename") or "").strip() or None
    raw_year = document.get("year")
    try:
        year = int(raw_year) if raw_year not in (None, "") else None
    except TypeError, ValueError:
        year = None

    figure_data = document.get("figure")
    figure = figure_data if isinstance(figure_data, dict) else {}
    figure_number = str(figure.get("number") or "").strip()
    figure_caption = str(figure.get("caption") or "").strip()
    figure_source = str(figure.get("source") or "").strip()
    figure_parts = [part for part in (figure_number, figure_caption) if part]
    if figure_source:
        figure_parts.append(f"Fuente original indicada en el informe: {figure_source}")

    custom_text: tuple[str, str] | None = None
    if report_title:
        year_label = f", {year}" if year else ""
        figure_label = f", {' · '.join(figure_parts)}" if figure_parts else ""
        original_source_en = (
            f" Original source cited in the report: {figure_source}." if figure_source else ""
        )
        figure_en = ""
        if figure_number or figure_caption:
            figure_en = f", {' · '.join(part for part in (figure_number, figure_caption) if part)}"
        custom_text = (
            (
                f"Fuente: FELGTBI+, “{report_title}”{year_label}{figure_label}. "
                "Visualización adaptada por RainbowLens Datahub."
            ),
            (
                f"Source: FELGTBI+, “{report_title}”{year_label}{figure_en}. "
                f"Visualisation adapted by RainbowLens Datahub.{original_source_en}"
            ),
        )

    return build_source_attribution(
        "felgtbi",
        source_name=report_title,
        year=year,
        source_url=str(document.get("source_url") or "").strip() or None,
        custom_text=custom_text,
        document_id=document_name,
        figure=" · ".join(figure_parts) or None,
        accessed_at=str(document.get("source_accessed_at") or "").strip() or None,
        compact=True,
    )


def _document_options(year: int | str | None = None) -> list[dict[str, str]]:
    clean_year = _clean_year(year)
    if clean_year is None:
        return []
    return get_felgtbi_document_options(year=clean_year)


def _available_years() -> list[int]:
    years = {
        clean_year for year in get_felgtbi_years() if (clean_year := _clean_year(year)) is not None
    }
    return sorted(years, reverse=True)


def _year_options(years: list[int] | None = None) -> list[dict[str, Any]]:
    available_years = _available_years() if years is None else sorted(set(years), reverse=True)
    return [{"label": str(year), "value": year} for year in available_years]


def _resolve_initial_year(years: list[int]) -> int | None:
    return max(years, default=None)


def _document_selector_state(
    year: int | str | None,
) -> tuple[list[dict[str, str]], str | None]:
    documents = _document_options(year)
    selected_document = documents[0]["value"] if len(documents) == 1 else None
    return documents, selected_document


def _clean_year(year: int | str | None) -> int | None:
    if year in (None, ""):
        return None
    try:
        return int(year)
    except TypeError, ValueError:
        return None


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
    counts = Counter(option["label"] for option in options)
    for index, option in enumerate(options, start=1):
        if counts[option["label"]] > 1:
            # Un encabezado oficial puede corresponder a varias secciones distintas.
            # Se muestra su posición sin cambiar el identificador canónico.
            option["label"] = f"{option['label']} · {index}/{len(options)}"
            option["title"] = option["label"]
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
    if not current:
        return values[0], "ok"
    selection_removed = current not in values
    if selection_removed:
        return values[0], "removed"

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
    if selection_status == "unselected":
        return text(
            f"{total} indicadores disponibles. Selecciona un indicador.",
            f"{total} indicators available. Select an indicator.",
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
    del value
    return clean_felgtbi_indicator_label(
        title or section or "Indicador FELGTBI+",
        report_title,
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
        section_children.append(
            html.H2(text("Contenido del informe", "Report content"))
            if section == "Contenido del informe"
            else html.H2(section)
        )
    section_children.append(html.Article(article_children, className="report-subsection"))
    return html.Div(
        html.Section(section_children, className="report-section"),
        className="spain-report-html",
    )


def _figure_component(document: dict[str, Any]) -> Any | None:
    url = _figure_url(document)
    figure = _dict_or_empty(document.get("figure"))
    caption = str(
        figure.get("caption") or document.get("figure_caption") or figure.get("title") or ""
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
            # Dash usa el id para renovar el nodo; key es una propiedad reservada de React.
            id={"type": "spain-report-figure", "source": url},
            src=None,
            alt=alt_text,
            width=width,
            height=height,
            className="report-figure-image",
            **dash_attrs({"data-lazy-src": url}),
        ),
        html.Div(
            [
                html.Strong(
                    "Imagen no disponible",
                    **text_attrs("Imagen no disponible", "Image unavailable"),
                ),
                html.Span(
                    "No se ha podido cargar la figura desde el almacenamiento.",
                    **text_attrs(
                        "No se ha podido cargar la figura desde el almacenamiento.",
                        "The figure could not be loaded from storage.",
                    ),
                ),
            ],
            className="report-figure-placeholder report-figure-load-error",
            hidden=True,
        ),
    ]
    if caption or source:
        caption_children: list[Any] = []
        if caption:
            caption_children.append(html.Span(caption))
        if source:
            clean_source = re.sub(r"^\s*Fuente\s*:\s*", "", source, flags=re.IGNORECASE)
            caption_children.append(
                html.Small(
                    [text("Fuente", "Source"), f": {clean_source}"],
                    className="report-figure-source",
                )
            )
        children.append(html.Figcaption(caption_children))
    return html.Figure(children, className="report-figure")


def _figure_placeholder_component(
    document: dict[str, Any] | None, *, caption: str = ""
) -> Any | None:
    if not _has_figure_metadata(document):
        return None
    title = "Imagen no disponible"
    children: list[Any] = [
        html.Div(
            [
                html.Strong(title, **text_attrs(title, "Image unavailable")),
                html.Span(
                    "La imagen no está disponible temporalmente.",
                    **text_attrs(
                        "La imagen no está disponible temporalmente.",
                        "The image is temporarily unavailable.",
                    ),
                ),
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
    return bool(figure or document.get("figure_caption") or figure.get("storage_path"))


def _figure_caption_text(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return ""
    figure = _dict_or_empty(document.get("figure"))
    return str(
        figure.get("caption") or document.get("figure_caption") or figure.get("title") or ""
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
    storage_path = str(figure.get("storage_path") or "").strip()
    if storage_path in _CORRECTED_FIGURE_ASSETS:
        return _CORRECTED_FIGURE_ASSETS[storage_path]
    return supabase_public_image_url(figure.get("storage_path"))


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except TypeError, ValueError:
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
        return escape_html(content_html)

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


def _answers(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    answers = document.get("answers")
    if not isinstance(answers, list):
        return []
    return [answer for answer in answers if isinstance(answer, dict)]


def _content_html(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return ""
    return str(document.get("content_html") or "").strip()


def _panel(title: str, child: Any, class_name: str = "stats-panel") -> Component:
    return html.Section(
        [html.H2(title, **text_attrs(title, TEXT_EN.get(title, title))), child],
        className=class_name,
    )


def _empty_state(title: str, detail: str) -> Component:
    return html.Div(
        [
            html.H2(title, **text_attrs(title, TEXT_EN.get(title, title))),
            html.P(detail, **text_attrs(detail, TEXT_EN.get(detail, detail))),
        ],
        className="stats-empty-state",
    )
