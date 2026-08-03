from __future__ import annotations

from collections.abc import Callable

from dash import dcc, html
from dash.development.base_component import Component

from app.dash.i18n import dash_attrs, text_attrs
from app.edu.glossary_service import get_glossary_term
from app.edu.models import GlossaryTerm, Lesson, TeacherResource
from app.edu.translations import category_name, pair, tr


def translated(
    key: str,
    *,
    tag: Callable[..., Component] = html.Span,
    class_name: str | None = None,
) -> Component:
    es, en = pair(key)
    return tag(es, className=class_name, **text_attrs(es, en))


def resource_card(title_key: str, description_key: str, href: str, icon: str) -> Component:
    return dcc.Link(
        [
            html.Span(
                icon,
                className="didactica-card-icon",
                **dash_attrs({"aria-hidden": "true"}),
            ),
            translated(title_key, tag=html.H2),
            translated(description_key, tag=html.P),
            html.Span(
                "→",
                className="didactica-card-arrow",
                **dash_attrs({"aria-hidden": "true"}),
            ),
        ],
        href=href,
        refresh=False,
        className="didactica-resource-card",
    )


def glossary_card(term: GlossaryTerm, language: str) -> Component:
    related = [get_glossary_term(item) for item in term.related_terms]
    return html.Article(
        [
            html.Div(
                [
                    html.Span(category_name(term.category, language), className="didactica-chip"),
                    html.H2(term.term.get(language)),
                ],
                className="didactica-card-heading",
            ),
            html.P(term.short_definition.get(language), className="didactica-definition-short"),
            html.Details(
                [
                    html.Summary(
                        "Ver definición ampliada" if language == "es" else "View full definition"
                    ),
                    html.P(term.definition.get(language)),
                    html.H3(tr("related", language)),
                    html.Ul([html.Li(item.term.get(language)) for item in related if item]),
                    html.P(
                        [
                            html.Strong(f"{tr('source', language)}: "),
                            html.A(
                                term.source,
                                href=term.source_url,
                                target="_blank",
                                rel="noopener noreferrer",
                            ),
                        ]
                    ),
                ]
            ),
        ],
        className="didactica-glossary-card",
    )


def lesson_card(lesson: Lesson, language: str) -> Component:
    level_es = f"Nivel: {lesson.level.es}"
    level_en = f"Level: {lesson.level.en}"
    duration_es = f"Duración: {lesson.duration_minutes} minutos"
    duration_en = f"Duration: {lesson.duration_minutes} minutes"
    return html.Article(
        [
            html.H2(lesson.title.get(language), **text_attrs(lesson.title.es, lesson.title.en)),
            html.P(
                lesson.description.get(language),
                **text_attrs(lesson.description.es, lesson.description.en),
            ),
            html.Div(
                [
                    html.Span(
                        level_en if language == "en" else level_es,
                        **text_attrs(level_es, level_en),
                    ),
                    html.Span(
                        duration_en if language == "en" else duration_es,
                        **text_attrs(duration_es, duration_en),
                    ),
                ],
                className="didactica-meta",
            ),
            dcc.Link(
                translated("start"),
                href=f"/didactica/presentaciones?lesson={lesson.id}",
                className="didactica-button",
            ),
        ],
        className="didactica-lesson-card",
    )


def teacher_resource_details(resource: TeacherResource, language: str) -> Component:
    return html.Article(
        [
            html.H2(resource.title.get(language)),
            html.P(resource.description.get(language)),
            html.Div(
                [
                    html.Span(f"{tr('level', language)}: {resource.level.get(language)}"),
                    html.Span(
                        f"{tr('duration', language)}: {resource.duration_minutes} {tr('minutes', language)}"
                    ),
                    html.Span(f"{tr('topic', language)}: {resource.topic.get(language)}"),
                ],
                className="didactica-meta",
            ),
            _section(
                "objectives",
                [html.Ul([html.Li(item.get(language)) for item in resource.objectives])],
                language,
            ),
            _section("instructions", [html.P(resource.instructions.get(language))], language),
            _section(
                "materials",
                [html.Ul([html.Li(item.get(language)) for item in resource.materials])],
                language,
            ),
            _section("teacher_guide", [html.P(resource.teacher_guide.get(language))], language),
            html.P(f"{tr('languages', language)}: {', '.join(resource.languages).upper()}"),
            html.P(f"{tr('formats', language)}: {', '.join(resource.formats).upper()}"),
        ],
        className="didactica-teacher-detail",
    )


def access_denied() -> Component:
    return html.Main(
        [
            html.Section(
                [
                    translated("restricted", tag=html.H1),
                    translated("restricted_desc", tag=html.P),
                    html.Div(
                        [
                            dcc.Link(
                                translated("back_learning"),
                                href="/didactica",
                                className="didactica-button",
                            ),
                            dcc.Link(
                                translated("back_home"),
                                href="/",
                                className="didactica-button didactica-button-secondary",
                            ),
                        ],
                        className="didactica-actions",
                    ),
                ],
                className="didactica-denied",
            )
        ],
        className="didactica-shell",
    )


def _section(key: str, children: list[Component], language: str) -> Component:
    return html.Section([html.H3(tr(key, language)), *children])
