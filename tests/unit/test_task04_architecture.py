from pathlib import Path


def test_production_text_path_does_not_import_legacy_role_routing() -> None:
    root = Path("src/procurement_platform")
    production_path = (
        root / "bootstrap/container.py",
        root / "application/assistant/service.py",
        root / "application/assistant/agent.py",
    )
    forbidden = (
        "assistant.agent_router",
        "assistant.role_intent",
        "assistant.agents",
        "assistant.tool_policy",
    )
    for path in production_path:
        content = path.read_text(encoding="utf-8")
        assert all(name not in content for name in forbidden), path
