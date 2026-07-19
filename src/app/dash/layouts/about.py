from __future__ import annotations

from typing import Any

from app.analytics.legal_criteria import (
    get_criterion_metadata,
    get_criterion_score_label,
    get_criterion_status,
)
from app.analytics.repository import get_latest_ilga_document
from app.dash.compat import Dash, Input, Output, dcc, html
from app.dash.i18n import text, text_attrs
from app.dash.layouts.navigation import build_navbar


PRIMARY_SOURCES = [
    {
        "entity": "FELGTBI+",
        "title": "Estado LGTBI+ - FELGTBI+",
        "url": "https://felgtbi.org/que-hacemos/investigacion/estado-lgtbi/",
        "description": (
            "Informes y estudios sobre la situación social, la discriminación y las "
            "experiencias de las personas LGTBI+ en España."
        ),
        "type": "Fuente principal",
    },
    {
        "entity": "Agencia de los Derechos Fundamentales de la Unión Europea",
        "title": "EU LGBTIQ Survey III - FRA",
        "url": "https://fra.europa.eu/en/publications-and-resources/data-and-maps/2024/eu-lgbtiq-survey-iii",
        "description": (
            "Resultados de la tercera encuesta europea sobre las experiencias, "
            "condiciones de vida y discriminación de las personas LGBTIQ."
        ),
        "type": "Fuente principal",
    },
    {
        "entity": "ILGA-Europe",
        "title": "Rainbow Map - ILGA-Europe",
        "url": "https://rainbowmap.ilga-europe.org",
        "description": (
            "Comparación anual de la situación legal y política de las personas "
            "LGBTI+ en 49 países europeos."
        ),
        "type": "Fuente principal",
    },
]

RECOMMENDED_SOURCE_GROUPS = [
    {
        "category": "Situación social y resultados de la encuesta",
        "sources": [
            {
                "entity": "FRA",
                "title": "LGBTIQ Equality at a Crossroads - FRA",
                "url": "https://fra.europa.eu/sites/default/files/fra_uploads/fra-2024-lgbtiq-equality_en.pdf",
                "description": (
                    "Informe detallado de la FRA sobre los principales resultados de la "
                    "encuesta europea LGBTIQ y las desigualdades que persisten en "
                    "distintos ámbitos de la vida."
                ),
                "type": "Lectura recomendada",
                "note": "Especialmente recomendada para interpretar los datos sociodemográficos.",
            }
        ],
    },
    {
        "category": "Políticas y acciones de la Unión Europea",
        "sources": [
            {
                "entity": "Comision Europea",
                "title": "LGBTIQ Equality Strategy 2026-2030 - Comision Europea",
                "url": "https://commission.europa.eu/strategy-and-policy/policies/justice-and-fundamental-rights/combatting-discrimination/lesbian-gay-bi-trans-and-intersex-equality/lgbtiq-equality-strategy-2026-2030_en",
                "description": (
                    "Estrategia de la Comision Europea que establece prioridades, "
                    "acciones y compromisos para avanzar en la igualdad LGBTIQ durante "
                    "el periodo 2026-2030."
                ),
                "type": "Lectura recomendada",
            }
        ],
    },
    {
        "category": "Contexto normativo y objetivos estrategicos",
        "sources": [
            {
                "entity": "Unión Europea",
                "title": "LGBTI Equality - Fichas informativas de la Unión Europea",
                "url": "https://op.europa.eu/webpub/com/factsheets/lgbti/en/",
                "description": (
                    "Resumen accesible de las políticas, marcos de actuación y "
                    "principales objetivos de la Unión Europea en materia de igualdad LGBTI."
                ),
                "type": "Lectura recomendada",
            }
        ],
    },
]


