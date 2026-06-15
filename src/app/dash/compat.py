from __future__ import annotations

import importlib

_dash = importlib.import_module("dash")
_dcc = importlib.import_module("dash.dcc")
_html = importlib.import_module("dash.html")
_dependencies = importlib.import_module("dash.dependencies")

Dash = _dash.Dash
Input = _dependencies.Input
Output = _dependencies.Output
State = _dependencies.State

dcc = _dcc
html = _html

