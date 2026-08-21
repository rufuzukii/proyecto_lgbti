from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from app.dash.components.source_attribution import (
    build_footer_attributions,
    build_source_attribution,
)
from app.dash_app import _build_application_shell
from app.source_attribution import (
    FELGTBI_REPORTS_URL,
    FELGTBI_URL,
    FRA_ORGANIZATION_URL,
    FRA_SURVEYS,
    ILGA_RAINBOW_MAP_URL,
    ILGA_URL,
    PROCESSED_BY,
    source_metadata,
    source_storage_fields,
)


def test_fra_publication_year_resolves_to_survey_iii_attribution() -> None:
    metadata = source_metadata("FRA", year=2024)

    assert metadata.source_name == "EU LGBTIQ Survey III"
    assert metadata.source_year == 2023
    assert metadata.source_url == FRA_SURVEYS[2023][1]
    assert "EU LGBTIQ Survey III, 2023" in metadata.source_attribution_es
    assert "FRA no participa" in metadata.source_attribution_es
    assert "FRA is not involved" in metadata.source_attribution_en


def test_each_source_exposes_required_storage_metadata_without_invented_license() -> None:
    required_fields = {
        "source_organization",
        "source_name",
        "source_url",
        "source_document",
        "source_year",
        "source_figure",
        "source_accessed_at",
        "source_license",
        "source_attribution",
        "source_disclaimer",
        "processed_by",
    }

    for source in ("fra", "ilga", "felgtbi"):
        fields = source_storage_fields(source, year=2023)
        assert required_fields == fields.keys()
        assert fields["processed_by"] == PROCESSED_BY
        assert "Consultar condiciones" in fields["source_license"]


def test_ilga_and_felgtbi_disclaim_affiliation_in_both_languages() -> None:
    ilga = source_metadata("rainbow map", year=2026)
    felgtbi = source_metadata("felgtbi", year=2025)

    assert ilga.source_url == ILGA_RAINBOW_MAP_URL
    assert "no está afiliada" in ilga.source_attribution_es
    assert "not affiliated" in ilga.source_attribution_en
    assert felgtbi.source_url == FELGTBI_REPORTS_URL
    assert "no está afiliada" in felgtbi.source_attribution_es
    assert "not affiliated" in felgtbi.source_attribution_en


def test_compact_component_is_bilingual_accessible_and_links_to_original_source() -> None:
    component = build_source_attribution("fra", year=2024, compact=True)
    links = [child for child in _walk(component) if _prop(child, "href")]

    assert _prop(component, "role") == "note"
    assert _prop(component, "data-source-attribution") == "fra"
    assert "EU LGBTIQ Survey III, 2023" in _content(component)
    assert any(_prop(child, "data-i18n-en") for child in _walk(component))
    assert len(links) == 1
    assert _prop(links[0], "href") == FRA_SURVEYS[2023][1]
    assert _prop(links[0], "target") == "_blank"
    assert _prop(links[0], "rel") == "noopener noreferrer"
    assert _prop(links[0], "aria-label")


def test_footer_attributions_contain_three_accessible_official_source_blocks() -> None:
    section = build_footer_attributions()
    source_blocks = {
        _prop(child, "data-footer-attribution"): child
        for child in _walk(section)
        if _prop(child, "data-footer-attribution")
    }

    assert set(source_blocks) == {"fra", "ilga", "felgtbi"}
    assert "Atribuciones" in _content(section)
    assert "RainbowLens DataHub" in _content(section)
    links = {
        _prop(child, "href"): child for child in _walk(section) if _prop(child, "href")
    }
    assert set(links) == {FRA_ORGANIZATION_URL, ILGA_URL, FELGTBI_URL}
    for link in links.values():
        assert _prop(link, "target") == "_blank"
        assert _prop(link, "rel") == "noopener noreferrer"
        assert _prop(link, "aria-label")
        assert "↗" in _content(link)


def test_attribution_styles_cover_dark_mode_mobile_wrapping_and_keyboard_focus() -> None:
    component_styles = Path("src/app/dash/assets/source_attribution.css").read_text(
        encoding="utf-8"
    )
    footer_styles = Path("src/app/dash/assets/styles.css").read_text(encoding="utf-8")

    assert ':root[data-theme="dark"] .source-attribution' in component_styles
    assert "@media (max-width: 640px)" in component_styles
    assert "overflow-wrap: anywhere" in component_styles
    assert ".source-attribution-link:focus-visible" in component_styles
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in footer_styles
    assert "grid-auto-flow: column" not in footer_styles
    assert "@media (max-width: 900px)" in footer_styles
    assert "grid-template-columns: 1fr" in footer_styles
    assert "align-items: stretch" in footer_styles
    assert "gap: clamp(0.75rem, 2vw, 1.25rem)" in footer_styles
    assert "font-size: 0.7rem" in footer_styles
    assert "font-size: 0.68rem" in footer_styles
    assert "@media (max-width: 1100px)" in footer_styles
    assert "@media (max-width: 680px)" in footer_styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" not in footer_styles
    assert footer_styles.count(".footer-attributions-grid {") == 2
    block_rule = footer_styles.split(".footer-attribution-block {", 1)[1].split("}", 1)[0]
    assert "background:" not in block_rule
    assert "border:" not in block_rule
    assert "border-radius:" not in block_rule
    assert "padding: 0.25rem 0" in block_rule
    assert ".footer-attribution-card" not in footer_styles
    assert ".footer-attribution-link:focus-visible" in footer_styles


def test_application_footer_has_sources_and_privacy_without_obsolete_links() -> None:
    with patch(
        "app.dash_app.current_user",
        SimpleNamespace(is_authenticated=False),
    ):
        shell = _build_application_shell()

    links = [_prop(child, "href") for child in _walk(shell) if _prop(child, "href")]
    assert FRA_ORGANIZATION_URL in links
    assert ILGA_URL in links
    assert FELGTBI_URL in links
    assert "/es/privacidad" in links
    assert "/about#sources-attributions" not in links
    assert not any("aepd.es" in str(link) for link in links)
    assert "Fuentes y atribuciones" not in _content(shell)


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "children") or hasattr(child, "to_plotly_json"):
                yield from _walk(child)
    elif hasattr(children, "children") or hasattr(children, "to_plotly_json"):
        yield from _walk(children)


def _prop(component: Any, name: str) -> Any:
    value = getattr(component, name, None)
    if value is not None:
        return value
    if hasattr(component, "to_plotly_json"):
        return component.to_plotly_json().get("props", {}).get(name)
    return None


def _content(component: Any) -> str:
    if isinstance(component, str):
        return component
    children = getattr(component, "children", None)
    if isinstance(children, str):
        return children
    if isinstance(children, (list, tuple)):
        return " ".join(_content(child) for child in children)
    return _content(children) if children is not None else ""
