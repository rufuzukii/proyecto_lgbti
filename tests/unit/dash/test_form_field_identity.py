from __future__ import annotations

import ast
from pathlib import Path

FORM_FIELD_COMPONENTS = {
    ("dcc", "Input"),
    ("dcc", "Textarea"),
    ("html", "Input"),
    ("html", "Select"),
    ("html", "Textarea"),
}


def test_native_form_fields_declare_an_id_or_name() -> None:
    missing_identity: list[str] = []
    for path in Path("src/app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            owner = node.func.value
            if not isinstance(owner, ast.Name):
                continue
            if (owner.id, node.func.attr) not in FORM_FIELD_COMPONENTS:
                continue
            attributes = {keyword.arg for keyword in node.keywords if keyword.arg}
            if not {"id", "name"}.intersection(attributes):
                missing_identity.append(f"{path}:{node.lineno}")

    assert missing_identity == []
