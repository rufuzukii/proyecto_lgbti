from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import plotly.graph_objects as go

from app.analytics.repository import (
    assert_analytics_databases_available,
    get_felgtbi_categories,
    get_felgtbi_indicator_answers,
    get_felgtbi_indicators_by_category,
    get_felgtbi_years,
)
from app.dash.compat import Dash, Input, Output, dcc, html
from app.dash.layouts.navigation import build_navbar

PERCENT_TEXT_PATTERN = re.compile(r"(\d{1,3}(?:[,.]\d{1,2})?\s*%)")


def build_spain_layout() -> html.Div:
    assert_analytics_databases_available()
    categories = _category_options()
    initial_category = categories[0]["value"] if categories else None
    years = _year_options(initial_category)
    initial_year = years[0]["value"] if years else None

    return html.Div(
        [
            build_navbar(active="spain"),
            html.Main(
                [
                    html.Header(
                        [
                            html.P("España", className="stats-eyebrow"),
                            html.H1("Indicadores estatales LGBTI+"),
                            html.P(
                                "Explora los datos extraídos de informes FELGTBI+ revisados por administración.",
                                className="stats-lead",
                            ),
                        ],
                        className="stats-header",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Label("Categoría", htmlFor="spain-category-select"),
                                    dcc.Dropdown(
                                        id="spain-category-select",
                                        options=categories,
                                        value=initial_category,
                                        clearable=False,
                                        placeholder="Selecciona una categoría",
                                    ),
                                ],
                                className="stats-control-field",
                            ),
                            html.Div(
                                [
                                    html.Label("Año", htmlFor="spain-year-select"),
                                    dcc.Dropdown(
                                        id="spain-year-select",
                                        options=years,
                                        value=initial_year,
                                        clearable=False,
                                        placeholder="Selecciona un año",
                                    ),
                                ],
                                className="stats-control-field",
                            ),
                            html.Div(
                                [
                                    html.Label("Tópico", htmlFor="spain-topic-select"),
                                    dcc.Dropdown(
                                        id="spain-topic-select",
                                        options=[],
                                        value=None,
                                        clearable=False,
                                        placeholder="Selecciona un tópico",
                                    ),
                                ],
                                className="stats-control-field",
                            ),
                            html.P(
                                "Selecciona una categoría para cargar sus tópicos.",
                                id="spain-indicator-summary",
                                className="stats-control-summary",
                            ),
                        ],
                        className="stats-controls",
                    ),
                    html.Section(
                        id="spain-visualization-grid",
                        className="stats-grid",
                        children=[
                            _empty_state(
                                "Sin datos FELGTBI+",
                                "Sube y aprueba un PDF FELGTBI+ para mostrar indicadores estatales.",
                            )
                        ],
                    ),
                ],
                className="stats-shell",
            ),
        ]
    )


def register_spain_callbacks(app: Dash) -> None:
    @app.callback(
        Output("spain-year-select", "options"),
        Output("spain-year-select", "value"),
        Output("spain-year-select", "disabled"),
        Input("spain-category-select", "value"),
    )
    def update_year_selector(category: str | None):
        years = _year_options(category)
        if not years:
            return [], None, True
        return years, years[0]["value"], False

    @app.callback(
        Output("spain-topic-select", "options"),
        Output("spain-topic-select", "value"),
        Output("spain-topic-select", "disabled"),
        Output("spain-indicator-summary", "children"),
        Input("spain-category-select", "value"),
        Input("spain-year-select", "value"),
    )
    def update_topic_selector(category: str | None, year: int | str | None):
        if not category:
            return [], None, True, "Selecciona una categoría para cargar sus tópicos."
        if not year:
            return [], None, True, "Selecciona un año para cargar sus tópicos."

        indicators = get_felgtbi_indicators_by_category(category, year)
        if not indicators:
            return [], None, True, f"{category} ({year}): sin tópicos importados."

        options = [
            {
                "label": _indicator_option_label(
                    indicator.question,
                    indicator.specific_category,
                    indicator.value,
                ),
                "value": indicator.code,
            }
            for indicator in indicators
        ]
        return (
            options,
            indicators[0].code,
            False,
            f"{category} ({year}): {len(indicators)} tópicos disponibles.",
        )

    @app.callback(
        Output("spain-visualization-grid", "children"),
        Input("spain-category-select", "value"),
        Input("spain-year-select", "value"),
        Input("spain-topic-select", "value"),
    )
    def update_spain_grid(category: str | None, year: int | str | None, code: str | None):
        if not category:
            return [_empty_state("Sin categoría", "Selecciona una categoría para empezar.")]
        if not year:
            return [_empty_state("Sin año", "Selecciona un año para continuar.")]

        indicators = get_felgtbi_indicators_by_category(category, year)
        if not indicators:
            return [
                _empty_state(
                    "Datos no disponibles",
                    "Esta categoría todavía no tiene PDFs FELGTBI+ aprobados para el año seleccionado.",
                )
            ]

        resolved_code = code or indicators[0].code
        document = get_felgtbi_indicator_answers(resolved_code)
        return _felgtbi_panels(document)


