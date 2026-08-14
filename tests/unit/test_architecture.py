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


def test_formal_card_and_application_modules_do_not_import_llm_or_agent_session() -> None:
    roots = (
        Path("src/procurement_platform/application/applicant"),
        Path("src/procurement_platform/application/building_manager"),
        Path("src/procurement_platform/application/purchaser"),
        Path("src/procurement_platform/application/warehouse"),
        Path("src/procurement_platform/application/inbound/card_interaction_handler.py"),
    )
    files = [path for root in roots for path in ([root] if root.is_file() else root.rglob("*.py"))]
    forbidden = ("llm", "openai", "assistant_session", "assistantorchestrator")
    for path in files:
        source = path.read_text(encoding="utf-8").lower()
        assert all(name not in source for name in forbidden), path


def test_notification_gateway_has_no_business_transition_dependency() -> None:
    path = Path("src/procurement_platform/application/notifications/gateway_service.py")
    source = path.read_text(encoding="utf-8").lower()
    forbidden = (
        "backendclient",
        "submit_review",
        "resubmit_review",
        "reject_requirement",
        "submit_purchaser",
        "start_purchase",
        "submit_warehouse",
        "complete_requirement",
    )
    assert all(name not in source for name in forbidden)


def test_assistant_runtime_has_no_role_business_dependencies() -> None:
    source = Path("src/procurement_platform/application/assistant/runtime.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "ApplicantCardFactory",
        "BuildingManagerCardFactory",
        "PurchaserCardFactory",
        "WarehouseCardFactory",
        "UpdatePurchaseDraftResult",
        "UpdateReviewDraftResult",
        "UpdatePurchaseExecutionDraftResult",
        "UpdateWarehouseReceiptDraftResult",
        "brand",
        "model",
        "supplier",
        "warehouse",
    )
    assert all(name not in source for name in forbidden)


def test_agent_tools_is_only_a_compatibility_facade() -> None:
    path = Path("src/procurement_platform/application/assistant/agent_tools.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not any(isinstance(node, (ast.ClassDef, ast.FunctionDef)) for node in tree.body)


def test_tooling_modules_are_split_by_role_without_agent_dependencies() -> None:
    root = Path("src/procurement_platform/application/assistant/tooling")
    assert {path.name for path in root.glob("*.py")} >= {
        "__init__.py",
        "common.py",
        "applicant.py",
        "building_manager.py",
        "purchaser.py",
        "warehouse.py",
    }
    for path in root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "application.assistant.agents" not in source, path
