from __future__ import annotations

from typing import Any

from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.development.base_component import Component
from flask_login import current_user
from pymongo.errors import PyMongoError

from app.auth.permissions import (
    Permission,
    can_access_docente_material,
    can_manage_own_edu_games,
    user_has_permission,
)
from app.dash.components.didactica import (
    access_denied,
    glossary_card,
    lesson_card,
    resource_card,
    teacher_resource_details,
    translated,
)
from app.dash.components.source_attribution import build_source_attribution
from app.dash.i18n import dash_attrs, text, text_attrs
from app.dash.layouts.navigation import build_navbar
from app.edu.custom_game_service import (
    CustomGameAuthorizationError,
    CustomGameValidationError,
    delete_owned_game,
    get_owned_game,
    list_owned_games,
    save_owned_game,
)
from app.edu.game_service import guess_options, new_game_state, true_false_question
from app.edu.glossary_service import (
    get_glossary_term,
    glossary_categories,
    search_glossary,
)
from app.edu.lesson_service import get_lesson, list_lessons
from app.edu.progress_service import complete_lesson, progress_summary, save_game_score
from app.edu.teacher_service import (
    generate_teacher_resource_pdf,
    get_teacher_resource,
    list_teacher_resources,
)
from app.edu.translations import CATEGORIES, pair, tr


def build_didactica_layout() -> Component:
    cards = [
        resource_card("dictionary", "dictionary_desc", "/didactica/diccionario", "Aa"),
        resource_card("presentations", "presentations_desc", "/didactica/presentaciones", "▤"),
    ]
    if user_has_permission(current_user, Permission.PLAY_EDU_GAMES):
        cards.append(resource_card("games", "games_desc", "/didactica/juegos", "◇"))
    if can_access_docente_material(current_user):
        cards.append(resource_card("docente", "docente_desc", "/didactica/docentes", "▣"))
    if current_user.is_authenticated:
        cards.append(resource_card("progress", "progress_desc", "/didactica/progreso", "✓"))
    return _page(
        html.Main(
            [
                html.Header(
                    [translated("learning", tag=html.H1), translated("intro", tag=html.P)],
                    className="didactica-hero",
                ),
                html.Section(
                    cards,
                    className="didactica-resource-grid",
                    **dash_attrs({"aria-label": pair("learning")[0]}),
                ),
            ],
            className="didactica-shell",
        )
    )


def build_dictionary_layout() -> Component:
    category_options = [{"label": text(*pair("all_categories")), "value": "all"}]
    category_options.extend(
        {"label": text(*CATEGORIES[category]), "value": category}
        for category in glossary_categories()
    )
    return _page(
        html.Main(
            [
                _subpage_header("dictionary", "dictionary_desc"),
                html.Section(
                    [
                        html.Div(
                            [
                                html.Label(
                                    translated("search_term"),
                                    htmlFor="didactica-glossary-search",
                                ),
                                dcc.Input(
                                    id="didactica-glossary-search",
                                    type="search",
                                    debounce=True,
                                    placeholder=pair("search_placeholder")[0],
                                ),
                            ],
                            className="didactica-field",
                        ),
                        html.Div(
                            [
                                html.Label(
                                    translated("category"),
                                    htmlFor="didactica-glossary-category",
                                ),
                                dcc.Dropdown(
                                    id="didactica-glossary-category",
                                    options=category_options,
                                    value="all",
                                    clearable=False,
                                    className="didactica-dropdown",
                                ),
                            ],
                            className="didactica-field",
                        ),
                    ],
                    className="didactica-filters",
                ),
                html.P(
                    id="didactica-glossary-count",
                    className="didactica-result-count",
                    **dash_attrs({"aria-live": "polite"}),
                ),
                html.Section(
                    id="didactica-glossary-results",
                    className="didactica-glossary-grid",
                    **dash_attrs({"aria-live": "polite"}),
                ),
            ],
            className="didactica-shell",
        )
    )


