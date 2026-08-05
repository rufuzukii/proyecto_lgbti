"""Temporal trend analysis for comparable FRA and ILGA historical series."""

from app.trends.callbacks import register_trend_callbacks
from app.trends.layout import build_trends_layout

__all__ = ["build_trends_layout", "register_trend_callbacks"]
