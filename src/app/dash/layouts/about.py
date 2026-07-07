from __future__ import annotations

from typing import Any

from app.analytics.repository import get_latest_ilga_document
from app.dash.compat import Dash, Input, Output, dcc, html
from app.dash.i18n import text, text_attrs
from app.dash.layouts.navigation import build_navbar


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
                                "Fuentes y metodologia",
                                className="about-eyebrow",
                                **text_attrs("Fuentes y metodologia", "Sources and methodology"),
                            ),
                            html.H1(
                                "Acerca de RainbowLens",
                                **text_attrs("Acerca de RainbowLens", "About RainbowLens"),
                            ),
                            html.P(
                                (
                                    "RainbowLens integra fuentes oficiales para analizar la "
                                    "situacion legal y social de las personas LGBTIQ+ en Europa."
                                ),
                                className="about-lead",
                                **text_attrs(
                                    (
                                        "RainbowLens integra fuentes oficiales para analizar la "
                                        "situacion legal y social de las personas LGBTIQ+ en Europa."
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
                    html.Section(
                        [
                            _about_block(
                                "ILGA Europe Rainbow Map",
                                [
                                    (
                                        "ILGA Europe evalua leyes y politicas publicas que afectan "
                                        "a las personas LGBTIQ+ en Europa y Asia Central.",
                                        (
                                            "ILGA Europe evaluates laws and public policies affecting "
                                            "LGBTIQ+ people in Europe and Central Asia."
                                        ),
                                    ),
                                    (
                                        "El Rainbow Map organiza esa informacion en indicadores "
                                        "relacionados con igualdad y no discriminacion, familia, "
                                        "delitos y discursos de odio, reconocimiento legal de genero, "
                                        "integridad corporal, asilo y espacio de sociedad civil.",
                                        (
                                            "The Rainbow Map organises this information into indicators "
                                            "related to equality and non-discrimination, family, hate "
                                            "crime and speech, legal gender recognition, bodily integrity, "
                                            "asylum and civil society space."
                                        ),
                                    ),
                                    (
                                        "En la aplicacion, estos datos permiten comparar paises y "
                                        "visualizar la evolucion del marco legal por año.",
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
                                        "La Agencia de los Derechos Fundamentales de la Union Europea "
                                        "recoge datos de encuesta sobre experiencias reales de la "
                                        "poblacion LGBTIQ+.",
                                        (
                                            "The European Union Agency for Fundamental Rights collects "
                                            "survey data on real experiences of the LGBTIQ+ population."
                                        ),
                                    ),
                                    (
                                        "Sus indicadores cubren dimensiones como discriminacion, "
                                        "visibilidad, seguridad, acoso, condiciones socioeconomicas "
                                        "y relacion con instituciones.",
                                        (
                                            "Its indicators cover dimensions such as discrimination, "
                                            "visibility, safety, harassment, socioeconomic conditions "
                                            "and relationships with institutions."
                                        ),
                                    ),
                                    (
                                        "En RainbowLens, FRA complementa el mapa legal de ILGA con "
                                        "evidencia social comparable entre paises.",
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
                                        "espanol, con atencion especial a quienes afrontan mayor "
                                        "vulnerabilidad.",
                                        (
                                            "FELGTBI+ defends and promotes human rights and equality "
                                            "for LGTBI+ people and their families in Spain, with special "
                                            "attention to those facing greater vulnerability."
                                        ),
                                    ),
                                    (
                                        "Su trabajo combina incidencia social y politica, apoyo al "
                                        "movimiento asociativo, cooperacion en red, transparencia, "
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
                                        "derechos y organizacion social LGTBI+.",
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


def register_about_callbacks(app: Dash) -> None:
    @app.callback(
        Output("about-ilga-criteria", "children"),
        Input("about-ilga-country", "value"),
    )
    def update_ilga_country_criteria(country_key: str | None):
        document = get_latest_ilga_document()
        country = _find_country(document, country_key)
        if not country:
            return html.P(
                "Selecciona un pais con criterios desglosados.",
                className="about-empty",
                **text_attrs(
                    "Selecciona un pais con criterios desglosados.",
                    "Select a country with detailed criteria.",
                ),
            )
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
                    html.P(
                        (
                            "El ranking global sintetiza criterios legales y politicos. "
                            "Cada criterio incluye su categoria, indicador, valor maximo "
                            "y valor registrado para el pais. En años historicos puede "
                            "existir solo el ranking global; en ese caso criteria se "
                            "guarda como null."
                        ),
                        className="about-lead",
                        **text_attrs(
                            (
                                "El ranking global sintetiza criterios legales y politicos. "
                                "Cada criterio incluye su categoria, indicador, valor maximo "
                                "y valor registrado para el pais. En años historicos puede "
                                "existir solo el ranking global; en ese caso criteria se "
                                "guarda como null."
                            ),
                            (
                                "The global ranking summarises legal and policy criteria. "
                                "Each criterion includes its category, indicator, maximum value "
                                "and value registered for the country. Historical years may only "
                                "contain the global ranking; in that case criteria is stored as null."
                            ),
                        ),
                    ),
                ],
                className="about-section-header",
            ),
            (
                html.Div(
                    [
                        html.Label(
                            text("Pais", "Country"),
                            htmlFor="about-ilga-country",
                        ),
                        dcc.Dropdown(
                            id="about-ilga-country",
                            options=options,
                            value=options[0]["value"] if options else None,
                            clearable=False,
                            className="about-country-dropdown",
                        ),
                        html.Div(
                            _country_criteria_panel(countries[0]) if countries else "",
                            id="about-ilga-criteria",
                            className="about-country-panel",
                        ),
                    ],
                    className="about-country-browser",
                )
                if countries
                else html.P(
                    "No hay criterios desglosados para el ultimo año disponible.",
                    className="about-empty",
                    **text_attrs(
                        "No hay criterios desglosados para el ultimo año disponible.",
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
                    html.H3(str(country.get("country") or "Pais")),
                    html.Span(str(country.get("country_code") or "")),
                    html.Strong(ranking_text),
                ],
                className="about-country-summary",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Indicador", **text_attrs("Indicador", "Indicator")),
                            html.Div(
                                [
                                    html.Span("Maximo", **text_attrs("Maximo", "Maximum")),
                                    html.Span("Pais", **text_attrs("Pais", "Country")),
                                ],
                                className="about-criterion-values",
                            ),
                        ],
                        className="about-criterion-row about-criterion-head",
                    ),
                    *[_criterion_row(criterion) for criterion in criteria],
                ],
                className="about-criteria-list",
            ),
        ],
    )


def _criterion_row(criterion: dict[str, Any]) -> html.Div:
    weight = criterion.get("weight")
    value = criterion.get("value")
    indicator = str(criterion.get("indicator") or "Indicador")
    category = str(criterion.get("category") or "Sin categoria")
    return html.Div(
        [
            html.Div(
                [
                    html.Strong(indicator, **text_attrs(indicator, indicator)),
                    html.Span(category, **text_attrs(category, category)),
                ],
                className="about-criterion-main",
            ),
            html.Div(
                [
                    html.Span(_format_number(weight), title="Maximum criterion value"),
                    html.Span(_format_number(value), title="Country value"),
                ],
                className="about-criterion-values",
            ),
        ],
        className="about-criterion-row",
    )


def _format_number(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return "-"
