from __future__ import annotations

from typing import Any, cast

from dash import Dash, Input, Output, dcc, html
from dash.development.base_component import Component

from app.analytics.legal_criteria import (
    get_criterion_metadata,
    get_criterion_score_label,
    get_criterion_status,
)
from app.analytics.repository import get_latest_ilga_document
from app.dash.i18n import country_labels, text, text_attrs
from app.dash.layouts.navigation import build_navbar

PRIMARY_SOURCES = [
    {
        "entity": "FELGTBI+",
        "title": "Estado LGBTIQ+ - FELGTBI+",
        "url": "https://felgtbi.org/que-hacemos/investigacion/estado-lgtbi/",
        "description": (
            "Informes y estudios sobre la situación social, la discriminación y las "
            "experiencias de las personas LGBTIQ+ en España."
        ),
        "description_en": (
            "Reports and studies on the social situation, discrimination and "
            "experiences of LGBTIQ+ people in Spain."
        ),
        "details": [
            (
                (
                    "La FELGTBI+ defiende y promueve los derechos humanos y la "
                    "igualdad de las personas LGBTIQ+ y sus familias en el Estado "
                    "español, con atención especial a quienes afrontan mayor "
                    "vulnerabilidad."
                ),
                (
                    "FELGTBI+ defends and promotes human rights and equality "
                    "for LGBTIQ+ people and their families in Spain, with special "
                    "attention to those facing greater vulnerability."
                ),
            ),
            (
                (
                    "En RainbowLens Datahub, FELGTBI+ aporta contexto estatal sobre activismo, "
                    "derechos y organización social LGBTIQ+."
                ),
                (
                    "In RainbowLens Datahub, FELGTBI+ adds national context on LGBTIQ+ "
                    "activism, rights and social organisation."
                ),
            ),
        ],
        "type": "Fuente principal",
        "type_en": "Primary source",
    },
    {
        "entity": "Agencia de los Derechos Fundamentales de la Unión Europea",
        "entity_en": "European Union Agency for Fundamental Rights",
        "title": "EU LGBTIQ Survey III - FRA",
        "url": "https://fra.europa.eu/en/publications-and-resources/data-and-maps/2024/eu-lgbtiq-survey-iii",
        "description": (
            "Resultados de la tercera encuesta europea sobre las experiencias, "
            "condiciones de vida y discriminación de las personas LGBTIQ+."
        ),
        "description_en": (
            "Results from the third European survey on the experiences, living "
            "conditions and discrimination of LGBTIQ+ people."
        ),
        "details": [
            (
                (
                    "La Agencia de los Derechos Fundamentales de la Unión Europea "
                    "recoge datos de encuesta sobre experiencias reales de la "
                    "población LGBTIQ+."
                ),
                (
                    "The European Union Agency for Fundamental Rights collects "
                    "survey data on real experiences of the LGBTIQ+ population."
                ),
            ),
            (
                (
                    "Sus indicadores cubren dimensiones como discriminación, "
                    "visibilidad, seguridad, acoso, condiciones socioeconómicas "
                    "y relación con instituciones."
                ),
                (
                    "Its indicators cover dimensions such as discrimination, "
                    "visibility, safety, harassment, socioeconomic conditions "
                    "and relationships with institutions."
                ),
            ),
            (
                (
                    "En RainbowLens Datahub, FRA complementa el mapa legal de ILGA con "
                    "evidencia social comparable entre países."
                ),
                (
                    "In RainbowLens Datahub, FRA complements ILGA's legal map with "
                    "social evidence that can be compared across countries."
                ),
            ),
        ],
        "type": "Fuente principal",
        "type_en": "Primary source",
    },
    {
        "entity": "ILGA-Europe",
        "title": "Rainbow Map - ILGA-Europe",
        "url": "https://rainbowmap.ilga-europe.org",
        "description": (
            "Comparación anual de la situación legal y política de las personas "
            "LGBTIQ+ en 49 países europeos."
        ),
        "description_en": (
            "Annual comparison of the legal and policy situation of LGBTIQ+ "
            "people in 49 European countries."
        ),
        "details": [
            (
                (
                    "ILGA Europe evalúa leyes y políticas públicas que afectan "
                    "a las personas LGBTIQ+ en Europa."
                ),
                (
                    "ILGA Europe evaluates laws and public policies affecting "
                    "LGBTIQ+ people in Europe."
                ),
            ),
            (
                (
                    "El Rainbow Map organiza esa información en indicadores "
                    "relacionados con igualdad y no discriminación, familia, "
                    "delitos y discursos de odio, reconocimiento legal de género, "
                    "integridad corporal, asilo y espacio de sociedad civil."
                ),
                (
                    "The Rainbow Map organises this information into indicators "
                    "related to equality and non-discrimination, family, hate "
                    "crime and speech, legal gender recognition, bodily integrity, "
                    "asylum and civil society space."
                ),
            ),
            (
                (
                    "En la aplicación, estos datos permiten comparar países y "
                    "visualizar la evolución del marco legal por año."
                ),
                (
                    "In the application, these data make it possible to compare "
                    "countries and visualise the legal framework over time."
                ),
            ),
        ],
        "type": "Fuente principal",
        "type_en": "Primary source",
    },
]

