from __future__ import annotations


def chart_text(language: str, spanish: str, english: str) -> str:
    """Select a chart label without coupling figure builders to Dash components."""
    return english if language == "en" else spanish
