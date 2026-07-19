from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ASSETS_JS = ROOT / "src" / "app" / "dash" / "assets" / "js"
ASSETS_CSS = ROOT / "src" / "app" / "dash" / "assets"


def test_dash_assets_do_not_replace_react_owned_text_nodes() -> None:
    forbidden_patterns = [
        "textContent =",
        "innerText =",
        "innerHTML =",
        "appendChild(",
        "removeChild(",
        "replaceChild(",
    ]

    matches: list[str] = []
    for path in ASSETS_JS.glob("*.js"):
        content = path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            if pattern in content:
                matches.append(f"{path.relative_to(ROOT)} contains {pattern!r}")

    assert matches == []


def test_statistics_segmented_buttons_use_outer_dash_options() -> None:
    js = (ASSETS_JS / "30_segmented_controls.js").read_text(encoding="utf-8")
    css = (ASSETS_CSS / "statistics.css").read_text(encoding="utf-8")

    assert ".dash-options-list-option" in js
    assert "markClickedLabel" not in js
    assert ".stats-data-type-control .dash-options-list-option:has(.stats-segmented-input:checked)" in css
    assert "stats-data-type-control--fra .stats-segmented-label:nth-of-type" not in css
    assert "stats-data-type-control--ilga .stats-segmented-label:nth-of-type" not in css
