from __future__ import annotations

from app.analytics import repository
from app.dash.pages.statistics import _year_options


class _Collection:
    def distinct(self, field, query):
        assert field == "year"
        assert query == {"dataset": "ilga_rainbow_map"}
        return [2012, 2026, "2025", 2011]


def test_ilga_year_catalog_drives_selector_in_descending_order(monkeypatch) -> None:
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: _Collection())
    years = repository.get_ilga_years()
    monkeypatch.setattr("app.dash.pages.statistics.get_ilga_years", lambda: years)

    assert years == [2026, 2025, 2012, 2011]
    assert [option["value"] for option in _year_options("ilga")] == years
