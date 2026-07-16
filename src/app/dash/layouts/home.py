from __future__ import annotations

from datetime import date
from typing import Any

from flask_login import current_user

from app.analytics.country_status_admin_service import (
    CountryStatusAuthorizationError,
    CountryStatusValidationError,
    delete_country_lgbti_status,
    load_country_lgbti_status_for_edit,
    save_country_lgbti_status,
)
from app.analytics.figures import build_fra_choropleth, build_ilga_choropleth
from app.analytics.country_status_service import get_country_lgbti_status
from app.analytics.repository import (
    FraIndicator,
    get_fra_categories,
    get_fra_indicator_answers,
    get_fra_mongo_indicators_by_category,
    get_ilga_document_by_year,
    get_ilga_years,
    get_latest_ilga_document,
)
from app.analytics.statistics_normalizers import normalize_country_code
from app.auth.permissions import is_admin_user
from app.dash.compat import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from app.dash.i18n import text, text_attrs
from app.dash.layouts.navigation import build_navbar


MAP_MODE_OPTIONS = [
    {"label": "Situacion legal LGBTIQ+ en Europa", "value": "ilga"},
    {"label": "Discriminacion y datos sociales", "value": "fra"},
]


def build_home_layout() -> html.Div:
    ilga_document = get_latest_ilga_document()
    ilga_years = get_ilga_years()
    current_year = ilga_document.get("year") if isinstance(ilga_document, dict) else None
    if current_year and current_year not in ilga_years:
        ilga_years = [int(current_year), *ilga_years]

    categories = get_fra_categories()

    return html.Div(
        [
            build_navbar(active="home"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.P(
                                                "RainbowLens",
                                                className="home-map-eyebrow",
                                                **text_attrs("RainbowLens", "RainbowLens"),
                                            ),
                                            html.H1(
                                                text("Mapa europeo LGBTIQ+", "European LGBTIQ+ map"),
                                                id="home-map-title",
                                                className="home-map-heading",
                                            ),
                                            html.P(
                                                _ilga_copy(ilga_document),
                                                id="home-map-copy",
                                                className="home-map-copy",
                                            ),
                                        ],
                                        className="home-map-intro",
                                    ),
                                    html.Div(
                                        _ilga_metrics(ilga_document),
                                        id="home-map-metrics",
                                        className="home-map-metrics",
                                    ),
                                ],
                                className="home-map-header",
                            ),
                            html.Div(
                                [
                                    _control_field(
                                        ("Vista del mapa", "Map view"),
                                        dcc.Dropdown(
                                            id="home-map-mode",
                                            options=MAP_MODE_OPTIONS,
                                            value="ilga",
                                            clearable=False,
                                            className="home-dropdown",
                                        ),
                                    ),
                                    _control_field(
                                        ("Año ILGA", "ILGA year"),
                                        dcc.Dropdown(
                                            id="home-ilga-year",
                                            options=[
                                                {"label": str(year), "value": year}
                                                for year in ilga_years
                                            ],
                                            value=current_year,
                                            clearable=False,
                                            disabled=not bool(ilga_years),
                                            className="home-dropdown",
                                        ),
                                        "home-ilga-control",
                                        "home-ilga-control",
                                    ),
                                    _control_field(
                                        ("Categoria FRA", "FRA category"),
                                        dcc.Dropdown(
                                            id="home-fra-category",
                                            options=[
                                                {"label": category, "value": category}
                                                for category in categories
                                            ],
                                            value=None,
                                            clearable=True,
                                            placeholder="Selecciona una categoria",
                                            disabled=True,
                                            className="home-dropdown",
                                        ),
                                        "home-fra-control",
                                        "home-fra-category-control",
                                    ),
                                    _control_field(
                                        ("Topico FRA", "FRA topic"),
                                        dcc.Dropdown(
                                            id="home-fra-indicator",
                                            options=[],
                                            value=None,
                                            clearable=False,
                                            disabled=True,
                                            placeholder="Selecciona primero una categoria",
                                            className="home-dropdown",
                                        ),
                                        "home-fra-control",
                                        "home-fra-indicator-control",
                                    ),
                                    _control_field(
                                        ("Pais o paises", "Country or countries"),
                                        dcc.Dropdown(
                                            id="home-country-select",
                                            options=_ilga_country_options(ilga_document),
                                            value=[],
                                            clearable=True,
                                            multi=True,
                                            placeholder="Selecciona en el mapa o aqui",
                                            className="home-dropdown home-country-dropdown",
                                        ),
                                        "home-country-control",
                                        "home-country-control",
                                    ),
                                ],
                                className="home-map-controls",
                            ),
                            dcc.Graph(
                                id="home-main-map",
                                figure=_home_map_figure(build_ilga_choropleth(ilga_document)),
                                className="home-europe-map",
                                config={
                                    "displayModeBar": True,
                                    "displaylogo": False,
                                    "responsive": True,
                                    "scrollZoom": True,
                                    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                                },
                            ),
                            dcc.Store(id="home-country-status-refresh", data=0),
                            dcc.Store(id="home-country-status-editor-state", data={}),
                            html.Div(
                                id="country-status-admin-feedback",
                                className="country-status-admin-feedback",
                                role="status",
                            ),
                            html.Div(id="home-country-status", className="country-status-anchor"),
                            html.Div(id="country-status-editor", className="country-status-editor-shell"),
                            html.Div(
                                [
                                    html.Span(
                                        _ilga_source(ilga_document),
                                        id="home-map-source",
                                        className="home-map-source",
                                    ),
                                    html.A(
                                        text("Abrir estadisticas", "Open statistics"),
                                        href="/statistics",
                                        className="home-map-link",
                                    ),
                                ],
                                className="home-map-footer",
                            ),
                        ],
                        className="home-map-stage",
                    ),
                    html.Section(
                        [
                            _source_summary(
                                "ILGA Europe",
                                (
                                    "ILGA Europe analiza el marco legal y politico que afecta a "
                                    "las personas LGBTIQ+ en Europa. Su Rainbow Map resume areas "
                                    "como igualdad, familia, delitos de odio, reconocimiento legal "
                                    "de genero, integridad corporal, asilo y espacio de sociedad civil."
                                ),
                                (
                                    "ILGA Europe analyses the legal and policy framework affecting "
                                    "LGBTIQ+ people in Europe. Its Rainbow Map summarises areas such "
                                    "as equality, family, hate crime, legal gender recognition, bodily "
                                    "integrity, asylum and civil society space."
                                ),
                                ("Explorar el contexto legal", "Explore the legal context"),
                            ),
                            _source_summary(
                                "FRA",
                                (
                                    "La Agencia de los Derechos Fundamentales de la Union Europea "
                                    "recoge datos de encuesta sobre experiencias de discriminacion, "
                                    "seguridad, visibilidad, vida cotidiana y condiciones sociales. "
                                    "Estos indicadores ayudan a complementar el analisis legal con "
                                    "evidencia social."
                                ),
                                (
                                    "The European Union Agency for Fundamental Rights collects survey "
                                    "data on discrimination, safety, visibility, daily life and social "
                                    "conditions. These indicators complement legal analysis with social "
                                    "evidence."
                                ),
                                ("Ampliar metodologia FRA", "Expand FRA methodology"),
                            ),
                        ],
                        className="home-source-grid",
                    ),
                ],
                className="home-data-shell",
            ),
        ]
    )


