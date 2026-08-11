from datetime import date
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from procurement_platform.adapters.backend.dto import (
    BackendAgentConversationDTO,
    BackendAgentMessagePageDTO,
    BackendAgentSessionStateDTO,
    BackendAgentStateSaveDTO,
    BackendCreatedRequirementDTO,
    BackendCurrentUserDTO,
    BackendEnvelope,
    BackendFieldsSaveDTO,
    BackendHandlerCandidatesDTO,
    BackendProductRecommendationsDTO,
    BackendPurchaseHistoryRecommendationsDTO,
    BackendPurchaseRecordPageDTO,
    BackendRequirementDetailDTO,
    BackendRequirementMutationDTO,
    BackendRequirementPageDTO,
    BackendSupplierCreatedDTO,
    BackendSupplierDetailDTO,
    BackendSupplierPageDTO,
    BackendSupplierRecommendationsDTO,
    BackendTimelineContactDTO,
    BackendTimelineDTO,
)
from procurement_platform.adapters.backend.error_mapping import map_backend_error
from procurement_platform.adapters.backend.mapper import (
    map_agent_conversation,
    map_agent_message_page,
    map_agent_session_state,
    map_agent_state_save,
    map_created_requirement,
    map_current_user,
    map_fields_save,
    map_handler_candidates,
    map_product_recommendations,
    map_purchase_history_recommendations,
    map_purchase_record_page,
    map_requirement_completion,
    map_requirement_detail,
    map_requirement_page,
    map_requirement_timeline,
    map_requirement_transition,
    map_supplier_created,
    map_supplier_detail,
    map_supplier_page,
    map_supplier_recommendations,
    map_timeline_contact,
)
from procurement_platform.adapters.backend.transport import SignedBackendTransport
from procurement_platform.domain.assistant_session import (
    AgentConversation,
    AgentConversationCompletion,
    AgentMessagePage,
    AgentMessageWriteResult,
    AgentSessionSnapshot,
    AgentSessionState,
    AgentSessionStateUpdate,
    AgentStateSaveResult,
)
from procurement_platform.domain.enums import (
    AgentMessageSender,
    RequirementStatus,
    RequirementView,
    RoleCode,
)
from procurement_platform.domain.errors import BackendProtocolError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFieldsPatch,
    ApplicantFieldsSaveResult,
    FieldsSaveResult,
    HandlerCandidates,
    ProductRecommendations,
    PurchaseFieldsPatch,
    PurchaseHistoryRecommendations,
    PurchaseRecordPage,
    RequirementCompletionResult,
    RequirementDetail,
    RequirementPage,
    RequirementSummary,
    RequirementTimeline,
    RequirementTransitionResult,
    ReviewFieldsPatch,
    SupplierDetail,
    SupplierPage,
    SupplierRecommendations,
    SupplierSummary,
    SupplierUpsertCommand,
    TimelineContact,
    WarehouseFieldsPatch,
)
from procurement_platform.domain.user import CurrentUser

ModelT = TypeVar("ModelT", bound=BaseModel)


