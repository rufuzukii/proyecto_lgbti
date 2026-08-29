"""Historical ILGA overall-score analysis and transparent short-term forecasts."""

from app.modules.trends.callbacks import register_trend_callbacks
from app.modules.trends.layout import build_trends_layout

__all__ = ["build_trends_layout", "register_trend_callbacks"]