def build_presentations_layout(lesson_id: str | None = None) -> Component:
    lesson = get_lesson(lesson_id or "")
    if lesson is None:
        return _page(
            html.Main(
                [
                    _subpage_header("presentations", "presentations_desc"),
                    html.Section(
                        [lesson_card(item, "es") for item in list_lessons()],
                        className="didactica-lesson-grid",
                    ),
                ],
                className="didactica-shell",
            )
        )
    activity = lesson.activity
    options = [
        {"label": text(option["label"]["es"], option["label"]["en"]), "value": option["id"]}
        for option in activity["options"]
    ]
    return _page(
        html.Main(
            [
                dcc.Store(id="didactica-lesson-id", data=lesson.id),
                dcc.Store(id="didactica-lesson-index", data=0),
                dcc.Link(
                    text("← Todas las presentaciones", "← All presentations"),
                    href="/didactica/presentaciones",
                    className="didactica-back-link",
                ),
                html.Header(
                    [
                        html.H1(lesson.title.es, **text_attrs(lesson.title.es, lesson.title.en)),
                        html.P(
                            lesson.description.es,
                            **text_attrs(lesson.description.es, lesson.description.en),
                        ),
                        html.Div(
                            [
                                html.Span(
                                    f"Nivel: {lesson.level.es}",
                                    **text_attrs(
                                        f"Nivel: {lesson.level.es}", f"Level: {lesson.level.en}"
                                    ),
                                ),
                                html.Span(
                                    f"Duración: {lesson.duration_minutes} minutos",
                                    **text_attrs(
                                        f"Duración: {lesson.duration_minutes} minutos",
                                        f"Duration: {lesson.duration_minutes} minutes",
                                    ),
                                ),
                            ],
                            className="didactica-meta",
                        ),
                        html.Section(
                            [
                                translated("objectives", tag=html.H2),
                                html.Ul(
                                    [
                                        html.Li(
                                            objective.es,
                                            **text_attrs(objective.es, objective.en),
                                        )
                                        for objective in lesson.objectives
                                    ]
                                ),
                            ],
                            className="didactica-objectives",
                        ),
                    ],
                    className="didactica-subpage-header",
                ),
                html.Progress(
                    id="didactica-lesson-progress",
                    value="1",
                    max=len(lesson.slides) + 1,
                    className="didactica-progress",
                    **dash_attrs({"aria-label": pair("progress")[0]}),
                ),
                html.Article(id="didactica-lesson-slide", className="didactica-slide"),
                html.Section(
                    [
                        translated("final_activity", tag=html.H2),
                        html.P(
                            activity["question"]["es"],
                            **text_attrs(activity["question"]["es"], activity["question"]["en"]),
                        ),
                        dcc.RadioItems(
                            id="didactica-lesson-answer",
                            options=options,
                            className="didactica-radio-group",
                        ),
                        html.Button(
                            translated("finish"),
                            id="didactica-lesson-finish",
                            type="button",
                            className="didactica-button",
                        ),
                    ],
                    id="didactica-lesson-activity",
                    className="didactica-activity is-hidden",
                ),
                html.P(
                    id="didactica-lesson-status",
                    className="didactica-feedback",
                    **dash_attrs({"aria-live": "polite"}),
                ),
                html.Div(
                    [
                        html.Button(
                            translated("previous"),
                            id="didactica-lesson-previous",
                            type="button",
                            className="didactica-button didactica-button-secondary",
                        ),
                        html.Button(
                            translated("next"),
                            id="didactica-lesson-next",
                            type="button",
                            className="didactica-button",
                        ),
                    ],
                    className="didactica-actions",
                ),
                html.Section(
                    [
                        translated("sources", tag=html.H2),
                        html.Ul(
                            [
                                html.Li(
                                    html.A(
                                        source["label"],
                                        href=source["url"],
                                        target="_blank",
                                        rel="noopener noreferrer",
                                    )
                                )
                                for source in lesson.sources
                            ]
                        ),
                        *_lesson_source_attributions(lesson.sources),
                    ],
                    className="didactica-sources",
                ),
            ],
            className="didactica-shell didactica-viewer",
        )
    )