def register_home_callbacks(app: Dash) -> None:
    @app.callback(
        Output("home-ilga-year", "disabled"),
        Output("home-fra-category", "disabled"),
        Output("home-ilga-control", "className"),
        Output("home-fra-category-control", "className"),
        Output("home-fra-indicator-control", "className"),
        Input("home-map-mode", "value"),
    )
    def update_home_control_state(mode: str | None):
        is_fra = mode == "fra"
        ilga_class = _control_class("home-ilga-control", inactive=is_fra)
        fra_category_class = _control_class("home-fra-control", inactive=not is_fra)
        fra_indicator_class = _control_class("home-fra-control", inactive=not is_fra)
        return is_fra, not is_fra, ilga_class, fra_category_class, fra_indicator_class

    @app.callback(
        Output("home-fra-indicator", "options"),
        Output("home-fra-indicator", "value"),
        Output("home-fra-indicator", "disabled"),
        Output("home-fra-indicator", "placeholder"),
        Input("home-map-mode", "value"),
        Input("home-fra-category", "value"),
    )
    def update_home_fra_indicators(mode: str | None, category: str | None):
        if mode != "fra":
            return [], None, True, "Activa la vista FRA"
        if not category:
            return [], None, True, "Selecciona primero una categoria"

        indicators = get_fra_mongo_indicators_by_category(category)
        if not indicators:
            return [], None, True, "No hay documentos para esta categoria"

        options = [
            {"label": _fra_indicator_option_label(indicator), "value": indicator.code}
            for indicator in indicators
        ]
        return options, None, False, "Selecciona un topico"

    @app.callback(
        Output("home-main-map", "figure"),
        Output("home-map-title", "children"),
        Output("home-map-copy", "children"),
        Output("home-map-source", "children"),
        Output("home-map-metrics", "children"),
        Input("home-map-mode", "value"),
        Input("home-ilga-year", "value"),
        Input("home-fra-indicator", "value"),
    )
    def update_home_map(mode: str | None, ilga_year: int | None, fra_code: str | None):
        if mode == "fra":
            document = get_fra_indicator_answers(fra_code or "")
            return (
                _home_map_figure(build_fra_choropleth(document)),
                text("Mapa europeo de indicadores FRA", "European FRA indicators map"),
                _fra_copy(document),
                _fra_source(document),
                _fra_metrics(document),
            )

        document = get_ilga_document_by_year(ilga_year)
        return (
            _home_map_figure(build_ilga_choropleth(document)),
            text("Situacion legal LGBTIQ+ en Europa", "LGBTIQ+ legal situation in Europe"),
            _ilga_copy(document),
            _ilga_source(document),
            _ilga_metrics(document),
        )

    @app.callback(
        Output("home-country-select", "options"),
        Output("home-country-select", "value"),
        Input("home-map-mode", "value"),
        Input("home-ilga-year", "value"),
        Input("home-fra-indicator", "value"),
        State("home-country-select", "value"),
    )
    def update_home_country_options(
        mode: str | None,
        ilga_year: int | None,
        fra_code: str | None,
        current_countries: list[str] | None,
    ):
        if mode == "fra":
            options = _fra_country_options(get_fra_indicator_answers(fra_code or ""))
        else:
            options = _ilga_country_options(get_ilga_document_by_year(ilga_year))
        available = {str(option.get("value")) for option in options}
        selected = [
            country
            for country in current_countries or []
            if normalize_country_code(country) in available or str(country) in available
        ]
        return options, selected

    @app.callback(
        Output("home-country-select", "value", allow_duplicate=True),
        Input("home-main-map", "clickData"),
        State("home-country-select", "value"),
        prevent_initial_call=True,
    )
    def select_home_country_from_map(click_data: dict[str, Any] | None, current: list[str] | None):
        iso = _iso_from_map_click(click_data)
        if not iso:
            return current or []
        selected = list(current or [])
        if iso not in selected:
            selected.append(iso)
        return selected

    @app.callback(
        Output("home-country-status", "children"),
        Input("home-country-select", "value"),
        Input("home-ilga-year", "value"),
        Input("home-country-status-refresh", "data"),
        State("home-country-select", "options"),
    )
    def update_home_country_status(
        selected_countries: list[str] | None,
        requested_year: int | None,
        _refresh: int | None,
        country_options: list[dict[str, Any]] | None,
    ):
        selected = _normalize_selected_countries(selected_countries)
        if not selected:
            return []
        label_by_code = _country_label_map(country_options or [])
        statuses = get_country_lgbti_status(selected, requested_year)
        return _country_status_section(
            statuses,
            label_by_code,
            requested_year,
            can_manage=is_admin_user(current_user),
        )

    @app.callback(
        Output("country-status-editor", "children"),
        Output("country-status-editor-state", "data"),
        Output("country-status-admin-feedback", "children"),
        Input({"type": "country-status-edit", "country_code": ALL, "year": ALL}, "n_clicks"),
        Input({"type": "country-status-add", "country_code": ALL, "year": ALL}, "n_clicks"),
        Input({"type": "country-status-editor-cancel", "slot": ALL}, "n_clicks"),
        State("home-country-select", "options"),
        prevent_initial_call=True,
    )
    def open_or_cancel_country_status_editor(
        _edit_clicks: list[int] | None,
        _add_clicks: list[int] | None,
        _cancel_clicks: int | None,
        country_options: list[dict[str, Any]] | None,
    ):
        trigger = ctx.triggered_id
        trigger_type = trigger.get("type") if isinstance(trigger, dict) else trigger
        if trigger_type == "country-status-editor-cancel":
            return [], {}, ""
        if not isinstance(trigger, dict):
            return no_update, no_update, no_update
        if not is_admin_user(current_user):
            return [], {}, "No tienes permisos para modificar estos datos."

        country_code = normalize_country_code(trigger.get("country_code"))
        year = _safe_year(trigger.get("year"))
        mode = "edit" if trigger.get("type") == "country-status-edit" else "create"
        record = load_country_lgbti_status_for_edit(country_code, year) if mode == "edit" else None
        label_by_code = _country_label_map(country_options or [])
        initial = _editor_initial_record(country_code, year, record, label_by_code)
        state = {
            "mode": mode,
            "country_code": country_code,
            "year": year,
            "exists": bool(record),
        }
        return _country_status_editor(initial, state, country_options or [], {}), state, ""

    @app.callback(
        Output("country-status-editor", "children", allow_duplicate=True),
        Output("country-status-editor-state", "data", allow_duplicate=True),
        Output("country-status-admin-feedback", "children", allow_duplicate=True),
        Output("home-country-status-refresh", "data"),
        Input({"type": "country-status-editor-save", "slot": ALL}, "n_clicks"),
        Input({"type": "country-status-editor-delete", "slot": ALL}, "n_clicks"),
        State("country-status-editor-state", "data"),
        State("home-country-select", "options"),
        State("home-country-status-refresh", "data"),
        State({"type": "country-status-form-country", "slot": ALL}, "value"),
        State({"type": "country-status-form-country-code", "slot": ALL}, "value"),
        State({"type": "country-status-form-year", "slot": ALL}, "value"),
        State({"type": "country-status-form-title", "slot": ALL}, "value"),
        State({"type": "country-status-form-summary", "slot": ALL}, "value"),
        State({"type": "country-status-form-legal-context", "slot": ALL}, "value"),
        State({"type": "country-status-form-social-context", "slot": ALL}, "value"),
        State({"type": "country-status-form-positive", "slot": ALL}, "value"),
        State({"type": "country-status-form-challenges", "slot": ALL}, "value"),
        State({"type": "country-status-form-source-name", "slot": ALL}, "value"),
        State({"type": "country-status-form-source-url", "slot": ALL}, "value"),
        State({"type": "country-status-form-reviewed-at", "slot": ALL}, "value"),
        State({"type": "country-status-form-observations", "slot": ALL}, "value"),
        State({"type": "country-status-form-active", "slot": ALL}, "value"),
        State({"type": "country-status-delete-confirm", "slot": ALL}, "value"),
        prevent_initial_call=True,
    )
    def persist_country_status_editor(
        _save_clicks: int | None,
        _delete_clicks: int | None,
        editor_state: dict[str, Any] | None,
        country_options: list[dict[str, Any]] | None,
        refresh: int | None,
        country_values: list[str] | None,
        country_code_values: list[str] | None,
        year_values: list[int | str] | None,
        title_values: list[str] | None,
        summary_values: list[str] | None,
        legal_context_values: list[str] | None,
        social_context_values: list[str] | None,
        positive_developments_values: list[str] | None,
        main_challenges_values: list[str] | None,
        source_name_values: list[str] | None,
        source_url_values: list[str] | None,
        reviewed_at_values: list[str] | None,
        observations_values: list[str] | None,
        active_value_lists: list[list[str]] | None,
        delete_confirm_value_lists: list[list[str]] | None,
    ):
        trigger = ctx.triggered_id
        trigger_type = trigger.get("type") if isinstance(trigger, dict) else trigger
        if trigger_type not in {"country-status-editor-save", "country-status-editor-delete"}:
            return no_update, no_update, no_update, no_update
        if not is_admin_user(current_user):
            return [], {}, "No tienes permisos para modificar estos datos.", refresh or 0

        state = editor_state or {}
        label_by_code = _country_label_map(country_options or [])
        country = _first_value(country_values)
        country_code = _first_value(country_code_values)
        year = _first_value(year_values)
        title = _first_value(title_values)
        summary = _first_value(summary_values)
        legal_context = _first_value(legal_context_values)
        social_context = _first_value(social_context_values)
        positive_developments = _first_value(positive_developments_values)
        main_challenges = _first_value(main_challenges_values)
        source_name = _first_value(source_name_values)
        source_url = _first_value(source_url_values)
        reviewed_at = _first_value(reviewed_at_values)
        observations = _first_value(observations_values)
        active_values = _first_value(active_value_lists, [])
        delete_confirm_values = _first_value(delete_confirm_value_lists, [])
        selected_country_code = normalize_country_code(country or country_code)
        selected_country_name = label_by_code.get(selected_country_code) or str(country or "").strip()
        payload = {
            "country": selected_country_name,
            "country_code": selected_country_code,
            "year": year,
            "title": title,
            "summary": summary,
            "legal_context": legal_context,
            "social_context": social_context,
            "positive_developments": positive_developments,
            "main_challenges": main_challenges,
            "source_name": source_name,
            "source_url": source_url,
            "reviewed_at": reviewed_at,
            "observations": observations,
            "active": "active" in (active_values or []),
        }

        if trigger_type == "country-status-editor-delete":
            try:
                delete_country_lgbti_status(
                    selected_country_code,
                    int(year or 0),
                    user=current_user,
                    confirmed="confirm" in (delete_confirm_values or []),
                )
            except CountryStatusValidationError as exc:
                return (
                    _country_status_editor(payload, state, country_options or [], exc.field_errors),
                    state,
                    "No se pudieron eliminar los datos. Revisa la confirmacion.",
                    refresh or 0,
                )
            except (CountryStatusAuthorizationError, RuntimeError):
                return [], {}, "No se pudieron eliminar los datos.", refresh or 0
            return [], {}, "Los datos se han eliminado correctamente.", (refresh or 0) + 1

        try:
            saved = save_country_lgbti_status(
                payload,
                user=current_user,
                mode=str(state.get("mode") or "edit"),
            )
        except CountryStatusValidationError as exc:
            return (
                _country_status_editor(payload, state, country_options or [], exc.field_errors),
                state,
                "No se pudieron guardar los cambios. Revisa los campos e intentalo de nuevo.",
                refresh or 0,
            )
        except (CountryStatusAuthorizationError, RuntimeError):
            return [], {}, "No se pudieron guardar los cambios.", refresh or 0

        message = (
            "Los datos se han creado correctamente."
            if state.get("mode") == "create"
            else "Los datos se han actualizado correctamente."
        )
        return [], {"country_code": saved["country_code"], "year": saved["year"]}, message, (refresh or 0) + 1

    @app.callback(
        Output({"type": "country-status-form-country-code", "slot": ALL}, "value"),
        Input({"type": "country-status-form-country", "slot": ALL}, "value"),
        prevent_initial_call=True,
    )
    def sync_country_status_iso(country_values: list[str] | None):
        return [normalize_country_code(value) for value in country_values or []]


