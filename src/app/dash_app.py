from pathlib import Path

from dash import Dash

from app.dash.layouts.home import build_home_layout


def create_dash_app() -> Dash:
    assets_path = Path(__file__).resolve().parent / "dash" / "assets"
    app = Dash(__name__, assets_folder=str(assets_path))
    app.layout = build_home_layout()
    return app
