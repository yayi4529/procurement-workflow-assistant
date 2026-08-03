from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementArgs,
    RecommendSuppliersForRequirementTool,
)
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.enums import (
    AllowedRequirementAction,
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFields,
    RequirementBuilding,
    RequirementDetail,
    RequirementHandler,
    SupplierBlacklistSummary,
    SupplierDetail,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def manager() -> CurrentUser:
    return CurrentUser(
        employee_id=7,
        name="楼长",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.BUILDING_MANAGER),),
        buildings=(UserBuilding(building_id=1, building_name="一号楼"),),
    )


def identity() -> PlatformIdentity:
    return PlatformIdentity(PlatformType.FEISHU, "ou_manager", "request")


def context() -> AssistantToolContext:
    return AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_manager",
        conversation_id=1,
        external_conversation_id="oc_1",
        external_message_id="om_1",
        current_time=datetime.now(UTC),
        timezone_name="Asia/Shanghai",
        current_user=manager(),
    )


def backend() -> FakeBackendClient:
    client = FakeBackendClient(manager())
    client.seed_requirement(
        RequirementDetail(
            requirement_id=1,
            requirement_no="PR-1",
            status=RequirementStatus.PENDING_REVIEW,
            version=2,
            building=RequirementBuilding(building_id=1, building_name="一号楼"),
            current_handler=RequirementHandler(employee_id=7, name="楼长"),
            applicant_fields=ApplicantFields(
                device_profession="网络", device_name="交换机", quantity="2", unit="台"
            ),
            missing_fields=(),
            allowed_actions=(AllowedRequirementAction.UPDATE_REVIEW_FIELDS,),
        )
    )
    client.seed_supplier(
        SupplierDetail(
            supplier_id=11,
            supplier_name="可用供应商",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    client.seed_supplier(
        SupplierDetail(
            supplier_id=12,
            supplier_name="黑名单供应商",
            blacklist=SupplierBlacklistSummary(active=True),
        )
    )
    return client


@pytest.mark.asyncio
async def test_manager_supplier_recommendation_rechecks_backend_and_saves_references() -> None:
    client = backend()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )
    result = await RecommendSuppliersForRequirementTool(client).execute(
        args=RecommendSuppliersForRequirementArgs(requirement_id=1),
        context=context().model_copy(update={"conversation_id": conversation.conversation_id}),
    )
    saved = await client.get_agent_state(
        identity=identity(), conversation_id=conversation.conversation_id
    )

    assert result.status == "SUCCESS"
    assert result.requirement_version == 2
    assert result.candidates[0].candidate_ref == "supplier:11"
    assert result.candidates[0].supplier_name == "可用供应商"
    assert len(result.candidates) == 1
    assert saved.purchase_request_id == 1
    assert saved.last_recommendations[0].reference_id == "supplier:11"
    assert client.call_counts["get_current_user"] == 1
    assert client.call_counts["get_requirement"] == 1
    assert client.call_counts["recommend_suppliers"] == 1


@pytest.mark.asyncio
async def test_supplier_recommendation_refuses_non_pending_requirement() -> None:
    client = backend()
    detail = client._requirements[1]
    client.seed_requirement(
        detail.model_copy(update={"status": RequirementStatus.PENDING_PURCHASE})
    )

    result = await RecommendSuppliersForRequirementTool(client).execute(
        args=RecommendSuppliersForRequirementArgs(requirement_id=1), context=context()
    )

    assert result.status == "INVALID_STATUS"
    assert client.call_counts["recommend_suppliers"] == 0