RECOMMENDED_SOURCE_GROUPS = [
    {
        "category": "Situación social y resultados de la encuesta",
        "category_en": "Social situation and survey results",
        "sources": [
            {
                "entity": "FRA",
                "title": "LGBTIQ+ Equality at a Crossroads - FRA",
                "url": "https://fra.europa.eu/sites/default/files/fra_uploads/fra-2024-lgbtiq-equality_en.pdf",
                "description": (
                    "Informe detallado de la FRA sobre los principales resultados de la "
                    "encuesta europea LGBTIQ+ y las desigualdades que persisten en "
                    "distintos ámbitos de la vida."
                ),
                "description_en": (
                    "Detailed FRA report on the main results of the European LGBTIQ+ "
                    "survey and the inequalities that persist across different areas of life."
                ),
                "type": "Lectura recomendada",
                "type_en": "Recommended reading",
                "note": "Especialmente recomendada para interpretar los datos sociodemográficos.",
                "note_en": "Especially recommended for interpreting sociodemographic data.",
            }
        ],
    },
    {
        "category": "Políticas y acciones de la Unión Europea",
        "category_en": "European Union policies and actions",
        "sources": [
            {
                "entity": "Comision Europea",
                "entity_en": "European Commission",
                "title": "LGBTIQ+ Equality Strategy 2026-2030 - Comision Europea",
                "title_en": "LGBTIQ+ Equality Strategy 2026-2030 - European Commission",
                "url": "https://commission.europa.eu/strategy-and-policy/policies/justice-and-fundamental-rights/combatting-discrimination/lesbian-gay-bi-trans-and-intersex-equality/lgbtiq-equality-strategy-2026-2030_en",
                "description": (
                    "Estrategia de la Comision Europea que establece prioridades, "
                    "acciones y compromisos para avanzar en la igualdad LGBTIQ+ durante "
                    "el periodo 2026-2030."
                ),
                "description_en": (
                    "European Commission strategy setting priorities, actions and "
                    "commitments to advance LGBTIQ+ equality during 2026-2030."
                ),
                "type": "Lectura recomendada",
                "type_en": "Recommended reading",
            }
        ],
    },
    {
        "category": "Contexto normativo y objetivos estrategicos",
        "category_en": "Policy context and strategic objectives",
        "sources": [
            {
                "entity": "Unión Europea",
                "entity_en": "European Union",
                "title": "LGBTIQ+ Equality - Fichas informativas de la Unión Europea",
                "title_en": "LGBTIQ+ Equality - European Union factsheets",
                "url": "https://op.europa.eu/webpub/com/factsheets/lgbti/en/",
                "description": (
                    "Resumen accesible de las políticas, marcos de actuación y "
                    "principales objetivos de la Unión Europea en materia de igualdad LGBTIQ+."
                ),
                "description_en": (
                    "Accessible overview of European Union policies, action frameworks "
                    "and key objectives on LGBTIQ+ equality."
                ),
                "type": "Lectura recomendada",
                "type_en": "Recommended reading",
            }
        ],
    },
]


