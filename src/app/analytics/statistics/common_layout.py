from __future__ import annotations

import plotly.graph_objects as go

PLOTLY_TRANSPARENT = "rgba(0,0,0,0)"


def apply_base_layout(figure: go.Figure, margin: dict[str, int] | None = None) -> None:
    """Apply the common visual contract used by statistics figures."""
    figure.update_layout(
        margin=margin or {"l": 45, "r": 20, "t": 20, "b": 55},
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        font={"family": "Segoe UI, Arial, sans-serif", "color": "#252a31"},
        showlegend=False,
    )
