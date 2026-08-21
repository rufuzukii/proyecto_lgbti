from __future__ import annotations

import hashlib
import random
import re
import secrets
import unicodedata
from collections.abc import Sequence
from copy import deepcopy
from typing import Any

from app.edu import glossary_service
from app.edu.models import GlossaryTerm

Direction = tuple[int, int]
Cell = tuple[int, int]

DIRECTIONS: dict[str, Direction] = {
    "right": (0, 1),
    "left": (0, -1),
    "down": (1, 0),
    "up": (-1, 0),
    "down_right": (1, 1),
    "up_left": (-1, -1),
    "down_left": (1, -1),
    "up_right": (-1, 1),
}
DEFAULT_WORD_COUNT = 8
MIN_WORD_COUNT = 6
MAX_WORD_COUNT = 10
MAX_BOARD_SIZE = 15
DEFAULT_MAX_TERM_LENGTH = 12
FILL_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def normalize_word_search_term(value: str) -> str:
    """Return the ASCII letter representation used by the board."""
    decomposed = unicodedata.normalize("NFKD", str(value or "").upper())
    unaccented = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^A-Z]", "", unaccented)


def select_word_search_terms(
    terms: Sequence[GlossaryTerm],
    *,
    count: int = DEFAULT_WORD_COUNT,
    max_length: int = MAX_BOARD_SIZE,
    seed: int | None = None,
) -> tuple[GlossaryTerm, ...]:
    """Select unique, board-safe glossary entries without altering their display text."""
    requested = max(1, min(int(count), MAX_WORD_COUNT))
    unique: dict[str, GlossaryTerm] = {}
    for term in terms:
        normalized = normalize_word_search_term(term.term)
        if normalized and len(normalized) <= max_length:
            unique.setdefault(normalized, term)
    candidates = list(unique.values())
    # Deterministic game layout; this randomness has no security purpose.
    random.Random(seed).shuffle(candidates)  # nosec B311
    return tuple(candidates[: min(requested, len(candidates))])