def _home_map_figure(figure: Any) -> Any:
    figure.update_layout(
        autosize=True,
        geo={
            "center": {"lon": 20, "lat": 54},
            "projection": {"scale": 1.18},
        },
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
    )
    return figure


def _ilga_country_options(document: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(document, dict):
        return []
    countries = []
    for country in document.get("countries", []):
        if not isinstance(country, dict):
            continue
        country_name = str(country.get("country") or "").strip()
        country_code = normalize_country_code(country.get("country_code"), country_name)
        if country_name and country_code:
            countries.append({"label": f"{country_name} ({country_code})", "value": country_code})
    return sorted(countries, key=lambda item: item["label"])


def _fra_country_options(document: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(document, dict):
        return []
    countries_by_code: dict[str, str] = {}
    for answer in document.get("answers", []):
        if not isinstance(answer, dict):
            continue
        country_name = str(answer.get("country") or "").strip()
        country_code = normalize_country_code(answer.get("country_code"), country_name)
        if country_name and country_code and country_code != "EU27":
            countries_by_code.setdefault(country_code, country_name)
    return [
        {"label": f"{country} ({country_code})", "value": country_code}
        for country_code, country in sorted(countries_by_code.items(), key=lambda item: item[1])
    ]


def _iso_from_map_click(click_data: dict[str, Any] | None) -> str:
    points = (click_data or {}).get("points") or []
    if not points:
        return ""
    customdata = points[0].get("customdata")
    raw_code = customdata[0] if isinstance(customdata, (list, tuple)) and customdata else customdata
    return normalize_country_code(raw_code)


def _normalize_selected_countries(countries: list[str] | None) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for country in countries or []:
        country_code = normalize_country_code(country)
        if country_code and country_code not in seen:
            selected.append(country_code)
            seen.add(country_code)
    return selected


def _country_label_map(options: list[dict[str, Any]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for option in options:
        code = normalize_country_code(option.get("value"))
        label = str(option.get("label") or code).strip()
        if "(" in label:
            label = label.rsplit("(", 1)[0].strip()
        if code:
            labels[code] = label
    return labels


def _country_status_section(
    statuses: list[dict[str, Any]],
    label_by_code: dict[str, str],
    requested_year: int | None = None,
    *,
    can_manage: bool = False,
) -> html.Section:
    title = (
        f"Situacion actual en {_status_country_name(statuses[0], label_by_code)}"
        if len(statuses) == 1
        else "Situacion actual de los paises seleccionados"
    )
    return html.Section(
        [
            html.Header(
                [
                    html.P("Contexto cualitativo", className="country-status-eyebrow"),
                    html.H2(title),
                ],
                className="country-status-section__header",
            ),
            html.Div(
                [
                    _country_status_card(status, label_by_code, requested_year, can_manage)
                    for status in statuses
                ],
                className="country-status-grid",
            ),
        ],
        className="country-status-section",
    )


def _country_status_card(
    status: dict[str, Any],
    label_by_code: dict[str, str],
    requested_year: int | None,
    can_manage: bool = False,
) -> html.Article:
    country_name = _status_country_name(status, label_by_code)
    country_code = str(status.get("country_code") or "").strip()
    year = status.get("year")
    if not status.get("available"):
        children: list[Any] = [
                html.Header(
                    [
                        html.H3(country_name),
                        html.Span(country_code, className="country-status-card__year"),
                    ],
                    className="country-status-card__header",
                ),
                html.P(status.get("summary"), className="country-status-card__empty"),
        ]
        if can_manage:
            children.append(_country_status_admin_button("add", country_code, requested_year, "Anadir datos"))
        return html.Article(children, className="country-status-card country-status-card--empty")

    details_children = []
    details_children.extend(_status_text_block("Contexto legal", status.get("legal_context")))
    details_children.extend(_status_text_block("Contexto social", status.get("social_context")))
    details_children.extend(_status_list_block("Avances destacados", status.get("positive_developments")))
    details_children.extend(_status_list_block("Retos principales", status.get("main_challenges")))

    children: list[Any] = [
        html.Header(
            [
                html.Div(
                    [
                        html.H3(country_name),
                        html.Span(country_code, className="country-status-card__code"),
                    ],
                    className="country-status-card__title",
                ),
                html.Span(f"Año {year or '-'}", className="country-status-card__year"),
            ],
            className="country-status-card__header",
        ),
    ]
    if status.get("title"):
        children.append(html.H4(str(status.get("title")), className="country-status-card__subtitle"))
    if requested_year and year and int(year) != int(requested_year):
        children.append(
            html.P(
                f"Informacion cualitativa disponible para {year}.",
                className="country-status-card__notice",
            )
        )
    children.append(html.P(status.get("summary"), className="country-status-card__summary"))
    if details_children:
        children.append(
            html.Details(
                [
                    html.Summary("Ver contexto completo"),
                    *details_children,
                ],
                className="country-status-card__details",
            )
        )
    if status.get("observations"):
        children.append(
            html.P(
                str(status.get("observations")),
                className="country-status-card__observations",
            )
        )
    children.append(_status_source(status))
    if can_manage:
        children.append(_country_status_admin_button("edit", country_code, year, "Editar"))
    return html.Article(children, className="country-status-card")


def _country_status_admin_button(
    action: str,
    country_code: str,
    year: int | str | None,
    label: str,
) -> html.Button:
    return html.Button(
        label,
        id={
            "type": f"country-status-{action}",
            "country_code": country_code,
            "year": str(year or ""),
        },
        type="button",
        className="country-status-admin-button",
    )


def _country_status_editor(
    record: dict[str, Any],
    state: dict[str, Any],
    country_options: list[dict[str, Any]],
    errors: dict[str, str],
) -> html.Div:
    mode = str(state.get("mode") or "edit")
    exists = bool(state.get("exists")) or mode == "edit"
    title = "Editar datos cualitativos" if exists else "Anadir datos cualitativos"
    country_code = normalize_country_code(record.get("country_code"))
    country_options = _ensure_country_option(country_options, record)
    return html.Div(
        [
            html.Div(className="country-status-editor-backdrop"),
            html.Section(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.P("Administracion", className="country-status-eyebrow"),
                                    html.H2(title),
                                    html.P(
                                        "Los cambios se guardaran directamente en la base de datos.",
                                        className="country-status-editor-copy",
                                    ),
                                ],
                                className="country-status-editor-title",
                            ),
                            html.Button(
                                "Cancelar",
                                id=_editor_id("country-status-editor-cancel"),
                                type="button",
                                className="country-status-editor-cancel",
                            ),
                        ],
                        className="country-status-editor-header",
                    ),
                    html.Div(
                        [
                            _editor_group(
                                "Identificacion",
                                [
                                    _editor_field(
                                        "Pais",
                                        dcc.Dropdown(
                                            id=_editor_id("country-status-form-country"),
                                            options=country_options,
                                            value=country_code,
                                            clearable=False,
                                            className="home-dropdown",
                                        ),
                                        errors.get("country"),
                                    ),
                                    _editor_field(
                                        "Codigo ISO",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-country-code"),
                                            type="text",
                                            value=country_code,
                                            maxLength=3,
                                        ),
                                        errors.get("country_code"),
                                    ),
                                    _editor_field(
                                        "Ano",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-year"),
                                            type="number",
                                            min=2000,
                                            max=2100,
                                            step=1,
                                            value=record.get("year") or date.today().year,
                                        ),
                                        errors.get("year"),
                                    ),
                                    dcc.Checklist(
                                        id=_editor_id("country-status-form-active"),
                                        options=[{"label": "Registro activo", "value": "active"}],
                                        value=["active"] if record.get("active", True) else [],
                                        className="country-status-editor-checklist",
                                    ),
                                ],
                            ),
                            _editor_group(
                                "Estado",
                                [
                                    _editor_field(
                                        "Estado general",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-title"),
                                            type="text",
                                            value=record.get("title") or "",
                                            maxLength=240,
                                        ),
                                        errors.get("title"),
                                    ),
                                    _editor_field(
                                        "Descripcion",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-summary"),
                                            value=record.get("summary") or "",
                                            maxLength=6000,
                                        ),
                                        errors.get("summary"),
                                    ),
                                ],
                            ),
                            _editor_group(
                                "Contexto",
                                [
                                    _editor_field(
                                        "Contexto legal",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-legal-context"),
                                            value=record.get("legal_context") or "",
                                            maxLength=6000,
                                        ),
                                        errors.get("legal_context"),
                                    ),
                                    _editor_field(
                                        "Contexto social",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-social-context"),
                                            value=record.get("social_context") or "",
                                            maxLength=6000,
                                        ),
                                        errors.get("social_context"),
                                    ),
                                    _editor_field(
                                        "Avances destacados",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-positive"),
                                            value=_lines_value(record.get("positive_developments")),
                                            maxLength=6000,
                                        ),
                                        errors.get("positive_developments"),
                                    ),
                                    _editor_field(
                                        "Retos principales",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-challenges"),
                                            value=_lines_value(record.get("main_challenges")),
                                            maxLength=6000,
                                        ),
                                        errors.get("main_challenges"),
                                    ),
                                ],
                            ),
                            _editor_group(
                                "Fuente",
                                [
                                    _editor_field(
                                        "Organizacion o informe",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-source-name"),
                                            type="text",
                                            value=record.get("source_name") or "",
                                            maxLength=240,
                                        ),
                                        errors.get("source_name"),
                                    ),
                                    _editor_field(
                                        "Enlace de la fuente",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-source-url"),
                                            type="url",
                                            value=record.get("source_url") or "",
                                        ),
                                        errors.get("source_url"),
                                    ),
                                    _editor_field(
                                        "Fecha de actualizacion",
                                        dcc.Input(
                                            id=_editor_id("country-status-form-reviewed-at"),
                                            type="text",
                                            placeholder="AAAA-MM-DD",
                                            value=record.get("reviewed_at") or date.today().isoformat(),
                                        ),
                                        errors.get("reviewed_at"),
                                    ),
                                ],
                            ),
                            _editor_group(
                                "Informacion adicional",
                                [
                                    _editor_field(
                                        "Observaciones",
                                        dcc.Textarea(
                                            id=_editor_id("country-status-form-observations"),
                                            value=record.get("observations") or "",
                                            maxLength=6000,
                                        ),
                                        errors.get("observations"),
                                    )
                                ],
                            ),
                            (
                                html.Div(
                                    [
                                        dcc.Checklist(
                                            id=_editor_id("country-status-delete-confirm"),
                                            options=[
                                                {
                                                    "label": "Confirmo que quiero eliminar este registro",
                                                    "value": "confirm",
                                                }
                                            ],
                                            value=[],
                                            className="country-status-editor-checklist",
                                        ),
                                        _editor_error(errors.get("delete_confirm")),
                                    ],
                                    className="country-status-editor-delete-confirm",
                                )
                                if exists
                                else dcc.Checklist(
                                    id=_editor_id("country-status-delete-confirm"),
                                    options=[],
                                    value=[],
                                    className="country-status-editor-checklist is-hidden",
                                )
                            ),
                        ],
                        className="country-status-editor-body",
                    ),
                    html.Footer(
                        [
                            html.Button(
                                "Guardar cambios",
                                id=_editor_id("country-status-editor-save"),
                                type="button",
                                className="country-status-editor-save",
                            ),
                            (
                                html.Button(
                                    "Eliminar",
                                    id=_editor_id("country-status-editor-delete"),
                                    type="button",
                                    className="country-status-editor-delete",
                                )
                                if exists
                                else html.Button(
                                    "Eliminar",
                                    id=_editor_id("country-status-editor-delete"),
                                    type="button",
                                    className="country-status-editor-delete is-hidden",
                                )
                            ),
                        ],
                        className="country-status-editor-actions",
                    ),
                ],
                className="country-status-editor-panel",
                role="dialog",
                **{"aria-modal": "true"},
            ),
        ],
        className="country-status-editor-modal",
    )