def _lesson_source_attributions(sources: tuple[dict[str, str], ...]) -> list[Component]:
    attributions: list[Component] = []
    seen: set[str] = set()
    for source in sources:
        label = str(source.get("label") or "")
        normalized = label.casefold()
        key = "fra" if "fra" in normalized else "ilga" if "ilga" in normalized else ""
        if not key or key in seen:
            continue
        seen.add(key)
        attributions.append(
            build_source_attribution(
                key,
                year=2023 if key == "fra" and "survey iii" in normalized else None,
                source_url=str(source.get("url") or "").strip() or None,
                compact=True,
            )
        )
    return attributions


def build_games_layout(game_id: str | None = None) -> Component:
    if game_id not in {"guess_term", "true_false"}:
        return _page(
            html.Main(
                [
                    _subpage_header("games", "games_desc"),
                    html.Section(
                        [
                            resource_card(
                                "guess_term", "guess_desc", "/didactica/juegos?game=guess_term", "?"
                            ),
                            resource_card(
                                "true_false",
                                "true_false_desc",
                                "/didactica/juegos?game=true_false",
                                "✓",
                            ),
                        ],
                        className="didactica-resource-grid",
                    ),
                ],
                className="didactica-shell",
            )
        )
    state = new_game_state(game_id)
    question, options = _game_round(state, "es")
    title_key = "guess_term" if game_id == "guess_term" else "true_false"
    return _page(
        html.Main(
            [
                dcc.Store(id="didactica-game-state", data=state),
                dcc.Link(
                    text("← Todos los juegos", "← All games"),
                    href="/didactica/juegos",
                    className="didactica-back-link",
                ),
                html.Header(
                    [
                        translated(title_key, tag=html.H1),
                        translated(
                            "guess_desc" if game_id == "guess_term" else "true_false_desc",
                            tag=html.P,
                        ),
                    ],
                    className="didactica-subpage-header",
                ),
                html.Div(
                    [
                        html.Strong(id="didactica-game-round"),
                        html.Strong(id="didactica-game-score"),
                    ],
                    className="didactica-game-stats",
                ),
                html.Progress(
                    id="didactica-game-progress",
                    value="1",
                    max=len(state["order"]),
                    className="didactica-progress",
                ),
                html.Article(
                    [
                        html.P(
                            id="didactica-game-prompt",
                            children=question,
                            className="didactica-game-prompt",
                        ),
                        dcc.RadioItems(
                            id="didactica-game-answer",
                            options=options,
                            className="didactica-radio-group",
                        ),
                        html.P(
                            id="didactica-game-hint-text",
                            className="didactica-hint",
                            **dash_attrs({"aria-live": "polite"}),
                        ),
                        html.P(
                            id="didactica-game-feedback",
                            className="didactica-feedback",
                            **dash_attrs({"aria-live": "assertive"}),
                        ),
                        html.Div(
                            [
                                html.Button(
                                    translated("hint"),
                                    id="didactica-game-hint",
                                    type="button",
                                    className="didactica-button didactica-button-secondary",
                                ),
                                html.Button(
                                    translated("answer"),
                                    id="didactica-game-submit",
                                    type="button",
                                    className="didactica-button",
                                ),
                                html.Button(
                                    translated("next"),
                                    id="didactica-game-next",
                                    type="button",
                                    className="didactica-button",
                                    disabled=True,
                                ),
                            ],
                            className="didactica-actions",
                        ),
                    ],
                    className="didactica-game-card",
                ),
                html.Div(
                    [
                        build_source_attribution("fra", compact=True),
                        build_source_attribution("ilga", compact=True),
                    ],
                    className="didactica-game-attributions",
                ),
            ],
            className="didactica-shell didactica-viewer",
        )
    )


