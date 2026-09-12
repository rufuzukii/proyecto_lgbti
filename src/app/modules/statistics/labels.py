from __future__ import annotations


def chart_text(language: str, spanish: str, english: str) -> str:
    """Selecciona una etiqueta sin acoplar los constructores de figuras a Dash."""
    return english if language == "en" else spanish
