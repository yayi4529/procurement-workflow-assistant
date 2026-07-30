import ast
from pathlib import Path


def test_domain_and_ports_do_not_import_frameworks_or_databases() -> None:
    forbidden = ("httpx", "fastapi", "sqlalchemy", "redis")
    files = [
        *Path("src/procurement_platform/domain").glob("*.py"),
        *Path("src/procurement_platform/ports").glob("*.py"),
    ]
    imported_modules: set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module.lower())
    for dependency in forbidden:
        assert all(not module.startswith(dependency) for module in imported_modules)