def build_docente_layout() -> Component:
    if not can_access_docente_material(current_user):
        return _page(access_denied())
    resources = list_teacher_resources()
    options = [
        {"label": text(item.title.es, item.title.en), "value": item.id} for item in resources
    ]
    first = resources[0]
    try:
        custom_games = list_owned_games(current_user)
    except PyMongoError, RuntimeError:
        custom_games = []
    game_options = [
        {"label": text(item["title_es"], item["title_en"]), "value": item["id"]}
        for item in custom_games
    ]
    return _page(
        html.Main(
            [
                _subpage_header("docente_resources", "docente_desc"),
                html.Section(
                    [
                        translated("docente_presentations", tag=html.H2),
                        translated("docente_presentations_desc", tag=html.P),
                        html.Div(
                            [lesson_card(item, "es") for item in list_lessons()],
                            className="didactica-lesson-grid",
                        ),
                    ],
                    className="didactica-docente-section",
                ),
                translated("docente_downloads", tag=html.H2),
                html.Div(
                    [
                        translated("select_resource", tag=html.Label),
                        dcc.Dropdown(
                            id="didactica-docente-select",
                            options=options,
                            value=first.id,
                            clearable=False,
                            className="didactica-dropdown",
                        ),
                    ],
                    className="didactica-field",
                ),
                html.Div(
                    id="didactica-docente-detail", children=teacher_resource_details(first, "es")
                ),
                html.Div(
                    [
                        html.Button(
                            translated("download_pdf"),
                            id="didactica-docente-download-button",
                            type="button",
                            className="didactica-button",
                        ),
                        dcc.Download(id="didactica-docente-download"),
                    ],
                    className="didactica-actions",
                ),
                html.P(
                    id="didactica-docente-status",
                    className="didactica-feedback",
                    **dash_attrs({"aria-live": "polite"}),
                ),
                html.Section(
                    [
                        translated("game_creator", tag=html.H2),
                        translated("game_creator_desc", tag=html.P),
                        html.Div(
                            [
                                translated("my_games", tag=html.Label),
                                dcc.Dropdown(
                                    id="didactica-custom-game-select",
                                    options=game_options,
                                    value=None,
                                    placeholder=pair("new_game")[0],
                                    clearable=True,
                                    className="didactica-dropdown",
                                ),
                            ],
                            className="didactica-field",
                        ),
                        html.Div(
                            [
                                translated("game_type", tag=html.Label),
                                dcc.RadioItems(
                                    id="didactica-custom-game-type",
                                    options=[
                                        {
                                            "label": text(*pair("multiple_choice")),
                                            "value": "multiple_choice",
                                        },
                                        {"label": text(*pair("guess_term")), "value": "guess_term"},
                                    ],
                                    value="multiple_choice",
                                    inline=True,
                                ),
                                *_bilingual_game_fields(),
                                html.Div(
                                    [
                                        html.Button(
                                            translated("save_game"),
                                            id="didactica-custom-game-save",
                                            type="button",
                                            className="didactica-button",
                                        ),
                                        html.Button(
                                            translated("delete_game"),
                                            id="didactica-custom-game-delete",
                                            type="button",
                                            className="didactica-button didactica-button-secondary",
                                        ),
                                    ],
                                    className="didactica-actions",
                                ),
                                html.P(
                                    id="didactica-custom-game-status",
                                    className="didactica-feedback",
                                    **dash_attrs({"aria-live": "polite"}),
                                ),
                            ],
                            className="didactica-game-editor",
                        ),
                    ],
                    className="didactica-docente-section",
                ),
            ],
            className="didactica-shell",
        )
    )


def build_access_denied_layout() -> Component:
    return _page(access_denied())


