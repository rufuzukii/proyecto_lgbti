from __future__ import annotations

import pytest

from app.modules.statistics.ranking import paginate_ranking


def _rows(count: int) -> list[dict[str, object]]:
    return [
        {"iso": f"C{index:02d}", "country": f"Country {index:02d}", "value": float(index)}
        for index in range(1, count + 1)
    ]


@pytest.mark.parametrize(
    ("count", "expected_size", "has_next"),
    [(4, 4, False), (5, 5, False), (6, 5, True)],
)
def test_first_ranking_page_has_at_most_five_rows(
    count: int,
    expected_size: int,
    has_next: bool,
) -> None:
    # Arrange
    rows = _rows(count)

    # Act
    page = paginate_ranking(rows, 0)

    # Assert
    assert len(page.rows) == expected_size
    assert page.has_next is has_next
    assert page.has_previous is False


def test_six_countries_create_an_incomplete_second_page() -> None:
    # Arrange
    rows = _rows(6)

    # Act
    page = paginate_ranking(rows, 1)

    # Assert
    assert [row["value"] for row in page.rows] == [1.0]
    assert (page.start, page.end, page.total_items) == (6, 6, 6)
    assert page.has_previous is True
    assert page.has_next is False


def test_forty_nine_countries_are_accessible_in_ten_pages() -> None:
    # Arrange
    rows = _rows(49)

    # Act
    pages = [paginate_ranking(rows, index) for index in range(10)]

    # Assert
    assert all(len(page.rows) == 5 for page in pages[:-1])
    assert len(pages[-1].rows) == 4
    assert pages[-1].end == 49
    assert {row["iso"] for page in pages for row in page.rows} == {row["iso"] for row in rows}


def test_ranking_is_sorted_descending_before_it_is_paginated() -> None:
    # Arrange
    rows = [
        {"iso": "A", "country": "Alpha", "value": 3},
        {"iso": "B", "country": "Beta", "value": 9},
        {"iso": "C", "country": "Gamma", "value": 5},
    ]

    # Act
    page = paginate_ranking(rows, 0)

    # Assert
    assert [row["iso"] for row in page.rows] == ["B", "C", "A"]


def test_missing_values_are_last_and_are_not_converted_to_zero() -> None:
    # Arrange
    rows = [
        {"iso": "NA", "country": "No data", "value": None},
        {"iso": "ZERO", "country": "Real zero", "value": 0},
        {"iso": "EMPTY", "country": "Empty", "value": ""},
        {"iso": "NAN", "country": "NaN", "value": float("nan")},
        {"iso": "ONE", "country": "One", "value": 1},
    ]

    # Act
    page = paginate_ranking(rows, 0)

    # Assert
    assert [row["iso"] for row in page.rows[:2]] == ["ONE", "ZERO"]
    assert page.rows[1]["value"] == 0
    assert all(row["value"] != 0 for row in page.rows[2:])


def test_page_is_clamped_when_a_new_query_has_fewer_results() -> None:
    # Arrange
    previous_page_number = paginate_ranking(_rows(49), 9).page

    # Act
    page = paginate_ranking(_rows(6), previous_page_number)

    # Assert
    assert page.page == 1
    assert page.end == 6


def test_selected_country_filter_is_applied_before_pagination() -> None:
    # Arrange
    rows = _rows(10)

    # Act
    page = paginate_ranking(rows, 0, selected_countries=["C02", "C08"])

    # Assert
    assert [row["iso"] for row in page.rows] == ["C08", "C02"]
    assert page.total_items == 2
