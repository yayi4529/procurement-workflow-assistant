from procurement_platform.application.assistant.prompts.applicant import APPLICANT_PROMPT
from procurement_platform.application.assistant.prompts.building_manager import (
    BUILDING_MANAGER_PROMPT,
)
from procurement_platform.application.assistant.prompts.common import COMMON_PROMPT
from procurement_platform.application.assistant.prompts.purchaser import PURCHASER_PROMPT
from procurement_platform.application.assistant.prompts.warehouse import WAREHOUSE_PROMPT


def test_common_prompt_contains_only_cross_role_boundaries() -> None:
    assert "后端" in COMMON_PROMPT
    assert "正式飞书卡片" in COMMON_PROMPT
    assert "update_purchase_draft" not in COMMON_PROMPT
    assert "供应商推荐" not in COMMON_PROMPT


def test_applicant_prompt_does_not_mix_purchaser_or_warehouse_writes() -> None:
    assert "update_applicant_draft" in APPLICANT_PROMPT
    assert "需求人采购助手" in APPLICANT_PROMPT
    assert "selection_index" in APPLICANT_PROMPT
    assert "fields_complete=true" in APPLICANT_PROMPT
    assert "update_purchase_execution_draft" not in APPLICANT_PROMPT
    assert "update_warehouse_receipt_draft" not in APPLICANT_PROMPT


def test_each_non_applicant_prompt_exposes_only_its_role_tools() -> None:
    assert "update_review_draft" in BUILDING_MANAGER_PROMPT
    assert "Backend" in BUILDING_MANAGER_PROMPT
    assert "selection_index" in BUILDING_MANAGER_PROMPT
    assert "Observation" in BUILDING_MANAGER_PROMPT
    assert "正式审批、驳回和提交采购员只能通过正式飞书卡片" in BUILDING_MANAGER_PROMPT
    assert "不得编造供应商" in BUILDING_MANAGER_PROMPT
    assert "选1" not in BUILDING_MANAGER_PROMPT
    assert "第1个" not in BUILDING_MANAGER_PROMPT
    assert "选择第一个" not in BUILDING_MANAGER_PROMPT
    assert "update_purchase_draft" not in BUILDING_MANAGER_PROMPT
    assert "update_purchase_draft" in PURCHASER_PROMPT
    assert "update_warehouse_receipt_draft" not in PURCHASER_PROMPT
    assert "update_warehouse_receipt_draft" in WAREHOUSE_PROMPT
    assert "update_purchase_draft" not in WAREHOUSE_PROMPT