def build_progress_layout() -> Component:
    summary = progress_summary(current_user.get_id())
    last = summary.get("last_activity")
    last_es, last_en = _last_activity_labels(last)
    scores = summary.get("game_scores", {})
    return _page(
        html.Main(
            [
                _subpage_header("progress", "progress_desc"),
                html.Section(
                    [
                        _metric(str(summary["completed_count"]), "completed_lessons"),
                        _metric(str(summary["played_count"]), "games_played"),
                        _metric(f"{summary['percentage']}%", "total_progress"),
                    ],
                    className="didactica-progress-grid",
                ),
                html.Section(
                    [
                        translated("best_scores", tag=html.H2),
                        html.Ul(
                            [
                                html.Li(
                                    text(
                                        f"{tr(game, 'es')}: {score}/5",
                                        f"{tr(game, 'en')}: {score}/5",
                                    )
                                )
                                for game, score in scores.items()
                            ]
                        )
                        if scores
                        else translated("no_activity", tag=html.P),
                        translated("last_activity", tag=html.H2),
                        html.P(last_es, **text_attrs(last_es, last_en)),
                    ],
                    className="didactica-progress-detail",
                ),
            ],
            className="didactica-shell",
        )
    )


def register_didactica_callbacks(app: Dash) -> None:
    @app.callback(
        Output("didactica-glossary-search", "placeholder"),
        Input("app-language-store", "data"),
    )
    def translate_glossary_placeholder(language: str | None):
        return tr("search_placeholder", _language(language))

    @app.callback(
        Output("didactica-glossary-results", "children"),
        Output("didactica-glossary-count", "children"),
        Input("didactica-glossary-search", "value"),
        Input("didactica-glossary-category", "value"),
        Input("app-language-store", "data"),
    )
    def filter_glossary(query: str | None, category: str | None, language: str | None):
        language = _language(language)
        results = search_glossary(query, category, language)
        return [
            glossary_card(item, language) for item in results
        ], f"{len(results)} {tr('results', language)}"

    @app.callback(
        Output("didactica-lesson-slide", "children"),
        Output("didactica-lesson-index", "data"),
        Output("didactica-lesson-previous", "disabled"),
        Output("didactica-lesson-next", "disabled"),
        Output("didactica-lesson-progress", "value"),
        Output("didactica-lesson-activity", "className"),
        Output("didactica-lesson-status", "children"),
        Output("didactica-lesson-status", "className"),
        Input("didactica-lesson-previous", "n_clicks"),
        Input("didactica-lesson-next", "n_clicks"),
        Input("didactica-lesson-finish", "n_clicks"),
        Input("app-language-store", "data"),
        State("didactica-lesson-answer", "value"),
        State("didactica-lesson-id", "data"),
        State("didactica-lesson-index", "data"),
    )
    def navigate_lesson(_previous, _next, _finish, language, answer, lesson_id, index):
        language = _language(language)
        lesson = get_lesson(str(lesson_id or ""))
        if lesson is None:
            return (
                tr("not_found", language),
                0,
                True,
                True,
                "0",
                "is-hidden",
                "",
                "didactica-feedback",
            )
        index = max(0, min(int(index or 0), len(lesson.slides)))
        if ctx.triggered_id == "didactica-lesson-previous":
            index = max(0, index - 1)
        elif ctx.triggered_id == "didactica-lesson-next":
            index = min(len(lesson.slides), index + 1)
        status, status_class = "", "didactica-feedback"
        if ctx.triggered_id == "didactica-lesson-finish":
            if not answer:
                status = tr("choose_answer", language)
                status_class += " is-error"
            else:
                correct = answer == lesson.activity["correct"]
                explanation = lesson.activity["explanation"][language]
                status = f"{tr('correct' if correct else 'incorrect', language)}. {explanation} "
                if current_user.is_authenticated:
                    complete_lesson(current_user.get_id(), lesson.id)
                    status += tr("lesson_complete", language)
                else:
                    status += tr("lesson_complete_anon", language)
                status_class += " is-success" if correct else " is-error"
        activity_visible = index == len(lesson.slides)
        content = (
            ""
            if activity_visible
            else _slide(lesson.slides[index], language, index + 1, len(lesson.slides))
        )
        return (
            content,
            index,
            index == 0,
            activity_visible,
            str(index + 1),
            ("didactica-activity" if activity_visible else "didactica-activity is-hidden"),
            status,
            status_class,
        )

    @app.callback(
        Output("didactica-game-prompt", "children"),
        Output("didactica-game-answer", "options"),
        Output("didactica-game-answer", "value"),
        Output("didactica-game-feedback", "children"),
        Output("didactica-game-feedback", "className"),
        Output("didactica-game-hint-text", "children"),
        Output("didactica-game-state", "data"),
        Output("didactica-game-round", "children"),
        Output("didactica-game-score", "children"),
        Output("didactica-game-progress", "value"),
        Output("didactica-game-submit", "disabled"),
        Output("didactica-game-next", "disabled"),
        Input("didactica-game-submit", "n_clicks"),
        Input("didactica-game-next", "n_clicks"),
        Input("didactica-game-hint", "n_clicks"),
        Input("app-language-store", "data"),
        State("didactica-game-answer", "value"),
        State("didactica-game-state", "data"),
    )
    def play_game(_submit, _next, _hint, language, selected, state):
        language = _language(language)
        if not user_has_permission(current_user, Permission.PLAY_EDU_GAMES):
            return (no_update,) * 12
        state = dict(state or {})
        order = state.get("order", [])
        index = min(int(state.get("index", 0)), max(0, len(order) - 1))
        feedback, feedback_class, hint = "", "didactica-feedback", ""
        if ctx.triggered_id == "didactica-game-next" and state.get("answered"):
            if index < len(order) - 1:
                index += 1
                state.update(index=index, answered=False, selected=None)
                selected = None
        elif ctx.triggered_id == "didactica-game-submit":
            if selected is None:
                feedback, feedback_class = (
                    tr("choose_answer", language),
                    "didactica-feedback is-error",
                )
            elif not state.get("answered"):
                correct, explanation = _check_game_answer(
                    state["game_id"], order[index], selected, language
                )
                state["answered"] = True
                state["selected"] = selected
                if correct:
                    state["score"] = int(state.get("score", 0)) + 1
                feedback = f"{tr('correct' if correct else 'incorrect', language)}. {explanation}"
                feedback_class = (
                    "didactica-feedback is-success" if correct else "didactica-feedback is-error"
                )
                if index == len(order) - 1 and current_user.is_authenticated:
                    save_game_score(current_user.get_id(), state["game_id"], state["score"])
                    feedback += f" {tr('game_finished', language)}."
        elif ctx.triggered_id == "didactica-game-hint":
            hint = _game_hint(state["game_id"], order[index], language)
        question, options = _game_round(state, language)
        answered = bool(state.get("answered"))
        return (
            question,
            options,
            state.get("selected") if answered else selected,
            feedback,
            feedback_class,
            hint,
            state,
            f"{tr('round', language)} {index + 1}/{len(order)}",
            f"{tr('score', language)}: {state.get('score', 0)}",
            str(index + 1),
            answered,
            not answered or index == len(order) - 1,
        )

    @app.callback(
        Output("didactica-docente-detail", "children"),
        Input("didactica-docente-select", "value"),
        Input("app-language-store", "data"),
    )
    def show_docente_resource(resource_id: str | None, language: str | None):
        if not can_access_docente_material(current_user):
            return access_denied()
        resource = get_teacher_resource(str(resource_id or ""))
        return (
            teacher_resource_details(resource, _language(language))
            if resource
            else tr("not_found", _language(language))
        )

    @app.callback(
        Output("didactica-docente-download", "data"),
        Output("didactica-docente-status", "children"),
        Input("didactica-docente-download-button", "n_clicks"),
        State("didactica-docente-select", "value"),
        State("app-language-store", "data"),
        prevent_initial_call=True,
    )
    def download_docente_resource(clicks, resource_id, language):
        language = _language(language)
        if not clicks:
            return no_update, no_update
        if not can_access_docente_material(current_user):
            return no_update, tr("download_denied", language)
        try:
            payload, filename = generate_teacher_resource_pdf(str(resource_id or ""), language)
        except ValueError:
            return no_update, tr("download_error", language)
        return dcc.send_bytes(payload, filename, type="application/pdf"), ""

    _register_custom_game_callbacks(app)


