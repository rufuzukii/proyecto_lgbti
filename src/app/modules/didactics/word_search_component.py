from __future__ import annotations

from typing import Any, cast

from dash import html
from dash.development.base_component import Component

from app.modules.didactics.translations import tr
from app.web.i18n import dash_attrs


def word_search_board(state: dict[str, Any], language: str) -> Component:
    rows = int(state.get("rows") or 0)
    columns = int(state.get("columns") or 0)
    found_ids = {str(identifier) for identifier in state.get("found", [])}
    found_cells = {
        tuple(cell)
        for word in state.get("words", [])
        if str(word.get("id")) in found_ids
        for cell in word.get("cells", [])
    }
    start = tuple(state["start"]) if isinstance(state.get("start"), list) else None
    cells: list[Component] = []
    for row, letters in enumerate(state.get("grid", [])):
        for column, letter in enumerate(letters):
            index = row * columns + column
            cell = (row, column)
            class_names = ["word-search-cell"]
            if cell in found_cells:
                class_names.append("is-found")
            if cell == start:
                class_names.append("is-selected")
            label = (
                f"Fila {row + 1}, columna {column + 1}: {letter}"
                if language == "es"
                else f"Row {row + 1}, column {column + 1}: {letter}"
            )
            cells.append(
                html.Button(
                    str(letter),
                    id={"type": "didactica-word-search-cell", "index": index},
                    n_clicks=0,
                    type="button",
                    className=" ".join(class_names),
                    role="gridcell",
                    **dash_attrs(
                        {
                            "aria-label": label,
                            "aria-pressed": "true"
                            if cell == start or cell in found_cells
                            else "false",
                        }
                    ),
                )
            )
    return html.Div(
        cells,
        className="word-search-grid",
        role="grid",
        style={"--word-search-columns": columns},
        **dash_attrs(
            {
                "aria-label": tr("word_search_board", language),
                "aria-rowcount": rows,
                "aria-colcount": columns,
            }
        ),
    )


def word_search_words(state: dict[str, Any], language: str) -> Component:
    found_ids = {str(identifier) for identifier in state.get("found", [])}
    return html.Ul(
        [
            html.Li(
                [
                    html.Span(
                        "✓" if str(word.get("id")) in found_ids else "○",
                        className="word-search-word__status",
                        **dash_attrs({"aria-hidden": "true"}),
                    ),
                    html.Span(str(word.get("display") or "")),
                    html.Span(
                        tr("word_found", language),
                        className="sr-only",
                    )
                    if str(word.get("id")) in found_ids
                    else None,
                ],
                className=(
                    "word-search-word is-found"
                    if str(word.get("id")) in found_ids
                    else "word-search-word"
                ),
                **dash_attrs(
                    {
                        "data-term-id": str(word.get("id") or ""),
                    }
                ),
            )
            for word in state.get("words", [])
        ],
        className="word-search-word-list",
    )


def word_search_progress(state: dict[str, Any], language: str) -> list[Component]:
    found = len({str(identifier) for identifier in state.get("found", [])})
    total = len(state.get("words", []))
    return [
        cast(Component, html.Strong(f"{tr('words_found', language)}: {found} / {total}")),
        cast(
            Component,
            html.Progress(
                value=str(found),
                max=str(max(total, 1)),
                className="word-search-progress-bar",
                **dash_attrs(
                    {"aria-label": f"{tr('words_found', language)}: {found} / {total}"}
                ),
            ),
        ),
    ]