def _editor_group(title: str, children: list[Any]) -> html.Fieldset:
    return html.Fieldset(
        [html.Legend(title), *children],
        className="country-status-editor-group",
    )


def _editor_id(component_type: str) -> dict[str, str]:
    return {"type": component_type, "slot": "main"}


def _first_value(values: list[Any] | None, default: Any = None) -> Any:
    if not values:
        return default
    return values[0]


def _editor_field(label: str, control: Any, error: str | None = None) -> html.Label:
    return html.Label(
        [
            html.Span(label),
            control,
            _editor_error(error),
        ],
        className="country-status-editor-field",
    )


def _editor_error(error: str | None) -> html.P | str:
    if not error:
        return ""
    return html.P(error, className="country-status-editor-error")


def _editor_initial_record(
    country_code: str,
    year: int | None,
    record: dict[str, Any] | None,
    label_by_code: dict[str, str],
) -> dict[str, Any]:
    if record:
        return record
    return {
        "country_code": country_code,
        "country": label_by_code.get(country_code, country_code),
        "year": year or date.today().year,
        "title": "",
        "summary": "",
        "legal_context": "",
        "social_context": "",
        "observations": "",
        "positive_developments": [],
        "main_challenges": [],
        "source_name": "ILGA-Europe Annual Review 2026",
        "source_url": "https://www.ilga-europe.org/files/uploads/2026/02/2026-ILGA-EUROPE-ANNUAL-REVIEW.pdf",
        "reviewed_at": date.today().isoformat(),
        "active": True,
    }