def _register_custom_game_callbacks(app: Dash) -> None:
    field_ids = (
        "title-es",
        "title-en",
        "prompt-es",
        "prompt-en",
        "answer-es",
        "answer-en",
        "distractors-es",
        "distractors-en",
        "explanation-es",
        "explanation-en",
    )

    @app.callback(
        Output("didactica-custom-game-type", "value"),
        *(Output(f"didactica-custom-game-{field_id}", "value") for field_id in field_ids),
        Input("didactica-custom-game-select", "value"),
    )
    def load_custom_game(game_id: str | None):
        empty = ("multiple_choice", *("" for _ in field_ids))
        if not game_id or not can_manage_own_edu_games(current_user):
            return empty
        try:
            game = get_owned_game(current_user, game_id)
        except PyMongoError, RuntimeError:
            return empty
        if not game:
            return empty
        values = []
        for field_id in field_ids:
            value = game.get(field_id.replace("-", "_"), "")
            values.append("\n".join(value) if isinstance(value, list) else value)
        return game["game_type"], *values

    @app.callback(
        Output("didactica-custom-game-select", "options"),
        Output("didactica-custom-game-select", "value"),
        Output("didactica-custom-game-status", "children"),
        Input("didactica-custom-game-save", "n_clicks"),
        Input("didactica-custom-game-delete", "n_clicks"),
        State("didactica-custom-game-select", "value"),
        State("didactica-custom-game-type", "value"),
        *(State(f"didactica-custom-game-{field_id}", "value") for field_id in field_ids),
        State("app-language-store", "data"),
        prevent_initial_call=True,
    )
    def mutate_custom_game(
        _save_clicks: int | None,
        _delete_clicks: int | None,
        game_id: str | None,
        game_type: str | None,
        *state_values: Any,
    ):
        language = _language(state_values[-1])
        field_values = state_values[:-1]
        if not can_manage_own_edu_games(current_user):
            return no_update, no_update, tr("download_denied", language)
        try:
            if ctx.triggered_id == "didactica-custom-game-delete":
                if game_id:
                    delete_owned_game(current_user, game_id)
                selected = None
                message = tr("game_deleted", language)
            else:
                values = {
                    "game_type": game_type,
                    **{
                        field_id.replace("-", "_"): value
                        for field_id, value in zip(field_ids, field_values, strict=True)
                    },
                }
                saved = save_owned_game(current_user, game_id, values)
                selected = saved["id"]
                message = tr("game_saved", language)
            games = list_owned_games(current_user)
        except CustomGameAuthorizationError, CustomGameValidationError:
            return no_update, no_update, tr("game_validation_error", language)
        except PyMongoError, RuntimeError:
            return no_update, no_update, tr("game_storage_error", language)
        options = [
            {
                "label": text(item["title_es"], item["title_en"]),
                "value": item["id"],
            }
            for item in games
        ]
        return options, selected, message


