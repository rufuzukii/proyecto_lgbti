from __future__ import annotations

import math

import plotly.graph_objects as go

from app.analytics.statistics.common_layout import apply_base_layout
from app.analytics.statistics.labels import chart_text
from app.analytics.statistics.normalization import safe_chart_float, safe_chart_int


def test_chart_normalization_preserves_missing_values_and_real_zero() -> None:
    # Arrange
    values = [None, "", math.nan, "0", 12.5]

    # Act
    normalized = [safe_chart_float(value) for value in values]

    # Assert
    assert normalized == [None, None, None, 0.0, 12.5]
    assert safe_chart_int("2023") == 2023
    assert safe_chart_int("20.5") is None


def test_common_layout_keeps_the_existing_visual_contract() -> None:
    # Arrange
    figure = go.Figure()

    # Act
    apply_base_layout(figure)

    # Assert
    assert figure.layout.margin.to_plotly_json() == {"l": 45, "r": 20, "t": 20, "b": 55}
    assert figure.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert figure.layout.showlegend is False


def test_chart_text_uses_only_the_requested_visible_language() -> None:
    assert chart_text("es", "Sin datos", "No data") == "Sin datos"
    assert chart_text("en", "Sin datos", "No data") == "No data"
