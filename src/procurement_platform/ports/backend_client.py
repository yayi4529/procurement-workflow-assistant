from datetime import date
from typing import Protocol
from uuid import UUID

from procurement_platform.domain.assets import (
    AssetContext,
    AssetPage,
    AssetSummary,
    EquipmentCategorySummary,
    EquipmentModelPage,
)
from procurement_platform.domain.assistant_session import (
    AgentConversation,
    AgentConversationCompletion,
    AgentMessage,
    AgentMessagePage,
    AgentMessageWriteResult,
    AgentSessionSnapshot,
    AgentSessionState,
    AgentSessionStateUpdate,
    AgentStateSaveResult,
)
from procurement_platform.domain.enums import (
    AgentMessageSender,
    RequestType,
    RequirementStatus,
    RequirementView,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    AppendReceiptCommand,
    ApplicantFieldsPatch,
    ApplicantFieldsSaveResult,
    FieldsSaveResult,
    HandlerCandidates,
    ProductRecommendations,
    PurchaseFieldsPatch,
    PurchaseHistoryRecommendations,
    PurchaseRecordPage,
    RequestItemDraft,
    RequirementCompletionResult,
    RequirementDetail,
    RequirementPage,
    RequirementSummary,
    RequirementTimeline,
    RequirementTransitionResult,
    ReviewFieldsPatch,
    ReviewItemDraft,
    SupplierDetail,
    SupplierPage,
    SupplierRecommendations,
    SupplierSummary,
    SupplierUpsertCommand,
    TimelineContact,
    WarehouseFieldsPatch,
)
from procurement_platform.domain.user import CurrentUser


class BackendClient(Protocol):
    async def replace_request_items(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        items: tuple[RequestItemDraft, ...],
        request_type: RequestType | None = None,
        source_asset_id: int | None = None,
    ) -> FieldsSaveResult: ...

    async def update_review_items(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        items: tuple[ReviewItemDraft, ...],
    ) -> FieldsSaveResult: ...

    async def update_purchase_item(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        request_item_id: int,
        expected_version: int,
        action_token: UUID,
        fields: PurchaseFieldsPatch,
    ) -> FieldsSaveResult: ...

    async def append_receipt(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        command: AppendReceiptCommand,
    ) -> FieldsSaveResult: ...

    async def list_equipment_categories(
        self,
        *,
        identity: PlatformIdentity,
        parent_category_id: int | None = None,
        category_level: int | None = None,
        status: str | None = "ACTIVE",
    ) -> tuple[EquipmentCategorySummary, ...]: ...

    async def list_equipment_models(
        self,
        *,
        identity: PlatformIdentity,
        category_id: int | None = None,
        brand: str | None = None,
        query: str | None = None,
        lifecycle_status: str | None = "ACTIVE",
        page: int = 1,
        page_size: int = 20,
    ) -> EquipmentModelPage: ...

    async def search_assets(
        self,
        *,
        identity: PlatformIdentity,
        building_id: int | None = None,
        category_id: int | None = None,
        category_code: str | None = None,
        model_id: int | None = None,
        status: str | None = "ACTIVE",
        criticality: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AssetPage: ...

    async def get_asset(self, *, identity: PlatformIdentity, asset_id: int) -> AssetSummary: ...

    async def get_asset_context(
        self, *, identity: PlatformIdentity, asset_id: int
    ) -> AssetContext: ...

    async def get_current_user(self, *, identity: PlatformIdentity) -> CurrentUser: ...

    async def create_requirement(
        self, *, identity: PlatformIdentity, building_id: int
    ) -> RequirementSummary: ...

    async def update_applicant_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: ApplicantFieldsPatch,
    ) -> ApplicantFieldsSaveResult: ...

    async def get_requirement(
        self, *, identity: PlatformIdentity, requirement_id: int
    ) -> RequirementDetail: ...

    async def list_requirements(
        self,
        *,
        identity: PlatformIdentity,
        view: RequirementView,
        status: RequirementStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> RequirementPage: ...

    async def get_requirement_timeline(
        self, *, identity: PlatformIdentity, requirement_id: int
    ) -> RequirementTimeline: ...

    async def get_timeline_contact(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        log_id: int,
        subject: str = "operator",
    ) -> TimelineContact: ...

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
    ) -> PurchaseRecordPage: ...

    async def recommend_products(
        self,
        *,
        identity: PlatformIdentity,
        device_name: str,
        device_profession: str | None = None,
        keyword: str | None = None,
        limit: int = 3,
    ) -> ProductRecommendations: ...

    async def recommend_purchase_history(
        self, *, identity: PlatformIdentity, requirement_id: int, limit: int = 10
    ) -> PurchaseHistoryRecommendations: ...

    async def list_handler_candidates(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        target_role: RoleCode,
    ) -> HandlerCandidates: ...

    async def submit_review(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult: ...

    async def resubmit_review(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult: ...

    async def update_review_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: ReviewFieldsPatch,
    ) -> FieldsSaveResult: ...

    async def reject_requirement(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        reason: str,
        action_token: UUID,
    ) -> RequirementTransitionResult: ...

    async def submit_purchaser(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult: ...

    async def start_purchase(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        action_token: UUID,
    ) -> RequirementTransitionResult: ...

    async def search_suppliers(
        self,
        *,
        identity: PlatformIdentity,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
    ) -> SupplierPage: ...

    async def recommend_suppliers(
        self, *, identity: PlatformIdentity, requirement_id: int, limit: int = 3
    ) -> SupplierRecommendations: ...

    async def get_supplier(
        self,
        *,
        identity: PlatformIdentity,
        supplier_id: int,
    ) -> SupplierDetail: ...

    async def create_supplier(
        self,
        *,
        identity: PlatformIdentity,
        command: SupplierUpsertCommand,
    ) -> SupplierSummary: ...

    async def update_purchase_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: PurchaseFieldsPatch,
    ) -> FieldsSaveResult: ...

    async def submit_warehouse(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int | None,
        action_token: UUID,
    ) -> RequirementTransitionResult: ...

    async def update_warehouse_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: WarehouseFieldsPatch,
    ) -> FieldsSaveResult: ...

    async def complete_requirement(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        action_token: UUID,
    ) -> RequirementCompletionResult: ...

    async def get_or_create_agent_conversation(
        self, *, identity: PlatformIdentity, current_action: str
    ) -> AgentConversation: ...

    async def append_agent_message(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        sender_type: AgentMessageSender,
        content: str,
    ) -> AgentMessageWriteResult: ...

    async def list_agent_messages(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> AgentMessagePage: ...

    async def get_agent_message_by_external_id(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
    ) -> AgentMessage | None: ...

    async def get_agent_state(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> AgentSessionState: ...

    async def update_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        state: AgentSessionStateUpdate,
    ) -> AgentStateSaveResult: ...

    async def snapshot_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        snapshot_reason: str,
    ) -> AgentSessionSnapshot: ...

    async def complete_agent_conversation(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        purchase_request_id: int | None,
    ) -> AgentConversationCompletion: ...

    async def aclose(self) -> None: ...