class HttpBackendClient:
    def __init__(self, transport: SignedBackendTransport) -> None:
        self._transport = transport

    async def _request_model(
        self,
        model: type[ModelT],
        *,
        method: str,
        path: str,
        identity: PlatformIdentity,
        query: dict[str, str | int | None] | None = None,
        json_body: object | None = None,
    ) -> ModelT:
        raw = await self._transport.request(
            method=method,
            path=path,
            identity=identity,
            query=query,
            json_body=json_body,
        )
        try:
            envelope = TypeAdapter(BackendEnvelope[object]).validate_python(raw.payload)
        except PydanticValidationError as exc:
            raise BackendProtocolError(
                "BACKEND_INVALID_ENVELOPE",
                "采购后端响应结构不符合契约",
                raw.trace_id,
            ) from exc
        trace_id = envelope.trace_id or raw.trace_id
        if not 200 <= raw.status_code < 300 or not envelope.success:
            raise map_backend_error(envelope.code, envelope.message, trace_id)
        if envelope.data is None:
            raise BackendProtocolError(
                "BACKEND_MISSING_DATA",
                "采购后端成功响应缺少 data",
                trace_id,
            )
        try:
            return model.model_validate(envelope.data)
        except PydanticValidationError as exc:
            raise BackendProtocolError(
                "BACKEND_INVALID_DATA",
                "采购后端 data 不符合契约",
                trace_id,
            ) from exc

    async def get_current_user(self, *, identity: PlatformIdentity) -> CurrentUser:
        dto = await self._request_model(
            BackendCurrentUserDTO,
            method="GET",
            path="/api/v1/users/me",
            identity=identity,
        )
        return map_current_user(dto)

    async def create_requirement(
        self, *, identity: PlatformIdentity, building_id: int
    ) -> RequirementSummary:
        dto = await self._request_model(
            BackendCreatedRequirementDTO,
            method="POST",
            path="/api/v1/requirements",
            identity=identity,
            json_body={"building_id": building_id},
        )
        return map_created_requirement(dto)

    async def update_applicant_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: ApplicantFieldsPatch,
    ) -> ApplicantFieldsSaveResult:
        dto = await self._request_model(
            BackendFieldsSaveDTO,
            method="PATCH",
            path=f"/api/v1/requirements/{requirement_id}/applicant-fields",
            identity=identity,
            json_body={
                "expected_version": expected_version,
                "fields": fields.model_dump(mode="json", exclude_unset=True),
            },
        )
        return ApplicantFieldsSaveResult.model_validate(map_fields_save(dto).model_dump())

    async def get_requirement(
        self, *, identity: PlatformIdentity, requirement_id: int
    ) -> RequirementDetail:
        dto = await self._request_model(
            BackendRequirementDetailDTO,
            method="GET",
            path=f"/api/v1/requirements/{requirement_id}",
            identity=identity,
        )
        return map_requirement_detail(dto)

    async def list_requirements(
        self,
        *,
        identity: PlatformIdentity,
        view: RequirementView,
        status: RequirementStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> RequirementPage:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("invalid pagination")
        dto = await self._request_model(
            BackendRequirementPageDTO,
            method="GET",
            path="/api/v1/requirements",
            identity=identity,
            query={
                "view": view.value,
                "status": status.value if status else None,
                "page": page,
                "page_size": page_size,
            },
        )
        return map_requirement_page(dto)

    async def get_requirement_timeline(
        self, *, identity: PlatformIdentity, requirement_id: int
    ) -> RequirementTimeline:
        dto = await self._request_model(
            BackendTimelineDTO,
            method="GET",
            path=f"/api/v1/requirements/{requirement_id}/timeline",
            identity=identity,
        )
        return map_requirement_timeline(dto)

    async def get_timeline_contact(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        log_id: int,
        subject: str = "operator",
    ) -> TimelineContact:
        if subject not in {"operator", "assignee"}:
            raise ValueError("unsupported timeline contact subject")
        dto = await self._request_model(
            BackendTimelineContactDTO,
            method="GET",
            path=f"/api/v1/requirements/{requirement_id}/timeline/{log_id}/contact",
            identity=identity,
            query={"subject": subject},
        )
        return map_timeline_contact(dto)

    async def list_purchase_records(
        self,
        *,
        identity: PlatformIdentity,
        requirement_no: str | None = None,
        supplier_id: int | None = None,
        status: RequirementStatus | None = None,
        device_name: str | None = None,
        brand: str | None = None,
        model: str | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PurchaseRecordPage:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("invalid pagination")
        dto = await self._request_model(
            BackendPurchaseRecordPageDTO,
            method="GET",
            path="/api/v1/purchase-records",
            identity=identity,
            query={
                "requirement_no": requirement_no,
                "supplier_id": supplier_id,
                "status": status.value if status else None,
                "device_name": device_name,
                "brand": brand,
                "model": model,
                "created_from": created_from.isoformat() if created_from else None,
                "created_to": created_to.isoformat() if created_to else None,
                "page": page,
                "page_size": page_size,
            },
        )
        return map_purchase_record_page(dto)

    async def recommend_products(
        self,
        *,
        identity: PlatformIdentity,
        device_name: str,
        device_profession: str | None = None,
        keyword: str | None = None,
        limit: int = 3,
    ) -> ProductRecommendations:
        if not device_name.strip() or not 1 <= limit <= 30:
            raise ValueError("invalid product recommendation query")
        dto = await self._request_model(
            BackendProductRecommendationsDTO,
            method="GET",
            path="/api/v1/recommendations/products",
            identity=identity,
            query={
                "device_name": device_name.strip(),
                "device_profession": device_profession,
                "keyword": keyword,
                "limit": limit,
            },
        )
        return map_product_recommendations(dto)

    async def recommend_purchase_history(
        self, *, identity: PlatformIdentity, requirement_id: int, limit: int = 10
    ) -> PurchaseHistoryRecommendations:
        if requirement_id < 1 or not 1 <= limit <= 30:
            raise ValueError("invalid purchase history recommendation query")
        dto = await self._request_model(
            BackendPurchaseHistoryRecommendationsDTO,
            method="GET",
            path="/api/v1/recommendations/purchase-history",
            identity=identity,
            query={"requirement_id": requirement_id, "limit": limit},
        )
        return map_purchase_history_recommendations(dto)

    async def list_handler_candidates(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        target_role: RoleCode,
    ) -> HandlerCandidates:
        if target_role not in {
            RoleCode.BUILDING_MANAGER,
            RoleCode.PURCHASER,
            RoleCode.WAREHOUSE_MANAGER,
        }:
            raise ValueError("unsupported handler target role")
        dto = await self._request_model(
            BackendHandlerCandidatesDTO,
            method="GET",
            path=f"/api/v1/requirements/{requirement_id}/handler-candidates",
            identity=identity,
            query={"target_role": target_role.value},
        )
        return map_handler_candidates(dto)

    async def _review_transition(
        self,
        path_action: str,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        dto = await self._request_model(
            BackendRequirementMutationDTO,
            method="POST",
            path=f"/api/v1/requirements/{requirement_id}/{path_action}",
            identity=identity,
            json_body={
                "expected_version": expected_version,
                "assigned_to_employee_id": assigned_to_employee_id,
                "action_token": str(action_token),
            },
        )
        return map_requirement_transition(dto)

    async def submit_review(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        return await self._review_transition(
            "submit-review",
            identity=identity,
            requirement_id=requirement_id,
            expected_version=expected_version,
            assigned_to_employee_id=assigned_to_employee_id,
            action_token=action_token,
        )

    async def resubmit_review(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        return await self._review_transition(
            "resubmit-review",
            identity=identity,
            requirement_id=requirement_id,
            expected_version=expected_version,
            assigned_to_employee_id=assigned_to_employee_id,
            action_token=action_token,
        )

    async def update_review_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: ReviewFieldsPatch,
    ) -> FieldsSaveResult:
        dto = await self._request_model(
            BackendFieldsSaveDTO,
            method="PATCH",
            path=f"/api/v1/requirements/{requirement_id}/review-fields",
            identity=identity,
            json_body={
                "expected_version": expected_version,
                "fields": fields.model_dump(mode="json", exclude_unset=True),
            },
        )
        return map_fields_save(dto)

    async def reject_requirement(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        reason: str,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        dto = await self._request_model(
            BackendRequirementMutationDTO,
            method="POST",
            path=f"/api/v1/requirements/{requirement_id}/reject",
            identity=identity,
            json_body={
                "expected_version": expected_version,
                "reason": reason,
                "action_token": str(action_token),
            },
        )
        return map_requirement_transition(dto)

    async def submit_purchaser(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        dto = await self._request_model(
            BackendRequirementMutationDTO,
            method="POST",
            path=f"/api/v1/requirements/{requirement_id}/submit-purchaser",
            identity=identity,
            json_body={
                "expected_version": expected_version,
                "assigned_to_employee_id": assigned_to_employee_id,
                "action_token": str(action_token),
            },
        )
        return map_requirement_transition(dto)

    async def start_purchase(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        dto = await self._request_model(
            BackendRequirementMutationDTO,
            method="POST",
            path=f"/api/v1/requirements/{requirement_id}/start-purchase",
            identity=identity,
            json_body={"expected_version": expected_version, "action_token": str(action_token)},
        )
        return map_requirement_transition(dto)

    async def search_suppliers(
        self,
        *,
        identity: PlatformIdentity,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
    ) -> SupplierPage:
        if not keyword.strip():
            raise ValueError("keyword must not be empty")
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("invalid pagination")
        dto = await self._request_model(
            BackendSupplierPageDTO,
            method="GET",
            path="/api/v1/suppliers",
            identity=identity,
            query={"keyword": keyword.strip(), "page": page, "page_size": page_size},
        )
        return map_supplier_page(dto)

    async def get_supplier(
        self,
        *,
        identity: PlatformIdentity,
        supplier_id: int,
    ) -> SupplierDetail:
        dto = await self._request_model(
            BackendSupplierDetailDTO,
            method="GET",
            path=f"/api/v1/suppliers/{supplier_id}",
            identity=identity,
        )
        return map_supplier_detail(dto)

    async def recommend_suppliers(
        self, *, identity: PlatformIdentity, requirement_id: int, limit: int = 3
    ) -> SupplierRecommendations:
        if requirement_id < 1:
            raise ValueError("requirement_id must be positive")
        if not 1 <= limit <= 3:
            raise ValueError("limit must be between 1 and 3")
        dto = await self._request_model(
            BackendSupplierRecommendationsDTO,
            method="GET",
            path="/api/v1/recommendations/suppliers",
            identity=identity,
            query={"requirement_id": requirement_id, "limit": limit},
        )
        return map_supplier_recommendations(dto)

    async def create_supplier(
        self,
        *,
        identity: PlatformIdentity,
        command: SupplierUpsertCommand,
    ) -> SupplierSummary:
        dto = await self._request_model(
            BackendSupplierCreatedDTO,
            method="POST",
            path="/api/v1/suppliers",
            identity=identity,
            json_body={
                "supplier_name": command.supplier_name,
                "unified_social_credit_code": command.supplier_tax_number,
                "bank_name": command.bank_name,
                "bank_account": command.bank_account,
                "registered_address": command.registered_address,
                "contract_contact_info": command.contract_contact_info,
            },
        )
        return map_supplier_created(dto)

    async def update_purchase_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: PurchaseFieldsPatch,
    ) -> FieldsSaveResult:
        dto = await self._request_model(
            BackendFieldsSaveDTO,
            method="PATCH",
            path=f"/api/v1/requirements/{requirement_id}/purchase-fields",
            identity=identity,
            json_body={
                "expected_version": expected_version,
                "fields": fields.model_dump(mode="json", exclude_unset=True),
            },
        )
        return map_fields_save(dto)

    async def submit_warehouse(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        dto = await self._request_model(
            BackendRequirementMutationDTO,
            method="POST",
            path=f"/api/v1/requirements/{requirement_id}/submit-warehouse",
            identity=identity,
            json_body={
                "expected_version": expected_version,
                "assigned_to_employee_id": assigned_to_employee_id,
                "action_token": str(action_token),
            },
        )
        return map_requirement_transition(dto)

    async def update_warehouse_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: WarehouseFieldsPatch,
    ) -> FieldsSaveResult:
        dto = await self._request_model(
            BackendFieldsSaveDTO,
            method="PATCH",
            path=f"/api/v1/requirements/{requirement_id}/warehouse-fields",
            identity=identity,
            json_body={
                "expected_version": expected_version,
                "fields": fields.model_dump(mode="json", exclude_unset=True),
            },
        )
        return map_fields_save(dto)

    async def complete_requirement(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        action_token: UUID,
    ) -> RequirementCompletionResult:
        dto = await self._request_model(
            BackendRequirementMutationDTO,
            method="POST",
            path=f"/api/v1/requirements/{requirement_id}/complete",
            identity=identity,
            json_body={"expected_version": expected_version, "action_token": str(action_token)},
        )
        return map_requirement_completion(dto)

    async def get_or_create_agent_conversation(
        self, *, identity: PlatformIdentity, current_action: str
    ) -> AgentConversation:
        dto = await self._request_model(
            BackendAgentConversationDTO,
            method="POST",
            path="/api/v1/agent/conversations/active",
            identity=identity,
            json_body={"current_action": current_action},
        )
        return map_agent_conversation(dto, current_action=current_action)

    async def append_agent_message(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        sender_type: AgentMessageSender,
        content: str,
    ) -> AgentMessageWriteResult:
        return await self._request_model(
            AgentMessageWriteResult,
            method="POST",
            path=f"/api/v1/agent/conversations/{conversation_id}/messages",
            identity=identity,
            json_body={
                "external_message_id": external_message_id,
                "sender_type": sender_type.value,
                "content": content,
            },
        )

    async def list_agent_messages(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> AgentMessagePage:
        if page < 1:
            raise ValueError("page must be at least 1")
        if not 1 <= page_size <= 200:
            raise ValueError("page_size must be between 1 and 200")
        dto = await self._request_model(
            BackendAgentMessagePageDTO,
            method="GET",
            path=f"/api/v1/agent/conversations/{conversation_id}/messages",
            identity=identity,
            query={"page": page, "page_size": page_size},
        )
        return map_agent_message_page(dto, conversation_id=conversation_id)

    async def get_agent_state(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> AgentSessionState:
        dto = await self._request_model(
            BackendAgentSessionStateDTO,
            method="GET",
            path=f"/api/v1/agent/conversations/{conversation_id}/state",
            identity=identity,
        )
        return map_agent_session_state(dto)

    async def update_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        state: AgentSessionStateUpdate,
    ) -> AgentStateSaveResult:
        dto = await self._request_model(
            BackendAgentStateSaveDTO,
            method="PUT",
            path=f"/api/v1/agent/conversations/{conversation_id}/state",
            identity=identity,
            json_body=state.model_dump(mode="json"),
        )
        return map_agent_state_save(dto)

    async def snapshot_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        snapshot_reason: str,
    ) -> AgentSessionSnapshot:
        return await self._request_model(
            AgentSessionSnapshot,
            method="POST",
            path=f"/api/v1/agent/conversations/{conversation_id}/snapshot",
            identity=identity,
            json_body={"snapshot_reason": snapshot_reason},
        )

    async def complete_agent_conversation(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        purchase_request_id: int | None,
    ) -> AgentConversationCompletion:
        return await self._request_model(
            AgentConversationCompletion,
            method="POST",
            path=f"/api/v1/agent/conversations/{conversation_id}/complete",
            identity=identity,
            json_body={"purchase_request_id": purchase_request_id},
        )

    async def aclose(self) -> None:
        await self._transport.aclose()
