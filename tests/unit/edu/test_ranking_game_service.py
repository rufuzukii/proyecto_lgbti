from __future__ import annotations

import app.modules.didactics.ranking_game_service as service


def _document() -> dict:
    return {
        "year": 2026,
        "countries": [
            {"country_code": "MT", "country": "Malta", "ranking": 89},
            {"country_code": "BE", "country": "Belgium", "ranking": 85},
            {"country_code": "IS", "country": "Iceland", "ranking": 84},
            {"country_code": "ES", "country": "Spain", "ranking": 78},
            {"country_code": "DE", "country": "Germany", "ranking": 69},
            {"country_code": "FR", "country": "France", "ranking": 61},
            {"country_code": "IT", "country": "Italy", "ranking": 24},
            {"country_code": "PL", "country": "Poland", "ranking": 0},
            {"country_code": "NL", "country": "Netherlands", "ranking": None},
        ],
    }


def test_new_round_uses_one_cached_dataset_read_and_only_valid_unique_countries(
    monkeypatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        service,
        "get_ilga_document_by_year",
        lambda year: calls.append(year) or _document(),
    )

    state = service.new_ranking_game(seed=7)

    assert calls == [2026]
    assert len(state["items"]) == service.RANKING_GAME_COUNTRY_COUNT
    assert len({item["country_code"] for item in state["items"]}) == len(state["items"])
    assert all(item["country_code"] != "NL" for item in state["items"])


def test_zero_is_valid_null_is_excluded_and_distinct_scores_are_preferred() -> None:
    states = [service.new_ranking_game(document=_document(), seed=seed) for seed in range(20)]

    assert any(any(item["score"] == 0 for item in state["items"]) for state in states)
    assert all(
        len({item["score"] for item in state["items"]}) == len(state["items"]) for state in states
    )
    assert all(item["country_code"] != "NL" for state in states for item in state["items"])


def test_new_round_avoids_previous_countries_when_enough_alternatives_exist() -> None:
    first = service.new_ranking_game(document=_document(), seed=3)
    previous = [item["country_code"] for item in first["items"]]

    second = service.new_ranking_game(
        document=_document(),
        seed=3,
        previous_codes=previous,
    )

    assert {item["country_code"] for item in first["items"]}.isdisjoint(
        item["country_code"] for item in second["items"]
    )


def test_check_orders_descending_and_accepts_any_order_within_ties() -> None:
    state = {
        "items": [
            {"country_code": "BE", "country_name": "Belgium", "score": 80},
            {"country_code": "MT", "country_name": "Malta", "score": 80},
            {"country_code": "ES", "country_name": "Spain", "score": 50},
            {"country_code": "IT", "country_name": "Italy", "score": 20},
        ],
        "checked": False,
    }

    result = service.check_ranking_game(state)

    assert result["is_correct"] is True
    assert result["positions_correct"] == 4
    assert [item["score"] for item in result["correct_order"]] == [80, 80, 50, 20]


def test_move_buttons_reorder_before_check_and_lock_after_check() -> None:
    state = service.new_ranking_game(document=_document(), seed=1)
    original = [item["country_code"] for item in state["items"]]

    moved = service.move_ranking_country(state, 1, -1)
    locked = service.move_ranking_country(service.check_ranking_game(moved), 0, 1)

    assert [item["country_code"] for item in moved["items"]][:2] == original[1::-1]
    assert locked["items"] == service.check_ranking_game(moved)["items"]
