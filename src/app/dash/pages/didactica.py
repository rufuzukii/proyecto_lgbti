from __future__ import annotations

from typing import Any

from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.development.base_component import Component
from flask_login import current_user
from pymongo.errors import PyMongoError

from app.analytics.home_legal_service import HOME_LEGAL_YEAR
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
from app.dash.components.ranking_game import ranking_game_result, ranking_game_rows
from app.dash.components.source_attribution import build_source_attribution
from app.dash.components.word_search import (
    word_search_board,
    word_search_progress,
    word_search_words,
)
from app.dash.i18n import dash_attrs, text, text_attrs
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import route_path
from app.edu.custom_game_service import (
    CustomGameAuthorizationError,
    CustomGameValidationError,
    delete_owned_game,
    get_owned_game,
    list_owned_games,
    save_owned_game,
)
from app.edu.game_service import guess_options, new_game_state
from app.edu.glossary_service import (
    FUNDEU_SOURCE_URL,
    UNAM_SOURCE_URL,
    get_glossary_term,
    glossary_categories,
    search_glossary,
)
from app.edu.lesson_service import get_lesson, list_lessons
from app.edu.progress_service import complete_lesson, progress_summary, save_game_score
from app.edu.ranking_game_service import (
    check_ranking_game,
    move_ranking_country,
    new_ranking_game,
)
from app.edu.teacher_service import (
    generate_teacher_resource_pdf,
    get_teacher_resource,
    list_teacher_resources,
)
from app.edu.translations import CATEGORIES, pair, tr
from app.edu.word_search_service import (
    apply_word_search_selection,
    create_word_search_game,
    is_word_search_complete,
)


def build_didactica_layout() -> Component:
    rows = [
        _didactica_mode_row(
            "dictionary",
            "dictionary_desc",
            resource_card(
                "dictionary",
                "dictionary_card_desc",
                "dictionary",
                "Aa",
                class_name="is-compact",
            ),
        ),
        _didactica_mode_row(
            "presentations",
            "presentations_desc",
            resource_card(
                "presentations",
                "presentations_card_desc",
                "presentations",
                "▤",
                class_name="is-compact",
            ),
        ),
    ]
    if user_has_permission(current_user, Permission.PLAY_EDU_GAMES):
        rows.append(
            _didactica_mode_row(
                "games",
                "games_desc",
                html.Div(
                    [
                        resource_card(
                            "guess_term",
                            "guess_desc",
                            "games",
                            "?",
                            query="?game=guess_term",
                            class_name="is-game-card",
                        ),
                        resource_card(
                            "word_search",
                            "word_search_card_desc",
                            "word_search",
                            "ABC",
                            class_name="is-game-card",
                        ),
                        resource_card(
                            "rank_countries",
                            "rank_countries_card_desc",
                            "games",
                            "↕",
                            query="?game=rank_countries",
                            class_name="is-game-card",
                        ),
                    ],
                    className="didactica-game-access-grid",
                ),
                games=True,
            )
        )
    if can_access_docente_material(current_user):
        rows.append(
            _didactica_mode_row(
                "docente",
                "docente_desc",
                resource_card(
                    "docente",
                    "docente_card_desc",
                    "educators",
                    "▣",
                    class_name="is-compact",
                ),
            )
        )
    if current_user.is_authenticated:
        rows.append(
            _didactica_mode_row(
                "progress",
                "progress_desc",
                resource_card(
                    "progress",
                    "progress_card_desc",
                    "progress",
                    "✓",
                    class_name="is-compact",
                ),
            )
        )
    return _page(
        html.Main(
            [
                html.Header(
                    [translated("learning", tag=html.H1), translated("intro", tag=html.P)],
                    className="didactica-hero",
                ),
                html.Section(
                    rows,
                    className="didactica-mode-list",
                    **dash_attrs({"aria-label": pair("learning")[0]}),
                ),
            ],
            className="didactica-shell app-page-container",
        )
    )


