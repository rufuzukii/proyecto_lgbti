from __future__ import annotations

from typing import Any

from dash import html
from dash.development.base_component import Component

from app.modules.didactics.components import translated
from app.modules.didactics.translations import tr
from app.shared.data.percentage_display import format_percentage
from app.web.i18n import country_labels, dash_attrs


def ranking_game_rows(state: dict[str, Any], language: str) -> list[Component]:
    items = state.get("items") if isinstance(state, dict) else None
    if not isinstance(items, list) or not items:
        return [translated("rank_no_data", tag=html.P, class_name="ranking-game-empty")]
    checked = bool(state.get("checked"))
    rows: list[Component] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = _country_name(item, language)
        up_label = f"{tr('move_up', language)}: {name}"
        down_label = f"{tr('move_down', language)}: {name}"
        score = format_percentage(item.get("score")) if checked else None
        rows.append(
            html.Div(
                [
                    html.Span(f"{index + 1}.", className="ranking-game-position"),
                    html.Span(name, className="ranking-game-country"),
                    _score(score, language),
                    html.Div(
                        [
                            _move_button("up", index, "↑", up_label, checked or index == 0),
                            _move_button(
                                "down",
                                index,
                                "↓",
                                down_label,
                                checked or index == len(items) - 1,
                            ),
                        ],
                        className="ranking-game-controls",
                    ),
                ],
                className="ranking-game-row",
            )
        )
    return rows


def ranking_game_result(state: dict[str, Any], language: str) -> Component | str:
    if not state.get("checked"):
        return ""
    raw_items = state.get("items")
    items: list[Any] = raw_items if isinstance(raw_items, list) else []
    raw_correct = state.get("correct_order")
    correct: list[Any] = raw_correct if isinstance(raw_correct, list) else []
    positions = int(state.get("positions_correct") or 0)
    heading = (
        tr("rank_all_correct", language)
        if state.get("is_correct")
        else tr("rank_positions_correct", language).format(correct=positions, total=len(items))
    )
    return html.Section(
        [
            html.H2(heading),
            translated("correct_order", tag=html.H3),
            html.Ol(
                [
                    html.Li(
                        [
                            html.Span(_country_name(item, language)),
                            _score(format_percentage(item.get("score")), language),
                        ]
                    )
                    for item in correct
                    if isinstance(item, dict)
                ],
                className="ranking-game-correct-order",
            ),
            translated("rank_result_explanation", tag=html.P),
        ],
        className=(
            "ranking-game-result-panel is-success"
            if state.get("is_correct")
            else "ranking-game-result-panel"
        ),
    )


def _move_button(
    direction: str,
    index: int,
    symbol: str,
    label: str,
    disabled: bool,
) -> Component:
    return html.Button(
        symbol,
        id={"type": f"didactica-ranking-{direction}", "index": index},
        n_clicks=0,
        type="button",
        title=label,
        disabled=disabled,
        className="ranking-game-move",
        **dash_attrs({"aria-label": label}),
    )


def _score(score: str | None, language: str) -> Component:
    label = f"{tr('legal_score', language)}: {score}" if score else ""
    attributes = dash_attrs({"aria-label": label}) if label else {}
    return html.Strong(
        score or "",
        title=label or None,
        className="ranking-game-score",
        **attributes,
    )


def _country_name(item: dict[str, Any], language: str) -> str:
    fallback = str(item.get("country_name") or item.get("country_code") or "").strip()
    labels = country_labels(str(item.get("country_code") or ""), fallback)
    return labels[1] if language == "en" else labels[0]
