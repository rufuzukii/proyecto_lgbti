from __future__ import annotations

from app.shared.data import repository


class _Collection:
    def distinct(self, field, query):
        assert field == "year"
        assert query == {"dataset": "ilga_rainbow_map"}
        return [2012, 2026, "2025", 2011]


def test_ilga_year_catalog_is_available_to_the_home_selector_in_descending_order(monkeypatch) -> None:
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: _Collection())
    years = repository.get_ilga_years.uncached()
    assert years == [2026, 2025, 2012, 2011]
