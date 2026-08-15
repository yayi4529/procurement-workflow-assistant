from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.capabilities.policy import CapabilityPolicy
from procurement_platform.application.assistant.tooling import QueryPurchaseRequestsArgs
from procurement_platform.bootstrap.container import _build_capability_registry
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserRole


@pytest.mark.asyncio
async def test_role_capability_registry_existing_tool_fake_backend_chain() -> None:
    user = CurrentUser(
        employee_id=1,
        name="Capability Integration",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.APPLICANT),),
        buildings=(),
    )
    registry = _build_capability_registry(FakeBackendClient(user))
    policy = CapabilityPolicy(registry)
    context = AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_capability_integration",
        conversation_id=1,
        external_conversation_id="oc_capability_integration",
        external_message_id="om_capability_integration",
        current_time=datetime(2026, 8, 15, tzinfo=UTC),
        timezone_name="Asia/Shanghai",
        current_user=user,
        active_requirement_id=None,
    )

    result = await registry.get("query_purchase_requests").execute(
        args=QueryPurchaseRequestsArgs(operation="SEARCH"),
        context=context,
    )

    assert "query_purchase_requests" in policy.allowed_names_for(user)
    assert result.status == "NOT_FOUND"
