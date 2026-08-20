"""Applicant tools for the optional conversational assistant."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from procurement_platform.application.applicant.options import DEVICE_PROFESSION_OPTIONS
from procurement_platform.application.assistant.entity_references import product_reference
from procurement_platform.application.assistant.tooling.common import (
    DraftUpdateResultBase,
    SessionReferenceStore,
    StrictArgs,
    _active_user,
)
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.assistant_session import (
    JsonValue,
    RecommendationReference,
)
from procurement_platform.domain.enums import (
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.errors import (
    BackendProtocolError,
    BackendTimeoutError,
    BackendUnavailableError,
    ConcurrentModificationError,
    PermissionDeniedError,
    RequirementNotFoundError,
    SessionNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFieldsPatch,
    ProductRecommendation,
)
from procurement_platform.ports.backend_client import BackendClient


class RecommendProductOptionsArgs(StrictArgs):
    requirement_id: int | None = Field(default=None, gt=0)
    device_name: str | None = Field(default=None, max_length=200)
    device_profession: str | None = Field(default=None, max_length=100)
    keyword: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=3, ge=1, le=3)

    @model_validator(mode="after")
    def require_source(self) -> "RecommendProductOptionsArgs":
        if self.requirement_id is None and not self.device_name:
            raise ValueError("requirement_id or device_name is required")
        return self


class ProductOptionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_ref: str
    brand: str | None
    model: str | None
    historical_count: int
    last_purchased_at: datetime
    source: Literal["PRODUCT_RECOMMENDATION", "PURCHASE_HISTORY", "MERGED"]


class RecommendProductOptionsResult(AssistantToolResult):
    candidates: tuple[ProductOptionCandidate, ...] = ()
    focused_field: str | None = None


class RecommendProductOptionsTool:
    name = "recommend_product_options"
    side_effect = "READ"
    description = "Recommend up to three product brand/model options from backend purchase history."
    args_model = RecommendProductOptionsArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: RecommendProductOptionsArgs, context: AssistantToolContext
    ) -> RecommendProductOptionsResult:
        try:
            resolved = await _active_user(self._backend, context, RoleCode.APPLICANT)
            if resolved is None:
                return RecommendProductOptionsResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是有效需求人"
                )
            identity, _ = resolved
            try:
                state = await self._session.state(identity, context.conversation_id)
            except SessionNotFoundError:
                state = None
            detail = None
            device_name = args.device_name
            profession = args.device_profession
            if args.requirement_id:
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=args.requirement_id
                )
                device_name = detail.applicant_fields.device_name
                profession = detail.applicant_fields.device_profession
            if not device_name:
                return RecommendProductOptionsResult(
                    status="NEED_MORE_INFORMATION", user_message="请先提供设备名称"
                )
            values = await self._backend.recommend_products_legacy(
                identity=identity,
                device_name=device_name,
                device_profession=profession,
                keyword=args.keyword,
                limit=30,
            )
            focused_field = state.pending_field if state else None
            selected_brand = None
            if detail is not None:
                selected_brand = detail.applicant_fields.brand
            if selected_brand is None and state is not None:
                value = state.collected_data.get("brand")
                selected_brand = value if isinstance(value, str) else None
            seen: set[str | tuple[str, str]] = set()
            candidates: list[ProductOptionCandidate] = []
            for item in values.items:
                if (
                    focused_field == "model"
                    and selected_brand
                    and ((item.brand or "").strip().casefold() != selected_brand.strip().casefold())
                ):
                    continue
                key: str | tuple[str, str]
                if focused_field == "brand":
                    key = (item.brand or "").strip().casefold()
                elif focused_field == "model":
                    key = (item.model or "").strip().casefold()
                else:
                    key = (
                        (item.brand or "").strip().casefold(),
                        (item.model or "").strip().casefold(),
                    )
                if not key:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    self._candidate(
                        item,
                        device_name=device_name,
                        device_profession=profession,
                    )
                )
                if len(candidates) == args.limit:
                    break
            if not candidates:
                return RecommendProductOptionsResult(
                    status="NOT_FOUND", user_message="没有历史产品推荐数据"
                )
            refs = tuple(
                RecommendationReference(
                    reference_id=item.candidate_ref,
                    kind="PRODUCT_RECOMMENDATION",
                    label=f"{item.brand or ''} {item.model or ''}".strip(),
                )
                for item in candidates
            )
            candidate_data: dict[str, JsonValue] = {
                "product_candidate_set_id": (
                    f"candidates:{context.conversation_id}:{context.external_message_id}"
                )
            }
            for candidate in candidates:
                candidate_data[f"product_candidate:{candidate.candidate_ref}:brand"] = (
                    candidate.brand
                )
                candidate_data[f"product_candidate:{candidate.candidate_ref}:model"] = (
                    candidate.model
                )
            candidate_set = await self._session.save(
                identity=identity,
                context=context,
                requirement_id=detail.requirement_id if detail else context.active_requirement_id,
                references=refs,
                focused_role=RoleCode.APPLICANT,
                focused_field=focused_field,
                pending_field=focused_field,
                missing_fields=state.missing_fields if state else None,
                collected_data=candidate_data,
                awaiting_confirmation=True,
            )
            return RecommendProductOptionsResult(
                status="SUCCESS",
                candidate_set_id=candidate_set,
                candidates=tuple(candidates),
                focused_field=focused_field,
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return RecommendProductOptionsResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )

    @staticmethod
    def _candidate(
        item: ProductRecommendation,
        *,
        device_name: str,
        device_profession: str | None,
    ) -> ProductOptionCandidate:
        return ProductOptionCandidate(
            candidate_ref=product_reference(
                product_id=item.product_id,
                device_profession=device_profession,
                device_name=device_name,
                brand=item.brand,
                model=item.model,
                fallback_discriminator=item.last_purchased_at.isoformat(),
            ),
            brand=item.brand,
            model=item.model,
            historical_count=item.historical_count,
            last_purchased_at=item.last_purchased_at,
            source="PRODUCT_RECOMMENDATION",
        )


class UpdatePurchaseDraftArgs(StrictArgs):
    requirement_id: int | None = Field(default=None, gt=0)
    start_new: bool = Field(
        default=False,
        description="用户明确要求新建另一张采购草稿时设为 true",
    )
    product_ref: str | None = Field(default=None, max_length=200)
    selection_index: int | None = Field(
        default=None,
        ge=1,
        description="用户选择最近一次推荐列表中的第几个选项, 从 1 开始",
    )
    device_profession: str | None = Field(default=None, max_length=100)
    device_name: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=150)
    quantity: str | None = None
    unit: str | None = Field(default=None, max_length=30)
    application_reason: str | None = None
    applicant_remark: str | None = None


class UpdatePurchaseDraftResult(DraftUpdateResultBase):
    requirement_no: str | None = None
    status_value: RequirementStatus | None = None
    device_profession_recommendations: tuple[str, ...] = ()


class UpdatePurchaseDraftTool:
    name = "update_purchase_draft"
    side_effect = "MUTATE"
    description = "Create or update applicant draft fields; never submits the requirement."
    args_model = UpdatePurchaseDraftArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: UpdatePurchaseDraftArgs, context: AssistantToolContext
    ) -> UpdatePurchaseDraftResult:
        try:
            resolved = await _active_user(self._backend, context, RoleCode.APPLICANT)
            if resolved is None:
                return UpdatePurchaseDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是有效需求人"
                )
            identity, user = resolved
            if args.start_new and args.requirement_id is not None:
                return UpdatePurchaseDraftResult(
                    status="INVALID_ARGUMENTS",
                    user_message="新建草稿时不能同时指定已有采购单",
                )
            raw = args.model_dump(
                exclude={"requirement_id", "start_new", "product_ref", "selection_index"},
                exclude_unset=True,
            )
            has_candidate_selection = (
                args.selection_index is not None or args.product_ref is not None
            )
            if not raw and not has_candidate_selection:
                return UpdatePurchaseDraftResult(
                    status="NEED_MORE_INFORMATION",
                    user_message="请先提供至少一项采购信息",
                )
            requirement_id = (
                None if args.start_new else args.requirement_id or context.active_requirement_id
            )
            detail = None
            if requirement_id is not None:
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=requirement_id
                )
                if detail.status not in {RequirementStatus.DRAFT, RequirementStatus.REJECTED}:
                    return UpdatePurchaseDraftResult(
                        status="INVALID_STATUS", user_message="当前状态不可修改需求草稿"
                    )
            if requirement_id is None:
                primary = [item for item in user.buildings if item.is_primary]
                building = (
                    user.buildings[0]
                    if len(user.buildings) == 1
                    else primary[0]
                    if len(primary) == 1
                    else None
                )
                if building is None:
                    return UpdatePurchaseDraftResult(
                        status="NEED_MORE_INFORMATION", user_message="请先选择唯一所属楼宇"
                    )
                summary = await self._backend.create_requirement(
                    identity=identity, building_id=building.building_id
                )
                requirement_id = summary.requirement_id
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=requirement_id
                )
            assert detail is not None
            if detail.status not in {RequirementStatus.DRAFT, RequirementStatus.REJECTED}:
                return UpdatePurchaseDraftResult(
                    status="INVALID_STATUS", user_message="当前状态不可修改需求草稿"
                )
            if (
                detail.current_handler is not None
                and detail.current_handler.employee_id != user.employee_id
            ):
                return UpdatePurchaseDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
                )
            if has_candidate_selection:
                state = await self._session.state(identity, context.conversation_id)
                if state.pending_field not in {"brand", "model"}:
                    return UpdatePurchaseDraftResult(
                        status="INVALID_ARGUMENTS", user_message="当前没有可选择的品牌或型号候选"
                    )
                recommendations = tuple(
                    item
                    for item in state.last_recommendations
                    if item.kind == "PRODUCT_RECOMMENDATION"
                )
                if args.selection_index is not None:
                    if args.selection_index > len(recommendations):
                        return UpdatePurchaseDraftResult(
                            status="INVALID_ARGUMENTS",
                            user_message="推荐序号超出当前候选范围",
                        )
                    reference_id = recommendations[args.selection_index - 1].reference_id
                else:
                    assert args.product_ref is not None
                    reference_id = args.product_ref
                if reference_id not in {item.reference_id for item in recommendations}:
                    return UpdatePurchaseDraftResult(
                        status="INVALID_ARGUMENTS", user_message="候选引用不存在或已过期"
                    )
                value = state.collected_data.get(
                    f"product_candidate:{reference_id}:{state.pending_field}"
                )
                if not isinstance(value, str) or not value.strip():
                    return UpdatePurchaseDraftResult(
                        status="INVALID_ARGUMENTS", user_message="候选不包含当前所需字段"
                    )
                raw[state.pending_field] = value
            if not raw:
                return UpdatePurchaseDraftResult(
                    status="NEED_MORE_INFORMATION", user_message="请提供需要保存的采购字段"
                )
            profession_recommendations: tuple[str, ...] = ()
            device_name = raw.get("device_name")
            if (
                isinstance(device_name, str)
                and device_name.strip()
                and not raw.get("device_profession")
                and not detail.applicant_fields.device_profession
            ):
                (
                    historical_profession,
                    profession_recommendations,
                ) = await self._historical_device_profession(
                    identity=identity,
                    device_name=device_name,
                    current_requirement_id=requirement_id,
                )
                if historical_profession is not None:
                    raw["device_profession"] = historical_profession
            patch = ApplicantFieldsPatch.model_validate(raw)
            saved = await self._backend.update_applicant_fields(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=detail.version,
                fields=patch,
            )
            latest = await self._backend.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            collection_missing_fields = list(saved.missing_fields)
            if not latest.applicant_fields.brand:
                collection_missing_fields.append("brand")
            elif not latest.applicant_fields.model:
                collection_missing_fields.append("model")
            next_missing_field = collection_missing_fields[0] if collection_missing_fields else None
            fields_complete = saved.fields_complete and not collection_missing_fields
            await self._session.save(
                identity=identity,
                context=context,
                requirement_id=requirement_id,
                focused_role=RoleCode.APPLICANT,
                focused_field=next_missing_field,
                missing_fields=tuple(collection_missing_fields),
                pending_field=next_missing_field,
                collected_data={key: value for key, value in raw.items()},
                awaiting_confirmation=fields_complete,
                clear_recommendations=True,
            )
            return UpdatePurchaseDraftResult(
                status="SUCCESS",
                requirement_id=requirement_id,
                requirement_version=latest.version,
                requirement_no=latest.requirement_no,
                status_value=latest.status,
                updated_fields=tuple(raw),
                updated_values={key: value for key, value in raw.items()},
                missing_fields=tuple(collection_missing_fields),
                next_missing_field=next_missing_field,
                fields_complete=fields_complete,
                device_profession_recommendations=profession_recommendations,
                user_message=(
                    "字段已完整, 请在正式需求卡片中确认并提交"
                    if fields_complete
                    else f"下一项请补充: {next_missing_field}"
                ),
            )
        except ConcurrentModificationError:
            return UpdatePurchaseDraftResult(
                status="CONCURRENT_MODIFICATION", user_message="版本已变化, 请基于最新内容重新确认"
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return UpdatePurchaseDraftResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )

    async def _historical_device_profession(
        self,
        *,
        identity: PlatformIdentity,
        device_name: str,
        current_requirement_id: int,
    ) -> tuple[str | None, tuple[str, ...]]:
        records = await self._backend.list_purchase_records(
            identity=identity,
            device_name=device_name.strip(),
            page=1,
            page_size=100,
        )
        profession_stats: dict[str, tuple[int, datetime]] = {}
        for record in records.items:
            if record.requirement_id == current_requirement_id:
                continue
            try:
                historical = await self._backend.get_requirement(
                    identity=identity, requirement_id=record.requirement_id
                )
            except (PermissionDeniedError, RequirementNotFoundError):
                continue
            profession = historical.applicant_fields.device_profession
            if profession and profession in DEVICE_PROFESSION_OPTIONS:
                count, latest = profession_stats.get(
                    profession, (0, datetime.min.replace(tzinfo=record.created_at.tzinfo))
                )
                profession_stats[profession] = (count + 1, max(latest, record.created_at))
        ranked = tuple(
            profession
            for profession, _ in sorted(
                profession_stats.items(),
                key=lambda item: (item[1][0], item[1][1]),
                reverse=True,
            )
        )
        return (ranked[0], ranked) if len(ranked) == 1 else (None, ranked)