def _category_options() -> list[dict[str, str]]:
    return [{"label": category, "value": category} for category in get_felgtbi_categories()]


def _year_options(category: str | None = None) -> list[dict[str, int]]:
    return [{"label": str(year), "value": year} for year in get_felgtbi_years(category)]


def _indicator_option_label(title: str, section: str, value: float | None) -> str:
    clean_section = title or section or "Indicador FELGTBI+"
    value_label = f" - {_format_percent(value)}" if value is not None else ""
    label = f"{clean_section}{value_label}"
    return label if len(label) <= 95 else f"{label[:92]}..."


def _felgtbi_panels(document: dict[str, Any] | None) -> list[Any]:
    if _content_html(document) or _has_structured_report_content(document):
        return [
            _panel("Contenido", _html_content_panel(document), "stats-panel stats-panel-wide"),
        ]
    return [
        _panel("Contenido", _value_panel_content(document), "stats-panel stats-panel-wide"),
        _panel("Detalle", _detail_table(document)),
    ]


def _summary_content(document: dict[str, Any] | None) -> html.Div:
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
    asset_url = _figure_url(document)
    if asset_url:
        return html.Img(
            src=asset_url,
            alt="Gráfica del PDF asociada al indicador",
            className="spain-pdf-figure",
        )
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
        return _empty_state("Sin contenido", "No hay resumen HTML para este indicador.")
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
    if not url:
        return None

    figure = document.get("figure") if isinstance(document.get("figure"), dict) else {}
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
    children: list[Any] = [
        html.Img(
            src=url,
            alt=alt_text,
            className="report-figure-image",
        )
    ]
    if caption:
        children.append(html.Figcaption(caption))
    return html.Figure(children, className="report-figure")


def _figure_url(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return ""
    figure = document.get("figure") if isinstance(document.get("figure"), dict) else {}
    context = document.get("visual_context") if isinstance(document.get("visual_context"), dict) else {}
    upload = figure.get("upload") if isinstance(figure.get("upload"), dict) else {}
    context_upload = (
        context.get("image_upload") if isinstance(context.get("image_upload"), dict) else {}
    )
    signed_storage_url = _signed_storage_url(figure, context_upload)
    candidates = [
        signed_storage_url,
        figure.get("image_url"),
        figure.get("signed_url"),
        upload.get("signed_url"),
        context_upload.get("signed_url"),
        figure.get("public_url"),
        upload.get("public_url"),
        context_upload.get("public_url"),
        figure.get("asset_url"),
        figure.get("image_path"),
        context.get("asset_url"),
    ]
    for candidate in candidates:
        url = str(candidate or "").strip()
        if url:
            return url
    return ""


def _signed_storage_url(figure: dict[str, Any], context_upload: dict[str, Any]) -> str:
    if _supabase_storage_is_public():
        return ""
    storage_path = str(
        figure.get("storage_path")
        or context_upload.get("storage_path")
        or ""
    ).strip()
    if not storage_path:
        return ""
    bucket = str(
        figure.get("bucket")
        or context_upload.get("bucket")
        or os.getenv("SUPABASE_STORAGE_BUCKET", "felgtbi-reports")
    ).strip()
    expires_in = int(os.getenv("SUPABASE_SIGNED_URL_EXPIRES_IN", "604800") or 604800)
    return _create_supabase_signed_url(bucket, storage_path, expires_in=expires_in)


def _supabase_storage_is_public() -> bool:
    return os.getenv("SUPABASE_STORAGE_PUBLIC", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "public",
    }


def _create_supabase_signed_url(bucket: str, storage_path: str, *, expires_in: int) -> str:
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_key or not bucket or not storage_path:
        return ""
    request = Request(
        f"{supabase_url}/storage/v1/object/sign/{quote(bucket, safe='')}/{quote(storage_path, safe='/')}",
        data=json.dumps({"expiresIn": int(expires_in)}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""
    signed_url = str(payload.get("signedURL") or payload.get("signedUrl") or "").strip()
    if not signed_url:
        return ""
    if signed_url.startswith("http://") or signed_url.startswith("https://"):
        return signed_url
    return f"{supabase_url}/storage/v1{signed_url if signed_url.startswith('/') else '/' + signed_url}"


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


def _detail_table(document: dict[str, Any] | None) -> html.Div:
    if not document:
        return _empty_state("Sin tópico", "Selecciona un tópico para ver sus datos.")
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


def _visual_asset_url(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return ""
    context = document.get("visual_context")
    if not isinstance(context, dict):
        return ""
    return str(context.get("asset_url") or "")


def _content_html(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return ""
    return str(document.get("content_html") or "").strip()


def _panel(title: str, child: Any, class_name: str = "stats-panel") -> html.Section:
    return html.Section([html.H2(title), child], className=class_name)


def _empty_state(title: str, detail: str) -> html.Div:
    return html.Div([html.H2(title), html.P(detail)], className="stats-empty-state")
