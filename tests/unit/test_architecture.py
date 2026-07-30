import ast
from pathlib import Path


def test_domain_and_ports_do_not_import_frameworks_or_databases() -> None:
    forbidden = ("httpx", "fastapi", "lark_oapi", "sqlalchemy", "redis")
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


def test_application_does_not_import_feishu_sdk() -> None:
    for path in Path("src/procurement_platform/application").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert all(not module.startswith("lark_oapi") for module in imported)
        assert all(
            alias.name != "lark_oapi"
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
