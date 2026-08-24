from pathlib import Path

import pytest

from procurement_platform.adapters.skills import MarkdownRoleSkillLoader
from procurement_platform.application.assistant.role_skills import (
    RoleSkill,
    RoleSkillRegistry,
    RoleWorkflow,
)
from procurement_platform.domain.enums import RoleCode

SKILLS_ROOT = Path(__file__).parents[2] / "skills"


def test_markdown_loader_loads_all_role_skills_and_workflows() -> None:
    registry = MarkdownRoleSkillLoader(SKILLS_ROOT).load()

    assert registry.get(RoleCode.APPLICANT) is not None
    purchaser = registry.get(RoleCode.PURCHASER)
    assert purchaser is not None
    assert set(purchaser.workflows) == {
        "pending-purchase",
        "procurement-analytics",
        "product-recommendation",
        "supplier-recommendation",
    }
    supplier = purchaser.workflows["supplier-recommendation"]
    assert supplier.capability_names == frozenset({"recommend_suppliers_with_evidence"})
    assert supplier.initial_phase.name == "execute"
    assert "供应商统计必须走智能问数" in supplier.instructions
    assert supplier.stop_after_success == frozenset({"recommend_suppliers_with_evidence"})
    assert purchaser.workflows["procurement-analytics"].stop_after_success == frozenset(
        {"analyze_procurement"}
    )


@pytest.mark.parametrize(
    ("role", "text", "expected"),
    (
        (RoleCode.APPLICANT, "我要买2个开关电源", "create-draft"),
        (RoleCode.APPLICANT, "2号UPS高温报警", "fault-procurement"),
        (RoleCode.PURCHASER, "今年每月采购金额趋势", "procurement-analytics"),
        (RoleCode.PURCHASER, "按合作次数推荐供应商", "supplier-recommendation"),
        (RoleCode.WAREHOUSE_MANAGER, "还有哪些待入库单据", "pending-receipt"),
    ),
)
def test_registry_selects_one_workflow(role: RoleCode, text: str, expected: str) -> None:
    selection = MarkdownRoleSkillLoader(SKILLS_ROOT).load().select(role=role, user_text=text)

    assert selection is not None
    assert selection.workflow.name == expected
    assert f'workflow name="{expected}"' in selection.system_context


def test_registry_returns_none_for_unclassified_conversation() -> None:
    registry = MarkdownRoleSkillLoader(SKILLS_ROOT).load()

    assert registry.select(role=RoleCode.APPLICANT, user_text="你好") is None


def test_registry_rejects_unknown_capability_reference() -> None:
    workflow = RoleWorkflow(
        name="test",
        description="test",
        instructions="test",
        triggers=("test",),
        capability_names=frozenset({"unknown_tool"}),
    )
    registry = RoleSkillRegistry(
        (
            RoleSkill(
                name="applicant",
                role=RoleCode.APPLICANT,
                description="test",
                instructions="test",
                workflows={"test": workflow},
            ),
        )
    )

    with pytest.raises(ValueError, match="unknown_tool"):
        registry.validate_capabilities(frozenset({"known_tool"}))
