from __future__ import annotations

from collections.abc import Iterable

from dash import dcc

_FIXED_MAP_MODE_BAR_BUTTONS = (
    "zoomInGeo",
    "zoomOutGeo",
    "resetGeo",
    "pan2d",
    "zoom2d",
    "autoScale2d",
    "resetScale2d",
    "lasso2d",
    "select2d",
)


def fixed_europe_map_config(
    *,
    extra_mode_bar_buttons_to_remove: Iterable[str] = (),
) -> dcc.Graph.Config:
    """Return a non-navigable map config that keeps hover and click events active."""
    buttons = list(dict.fromkeys((*_FIXED_MAP_MODE_BAR_BUTTONS, *extra_mode_bar_buttons_to_remove)))
    return {
        "displaylogo": False,
        "responsive": True,
        "scrollZoom": False,
        "doubleClick": False,
        "modeBarButtonsToRemove": buttons,
    }
