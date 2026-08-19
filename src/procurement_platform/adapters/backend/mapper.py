from decimal import Decimal

from procurement_platform.adapters.backend.dto import (
    BackendAgentConversationDTO,
    BackendAgentMessageDTO,
    BackendAgentMessagePageDTO,
    BackendAgentSessionStateDTO,
    BackendAgentStateSaveDTO,
    BackendAllowedRequirementAction,
    BackendAssetContextDTO,
    BackendAssetDTO,
    BackendAssetPageDTO,
    BackendCreatedRequirementDTO,
    BackendCurrentUserDTO,
    BackendEquipmentCategoryDTO,
    BackendEquipmentModelDTO,
    BackendEquipmentModelPageDTO,
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
from procurement_platform.domain.assets import (
    AssetComponent,
    AssetContext,
    AssetPage,
    AssetRelation,
    AssetSummary,
    BuildingSummary,
    EquipmentCategorySummary,
    EquipmentModelPage,
    EquipmentModelSummary,
    RelatedAsset,
)
from procurement_platform.domain.assistant_session import (
    AgentConversation,
    AgentMessage,
    AgentMessagePage,
    AgentSessionState,
    AgentStateSaveResult,
)
from procurement_platform.domain.enums import AgentMessageSender, AllowedRequirementAction
from procurement_platform.domain.requirement import (
    ApplicantFields,
    FieldsSaveResult,
    HandlerCandidate,
    HandlerCandidates,
    ProductRecommendation,
    ProductRecommendations,
    PurchaseExecutionView,
    PurchaseFields,
    PurchaseHistoryItem,
    PurchaseHistoryRecommendations,
    PurchaseRecord,
    PurchaseRecordPage,
    PurchaseRequestItem,
    PurchaseReviewItem,
    RequirementBuilding,
    RequirementCompletionResult,
    RequirementDetail,
    RequirementFulfillmentSummary,
    RequirementHandler,
    RequirementListItem,
    RequirementPage,
    RequirementSummary,
    RequirementTimeline,
    RequirementTransitionResult,
    ReviewFields,
    ReviewRecordSummary,
    SupplierBlacklistSummary,
    SupplierDetail,
    SupplierPage,
    SupplierRecommendation,
    SupplierRecommendations,
    SupplierSummary,
    TimelineContact,
    TimelineItem,
    WarehouseFields,
    WarehouseReceiptView,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def map_current_user(dto: BackendCurrentUserDTO) -> CurrentUser:
    return CurrentUser(
        employee_id=dto.employee_id,
        name=dto.name,
        mobile=dto.mobile,
        status=dto.status,
        roles=tuple(
            UserRole(role_code=role.role_code, role_name=role.role_name) for role in dto.roles
        ),
        buildings=tuple(
            UserBuilding(
                building_id=building.building_id,
                building_name=building.building_name,
                is_primary=building.is_primary,
            )
            for building in dto.buildings
        ),
    )


def map_agent_conversation(
    dto: BackendAgentConversationDTO, *, current_action: str
) -> AgentConversation:
    return AgentConversation(
        conversation_id=dto.conversation_id,
        current_action=current_action,
        status=dto.status,
    )


def map_agent_message_page(
    dto: BackendAgentMessagePageDTO, *, conversation_id: int
) -> AgentMessagePage:
    """Map backend list items and restore their path-scoped conversation id."""

    return AgentMessagePage(
        items=tuple(
            AgentMessage(
                message_id=item.message_id,
                conversation_id=conversation_id,
                external_message_id=item.external_message_id,
                sender_type=AgentMessageSender(item.sender_type),
                content=item.content,
                created_at=item.created_at,
            )
            for item in dto.items
        ),
        page=dto.page,
        page_size=dto.page_size,
        total=dto.total,
    )


def map_agent_message(dto: BackendAgentMessageDTO, *, conversation_id: int) -> AgentMessage:
    return AgentMessage(
        message_id=dto.message_id,
        conversation_id=conversation_id,
        external_message_id=dto.external_message_id,
        sender_type=AgentMessageSender(dto.sender_type),
        content=dto.content,
        created_at=dto.created_at,
    )


def map_agent_session_state(dto: BackendAgentSessionStateDTO) -> AgentSessionState:
    return AgentSessionState.model_validate(dto.model_dump(mode="python"))


def map_agent_state_save(dto: BackendAgentStateSaveDTO) -> AgentStateSaveResult:
    return AgentStateSaveResult(
        saved=dto.saved,
        expires_in_seconds=dto.expires_in_seconds,
    )


def map_created_requirement(dto: BackendCreatedRequirementDTO) -> RequirementSummary:
    return RequirementSummary(
        requirement_id=dto.requirement_id,
        requirement_no=dto.requirement_no,
        status=dto.status,
        version=dto.version,
    )


def map_requirement_detail(dto: BackendRequirementDetailDTO) -> RequirementDetail:
    latest_review = dto.review_records[-1] if dto.review_records else None
    purchase = dto.purchase_execution
    receipt = dto.warehouse_receipt
    return RequirementDetail(
        requirement_id=dto.requirement_id,
        requirement_no=dto.requirement_no,
        status=dto.status,
        version=dto.version,
        building=RequirementBuilding(
            building_id=dto.building.building_id,
            building_name=dto.building.building_name,
        ),
        current_handler=(
            RequirementHandler(
                employee_id=dto.current_handler.employee_id,
                name=dto.current_handler.name,
            )
            if dto.current_handler is not None
            else None
        ),
        applicant_fields=ApplicantFields(**dto.applicant_fields.model_dump(mode="json")),
        review_fields=(
            ReviewFields(
                proposed_supplier_id=latest_review.proposed_supplier_id,
                proposed_supplier_name=latest_review.proposed_supplier_name,
                supplier_contact_name=latest_review.supplier_contact_name,
                supplier_contact_info=latest_review.supplier_contact_info,
                supplier_link=latest_review.supplier_link,
                estimated_unit_price=_decimal_string(latest_review.estimated_unit_price),
                estimated_total_price=_decimal_string(latest_review.estimated_total_price),
                need_contract=latest_review.need_contract,
                contract_type=latest_review.contract_type,
                payment_method=latest_review.payment_method,
                expected_arrival_date=latest_review.expected_arrival_date,
                warranty_info=latest_review.warranty_info,
                review_remark=latest_review.review_remark,
            )
            if latest_review is not None
            else None
        ),
        review_record=(
            ReviewRecordSummary(review_status=latest_review.review_status)
            if latest_review is not None
            else None
        ),
        purchase_fields=(
            PurchaseFields(
                supplier_id=purchase.supplier_id,
                supplier_name=purchase.supplier_name,
                supplier_tax_number=purchase.supplier_tax_number,
                bank_name=purchase.bank_name,
                bank_account=purchase.bank_account,
                registered_address=purchase.registered_address,
                contract_contact_info=purchase.contract_contact_info,
                actual_unit_price=_decimal_string(purchase.actual_unit_price),
                actual_total_price=_decimal_string(purchase.actual_total_price),
                tax_rate=_decimal_string(purchase.tax_rate),
                purchased_at=purchase.purchased_at,
                purchase_remark=purchase.purchase_remark,
            )
            if purchase is not None
            else None
        ),
        warehouse_fields=(
            WarehouseFields(
                warehouse_location=receipt.warehouse_location,
                received_quantity=_decimal_string(receipt.received_quantity),
                receipt_remark=receipt.receipt_remark,
            )
            if receipt is not None
            else None
        ),
        missing_fields=dto.missing_fields,
        allowed_actions=tuple(_map_allowed_action(action) for action in dto.allowed_actions),
        fields_complete=not dto.missing_fields,
        rejection_reason=(
            latest_review.review_opinion
            if latest_review is not None and latest_review.review_result == "REJECTED"
            else None
        ),
        completed_at=(
            receipt.received_at if dto.status.value == "COMPLETED" and receipt is not None else None
        ),
        request_type=dto.request_type,
        source_asset=dto.source_asset,
        items=tuple(
            PurchaseRequestItem(
                request_item_id=item.request_item_id,
                item_no=item.item_no,
                item_kind=item.item_kind,
                equipment_category_id=item.equipment_category_id,
                equipment_model_id=item.equipment_model_id,
                item_name=item.item_name,
                brand_snapshot=item.brand_snapshot,
                model_snapshot=item.model_snapshot,
                quantity=str(item.quantity),
                unit=item.unit,
                requires_warehouse=item.requires_warehouse,
                item_reason=item.item_reason,
                is_active=item.is_active,
                remark=item.remark,
                fulfillment_status=item.fulfillment_status,
            )
            for item in dto.items
        ),
        review_items=tuple(
            PurchaseReviewItem(
                review_item_id=item.review_item_id,
                request_item_id=item.request_item_id,
                item_kind_snapshot=item.item_kind_snapshot,
                item_name_snapshot=item.item_name_snapshot,
                quantity_snapshot=str(item.quantity_snapshot),
                unit_snapshot=item.unit_snapshot,
                proposed_supplier_id=item.proposed_supplier_id,
                proposed_supplier_name=item.proposed_supplier_name,
                estimated_unit_price=_decimal_string(item.estimated_unit_price),
                estimated_total_price=_decimal_string(item.estimated_total_price),
            )
            for review in dto.review_records
            for item in review.items
        ),
        executions=tuple(
            PurchaseExecutionView(
                execution_id=item.execution_id,
                request_item_id=item.request_item_id,
                supplier_id=item.supplier_id,
                supplier_name=item.supplier_name,
                purchased_quantity=str(item.purchased_quantity),
                actual_unit_price=str(item.actual_unit_price),
                actual_total_price=str(item.actual_total_price),
                tax_rate=_decimal_string(item.tax_rate),
                purchased_at=item.purchased_at,
                purchase_remark=item.purchase_remark,
            )
            for item in dto.executions
        ),
        receipts=tuple(
            WarehouseReceiptView(
                receipt_id=item.receipt_id,
                execution_id=item.execution_id,
                warehouse_location=item.warehouse_location,
                received_quantity=str(item.received_quantity),
                receipt_remark=item.receipt_remark,
                received_at=item.received_at,
            )
            for item in dto.receipts
        ),
        request_fulfillment=RequirementFulfillmentSummary(
            active_item_count=dto.request_fulfillment.active_item_count,
            fulfilled_item_count=dto.request_fulfillment.fulfilled_item_count,
            all_active_items_fulfilled=dto.request_fulfillment.all_active_items_fulfilled,
        ),
    )


def _decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def map_requirement_page(dto: BackendRequirementPageDTO) -> RequirementPage:
    return RequirementPage(
        items=tuple(
            RequirementListItem(
                requirement_id=item.requirement_id,
                requirement_no=item.requirement_no,
                device_name=item.device_name,
                status=item.status,
                current_handler_name=item.current_handler_name,
            )
            for item in dto.items
        ),
        page=dto.page,
        page_size=dto.page_size,
        total=dto.total,
    )


def map_requirement_timeline(dto: BackendTimelineDTO) -> RequirementTimeline:
    return RequirementTimeline(
        items=tuple(
            TimelineItem(
                log_id=item.log_id,
                action_type=item.action_type,
                operator_name=item.operator_name,
                operator_role_name=item.operator_role_name,
                operator_mobile_masked=item.operator_mobile_masked,
                from_status=item.from_status,
                to_status=item.to_status,
                assigned_to_employee_id=item.assigned_to_employee_id,
                assigned_to_name=item.assigned_to_name,
                assigned_to_mobile_masked=item.assigned_to_mobile_masked,
                operation_summary=item.operation_summary,
                operated_at=item.operated_at,
            )
            for item in dto.items
        )
    )


def map_timeline_contact(dto: BackendTimelineContactDTO) -> TimelineContact:
    return TimelineContact(employee_name=dto.employee_name, mobile=dto.mobile)


def map_purchase_record_page(dto: BackendPurchaseRecordPageDTO) -> PurchaseRecordPage:
    return PurchaseRecordPage(
        items=tuple(
            PurchaseRecord(
                requirement_id=item.requirement_id,
                requirement_no=item.requirement_no,
                building_id=item.building_id,
                device_profession=item.device_profession,
                device_name=item.device_name,
                brand=item.brand,
                model=item.model,
                quantity=_decimal_string(item.quantity),
                unit=item.unit,
                status=item.status,
                supplier_id=item.supplier_id,
                supplier_name=item.supplier_name,
                actual_total_price=_decimal_string(item.actual_total_price),
                purchased_at=item.purchased_at,
                created_at=item.created_at,
                submitted_at=item.submitted_at,
                reviewed_at=item.reviewed_at,
                received_at=item.received_at,
                completed_at=item.completed_at,
            )
            for item in dto.items
        ),
        page=dto.page,
        page_size=dto.page_size,
        total=dto.total,
    )


def map_product_recommendations(
    dto: BackendProductRecommendationsDTO,
) -> ProductRecommendations:
    return ProductRecommendations(
        items=tuple(
            ProductRecommendation(
                product_id=item.product_id,
                brand=item.brand,
                model=item.model,
                historical_count=item.historical_count,
                last_purchased_at=item.last_purchased_at,
            )
            for item in dto.items
        )
    )


def map_purchase_history_recommendations(
    dto: BackendPurchaseHistoryRecommendationsDTO,
) -> PurchaseHistoryRecommendations:
    return PurchaseHistoryRecommendations(
        items=tuple(
            PurchaseHistoryItem(
                requirement_id=item.requirement_id,
                device_name=item.device_name,
                brand=item.brand,
                model=item.model,
                quantity=str(item.quantity),
                supplier_id=item.supplier_id,
                supplier_name=item.supplier_name,
                actual_total_price=str(item.actual_total_price),
                purchased_at=item.purchased_at,
                blacklist_status=item.blacklist_status,
            )
            for item in dto.items
        )
    )


def map_handler_candidates(dto: BackendHandlerCandidatesDTO) -> HandlerCandidates:
    return HandlerCandidates(
        items=tuple(
            HandlerCandidate(employee_id=item.employee_id, name=item.name) for item in dto.items
        ),
        auto_selected_employee_id=dto.auto_selected_employee_id,
    )


def map_fields_save(dto: BackendFieldsSaveDTO) -> FieldsSaveResult:
    return FieldsSaveResult(
        requirement_id=dto.requirement_id,
        status=dto.status,
        version=dto.version,
        missing_fields=dto.missing_fields,
        next_missing_field=dto.next_missing_field,
        fields_complete=dto.fields_complete,
    )


def map_supplier_page(dto: BackendSupplierPageDTO) -> SupplierPage:
    return SupplierPage(
        items=tuple(
            SupplierSummary(
                supplier_id=item.supplier_id,
                supplier_name=item.supplier_name,
                supplier_tax_number=item.unified_social_credit_code,
                blacklist=SupplierBlacklistSummary(active=item.blacklist_status == "ACTIVE"),
            )
            for item in dto.items
        ),
        page=dto.page,
        page_size=dto.page_size,
        total=dto.total,
    )


def map_supplier_recommendations(
    dto: BackendSupplierRecommendationsDTO,
) -> SupplierRecommendations:
    return SupplierRecommendations(
        items=tuple(
            SupplierRecommendation(
                supplier_id=item.supplier_id,
                supplier_name=item.supplier_name,
                historical_purchase_count=item.historical_purchase_count,
                last_purchase_at=item.last_purchase_at,
                blacklist_status=item.blacklist_status,
            )
            for item in dto.items
        )
    )


def map_supplier_detail(dto: BackendSupplierDetailDTO) -> SupplierDetail:
    return SupplierDetail(
        supplier_id=dto.supplier_id,
        supplier_name=dto.supplier_name,
        supplier_tax_number=dto.unified_social_credit_code,
        blacklist=SupplierBlacklistSummary(active=dto.blacklist.status == "ACTIVE"),
        bank_name=dto.bank_name,
        bank_account=dto.bank_account,
        bank_account_masked=bool(dto.bank_account and "*" in dto.bank_account),
        registered_address=dto.registered_address,
        contract_contact_info=dto.contract_contact_info,
    )


def map_supplier_created(dto: BackendSupplierCreatedDTO) -> SupplierSummary:
    return SupplierSummary(
        supplier_id=dto.supplier_id,
        supplier_name=dto.supplier_name,
    )


def map_requirement_transition(
    dto: BackendRequirementMutationDTO,
) -> RequirementTransitionResult:
    return RequirementTransitionResult(
        requirement_id=dto.requirement_id,
        requirement_no=dto.requirement_no or str(dto.requirement_id),
        status=dto.status,
        version=dto.version,
        current_handler=(
            RequirementHandler(
                employee_id=dto.current_handler.employee_id,
                name=dto.current_handler.name,
            )
            if dto.current_handler is not None
            else None
        ),
        action_token=dto.action_token,
    )


def map_requirement_completion(
    dto: BackendRequirementMutationDTO,
) -> RequirementCompletionResult:
    if dto.completed_at is None:
        raise ValueError("completed mutation response requires completed_at")
    return RequirementCompletionResult(
        requirement_id=dto.requirement_id,
        requirement_no=dto.requirement_no or str(dto.requirement_id),
        status=dto.status,
        version=dto.version,
        current_handler=(
            RequirementHandler(
                employee_id=dto.current_handler.employee_id,
                name=dto.current_handler.name,
            )
            if dto.current_handler is not None
            else None
        ),
        completed_at=dto.completed_at,
        action_token=dto.action_token,
    )


def _map_allowed_action(
    action: BackendAllowedRequirementAction,
) -> AllowedRequirementAction:
    aliases = {
        BackendAllowedRequirementAction.SAVE_APPLICANT_FIELDS: (
            AllowedRequirementAction.UPDATE_APPLICANT_FIELDS
        ),
        BackendAllowedRequirementAction.SAVE_REVIEW_FIELDS: (
            AllowedRequirementAction.UPDATE_REVIEW_FIELDS
        ),
        BackendAllowedRequirementAction.SAVE_PURCHASE_FIELDS: (
            AllowedRequirementAction.UPDATE_PURCHASE_FIELDS
        ),
        BackendAllowedRequirementAction.SAVE_WAREHOUSE_FIELDS: (
            AllowedRequirementAction.UPDATE_WAREHOUSE_FIELDS
        ),
    }
    if action in aliases:
        return aliases[action]
    return AllowedRequirementAction(action.value)


def map_equipment_category(dto: BackendEquipmentCategoryDTO) -> EquipmentCategorySummary:
    return EquipmentCategorySummary.model_validate(dto.model_dump())


def map_equipment_model(dto: BackendEquipmentModelDTO) -> EquipmentModelSummary:
    return EquipmentModelSummary.model_validate(dto.model_dump())


def map_asset(dto: BackendAssetDTO) -> AssetSummary:
    return AssetSummary(
        **dto.model_dump(exclude={"category", "model", "building", "aliases"}),
        aliases=dto.aliases or (),
        category=map_equipment_category(dto.category),
        model=map_equipment_model(dto.model) if dto.model is not None else None,
        building=BuildingSummary.model_validate(dto.building.model_dump()),
    )


def map_asset_page(dto: BackendAssetPageDTO) -> AssetPage:
    return AssetPage(
        items=tuple(map_asset(item) for item in dto.items),
        page=dto.page,
        page_size=dto.page_size,
        total=dto.total,
    )


def map_equipment_model_page(dto: BackendEquipmentModelPageDTO) -> EquipmentModelPage:
    return EquipmentModelPage(
        items=tuple(map_equipment_model(item) for item in dto.items),
        page=dto.page,
        page_size=dto.page_size,
        total=dto.total,
    )


def map_asset_context(dto: BackendAssetContextDTO) -> AssetContext:
    return AssetContext(
        asset=map_asset(dto.asset),
        components=tuple(
            AssetComponent.model_validate(item.model_dump()) for item in dto.components
        ),
        relations=tuple(
            AssetRelation(
                **item.model_dump(exclude={"related_asset"}),
                related_asset=RelatedAsset.model_validate(item.related_asset.model_dump()),
            )
            for item in dto.relations
        ),
        redundancy_peers=tuple(map_asset(item) for item in dto.redundancy_peers),
    )