def build_about_layout() -> Component:
    ilga_document = get_latest_ilga_document()
    return html.Div(
        [
            build_navbar(active="about"),
            html.Main(
                [
                    html.Section(
                        [
                            html.P(
                                "Fuentes y metodología",
                                className="about-eyebrow",
                                **text_attrs("Fuentes y metodología", "Sources and methodology"),
                            ),
                            html.H1(
                                "Acerca de RainbowLens Datahub",
                                **text_attrs(
                                    "Acerca de RainbowLens Datahub",
                                    "About RainbowLens Datahub",
                                ),
                            ),
                            html.P(
                                (
                                    "RainbowLens Datahub integra fuentes oficiales para analizar la "
                                    "situación legal y social de las personas LGBTIQ+ en Europa."
                                ),
                                className="about-lead",
                                **text_attrs(
                                    (
                                        "RainbowLens Datahub integra fuentes oficiales para analizar la "
                                        "situación legal y social de las personas LGBTIQ+ en Europa."
                                    ),
                                    (
                                        "RainbowLens Datahub integrates official sources to analyse the "
                                        "legal and social situation of LGBTIQ+ people in Europe."
                                    ),
                                ),
                            ),
                        ],
                        className="about-header",
                    ),
                    _source_cards_section(
                        "Fuentes principales de datos y situación social",
                        "Main data and social-context sources",
                        PRIMARY_SOURCES,
                        class_name="about-source-section",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.P(
                                        "Para profundizar",
                                        className="about-eyebrow",
                                        **text_attrs("Para profundizar", "Further reading"),
                                    ),
                                    html.H2(
                                        "Fuentes recomendadas para profundizar",
                                        **text_attrs(
                                            "Fuentes recomendadas para profundizar",
                                            "Recommended sources for further reading",
                                        ),
                                    ),
                                    html.P(
                                        (
                                            "Para comprender mejor los datos y su contexto, "
                                            "recomendamos consultar también las siguientes "
                                            "publicaciones y estrategias oficiales."
                                        ),
                                        className="about-lead",
                                        **text_attrs(
                                            (
                                                "Para comprender mejor los datos y su contexto, "
                                                "recomendamos consultar también las siguientes "
                                                "publicaciones y estrategias oficiales."
                                            ),
                                            (
                                                "To better understand the data and its context, "
                                                "we also recommend consulting the following "
                                                "official publications and strategies."
                                            ),
                                        ),
                                    ),
                                ],
                                className="about-section-header",
                            ),
                            *[
                                _recommended_source_group(group)
                                for group in RECOMMENDED_SOURCE_GROUPS
                            ],
                        ],
                        className="about-recommended-section",
                    ),
                    html.P(
                        (
                            "RainbowLens Datahub recopila, organiza y visualiza información procedente "
                            "de fuentes externas. La autoría, metodología y responsabilidad de "
                            "los datos corresponden a las organizaciones que publican cada recurso."
                        ),
                        className="about-attribution",
                        **text_attrs(
                            (
                                "RainbowLens Datahub recopila, organiza y visualiza información procedente "
                                "de fuentes externas. La autoría, metodología y responsabilidad de "
                                "los datos corresponden a las organizaciones que publican cada recurso."
                            ),
                            (
                                "RainbowLens Datahub collects, organises and visualises information from "
                                "external sources. Authorship, methodology and responsibility for "
                                "the data remain with the organisations publishing each resource."
                            ),
                        ),
                    ),
                    _ilga_detail_section(ilga_document),
                ],
                className="about-shell",
            ),
        ]
    )


def _source_cards_section(
    title_es: str,
    title_en: str,
    sources: list[dict[str, Any]],
    *,
    class_name: str,
) -> Component:
    return html.Section(
        [
            html.Div(
                [
                    html.P(
                        "Fuentes oficiales",
                        className="about-eyebrow",
                        **text_attrs("Fuentes oficiales", "Official sources"),
                    ),
                    html.H2(title_es, **text_attrs(title_es, title_en)),
                ],
                className="about-section-header",
            ),
            html.Div(
                [_source_card(source) for source in sources],
                className="about-source-grid",
            ),
        ],
        className=class_name,
    )


def _recommended_source_group(group: dict[str, Any]) -> Component:
    category_es = str(group.get("category") or "Fuente recomendada")
    category_en = str(group.get("category_en") or "Recommended source")
    return html.Section(
        [
            html.H3(category_es, **text_attrs(category_es, category_en)),
            html.Div(
                [_source_card(source) for source in group.get("sources", [])],
                className="about-source-grid about-source-grid--single",
            ),
        ],
        className="about-source-category",
    )