def _didactica_mode_row(
    title_key: str,
    description_key: str,
    access: Component,
    *,
    games: bool = False,
) -> Component:
    modifier = " didactica-mode-row--games" if games else ""
    return html.Article(
        [
            html.Div(
                [translated(title_key, tag=html.H2), translated(description_key, tag=html.P)],
                className="didactica-mode-copy",
            ),
            html.Div(access, className="didactica-mode-access"),
        ],
        className=f"didactica-mode-row{modifier}",
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
                html.Aside(
                    [
                        html.P(
                            [
                                text(
                                    "Definiciones recopiladas y adaptadas a partir de los glosarios de ",
                                    "Definitions compiled and adapted from the glossaries of ",
                                ),
                                html.A(
                                    "UNAM ↗",
                                    href=UNAM_SOURCE_URL,
                                    target="_blank",
                                    rel="noopener noreferrer",
                                ),
                                " · ",
                                html.A(
                                    "FundéuRAE ↗",
                                    href=FUNDEU_SOURCE_URL,
                                    target="_blank",
                                    rel="noopener noreferrer",
                                ),
                            ]
                        ),
                        translated("glossary_original_language", tag=html.P),
                    ],
                    className="didactica-glossary-note",
                ),
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
            className="didactica-shell app-page-container",
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
                className="didactica-shell app-page-container",
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
                    href=route_path("presentations"),
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
            className="didactica-shell didactica-viewer app-page-container",
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
    if game_id == "rank_countries":
        return _build_ranking_game_layout()
    if game_id != "guess_term":
        return html.Div(
            dcc.Location(
                id="didactica-games-catalog-redirect",
                href=route_path("didactica"),
                refresh=False,
            )
        )
    state = new_game_state(game_id)
    question, options = _game_round(state, "es")
    return _page(
        html.Main(
            [
                dcc.Store(id="didactica-game-state", data=state),
                dcc.Link(
                    text("← Didáctica", "← Learning"),
                    href=route_path("didactica"),
                    className="didactica-back-link",
                ),
                html.Header(
                    [
                        translated("guess_term", tag=html.H1),
                        translated("guess_desc", tag=html.P),
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
            className="didactica-shell didactica-viewer app-page-container",
        )
    )


def _build_ranking_game_layout() -> Component:
    state = new_ranking_game()
    return _page(
        html.Main(
            [
                dcc.Store(
                    id="didactica-ranking-state",
                    data=state,
                    storage_type="memory",
                ),
                dcc.Link(
                    text("← Didáctica", "← Learning"),
                    href=route_path("didactica"),
                    className="didactica-back-link",
                ),
                html.Header(
                    [
                        translated("rank_countries", tag=html.H1),
                        translated("rank_countries_desc", tag=html.P),
                    ],
                    className="didactica-subpage-header",
                ),
                html.P(
                    translated("rank_countries_instructions"),
                    className="ranking-game-instructions",
                ),
                html.Article(
                    [
                        html.Div(
                            ranking_game_rows(state, "es"),
                            id="didactica-ranking-list",
                            className="ranking-game-list",
                            **dash_attrs({"aria-live": "polite"}),
                        ),
                        html.Div(
                            [
                                html.Button(
                                    translated("check"),
                                    id="didactica-ranking-check",
                                    n_clicks=0,
                                    type="button",
                                    disabled=len(state.get("items", [])) < 2,
                                    className="didactica-button",
                                ),
                                html.Button(
                                    translated("new_round"),
                                    id="didactica-ranking-new",
                                    n_clicks=0,
                                    type="button",
                                    className="didactica-button didactica-button-secondary",
                                ),
                            ],
                            className="didactica-actions ranking-game-actions",
                        ),
                        html.Div(
                            id="didactica-ranking-result",
                            className="ranking-game-result",
                            **dash_attrs({"aria-live": "assertive"}),
                        ),
                    ],
                    className="didactica-game-card ranking-game-card",
                ),
                translated(
                    "rank_countries_methodology", tag=html.P, class_name="ranking-game-note"
                ),
                build_source_attribution("ilga", year=HOME_LEGAL_YEAR, compact=True),
            ],
            className="didactica-shell didactica-viewer app-page-container",
        )
    )


def build_word_search_layout(*, seed: int | None = None) -> Component:
    state = create_word_search_game(seed=seed)
    return _page(
        html.Main(
            [
                dcc.Store(id="didactica-word-search-state", data=state, storage_type="memory"),
                dcc.Link(
                    text("← Didáctica", "← Learning"),
                    href=route_path("didactica"),
                    className="didactica-back-link",
                ),
                html.Header(
                    [
                        translated("word_search", tag=html.H1),
                        translated("word_search_desc", tag=html.P),
                    ],
                    className="didactica-subpage-header",
                ),
                html.P(
                    translated("word_search_instructions"),
                    className="word-search-instructions",
                    id="didactica-word-search-instructions",
                ),
                html.Div(
                    [
                        html.Section(
                            [
                                html.Div(
                                    word_search_progress(state, "es"),
                                    id="didactica-word-search-progress",
                                    className="word-search-progress",
                                    **dash_attrs({"aria-live": "polite"}),
                                ),
                                html.Div(
                                    word_search_board(state, "es"),
                                    id="didactica-word-search-grid",
                                ),
                            ],
                            className="word-search-board-panel",
                            **dash_attrs({"aria-labelledby": "didactica-word-search-instructions"}),
                        ),
                        html.Aside(
                            [
                                translated("words", tag=html.H2),
                                html.Div(
                                    word_search_words(state, "es"),
                                    id="didactica-word-search-words",
                                ),
                                html.P(
                                    id="didactica-word-search-feedback",
                                    className="didactica-feedback word-search-feedback",
                                    **dash_attrs({"aria-live": "assertive"}),
                                ),
                                html.Button(
                                    translated("new_word_search"),
                                    id="didactica-word-search-new",
                                    n_clicks=0,
                                    type="button",
                                    className="didactica-button word-search-new-game",
                                ),
                            ],
                            className="word-search-sidebar",
                        ),
                    ],
                    className="word-search-layout",
                ),
            ],
            className="didactica-shell word-search-page app-page-container",
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
    can_manage_games = can_manage_own_edu_games(current_user)
    if can_manage_games:
        try:
            custom_games = list_owned_games(current_user)
        except PyMongoError, RuntimeError:
            custom_games = []
    else:
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
                        html.Label(
                            translated("select_resource"),
                            htmlFor="didactica-docente-select",
                        ),
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
                                html.Label(
                                    translated("my_games"),
                                    htmlFor="didactica-custom-game-select",
                                ),
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
                                html.Div(
                                    [
                                        html.Span(
                                            translated("game_type"),
                                            id="didactica-custom-game-type-label",
                                            className="didactica-field-label",
                                        ),
                                        dcc.RadioItems(
                                            id="didactica-custom-game-type",
                                            options=[
                                                {
                                                    "label": text(*pair("multiple_choice")),
                                                    "value": "multiple_choice",
                                                },
                                                {
                                                    "label": text(*pair("guess_term")),
                                                    "value": "guess_term",
                                                },
                                            ],
                                            value="multiple_choice",
                                            inline=True,
                                        ),
                                    ],
                                    className="didactica-field",
                                    role="group",
                                    **dash_attrs(
                                        {"aria-labelledby": ("didactica-custom-game-type-label")}
                                    ),
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
                )
                if can_manage_games
                else html.Section(
                    [
                        translated("game_creator", tag=html.H2),
                        html.P(
                            text(
                                "La consulta y descarga son públicas. Inicia sesión con un perfil Docente aprobado para crear y guardar juegos propios.",
                                "Viewing and downloading are public. Sign in with an approved Educator profile to create and save your own games.",
                            )
                        ),
                    ],
                    className="didactica-docente-section",
                ),
            ],
            className="didactica-shell app-page-container",
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
            className="didactica-shell app-page-container",
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
        Output("didactica-word-search-grid", "children"),
        Output("didactica-word-search-words", "children"),
        Output("didactica-word-search-progress", "children"),
        Output("didactica-word-search-feedback", "children"),
        Output("didactica-word-search-feedback", "className"),
        Output("didactica-word-search-state", "data"),
        Input("didactica-word-search-new", "n_clicks"),
        Input({"type": "didactica-word-search-cell", "index": ALL}, "n_clicks"),
        Input("app-language-store", "data"),
        State("didactica-word-search-state", "data"),
    )
    def play_word_search(_new_game, _cell_clicks, language, state):
        language = _language(language)
        triggered = ctx.triggered_id
        status = ""
        if triggered == "didactica-word-search-new" or not isinstance(state, dict):
            state = create_word_search_game()
        elif (
            isinstance(triggered, dict)
            and triggered.get("type") == "didactica-word-search-cell"
            and any(_cell_clicks or [])
        ):
            state, status = apply_word_search_selection(state, int(triggered["index"]))

        feedback = {
            "start": tr("select_word_end", language),
            "found": tr("word_search_found", language),
            "duplicate": tr("word_search_duplicate", language),
            "incorrect": tr("word_search_incorrect", language),
            "complete": tr("word_search_complete", language),
        }.get(status, "")
        if not feedback and is_word_search_complete(state):
            feedback = tr("word_search_complete", language)
            status = "complete"
        feedback_class = "didactica-feedback word-search-feedback"
        if status in {"found", "complete"}:
            feedback_class += " is-success"
        elif status in {"incorrect", "duplicate"}:
            feedback_class += " is-error"
        return (
            word_search_board(state, language),
            word_search_words(state, language),
            word_search_progress(state, language),
            feedback,
            feedback_class,
            state,
        )

    @app.callback(
        Output("didactica-ranking-list", "children"),
        Output("didactica-ranking-result", "children"),
        Output("didactica-ranking-state", "data"),
        Output("didactica-ranking-check", "disabled"),
        Input("didactica-ranking-new", "n_clicks"),
        Input("didactica-ranking-check", "n_clicks"),
        Input({"type": "didactica-ranking-up", "index": ALL}, "n_clicks"),
        Input({"type": "didactica-ranking-down", "index": ALL}, "n_clicks"),
        Input("app-language-store", "data"),
        State("didactica-ranking-state", "data"),
    )
    def play_ranking_game(_new, _check, _up, _down, language, state):
        language = _language(language)
        current = dict(state or {})
        triggered = ctx.triggered_id
        if triggered == "didactica-ranking-new" or not current:
            previous_codes = [
                str(item.get("country_code") or "")
                for item in current.get("items", [])
                if isinstance(item, dict)
            ]
            current = new_ranking_game(previous_codes=previous_codes)
        elif triggered == "didactica-ranking-check" and not current.get("checked"):
            current = check_ranking_game(current)
            if current_user.is_authenticated:
                save_game_score(
                    current_user.get_id(),
                    "rank_countries",
                    int(current.get("positions_correct") or 0),
                )
        elif isinstance(triggered, dict):
            control_type = triggered.get("type")
            if control_type in {"didactica-ranking-up", "didactica-ranking-down"}:
                direction = -1 if control_type == "didactica-ranking-up" else 1
                current = move_ranking_country(
                    current,
                    int(triggered.get("index", 0)),
                    direction,
                )
        raw_items = current.get("items")
        items: list[Any] = raw_items if isinstance(raw_items, list) else []
        return (
            ranking_game_rows(current, language),
            ranking_game_result(current, language),
            current,
            bool(current.get("checked")) or len(items) < 2,
        )

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
                href=route_path("didactica"),
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
    if last.get("kind") == "game" and identifier in {"guess_term", "rank_countries"}:
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
    if state.get("game_id") != "guess_term":
        raise ValueError("unknown_game")
    term = get_glossary_term(identifier)
    if term is None:
        raise ValueError("unknown_glossary_term")
    return term.definition, guess_options(identifier, language)


def _check_game_answer(
    game_id: str, identifier: str, selected: str, language: str
) -> tuple[bool, str]:
    if game_id != "guess_term":
        raise ValueError("unknown_game")
    term = get_glossary_term(identifier)
    if term is None:
        raise ValueError("unknown_glossary_term")
    return selected == identifier, term.definition


def _game_hint(game_id: str, identifier: str, language: str) -> str:
    if game_id != "guess_term":
        raise ValueError("unknown_game")
    term = get_glossary_term(identifier)
    if term is None:
        raise ValueError("unknown_glossary_term")
    return f"{tr('hint_text', language)} «{term.term[0].upper()}»."
