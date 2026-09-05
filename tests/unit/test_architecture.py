from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "src" / "app"


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(APP_ROOT.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _app_import_graph() -> dict[str, set[str]]:
    modules = {_module_name(path): path for path in APP_ROOT.rglob("*.py")}
    graph: dict[str, set[str]] = {module: set() for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        imported = _runtime_imports(tree, module, path.name == "__init__.py", set(modules))
        for candidate in imported:
            while candidate and candidate not in modules:
                candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
            if candidate and candidate != module:
                graph[module].add(candidate)
    return graph


def _runtime_imports(
    tree: ast.AST,
    module: str,
    is_package: bool,
    modules: set[str],
) -> set[str]:
    imported: set[str] = set()
    package = module if is_package else module.rpartition(".")[0]

    class Visitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                return
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            imported.update(alias.name for alias in node.names if alias.name.startswith("app"))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.level:
                parts = package.split(".")
                parent = ".".join(parts[: len(parts) - node.level + 1])
                base = ".".join(filter(None, (parent, node.module or "")))
            else:
                base = node.module or ""
            if not base.startswith("app"):
                return
            for alias in node.names:
                submodule = f"{base}.{alias.name}"
                imported.add(submodule if submodule in modules else base)

    Visitor().visit(tree)
    return imported


def _first_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()

    def visit(module: str) -> list[str] | None:
        visited.add(module)
        active.append(module)
        active_set.add(module)
        for dependency in graph[module]:
            if dependency in active_set:
                start = active.index(dependency)
                return [*active[start:], dependency]
            if dependency not in visited:
                cycle = visit(dependency)
                if cycle:
                    return cycle
        active.pop()
        active_set.remove(module)
        return None

    for module in graph:
        if module not in visited and (cycle := visit(module)):
            return cycle
    return None


def test_runtime_has_explicit_modular_monolith_boundaries() -> None:
    assert {path.name for path in APP_ROOT.iterdir() if path.is_dir()} >= {
        "api",
        "core",
        "infrastructure",
        "modules",
        "shared",
        "web",
    }
    assert {path.name for path in (APP_ROOT / "modules").iterdir() if path.is_dir()} >= {
        "account",
        "administration",
        "didactics",
        "home",
        "imports",
        "reports",
        "spain",
        "statistics",
        "trends",
    }


def test_internal_app_imports_are_acyclic() -> None:
    cycle = _first_cycle(_app_import_graph())
    assert cycle is None, " -> ".join(cycle or ())


def test_runtime_does_not_use_path_hacks_or_old_python_packages() -> None:
    source = "\n".join(path.read_text(encoding="utf-8-sig") for path in APP_ROOT.rglob("*.py"))
    assert "sys.path.append" not in source
    assert "sys.path.insert" not in source
    for old_package in (
        "analytics",
        "dash",
        "edu",
        "import_to_db",
        "privacy",
        "reports",
        "trends",
        "users",
    ):
        assert not any((APP_ROOT / old_package).rglob("*.py"))