def _bilingual_game_fields() -> list[Component]:
    definitions = (
        ("title_es", "title-es", False),
        ("title_en", "title-en", False),
        ("prompt_es", "prompt-es", True),
        ("prompt_en", "prompt-en", True),
        ("answer_es", "answer-es", False),
        ("answer_en", "answer-en", False),
        ("distractors_es", "distractors-es", True),
        ("distractors_en", "distractors-en", True),
        ("explanation_es", "explanation-es", True),
        ("explanation_en", "explanation-en", True),
    )
    components: list[Component] = []
    for key, suffix, multiline in definitions:
        component_id = f"didactica-custom-game-{suffix}"
        control = (
            dcc.Textarea(id=component_id, maxLength=800, className="didactica-textarea")
            if multiline
            else dcc.Input(
                id=component_id,
                type="text",
                maxLength=160,
                className="didactica-input",
            )
        )
        children: list[Component] = [
            html.Label(translated(key), htmlFor=component_id),
            control,
        ]
        if key.startswith("distractors"):
            children.append(translated("one_option_per_line", tag=html.Small))
        components.append(html.Div(children, className="didactica-field"))
    return components


def _page(content: Component) -> Component:
    return html.Div([build_navbar(active="didactica"), content])


def _subpage_header(title_key: str, description_key: str) -> Component:
    return html.Header(
        [
            dcc.Link(
                text("← Didáctica", "← Learning"),
                href="/didactica",
                className="didactica-back-link",
            ),
            translated(title_key, tag=html.H1),
            translated(description_key, tag=html.P),
        ],
        className="didactica-subpage-header",
    )


