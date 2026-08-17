"""Purchaser tools for the optional conversational assistant."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from procurement_platform.application.assistant.candidate_resolver import CandidateResolver
from procurement_platform.application.assistant.exact_field_renderer import ExactFieldRenderer
from procurement_platform.application.assistant.tooling.common import (
    DraftUpdateResultBase,
    SessionReferenceStore,
    StrictArgs,
    _active_user,
    _identity,
    _is_handler,
)
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.assistant_session import (
    JsonValue,
    RecommendationReference,
)
from procurement_platform.domain.enums import (
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.errors import (
    BackendProtocolError,
    BackendTimeoutError,
    BackendUnavailableError,
    ConcurrentModificationError,
    SessionNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import (
    ActionButton,
    InteractionView,
    KeyValueField,
    KeyValueSection,
)
from procurement_platform.domain.notification import (
    InteractionNotification,
    NotificationGatewayRequest,
)
from procurement_platform.domain.requirement import (
    PurchaseFields,
    PurchaseFieldsPatch,
    PurchaseRecord,
    RequirementDetail,
    SupplierDetail,
)
from procurement_platform.domain.user import CurrentUser
from procurement_platform.ports.backend_client import BackendClient

SupplierProfileField = Literal[
    "UNIFIED_SOCIAL_CREDIT_CODE",
    "BANK_NAME",
    "BANK_ACCOUNT",
    "REGISTERED_ADDRESS",
    "CONTRACT_CONTACT_INFO",
]


class QuerySupplierProfileArgs(StrictArgs):
    supplier_query: str | None = Field(default=None, max_length=200)
    supplier_ref: str | None = Field(default=None, max_length=200)
    requirement_id: int | None = Field(default=None, gt=0)
    requested_fields: tuple[SupplierProfileField, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_source(self) -> "QuerySupplierProfileArgs":
        if self.requirement_id is None and not self.supplier_ref and not self.supplier_query:
            raise ValueError("supplier source is required")
        return self


class SupplierProfileCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_ref: str
    supplier_id: int
    supplier_name: str


class QuerySupplierProfileResult(AssistantToolResult):
    supplier_id: int | None = None
    supplier_name: str | None = None
    candidates: tuple[SupplierProfileCandidate, ...] = ()
    rendered_text: str | None = None


class QuerySupplierProfileTool:
    name = "query_supplier_profile"
    side_effect = "READ"
    description = (
        "Precisely query selected supplier master fields; exact values are rendered "
        "deterministically."
    )
    args_model = QuerySupplierProfileArgs

    _LABELS: ClassVar[dict[str, str]] = {
        "UNIFIED_SOCIAL_CREDIT_CODE": "统一社会信用代码",
        "BANK_NAME": "开户行",
        "BANK_ACCOUNT": "银行账号",
        "REGISTERED_ADDRESS": "注册地址",
        "CONTRACT_CONTACT_INFO": "合同联系方式",
    }

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: QuerySupplierProfileArgs, context: AssistantToolContext
    ) -> QuerySupplierProfileResult:
        identity = _identity(context)
        user = await self._backend.get_current_user(identity=identity)
        resolved = (
            (identity, user)
            if user.status == "ACTIVE"
            and {
                RoleCode.PURCHASER,
                RoleCode.BUILDING_MANAGER,
            }.intersection(role.role_code for role in user.roles)
            else None
        )
        if resolved is None:
            return QuerySupplierProfileResult(
                status="PERMISSION_DENIED", user_message="当前用户不是有效采购员"
            )
        identity, _ = resolved
        try:
            supplier_id: int | None = None
            requirement_id = args.requirement_id
            if args.supplier_query:
                page = await self._backend.search_suppliers(
                    identity=identity, keyword=args.supplier_query, page_size=20
                )
                if not page.items:
                    return QuerySupplierProfileResult(
                        status="NOT_FOUND", user_message="未找到供应商"
                    )
                exact = tuple(
                    item
                    for item in page.items
                    if item.supplier_name.strip() == args.supplier_query.strip()
                )
                if len(exact) == 1:
                    supplier_id = exact[0].supplier_id
                elif len(page.items) > 1:
                    candidates = tuple(
                        SupplierProfileCandidate(
                            candidate_ref=f"supplier:{item.supplier_id}",
                            supplier_id=item.supplier_id,
                            supplier_name=item.supplier_name,
                        )
                        for item in page.items
                    )
                    candidate_set = await self._session.save(
                        identity=identity,
                        context=context,
                        requirement_id=requirement_id,
                        references=tuple(
                            RecommendationReference(
                                reference_id=item.candidate_ref,
                                kind="SUPPLIER_PROFILE",
                                label=item.supplier_name,
                            )
                            for item in candidates
                        ),
                        focused_role=RoleCode.PURCHASER,
                        awaiting_confirmation=True,
                    )
                    return QuerySupplierProfileResult(
                        status="MULTIPLE_MATCHES",
                        candidate_set_id=candidate_set,
                        candidates=candidates,
                    )
                else:
                    supplier_id = page.items[0].supplier_id
            elif args.supplier_ref:
                state = await self._session.state(identity, context.conversation_id)
                supplier_id = CandidateResolver.resolve(
                    args.supplier_ref, kind="SUPPLIER_PROFILE", state=state
                )
            else:
                requirement_id = requirement_id or context.active_requirement_id
            if supplier_id is not None:
                pass
            elif requirement_id:
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=requirement_id
                )
                selected = await _selected_supplier(self._backend, identity, detail)
                if selected is None:
                    return QuerySupplierProfileResult(
                        status="NOT_FOUND",
                        user_message="当前采购单没有可确认的供应商记录",
                    )
                supplier_id = selected.supplier_id
            assert supplier_id is not None
            supplier = await self._backend.get_supplier(identity=identity, supplier_id=supplier_id)
            values = self._values(supplier)
            rendered = ExactFieldRenderer.render(
                supplier_name=supplier.supplier_name,
                fields=tuple((self._LABELS[name], values[name]) for name in args.requested_fields),
            )
            return QuerySupplierProfileResult(
                status="SUCCESS",
                supplier_id=supplier.supplier_id,
                supplier_name=supplier.supplier_name,
                exact_render_required=True,
                rendered_text=rendered,
                user_message=rendered,
            )
        except ValueError as exc:
            return QuerySupplierProfileResult(status="INVALID_ARGUMENTS", user_message=str(exc))

    @staticmethod
    def _values(supplier: SupplierDetail) -> dict[str, str | None]:
        return {
            "UNIFIED_SOCIAL_CREDIT_CODE": supplier.supplier_tax_number,
            "BANK_NAME": supplier.bank_name,
            "BANK_ACCOUNT": supplier.bank_account,
            "REGISTERED_ADDRESS": supplier.registered_address,
            "CONTRACT_CONTACT_INFO": supplier.contract_contact_info,
        }


class PreparePurchasePrefillArgs(StrictArgs):
    requirement_id: int = Field(gt=0)


class PurchasePrefillField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field_name: str
    value: str | None
    resolution: Literal["EXACT", "RECOMMENDED", "AMBIGUOUS", "MISSING"]
    source: Literal["REQUIREMENT", "SUPPLIER_MASTER", "PURCHASE_HISTORY"]
    evidence_count: int = 0
    alternatives: tuple[str, ...] = ()


class PreparePurchasePrefillResult(AssistantToolResult):
    supplier_id: int | None = None
    supplier_name: str | None = None
    fields: tuple[PurchasePrefillField, ...] = ()


class PurchasePrefillService:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def prepare(
        self, *, identity: PlatformIdentity, user: CurrentUser, requirement_id: int
    ) -> PreparePurchasePrefillResult:
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        if detail.status not in {RequirementStatus.PENDING_PURCHASE, RequirementStatus.PURCHASING}:
            return PreparePurchasePrefillResult(
                status="INVALID_STATUS", user_message="当前状态不能生成采购预填"
            )
        if not _is_handler(detail, user):
            return PreparePurchasePrefillResult(
                status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
            )
        supplier_id = detail.review_fields.proposed_supplier_id if detail.review_fields else None
        if supplier_id is None:
            return PreparePurchasePrefillResult(
                status="NOT_FOUND", user_message="楼长尚未确定供应商"
            )
        supplier = await self._backend.get_supplier(identity=identity, supplier_id=supplier_id)
        history = await self._backend.recommend_purchase_history(
            identity=identity, requirement_id=requirement_id, limit=10
        )
        snapshots: list[PurchaseFields] = []
        for item in history.items[:10]:
            historical = await self._backend.get_requirement(
                identity=identity, requirement_id=item.requirement_id
            )
            if historical.purchase_fields:
                snapshots.append(historical.purchase_fields)
        master = {
            "supplier_name": supplier.supplier_name,
            "supplier_tax_number": supplier.supplier_tax_number,
            "bank_name": supplier.bank_name,
            "bank_account": supplier.bank_account,
            "registered_address": supplier.registered_address,
            "contract_contact_info": supplier.contract_contact_info,
        }
        fields = [self._field(name, value, snapshots) for name, value in master.items()]
        fields.append(self._history_field("tax_rate", snapshots))
        return PreparePurchasePrefillResult(
            status="SUCCESS",
            requirement_id=requirement_id,
            requirement_version=detail.version,
            supplier_id=supplier.supplier_id,
            supplier_name=supplier.supplier_name,
            fields=tuple(fields),
        )

    def _field(
        self, name: str, master_value: str | None, snapshots: list[PurchaseFields]
    ) -> PurchasePrefillField:
        if master_value:
            return PurchasePrefillField(
                field_name=name, value=master_value, resolution="EXACT", source="SUPPLIER_MASTER"
            )
        return self._history_field(name, snapshots)

    @staticmethod
    def _history_field(name: str, snapshots: list[PurchaseFields]) -> PurchasePrefillField:
        values = tuple(
            dict.fromkeys(
                str(value)
                for item in snapshots
                if (value := getattr(item, name, None)) not in {None, ""}
            )
        )
        if len(values) == 1:
            return PurchasePrefillField(
                field_name=name,
                value=values[0],
                resolution="RECOMMENDED",
                source="PURCHASE_HISTORY",
                evidence_count=sum(
                    1 for item in snapshots if getattr(item, name, None) not in {None, ""}
                ),
            )
        if len(values) > 1:
            return PurchasePrefillField(
                field_name=name,
                value=None,
                resolution="AMBIGUOUS",
                source="PURCHASE_HISTORY",
                evidence_count=len(snapshots),
                alternatives=values,
            )
        return PurchasePrefillField(
            field_name=name, value=None, resolution="MISSING", source="PURCHASE_HISTORY"
        )


class PurchasePrefillNotificationService:
    """Build optional purchaser prefill content outside the notification gateway."""

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._prefill = PurchasePrefillService(backend)

    async def render(self, request: NotificationGatewayRequest) -> InteractionNotification | None:
        requirement_id = request.payload.get("requirement_id")
        if not isinstance(requirement_id, int):
            return None
        identity = PlatformIdentity.create(PlatformType.FEISHU, request.receiver_platform_user_id)
        user = await self._backend.get_current_user(identity=identity)
        result = await self._prefill.prepare(
            identity=identity, user=user, requirement_id=requirement_id
        )
        if result.status != "SUCCESS":
            return None
        return InteractionNotification(
            view=InteractionView(
                title="采购员预填推荐",
                subtitle="仅展示建议, 请打开正式卡片确认",
                elements=(
                    KeyValueSection(
                        fields=tuple(
                            KeyValueField(
                                label=item.field_name,
                                value=item.value
                                if item.value is not None
                                else "/".join(item.alternatives) or "待补充",
                            )
                            for item in result.fields
                        )
                    ),
                ),
                actions=(
                    ActionButton(
                        action_id="purchaser.open_requirement",
                        label="打开采购卡片",
                        value={"requirement_id": requirement_id},
                        style="primary",
                    ),
                ),
            )
        )


class PreparePurchasePrefillTool:
    name = "prepare_purchase_prefill"
    side_effect = "READ"
    description = "Prepare purchaser fields using the supplier selected by the building manager."
    args_model = PreparePurchasePrefillArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._service = PurchasePrefillService(backend)

    async def execute(
        self, *, args: PreparePurchasePrefillArgs, context: AssistantToolContext
    ) -> PreparePurchasePrefillResult:
        resolved = await _active_user(self._backend, context, RoleCode.PURCHASER)
        if resolved is None:
            return PreparePurchasePrefillResult(
                status="PERMISSION_DENIED", user_message="当前用户不是有效采购员"
            )
        identity, user = resolved
        try:
            return await self._service.prepare(
                identity=identity, user=user, requirement_id=args.requirement_id
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return PreparePurchasePrefillResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )


class FillSelectedSupplierProfileArgs(StrictArgs):
    requirement_id: int = Field(gt=0)


class FillSelectedSupplierProfileResult(AssistantToolResult):
    supplier_name: str | None = None
    next_missing_field: Literal["actual_unit_price"] | None = None
    updated_fields: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    fields_complete: bool = False


class FillSelectedSupplierProfileTool:
    """Resolve supplier facts deterministically before a complete purchase save."""

    name = "fill_selected_supplier_profile"
    side_effect = "MUTATE"
    description = (
        "Use the supplier selected on the current requirement and re-read its master data. "
        "Use this when the user asks to fill/carry/copy that supplier's information into "
        "the purchase form. Never copy supplier values from chat history."
    )
    args_model = FillSelectedSupplierProfileArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: FillSelectedSupplierProfileArgs, context: AssistantToolContext
    ) -> FillSelectedSupplierProfileResult:
        resolved = await _active_user(self._backend, context, RoleCode.PURCHASER)
        if resolved is None:
            return FillSelectedSupplierProfileResult(
                status="PERMISSION_DENIED", user_message="当前用户不是有效采购员"
            )
        identity, user = resolved
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=args.requirement_id
        )
        if detail.status is not RequirementStatus.PURCHASING:
            return FillSelectedSupplierProfileResult(
                status="INVALID_STATUS", user_message="只有采购中状态可以填写采购执行信息"
            )
        if not _is_handler(detail, user):
            return FillSelectedSupplierProfileResult(
                status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
            )
        supplier = await _selected_supplier(self._backend, identity, detail)
        if supplier is None:
            return FillSelectedSupplierProfileResult(
                status="NOT_FOUND", user_message="当前采购单没有可确认的供应商记录"
            )
        exact_fields = {
            "supplier_id": supplier.supplier_id,
            "supplier_tax_number": supplier.supplier_tax_number,
            "bank_name": supplier.bank_name,
            "bank_account": supplier.bank_account,
            "registered_address": supplier.registered_address,
            "contract_contact_info": supplier.contract_contact_info,
        }
        saved = await self._backend.update_purchase_fields(
            identity=identity,
            requirement_id=args.requirement_id,
            expected_version=detail.version,
            fields=PurchaseFieldsPatch.model_validate(exact_fields),
        )
        next_missing_field: Literal["actual_unit_price"] | None = (
            "actual_unit_price" if "actual_unit_price" in saved.missing_fields else None
        )
        await self._session.save(
            identity=identity,
            context=context,
            requirement_id=args.requirement_id,
            focused_role=RoleCode.PURCHASER,
            focused_field=next_missing_field,
            pending_field=next_missing_field,
        )
        return FillSelectedSupplierProfileResult(
            status="SUCCESS",
            requirement_id=args.requirement_id,
            requirement_version=saved.version,
            supplier_name=supplier.supplier_name,
            next_missing_field=next_missing_field,
            updated_fields=tuple(exact_fields),
            missing_fields=saved.missing_fields,
            fields_complete=saved.fields_complete,
            user_message=f"已将{supplier.supplier_name}的最新主数据保存到采购单。",
        )


class UpdatePurchaseExecutionDraftArgs(StrictArgs):
    requirement_id: int = Field(gt=0)
    actual_unit_price: str | None = None
    tax_rate: str | None = None
    purchased_at: datetime | None = None
    purchase_remark: str | None = None
    update_supplier_profile: bool = False


class UpdatePurchaseExecutionDraftResult(DraftUpdateResultBase):
    actual_total_price: str | None = None


class UpdatePurchaseExecutionDraftTool:
    name = "update_purchase_execution_draft"
    side_effect = "MUTATE"
    description = (
        "Save purchaser execution draft fields without starting or submitting procurement."
    )
    args_model = UpdatePurchaseExecutionDraftArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: UpdatePurchaseExecutionDraftArgs, context: AssistantToolContext
    ) -> UpdatePurchaseExecutionDraftResult:
        resolved = await _active_user(self._backend, context, RoleCode.PURCHASER)
        if resolved is None:
            return UpdatePurchaseExecutionDraftResult(
                status="PERMISSION_DENIED", user_message="当前用户不是有效采购员"
            )
        identity, user = resolved
        try:
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            if detail.status is not RequirementStatus.PURCHASING:
                return UpdatePurchaseExecutionDraftResult(
                    status="INVALID_STATUS", user_message="只有采购中状态可以保存执行草稿"
                )
            if not _is_handler(detail, user):
                return UpdatePurchaseExecutionDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
                )
            supplier = await _selected_supplier(self._backend, identity, detail)
            if supplier is None:
                return UpdatePurchaseExecutionDraftResult(
                    status="NOT_FOUND", user_message="当前采购单没有可确认的供应商记录"
                )
            existing = detail.purchase_fields or PurchaseFields()
            raw = args.model_dump(exclude={"requirement_id"}, exclude_unset=True)
            collected: dict[str, JsonValue] = {}
            session_exists = False
            try:
                state = await self._session.state(identity, context.conversation_id)
                session_exists = True
                if state.purchase_request_id == args.requirement_id:
                    collected.update(
                        {
                            key: value
                            for key, value in state.collected_data.items()
                            if key
                            in {
                                "actual_unit_price",
                                "tax_rate",
                                "purchased_at",
                                "purchase_remark",
                            }
                        }
                    )
            except SessionNotFoundError:
                pass
            collected.update(
                {
                    key: value.isoformat() if isinstance(value, datetime) else value
                    for key, value in raw.items()
                    if key != "update_supplier_profile"
                }
            )
            unit_price = collected.get("actual_unit_price", existing.actual_unit_price)
            purchased_value = collected.get(
                "purchased_at", existing.purchased_at or context.current_time
            )
            purchased_at = (
                datetime.fromisoformat(purchased_value)
                if isinstance(purchased_value, str)
                else purchased_value
            )
            if unit_price is None:
                next_missing = "actual_unit_price"
                await self._session.save(
                    identity=identity,
                    context=context,
                    requirement_id=args.requirement_id,
                    focused_role=RoleCode.PURCHASER,
                    focused_field=next_missing,
                    pending_field=next_missing,
                    collected_data=collected,
                )
                return UpdatePurchaseExecutionDraftResult(
                    status="NEED_MORE_INFORMATION",
                    user_message="请补充实际采购单价",
                )
            try:
                unit_decimal = Decimal(str(unit_price))
                quantity = Decimal(detail.applicant_fields.quantity or "0")
                tax_rate = collected.get("tax_rate", existing.tax_rate)
                tax_decimal = Decimal(str(tax_rate)) if tax_rate is not None else None
                if (
                    unit_decimal < 0
                    or quantity <= 0
                    or (
                        tax_decimal is not None
                        and not Decimal("0") <= tax_decimal <= Decimal("100")
                    )
                ):
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                return UpdatePurchaseExecutionDraftResult(
                    status="INVALID_ARGUMENTS", user_message="金额、数量或税率格式无效"
                )
            total = format(quantity * unit_decimal, "f")
            merged = {
                "supplier_id": supplier.supplier_id,
                "supplier_tax_number": supplier.supplier_tax_number,
                "bank_name": supplier.bank_name,
                "bank_account": supplier.bank_account,
                "registered_address": supplier.registered_address,
                "contract_contact_info": supplier.contract_contact_info,
                "actual_unit_price": str(unit_price),
                "actual_total_price": total,
                "tax_rate": collected.get("tax_rate", existing.tax_rate),
                "purchased_at": purchased_at,
                "purchase_remark": collected.get("purchase_remark", existing.purchase_remark),
                "update_supplier_profile": args.update_supplier_profile,
            }
            saved = await self._backend.update_purchase_fields(
                identity=identity,
                requirement_id=args.requirement_id,
                expected_version=detail.version,
                fields=PurchaseFieldsPatch.model_validate(merged),
            )
            latest = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            next_missing_field = saved.missing_fields[0] if saved.missing_fields else None
            safe_fields = tuple(name for name in raw if name != "update_supplier_profile")
            purchase = latest.purchase_fields
            safe_values: dict[str, str | None] = {}
            if purchase is not None:
                for name in safe_fields:
                    value = getattr(purchase, name)
                    safe_values[name] = (
                        value.isoformat()
                        if isinstance(value, datetime)
                        else str(value)
                        if value is not None
                        else None
                    )
            try:
                await self._session.save(
                    identity=identity,
                    context=context,
                    requirement_id=args.requirement_id,
                    focused_role=RoleCode.PURCHASER,
                    focused_field=next_missing_field,
                    missing_fields=saved.missing_fields,
                    pending_field=next_missing_field,
                    collected_data=collected if session_exists else None,
                    awaiting_confirmation=saved.fields_complete,
                )
            except SessionNotFoundError:
                pass
            return UpdatePurchaseExecutionDraftResult(
                status="SUCCESS",
                requirement_id=args.requirement_id,
                requirement_version=latest.version,
                updated_fields=safe_fields,
                updated_values=safe_values,
                actual_total_price=total,
                missing_fields=saved.missing_fields,
                next_missing_field=next_missing_field,
                fields_complete=saved.fields_complete,
            )
        except ConcurrentModificationError:
            return UpdatePurchaseExecutionDraftResult(
                status="CONCURRENT_MODIFICATION", user_message="版本已变化, 请重新确认"
            )


async def _selected_supplier(
    backend: BackendClient, identity: PlatformIdentity, detail: RequirementDetail
) -> SupplierDetail | None:
    """Resolve the selected supplier from backend facts, including legacy name-only reviews."""
    purchase = detail.purchase_fields
    purchase_name = (purchase.supplier_name or "").strip() if purchase is not None else ""
    review = detail.review_fields
    review_name = (review.proposed_supplier_name or "").strip() if review is not None else ""
    record: PurchaseRecord | None = None
    record_name = ""
    if not purchase_name and not review_name:
        records = await backend.list_purchase_records(
            identity=identity,
            requirement_no=detail.requirement_no,
            page=1,
            page_size=20,
        )
        exact_records = tuple(
            item for item in records.items if item.requirement_no == detail.requirement_no
        )
        record = exact_records[0] if len(exact_records) == 1 else None
        record_name = (record.supplier_name or "").strip() if record is not None else ""

    # A name stored on the requirement/record is a visible business fact. When it
    # disagrees with a legacy supplier ID, resolve the exact name instead of silently
    # returning an unrelated supplier profile.
    selected_name = purchase_name or record_name or review_name
    candidate_ids = (
        purchase.supplier_id if purchase is not None else None,
        record.supplier_id if record is not None else None,
        review.proposed_supplier_id if review is not None else None,
    )
    for supplier_id in candidate_ids:
        if supplier_id is None:
            continue
        supplier = await backend.get_supplier(identity=identity, supplier_id=supplier_id)
        if not selected_name or supplier.supplier_name.strip() == selected_name:
            return supplier

    if selected_name:
        page = await backend.search_suppliers(
            identity=identity, keyword=selected_name, page_size=20
        )
        exact = tuple(item for item in page.items if item.supplier_name.strip() == selected_name)
        if len(exact) == 1:
            return await backend.get_supplier(identity=identity, supplier_id=exact[0].supplier_id)
    return None