def build_about_layout() -> html.Div:
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
                                "Acerca de RainbowLens",
                                **text_attrs("Acerca de RainbowLens", "About RainbowLens"),
                            ),
                            html.P(
                                (
                                    "RainbowLens integra fuentes oficiales para analizar la "
                                    "situación legal y social de las personas LGBTIQ+ en Europa."
                                ),
                                className="about-lead",
                                **text_attrs(
                                    (
                                        "RainbowLens integra fuentes oficiales para analizar la "
                                        "situación legal y social de las personas LGBTIQ+ en Europa."
                                    ),
                                    (
                                        "RainbowLens integrates official sources to analyse the "
                                        "legal and social situation of LGBTIQ+ people in Europe."
                                    ),
                                ),
                            ),
                        ],
                        className="about-header",
                    ),
                    _source_cards_section(
                        "Fuentes principales de datos y situación social",
                        PRIMARY_SOURCES,
                        class_name="about-source-section",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.P("Para profundizar", className="about-eyebrow"),
                                    html.H2("Fuentes recomendadas para profundizar"),
                                    html.P(
                                        (
                                            "Para comprender mejor los datos y su contexto, "
                                            "recomendamos consultar también las siguientes "
                                            "publicaciones y estrategias oficiales."
                                        ),
                                        className="about-lead",
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
                            "Rainbow Lens recopila, organiza y visualiza información procedente "
                            "de fuentes externas. La autoría, metodología y responsabilidad de "
                            "los datos corresponden a las organizaciones que publican cada recurso."
                        ),
                        className="about-attribution",
                    ),
                    html.Section(
                        [
                            _about_block(
                                "ILGA Europe Rainbow Map",
                                [
                                    (
                                        "ILGA Europe evalúa leyes y políticas públicas que afectan "
                                        "a las personas LGBTIQ+ en Europa y Asia Central.",
                                        (
                                            "ILGA Europe evaluates laws and public policies affecting "
                                            "LGBTIQ+ people in Europe and Central Asia."
                                        ),
                                    ),
                                    (
                                        "El Rainbow Map organiza esa información en indicadores "
                                        "relacionados con igualdad y no discriminación, familia, "
                                        "delitos y discursos de odio, reconocimiento legal de género, "
                                        "integridad corporal, asilo y espacio de sociedad civil.",
                                        (
                                            "The Rainbow Map organises this information into indicators "
                                            "related to equality and non-discrimination, family, hate "
                                            "crime and speech, legal gender recognition, bodily integrity, "
                                            "asylum and civil society space."
                                        ),
                                    ),
                                    (
                                        "En la aplicación, estos datos permiten comparar países y "
                                        "visualizar la evolución del marco legal por año.",
                                        (
                                            "In the application, these data make it possible to compare "
                                            "countries and visualise the legal framework over time."
                                        ),
                                    ),
                                ],
                            ),
                            _about_block(
                                "FRA",
                                [
                                    (
                                        "La Agencia de los Derechos Fundamentales de la Unión Europea "
                                        "recoge datos de encuesta sobre experiencias reales de la "
                                        "población LGBTIQ+.",
                                        (
                                            "The European Union Agency for Fundamental Rights collects "
                                            "survey data on real experiences of the LGBTIQ+ population."
                                        ),
                                    ),
                                    (
                                        "Sus indicadores cubren dimensiones como discriminación, "
                                        "visibilidad, seguridad, acoso, condiciones socioeconómicas "
                                        "y relación con instituciones.",
                                        (
                                            "Its indicators cover dimensions such as discrimination, "
                                            "visibility, safety, harassment, socioeconomic conditions "
                                            "and relationships with institutions."
                                        ),
                                    ),
                                    (
                                        "En RainbowLens, FRA complementa el mapa legal de ILGA con "
                                        "evidencia social comparable entre países.",
                                        (
                                            "In RainbowLens, FRA complements ILGA's legal map with "
                                            "social evidence that can be compared across countries."
                                        ),
                                    ),
                                ],
                            ),
                            _about_block(
                                "FELGTBI+",
                                [
                                    (
                                        "La FELGTBI+ defiende y promueve los derechos humanos y la "
                                        "igualdad de las personas LGTBI+ y sus familias en el Estado "
                                        "español, con atención especial a quienes afrontan mayor "
                                        "vulnerabilidad.",
                                        (
                                            "FELGTBI+ defends and promotes human rights and equality "
                                            "for LGTBI+ people and their families in Spain, with special "
                                            "attention to those facing greater vulnerability."
                                        ),
                                    ),
                                    (
                                        "Su trabajo combina incidencia social y política, apoyo al "
                                        "movimiento asociativo, cooperación en red, transparencia, "
                                        "interseccionalidad y compromiso con la justicia social.",
                                        (
                                            "Its work combines social and policy advocacy, support for "
                                            "the associative movement, network-based cooperation, "
                                            "transparency, intersectionality and a commitment to social "
                                            "justice."
                                        ),
                                    ),
                                    (
                                        "En RainbowLens, FELGTBI+ aporta contexto estatal sobre activismo, "
                                        "derechos y organización social LGTBI+.",
                                        (
                                            "In RainbowLens, FELGTBI+ adds national context on LGTBI+ "
                                            "activism, rights and social organisation."
                                        ),
                                    ),
                                ],
                                link=("https://felgtbi.org", "Web de FELGTBI+", "FELGTBI+ website"),
                            ),
                        ],
                        className="about-grid",
                    ),
                    _ilga_detail_section(ilga_document),
                ],
                className="about-shell",
            ),
        ]
    )