def _metric(value: str, label_key: str) -> Component:
    return html.Article(
        [html.Strong(value), translated(label_key)], className="didactica-progress-card"
    )


def _last_activity_labels(last: object) -> tuple[str, str]:
    if not isinstance(last, dict):
        return pair("no_activity")
    identifier = str(last.get("id") or "")
    if last.get("kind") == "lesson":
        lesson = get_lesson(identifier)
        if lesson:
            return lesson.title.es, lesson.title.en
    if last.get("kind") == "game" and identifier in {"guess_term", "true_false"}:
        return pair(identifier)
    return pair("no_activity")


def _language(value: str | None) -> str:
    return "en" if value == "en" else "es"


def _slide(slide: dict[str, Any], language: str, number: int, total: int) -> list[Component]:
    return [
        html.P(f"{number}/{total}", className="didactica-slide-number"),
        html.H2(slide["title"][language]),
        html.P(slide["body"][language]),
    ]


def _game_round(state: dict[str, Any], language: str) -> tuple[str, list[dict[str, str]]]:
    identifier = state["order"][int(state.get("index", 0))]
    if state["game_id"] == "guess_term":
        term = get_glossary_term(identifier)
        if term is None:
            raise ValueError("unknown_glossary_term")
        return term.short_definition.get(language), guess_options(identifier, language)
    question = true_false_question(identifier)
    if question is None:
        raise ValueError("unknown_true_false_question")
    return question["statement"][language], [
        {"label": tr("true", language), "value": "true"},
        {"label": tr("false", language), "value": "false"},
    ]


def _check_game_answer(
    game_id: str, identifier: str, selected: str, language: str
) -> tuple[bool, str]:
    if game_id == "guess_term":
        term = get_glossary_term(identifier)
        if term is None:
            raise ValueError("unknown_glossary_term")
        return selected == identifier, term.definition.get(language)
    question = true_false_question(identifier)
    if question is None:
        raise ValueError("unknown_true_false_question")
    return (
        selected == str(question["answer"]).lower(),
        f"{question['explanation'][language]} {tr('source', language)}: {question['source']}.",
    )


def _game_hint(game_id: str, identifier: str, language: str) -> str:
    if game_id == "guess_term":
        term = get_glossary_term(identifier)
        if term is None:
            raise ValueError("unknown_glossary_term")
        return f"{tr('hint_text', language)} «{term.term.get(language)[0].upper()}»."
    question = true_false_question(identifier)
    if question is None:
        raise ValueError("unknown_true_false_question")
    return f"{tr('source', language)}: {question['source']}"
