from __future__ import annotations

from typing import Any

from dash import Dash, html
from dash.development.base_component import Component

from app.dash.components.contact_form import (
    build_contact_panel,
    register_contact_form_callbacks,
)
from app.dash.components.page_structure import build_page_header
from app.dash.i18n import dash_attrs, text, text_attrs, ui_text, ui_text_component
from app.dash.layouts.navigation import build_navbar
from app.source_attribution import FELGTBI_REPORTS_URL, FRA_SURVEYS, ILGA_RAINBOW_MAP_URL

PRIMARY_SOURCES = [
    {
        "entity": "FELGTBI+",
        "title": "Estado LGBTIQ+ - FELGTBI+",
        "url": FELGTBI_REPORTS_URL,
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
        "title": "EU LGBT/LGBTI/LGBTIQ Surveys - FRA",
        "links": [
            {"label_key": f"fra_survey_{year}", "url": survey[1]}
            for year, survey in FRA_SURVEYS.items()
        ],
        "description": (
            "Resultados de las encuestas europeas de 2019 y 2023 sobre las "
            "experiencias, condiciones de vida y discriminación de las personas LGBTIQ+."
        ),
        "description_en": (
            "Results from the 2019 and 2023 European surveys on the experiences, "
            "living conditions and discrimination of LGBTIQ+ people."
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
        "url": ILGA_RAINBOW_MAP_URL,
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
    return html.Div(
        [
            build_navbar(active="about"),
            html.Main(
                [
                    build_page_header(
                        eyebrow=text("Fuentes y metodología", "Sources and methodology"),
                        title=text(
                            "Acerca de RainbowLens Datahub",
                            "About RainbowLens Datahub",
                        ),
                        description=text(
                            "RainbowLens Datahub integra fuentes oficiales para analizar la situación legal y social de las personas LGBTIQ+ en Europa.",
                            "RainbowLens Datahub integrates official sources to analyse the legal and social situation of LGBTIQ+ people in Europe.",
                        ),
                        class_name="about-header",
                    ),
                    _source_cards_section(
                        ui_text("about_primary_sources_title", "es"),
                        ui_text("about_primary_sources_title", "en"),
                        PRIMARY_SOURCES,
                        class_name="about-source-section",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
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
                    build_contact_panel(),
                ],
                className="about-shell app-page app-page-container",
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
    source_links = source.get("links")
    if isinstance(source_links, list):
        children.append(
            html.Nav(
                [_source_card_link(link) for link in source_links],
                className="about-resource-card__links",
                **dash_attrs(
                    {
                        "aria-label": "Encuestas oficiales de la FRA",
                        "data-i18n-aria-label-es": "Encuestas oficiales de la FRA",
                        "data-i18n-aria-label-en": "Official FRA surveys",
                    }
                ),
            )
        )
    else:
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


def _source_card_link(link: Any) -> Component:
    if not isinstance(link, dict):
        raise TypeError("source link must be a mapping")
    label_key = str(link.get("label_key") or "")
    label_es = ui_text(label_key, "es")
    label_en = ui_text(label_key, "en")
    aria_es = f"{label_es} (se abre en una pestaña nueva)"
    aria_en = f"{label_en} (opens in a new tab)"
    return html.A(
        [
            ui_text_component(label_key),
            html.Span("↗", **dash_attrs({"aria-hidden": "true"})),
        ],
        href=str(link.get("url") or "#"),
        target="_blank",
        rel="noopener noreferrer",
        className="about-resource-card__link",
        **dash_attrs(
            {
                "aria-label": aria_es,
                "data-i18n-aria-label-es": aria_es,
                "data-i18n-aria-label-en": aria_en,
            }
        ),
    )


def register_about_callbacks(app: Dash) -> None:
    register_contact_form_callbacks(app)