def _source_card(source: dict[str, Any]) -> Component:
    note = str(source.get("note") or "").strip()
    note_en = str(source.get("note_en") or note).strip()
    source_type = str(source.get("type") or "Fuente")
    source_type_en = str(source.get("type_en") or "Source")
    description = str(source.get("description") or "")
    description_en = str(source.get("description_en") or description)
    title = str(source.get("title") or "")
    title_en = str(source.get("title_en") or title)
    entity = str(source.get("entity") or "")
    entity_en = str(source.get("entity_en") or entity)
    link_es = f"Abrir {title or 'recurso oficial'} en una pestaña nueva"
    link_en = f"Open {title_en or 'official resource'} in a new tab"
    children: list[Any] = [
        html.Div(
            [
                html.Span(
                    source_type,
                    className="about-resource-card__tag",
                    **text_attrs(source_type, source_type_en),
                ),
                html.Span(
                    entity,
                    className="about-resource-card__entity",
                    **text_attrs(entity, entity_en),
                ),
            ],
            className="about-resource-card__meta",
        ),
        html.H3(title, **text_attrs(title, title_en)),
        html.P(description, **text_attrs(description, description_en)),
    ]
    detail_paragraphs = source.get("details") or []
    for paragraph in detail_paragraphs:
        if isinstance(paragraph, tuple) and len(paragraph) == 2:
            children.append(html.P(paragraph[0], **text_attrs(paragraph[0], paragraph[1])))
    if note:
        children.append(
            html.P(
                note,
                className="about-resource-card__note",
                **text_attrs(note, note_en),
            )
        )
    children.append(
        html.A(
            link_es,
            href=str(source.get("url") or "#"),
            target="_blank",
            rel="noopener noreferrer",
            className="about-resource-card__link",
            **text_attrs(link_es, link_en),
        )
    )
    return html.Article(children, className="about-resource-card")


def register_about_callbacks(app: Dash) -> None:
    @app.callback(
        Output("about-ilga-criteria", "children"),
        Input("about-ilga-country", "value"),
    )
    def update_ilga_country_criteria(country_key: str | None):
        if not country_key:
            return _about_ilga_empty_state()
        document = get_latest_ilga_document()
        country = _find_country(document, country_key)
        if not country:
            return _about_ilga_empty_state()
        return _country_criteria_panel(country)

    @app.callback(
        Output("about-ilga-country", "placeholder"),
        Input("app-language-store", "data"),
    )
    def translate_about_controls(language: str | None) -> str:
        return (
            "Select a criterion"
            if language == "en"
            else "Selecciona un criterio"
        )


def _about_ilga_empty_state() -> Component:
    return html.P(
        "Selecciona un criterio para consultar su detalle jurídico.",
        className="about-empty about-empty--compact",
        **text_attrs(
            "Selecciona un criterio para consultar su detalle jurídico.",
            "Select a criterion to view its legal details.",
        ),
    )


def _ilga_detail_section(document: dict[str, Any] | None) -> Component:
    year = document.get("year") if isinstance(document, dict) else None
    countries = _countries_with_criteria(document)
    options = []
    for country in countries:
        country_code = str(country.get("country_code") or "").strip().upper()
        country_name = str(country.get("country") or "").strip()
        name_es, name_en = country_labels(country_code, country_name)
        options.append(
            {
                "label": text(
                    f"{name_es} ({country_code})",
                    f"{name_en} ({country_code})",
                ),
                "value": _country_key(country),
            }
        )
    title_es = f"Indicadores registrados en {year}" if year else "Indicadores ILGA"
    title_en = f"Indicators registered in {year}" if year else "ILGA indicators"
    lead_es = (
        "La puntuación global sintetiza criterios legales y políticos. "
        "Cada criterio incluye su categoría, indicador, valor máximo "
        "y valor registrado para el país."
    )
    lead_en = (
        "The global ranking summarises legal and policy criteria. "
        "Each criterion includes its category, indicator, maximum value "
        "and value registered for the country."
    )
    return html.Section(
        [
            html.Div(
                [
                    html.P(
                        "Desglose ILGA actual",
                        className="about-eyebrow",
                        **text_attrs("Desglose ILGA actual", "Current ILGA breakdown"),
                    ),
                    html.H2(title_es, **text_attrs(title_es, title_en)),
                    html.P(lead_es, className="about-lead", **text_attrs(lead_es, lead_en)),
                ],
                className="about-section-header",
            ),
            (
                html.Div(
                    [
                        html.Label(
                            text("País", "Country"),
                            htmlFor="about-ilga-country",
                        ),
                        dcc.Dropdown(
                            id="about-ilga-country",
                            options=options,
                            value=None,
                            clearable=True,
                            placeholder="Selecciona un criterio",
                            className="about-country-dropdown",
                        ),
                        html.Div(
                            _about_ilga_empty_state(),
                            id="about-ilga-criteria",
                            className="about-country-panel",
                        ),
                    ],
                    className="about-country-browser",
                )
                if countries
                else html.P(
                    "No hay criterios desglosados para el último año disponible.",
                    className="about-empty",
                    **text_attrs(
                        "No hay criterios desglosados para el último año disponible.",
                        "There are no detailed criteria for the latest available year.",
                    ),
                )
            ),
        ],
        className="about-detail-section",
    )


