from __future__ import annotations

import importlib

_dash = importlib.import_module("dash")
_dcc = importlib.import_module("dash.dcc")
_html = importlib.import_module("dash.html")
_dependencies = importlib.import_module("dash.dependencies")
_exceptions = importlib.import_module("dash.exceptions")

Dash = _dash.Dash
Input = _dependencies.Input
Output = _dependencies.Output
State = _dependencies.State
ALL = _dependencies.ALL
ctx = _dash.ctx
no_update = _dash.no_update
PreventUpdate = _exceptions.PreventUpdate

dcc = _dcc
html = _html