def _ensure_country_option(
    options: list[dict[str, Any]],
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    country_code = normalize_country_code(record.get("country_code"))
    values = {normalize_country_code(option.get("value")) for option in options}
    if country_code and country_code not in values:
        return [
            *options,
            {
                "label": f"{record.get('country') or country_code} ({country_code})",
                "value": country_code,
            },
        ]
    return options


def _lines_value(value: Any) -> str:
    if not isinstance(value, list):
        return str(value or "")
    return "\n".join(str(item) for item in value if str(item).strip())


def _safe_year(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status_country_name(status: dict[str, Any], label_by_code: dict[str, str]) -> str:
    country_code = str(status.get("country_code") or "").strip()
    return str(status.get("country") or label_by_code.get(country_code) or country_code).strip()


def _status_text_block(title: str, value: Any) -> list[Any]:
    text_value = str(value or "").strip()
    if not text_value:
        return []
    return [html.H4(title), html.P(text_value)]


def _status_list_block(title: str, values: Any) -> list[Any]:
    if not isinstance(values, list) or not values:
        return []
    return [html.H4(title), html.Ul([html.Li(str(value)) for value in values if str(value).strip()])]


def _status_source(status: dict[str, Any]) -> html.Footer:
    source_name = str(status.get("source_name") or "").strip()
    source_url = str(status.get("source_url") or "").strip()
    reviewed_at = str(status.get("reviewed_at") or "").strip()
    children: list[Any] = []
    if source_name and source_url:
        children.append(
            html.A(
                source_name,
                href=source_url,
                target="_blank",
                rel="noopener noreferrer",
                className="country-status-card__source-link",
            )
        )
    elif source_name:
        children.append(html.Span(source_name))
    if reviewed_at:
        children.append(html.Span(f"Ultima revision manual: {reviewed_at}"))
    return html.Footer(children, className="country-status-card__source")


def _control_field(
    label: tuple[str, str],
    control: Any,
    class_name: str = "",
    field_id: str | None = None,
) -> html.Div:
    classes = ["home-control-field"]
    if class_name:
        classes.append(class_name)
    props = {"className": " ".join(classes)}
    if field_id:
        props["id"] = field_id
    return html.Div(
        [
            html.Label(text(label[0], label[1])),
            control,
        ],
        **props,
    )


def _control_class(base_class: str, *, inactive: bool) -> str:
    classes = ["home-control-field", base_class]
    if inactive:
        classes.append("is-inactive")
    return " ".join(classes)


def _metric(value: str, label_es: str, label_en: str) -> html.Div:
    return html.Div(
        [
            html.Strong(value),
            html.Span(label_es, **text_attrs(label_es, label_en)),
        ],
        className="home-map-metric",
    )


def _source_summary(
    title: str,
    body_es: str,
    body_en: str,
    link_label: tuple[str, str],
) -> html.Article:
    return html.Article(
        [
            html.H2(title),
            html.P(body_es, **text_attrs(body_es, body_en)),
            html.A(text(link_label[0], link_label[1]), href="/about", className="home-analysis-link"),
        ],
        className="home-source-card",
    )


def _ilga_copy(document: dict[str, Any] | None):
    if not isinstance(document, dict):
        return text("No hay un Rainbow Map disponible.", "No Rainbow Map is available.")
    year = document.get("year")
    if year:
        return text(
            f"Ranking oficial de {year}, leido desde Indicator_ilga en MongoDB.",
            f"Official {year} ranking, read from Indicator_ilga in MongoDB.",
        )
    return text(
        "Ranking legal LGBTIQ+ leido desde Indicator_ilga en MongoDB.",
        "LGBTIQ+ legal ranking read from Indicator_ilga in MongoDB.",
    )


def _ilga_source(document: dict[str, Any] | None):
    year = document.get("year") if isinstance(document, dict) else None
    if year:
        return text(f"Fuente: ILGA Europe - {year}", f"Source: ILGA Europe - {year}")
    return text("Fuente: ILGA Europe", "Source: ILGA Europe")


def _ilga_metrics(document: dict[str, Any] | None) -> list[html.Div]:
    countries = (
        document.get("countries", [])
        if isinstance(document, dict) and isinstance(document.get("countries"), list)
        else []
    )
    rankings = [
        float(country["ranking"])
        for country in countries
        if isinstance(country, dict) and isinstance(country.get("ranking"), (int, float))
    ]
    average = f"{sum(rankings) / len(rankings):.1f}%" if rankings else "-"
    year = document.get("year") if isinstance(document, dict) else None
    return [
        _metric(str(year or "-"), "Año", "Year"),
        _metric(str(len(countries)), "Paises", "Countries"),
        _metric(average, "Media ILGA", "ILGA average"),
    ]


def _fra_copy(document: dict[str, Any] | None):
    if not isinstance(document, dict):
        return text(
            "Selecciona una categoria y un topico FRA para representar sus valores por pais.",
            "Select a FRA category and topic to map values by country.",
        )
    label = (
        f"{document.get('category', '')} - "
        f"{document.get('specific_category', '')}"
    ).strip(" -")
    return text(label, label)


def _fra_source(document: dict[str, Any] | None):
    if not isinstance(document, dict):
        return text("Fuente: FRA", "Source: FRA")
    code = document.get("code", "indicador")
    return text(f"Fuente: FRA - {code}", f"Source: FRA - {code}")


def _fra_metrics(document: dict[str, Any] | None) -> list[html.Div]:
    answers = document.get("answers", []) if isinstance(document, dict) else []
    countries = {
        str(answer.get("country") or "").strip()
        for answer in answers
        if isinstance(answer, dict) and answer.get("country")
    }
    percentages = [
        float(answer["percentage"])
        for answer in answers
        if isinstance(answer, dict) and isinstance(answer.get("percentage"), (int, float))
    ]
    average = f"{sum(percentages) / len(percentages):.1f}%" if percentages else "-"
    return [
        _metric(str(len(countries)), "Paises", "Countries"),
        _metric(str(len(percentages)), "Observaciones", "Observations"),
        _metric(average, "Media FRA", "FRA average"),
    ]


def _fra_indicator_option_label(indicator: FraIndicator) -> str:
    detail = indicator.specific_category.strip()
    if detail:
        return f"{detail} - {indicator.question}"
    return indicator.question or indicator.code