def _countries_with_criteria(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    countries = document.get("countries")
    if not isinstance(countries, list):
        return []
    return [
        country
        for country in countries
        if isinstance(country, dict) and isinstance(country.get("criteria"), list)
    ]


def _find_country(
    document: dict[str, Any] | None,
    country_key: str | None,
) -> dict[str, Any] | None:
    if not country_key:
        return None
    for country in _countries_with_criteria(document):
        if _country_key(country) == country_key:
            return country
    return None


def _country_key(country: dict[str, Any]) -> str:
    country_code = str(country.get("country_code") or "").strip()
    country_name = str(country.get("country") or "").strip()
    return country_code or country_name


def _country_criteria_panel(country: dict[str, Any]) -> Component:
    ranking = country.get("ranking")
    ranking_text = f"{float(ranking):.2f}%" if isinstance(ranking, (int, float)) else "-"
    country_code = str(country.get("country_code") or "").strip().upper()
    country_fallback = str(country.get("country") or country_code or "País")
    country_es, country_en = country_labels(country_code, country_fallback)
    criteria = (
        cast(list[dict[str, Any]], country.get("criteria"))
        if isinstance(country.get("criteria"), list)
        else []
    )
    return html.Div(
        [
            html.Div(
                [
                    html.H3(country_es, **text_attrs(country_es, country_en)),
                    html.Span(country_code),
                    html.Strong(ranking_text),
                ],
                className="about-country-summary",
            ),
            html.Div(
                [_criterion_row(criterion) for criterion in criteria],
                className="about-criteria-list",
            ),
        ],
    )


def _criterion_row(criterion: dict[str, Any]) -> Component:
    weight = criterion.get("weight")
    value = criterion.get("value")
    metadata_es = get_criterion_metadata(criterion, "es")
    metadata_en = get_criterion_metadata(criterion, "en")
    status_es = get_criterion_status(value, weight, "es")
    status_en = get_criterion_status(value, weight, "en")
    score_es = (
        get_criterion_score_label(value, weight, "es") or "Puntuación: información no disponible"
    )
    score_en = get_criterion_score_label(value, weight, "en") or "Score: information unavailable"
    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        metadata_es["category_label"],
                        className="ilga-indicator-card__category",
                        **text_attrs(metadata_es["category_label"], metadata_en["category_label"]),
                    ),
                    html.Strong(
                        metadata_es["display_title"],
                        className="ilga-indicator-card__title",
                        **text_attrs(metadata_es["display_title"], metadata_en["display_title"]),
                    ),
                    html.P(
                        metadata_es["summary"],
                        className="ilga-indicator-card__description",
                        **text_attrs(metadata_es["summary"], metadata_en["summary"]),
                    ),
                ],
                className="ilga-indicator-card__content",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Estado", **text_attrs("Estado", "Status")),
                            html.Strong(
                                status_es["label"],
                                **text_attrs(status_es["label"], status_en["label"]),
                            ),
                        ],
                        className="ilga-indicator-card__meta-item",
                    ),
                    html.Div(
                        [
                            html.Span("Valor", **text_attrs("Valor", "Value")),
                            html.Strong(score_es, **text_attrs(score_es, score_en)),
                        ],
                        className="ilga-indicator-card__meta-item",
                    ),
                ],
                className="ilga-indicator-card__metadata",
            ),
        ],
        className="ilga-indicator-card",
    )


def _format_number(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return "-"