def _source_cards_section(
    title: str,
    sources: list[dict[str, str]],
    *,
    class_name: str,
) -> html.Section:
    return html.Section(
        [
            html.Div(
                [
                    html.P("Fuentes oficiales", className="about-eyebrow"),
                    html.H2(title),
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


def _recommended_source_group(group: dict[str, Any]) -> html.Section:
    return html.Section(
        [
            html.H3(str(group.get("category") or "Fuente recomendada")),
            html.Div(
                [_source_card(source) for source in group.get("sources", [])],
                className="about-source-grid about-source-grid--single",
            ),
        ],
        className="about-source-category",
    )


def _source_card(source: dict[str, str]) -> html.Article:
    note = str(source.get("note") or "").strip()
    children: list[Any] = [
        html.Div(
            [
                html.Span(str(source.get("type") or "Fuente"), className="about-resource-card__tag"),
                html.Span(str(source.get("entity") or ""), className="about-resource-card__entity"),
            ],
            className="about-resource-card__meta",
        ),
        html.H3(str(source.get("title") or "")),
        html.P(str(source.get("description") or "")),
    ]
    if note:
        children.append(html.P(note, className="about-resource-card__note"))
    children.append(
        html.A(
            f"Abrir {source.get('title') or 'recurso oficial'} en una pestaña nueva",
            href=str(source.get("url") or "#"),
            target="_blank",
            rel="noopener noreferrer",
            className="about-resource-card__link",
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


def _about_block(
    title: str,
    paragraphs: list[tuple[str, str]],
    link: tuple[str, str, str] | None = None,
) -> html.Article:
    children: list[Any] = [
        html.H2(title),
        *[html.P(es, **text_attrs(es, en)) for es, en in paragraphs],
    ]
    if link:
        href, label_es, label_en = link
        children.append(
            html.A(
                label_es,
                href=href,
                target="_blank",
                rel="noopener noreferrer",
                className="about-source-link",
                **text_attrs(label_es, label_en),
            )
        )
    return html.Article(
        children,
        className="about-card",
    )


def _about_ilga_empty_state() -> html.P:
    return html.P(
        "Selecciona un criterio para consultar su detalle jurídico.",
        className="about-empty about-empty--compact",
        **text_attrs(
            "Selecciona un criterio para consultar su detalle jurídico.",
            "Select a criterion to view its legal details.",
        ),
    )


def _ilga_detail_section(document: dict[str, Any] | None) -> html.Section:
    year = document.get("year") if isinstance(document, dict) else None
    countries = _countries_with_criteria(document)
    options = [
        {
            "label": f"{country.get('country', '')} ({country.get('country_code', '')})",
            "value": _country_key(country),
        }
        for country in countries
    ]
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


def _country_criteria_panel(country: dict[str, Any]) -> html.Div:
    ranking = country.get("ranking")
    ranking_text = f"{float(ranking):.2f}%" if isinstance(ranking, (int, float)) else "-"
    criteria = country.get("criteria") if isinstance(country.get("criteria"), list) else []
    return html.Div(
        [
            html.Div(
                [
                    html.H3(str(country.get("country") or "País")),
                    html.Span(str(country.get("country_code") or "")),
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


def _criterion_row(criterion: dict[str, Any]) -> html.Div:
    weight = criterion.get("weight")
    value = criterion.get("value")
    metadata_es = get_criterion_metadata(criterion, "es")
    metadata_en = get_criterion_metadata(criterion, "en")
    status_es = get_criterion_status(value, weight, "es")
    status_en = get_criterion_status(value, weight, "en")
    score_es = get_criterion_score_label(value, weight, "es") or "Puntuación: información no disponible"
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
