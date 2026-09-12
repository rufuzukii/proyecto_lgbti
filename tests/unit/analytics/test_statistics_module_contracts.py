from __future__ import annotations

import math

import plotly.graph_objects as go
import pytest

from app.modules.statistics.common_layout import apply_base_layout
from app.modules.statistics.labels import chart_text
from app.modules.statistics.normalization import safe_chart_float, safe_chart_int


def test_chart_normalization_preserves_missing_values_and_real_zero() -> None:
    values = [None, "", math.nan, "0", 12.5]

    normalized = [safe_chart_float(value) for value in values]

    assert normalized == [None, None, None, 0.0, 12.5]
    assert safe_chart_int("2023") == 2023
    assert safe_chart_int("20.5") is None


def test_common_layout_keeps_the_existing_visual_contract() -> None:
    figure = go.Figure()

    apply_base_layout(figure)

    assert figure.layout.margin.to_plotly_json() == {"l": 45, "r": 20, "t": 20, "b": 55}
    assert figure.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert figure.layout.showlegend is False


@pytest.mark.parametrize("value", [math.inf, -math.inf, "Infinity", 10**400])
def test_chart_normalization_rejects_non_finite_values(value) -> None:
    assert safe_chart_float(value) is None
    assert safe_chart_int(value) is None


def test_chart_text_uses_only_the_requested_visible_language() -> None:
    assert chart_text("es", "Sin datos", "No data") == "Sin datos"
    assert chart_text("en", "Sin datos", "No data") == "No data"