def generate_word_search(
    words: Sequence[str],
    rows: int,
    columns: int,
    seed: int | None = None,
    *,
    directions: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Generate a deterministic word-search matrix when ``seed`` is provided."""
    if rows < 1 or columns < 1:
        raise ValueError("invalid_word_search_dimensions")
    direction_names = tuple(directions or DIRECTIONS)
    if not direction_names or any(name not in DIRECTIONS for name in direction_names):
        raise ValueError("invalid_word_search_directions")

    unique_words: dict[str, None] = {}
    for value in words:
        word = normalize_word_search_term(value)
        if word and _can_fit(word, rows, columns, direction_names):
            unique_words.setdefault(word, None)

    # Deterministic game layout; this randomness has no security purpose.
    randomizer = random.Random(seed)  # nosec B311
    ordered_words = list(unique_words)
    randomizer.shuffle(ordered_words)
    ordered_words.sort(key=len, reverse=True)
    grid: list[list[str | None]] = [[None for _column in range(columns)] for _row in range(rows)]
    placements: list[dict[str, Any]] = []

    for word in ordered_words:
        candidates = _placement_candidates(word, grid, rows, columns, direction_names)
        if not candidates:
            continue
        randomizer.shuffle(candidates)
        candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        _overlap, direction_name, cells = candidates[0]
        for letter, (row, column) in zip(word, cells, strict=True):
            grid[row][column] = letter
        placements.append(
            {
                "word": word,
                "start": list(cells[0]),
                "end": list(cells[-1]),
                "direction": direction_name,
                "cells": [list(cell) for cell in cells],
            }
        )

    completed_grid = [[letter or randomizer.choice(FILL_LETTERS) for letter in row] for row in grid]
    return {
        "grid": completed_grid,
        "words_used": [placement["word"] for placement in placements],
        "placements": placements,
        "rows": rows,
        "columns": columns,
    }


def create_word_search_game(
    *,
    seed: int | None = None,
    word_count: int = DEFAULT_WORD_COUNT,
    term_ids: Sequence[str] | None = None,
    board_size: int | None = None,
) -> dict[str, Any]:
    """Build a serializable game using the same cached catalog as the dictionary."""
    effective_seed = seed if seed is not None else secrets.randbits(63)
    catalog = glossary_service.list_glossary_terms()
    allowed_ids = {str(identifier) for identifier in term_ids or ()}
    candidates = (
        tuple(term for term in catalog if term.id in allowed_ids)
        if term_ids is not None
        else catalog
    )
    selected = select_word_search_terms(
        candidates,
        count=word_count,
        max_length=board_size or DEFAULT_MAX_TERM_LENGTH,
        seed=effective_seed,
    )
    longest = max((len(normalize_word_search_term(term.term)) for term in selected), default=10)
    size = max(longest, min(int(board_size), MAX_BOARD_SIZE)) if board_size else _board_size(longest)
    generated = generate_word_search(
        [term.term for term in selected],
        size,
        size,
        seed=effective_seed,
    )
    if len(generated["words_used"]) < min(MIN_WORD_COUNT, len(selected)) and size < MAX_BOARD_SIZE:
        size = MAX_BOARD_SIZE
        generated = generate_word_search(
            [term.term for term in selected],
            size,
            size,
            seed=effective_seed,
        )

    terms_by_word = {normalize_word_search_term(term.term): term for term in selected}
    placements_by_word = {placement["word"]: placement for placement in generated["placements"]}
    game_words = []
    for normalized in generated["words_used"]:
        term = terms_by_word[normalized]
        placement = placements_by_word[normalized]
        game_words.append(
            {
                "id": term.id,
                "display": term.term,
                "normalized": normalized,
                "start": placement["start"],
                "end": placement["end"],
                "direction": placement["direction"],
                "cells": placement["cells"],
            }
        )
    digest = hashlib.sha256(f"{effective_seed}:{generated['grid']}".encode()).hexdigest()[:16]
    return {
        "game_id": digest,
        "seed": effective_seed,
        "rows": size,
        "columns": size,
        "grid": generated["grid"],
        "words": game_words,
        "found": [],
        "start": None,
    }


def selection_cells(start: Cell, end: Cell) -> list[Cell]:
    row_delta = end[0] - start[0]
    column_delta = end[1] - start[1]
    if row_delta and column_delta and abs(row_delta) != abs(column_delta):
        return []
    if not row_delta and not column_delta:
        return [start]
    row_step = (row_delta > 0) - (row_delta < 0)
    column_step = (column_delta > 0) - (column_delta < 0)
    length = max(abs(row_delta), abs(column_delta)) + 1
    return [
        (start[0] + index * row_step, start[1] + index * column_step) for index in range(length)
    ]


def detect_word_selection(words: Sequence[dict[str, Any]], start: Cell, end: Cell) -> str | None:
    selected = [list(cell) for cell in selection_cells(start, end)]
    if not selected:
        return None
    for word in words:
        cells = word.get("cells")
        if selected == cells or selected == list(reversed(cells or [])):
            return str(word.get("id") or "") or None
    return None


def apply_word_search_selection(
    state: dict[str, Any], cell_index: int
) -> tuple[dict[str, Any], str]:
    """Apply one endpoint selection and return the new state plus a UI status."""
    updated = deepcopy(state)
    rows = int(updated.get("rows") or 0)
    columns = int(updated.get("columns") or 0)
    if rows < 1 or columns < 1 or not 0 <= cell_index < rows * columns:
        return updated, "incorrect"
    cell = [cell_index // columns, cell_index % columns]
    start = updated.get("start")
    if not isinstance(start, list) or len(start) != 2:
        updated["start"] = cell
        return updated, "start"

    updated["start"] = None
    term_id = detect_word_selection(
        updated.get("words", []),
        (int(start[0]), int(start[1])),
        (cell[0], cell[1]),
    )
    if not term_id:
        return updated, "incorrect"
    found = [str(identifier) for identifier in updated.get("found", [])]
    if term_id in found:
        return updated, "duplicate"
    found.append(term_id)
    updated["found"] = found
    return updated, "complete" if is_word_search_complete(updated) else "found"


def is_word_search_complete(state: dict[str, Any]) -> bool:
    expected = {str(word.get("id")) for word in state.get("words", []) if word.get("id")}
    return bool(expected) and expected.issubset({str(item) for item in state.get("found", [])})


def _board_size(longest_word: int) -> int:
    if longest_word <= 10:
        return 10
    if longest_word <= 12:
        return 12
    return MAX_BOARD_SIZE


def _can_fit(word: str, rows: int, columns: int, direction_names: Sequence[str]) -> bool:
    for name in direction_names:
        row_step, column_step = DIRECTIONS[name]
        if (not row_step or len(word) <= rows) and (not column_step or len(word) <= columns):
            return True
    return False


def _placement_candidates(
    word: str,
    grid: list[list[str | None]],
    rows: int,
    columns: int,
    direction_names: Sequence[str],
) -> list[tuple[int, str, list[Cell]]]:
    candidates: list[tuple[int, str, list[Cell]]] = []
    for direction_name in direction_names:
        row_step, column_step = DIRECTIONS[direction_name]
        for row in range(rows):
            for column in range(columns):
                end_row = row + (len(word) - 1) * row_step
                end_column = column + (len(word) - 1) * column_step
                if not (0 <= end_row < rows and 0 <= end_column < columns):
                    continue
                cells = [
                    (row + index * row_step, column + index * column_step)
                    for index in range(len(word))
                ]
                existing = [grid[cell_row][cell_column] for cell_row, cell_column in cells]
                if any(
                    letter is not None and letter != word[index]
                    for index, letter in enumerate(existing)
                ):
                    continue
                overlap = sum(letter is not None for letter in existing)
                candidates.append((overlap, direction_name, cells))
    return candidates
