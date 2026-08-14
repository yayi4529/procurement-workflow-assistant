# ruff: noqa: RUF001

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from procurement_platform.application.assistant.agent_tools import UpdateReviewDraftResult
from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.prompts.building_manager import (
    BUILDING_MANAGER_PROMPT,
)
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementResult,
)
from procurement_platform.application.assistant.tools import ToolExecutor
from procurement_platform.application.building_manager.card_factory import (
    BuildingManagerCardFactory,
)
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.assistant_session import (
    AgentSessionState,
    AgentSessionStateUpdate,
    RecommendationReference,
)
from procurement_platform.domain.enums import PlatformType, RequirementStatus, RoleCode
from procurement_platform.domain.errors import BackendApplicationError, SessionNotFoundError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.ports.backend_client import BackendClient


class BuildingManagerAgent(BasicRoleAgent):
    role = RoleCode.BUILDING_MANAGER
    role_prompt = BUILDING_MANAGER_PROMPT
    tool_names = frozenset(
        {
            "query_purchase_requests",
            "query_supplier_profile",
            "recommend_suppliers_for_requirement",
            "update_review_draft",
        }
    )

    _SELECTIONS: ClassVar[dict[str, int]] = {
        "1": 1,
        "第一个": 1,
        "第1个": 1,
        "选1": 1,
        "选第一个": 1,
        "2": 2,
        "第二个": 2,
        "第2个": 2,
        "选2": 2,
        "选第二个": 2,
        "3": 3,
        "第三个": 3,
        "第3个": 3,
        "选3": 3,
        "选第三个": 3,
    }
    _NEGATIVE_RESPONSES: ClassVar[frozenset[str]] = frozenset(
        {"否", "不是", "不用", "不选", "换一个", "no", "false"}
    )

    def __init__(
        self,
        session_service: AssistantSessionService,
        tool_executor: ToolExecutor,
        backend_client: BackendClient,
    ) -> None:
        super().__init__(session_service)
        self._tool_executor = tool_executor
        self._backend_client = backend_client

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if isinstance(result, RecommendSuppliersForRequirementResult):
            text = self._recommendation_text(result)
            await self._append_reply(context, external_message_id, text)
            return AssistantTextResponse(text=text)
        if isinstance(result, UpdateReviewDraftResult) and result.status == "SUCCESS":
            if result.fields_complete:
                return await self._review_update_response(
                    result=result, context=context, external_message_id=external_message_id
                )
            return None
        return await super().handle_tool_result(
            result=result, context=context, external_message_id=external_message_id
        )

    async def before_run(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        del history
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            current_state = await self._session_service.state(
                identity=identity, conversation_id=context.conversation_id
            )
        except SessionNotFoundError:
            current_state = None
        if current_state is not None:
            contact_selection = await self._handle_contact_selection(
                state=current_state,
                context=context,
                user_text=user_text,
                external_message_id=external_message_id,
            )
            if contact_selection is not None:
                return contact_selection
            named_supplier_selection = await self._handle_named_supplier_selection(
                state=current_state,
                context=context,
                user_text=user_text,
                external_message_id=external_message_id,
            )
            if named_supplier_selection is not None:
                return named_supplier_selection
            contact_response = await self._handle_supplier_contact_query(
                state=current_state,
                context=context,
                user_text=user_text,
                external_message_id=external_message_id,
            )
            if contact_response is not None:
                return contact_response
            pending_response = await self._handle_pending_field(
                state=current_state,
                context=context,
                user_text=user_text,
                external_message_id=external_message_id,
            )
            if pending_response is not None:
                return pending_response
        selection = self._SELECTIONS.get(user_text.strip().rstrip(".!?。").replace(" ", ""))
        if selection is None:
            return None
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            state = await self._session_service.state(
                identity=identity, conversation_id=context.conversation_id
            )
        except SessionNotFoundError:
            return None
        candidates = tuple(
            item for item in state.last_recommendations if item.kind == "SUPPLIER_RECOMMENDATION"
        )
        if selection > len(candidates):
            return await self._reply(
                context, external_message_id, "推荐序号超出当前候选范围, 请重新选择。"
            )
        requirement_id = state.purchase_request_id or context.active_requirement_id
        if requirement_id is None:
            return await self._reply(context, external_message_id, "当前没有可更新的待审核采购单。")
        candidate: RecommendationReference = candidates[selection - 1]
        _, result = await self._tool_executor.execute_result(
            name="update_review_draft",
            arguments_json=json.dumps(
                {
                    "requirement_id": requirement_id,
                    "proposed_supplier_ref": candidate.reference_id,
                },
                ensure_ascii=False,
            ),
            tool_call_id="building-manager-supplier-selection",
            context=context,
            allowed_names=frozenset({"update_review_draft"}),
        )
        if not isinstance(result, UpdateReviewDraftResult) or result.status != "SUCCESS":
            return await self._reply(
                context,
                external_message_id,
                result.user_message or "供应商保存失败, 请重新推荐后再选择。",
            )
        return await self._after_supplier_selection(
            context=context,
            external_message_id=external_message_id,
            supplier_name=candidate.label,
            supplier_id=int(candidate.reference_id.removeprefix("supplier:")),
        )

    async def _handle_named_supplier_selection(
        self,
        *,
        state: AgentSessionState,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        normalized = user_text.strip().replace(" ", "")
        candidate = next(
            (
                item
                for item in state.last_recommendations
                if item.kind == "SUPPLIER_RECOMMENDATION"
                and item.label.replace(" ", "") in normalized
            ),
            None,
        )
        if candidate is None:
            return None
        requirement_id = state.purchase_request_id or context.active_requirement_id
        if requirement_id is None:
            return None
        _, result = await self._tool_executor.execute_result(
            name="update_review_draft",
            arguments_json=json.dumps(
                {
                    "requirement_id": requirement_id,
                    "proposed_supplier_ref": candidate.reference_id,
                },
                ensure_ascii=False,
            ),
            tool_call_id="building-manager-named-supplier-selection",
            context=context,
            allowed_names=frozenset({"update_review_draft"}),
        )
        if not isinstance(result, UpdateReviewDraftResult) or result.status != "SUCCESS":
            return await self._reply(
                context,
                external_message_id,
                result.user_message or "供应商保存失败，请重新选择。",
            )
        return await self._after_supplier_selection(
            context=context,
            external_message_id=external_message_id,
            supplier_name=candidate.label,
            supplier_id=int(candidate.reference_id.removeprefix("supplier:")),
        )

    async def _after_supplier_selection(
        self,
        *,
        context: AssistantToolContext,
        external_message_id: str,
        supplier_name: str,
        supplier_id: int,
    ) -> AssistantResponse:
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        state = await self._session_service.state(
            identity=identity, conversation_id=context.conversation_id
        )
        requirement_id = state.purchase_request_id or context.active_requirement_id
        assert requirement_id is not None
        contacts = await self._historical_contacts(
            identity=identity, requirement_id=requirement_id, supplier_id=supplier_id
        )
        if not contacts:
            await self._save_contact_state(
                identity=identity,
                context=context,
                state=state,
                pending_field="supplier_contact_name",
                references=(),
            )
            text = (
                f"好的, 已为您记录拟供应商为**{supplier_name}**。\n\n"
                f"请提供 {supplier_name} 的联系人姓名。"
            )
            return await self._reply(context, external_message_id, text)
        references = tuple(
            RecommendationReference(
                reference_id=f"supplier-contact:{index}",
                kind="SUPPLIER_CONTACT",
                label=f"{name}\n{info}",
            )
            for index, (name, info) in enumerate(contacts, start=1)
        )
        await self._save_contact_state(
            identity=identity,
            context=context,
            state=state,
            pending_field="supplier_contact_selection",
            references=references,
        )
        options = "\n".join(
            f"{index}. {name}, {info}" for index, (name, info) in enumerate(contacts, start=1)
        )
        text = (
            f"好的, 已为您记录拟供应商为**{supplier_name}**。\n\n"
            f"根据历史采购记录, {supplier_name} 的联系人和联系方式如下：\n"
            f"{options}\n\n"
            "请回复序号选择相应的联系人, 如有其他联系人则直接告诉我。"
        )
        return await self._reply(context, external_message_id, text)

    async def _handle_contact_selection(
        self,
        *,
        state: AgentSessionState,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if getattr(state, "pending_field", None) != "supplier_contact_selection":
            return None
        normalized = user_text.strip().lower().replace(" ", "").rstrip(".!?")
        references = tuple(
            item
            for item in getattr(state, "last_recommendations", ())
            if item.kind == "SUPPLIER_CONTACT"
        )
        if normalized in self._NEGATIVE_RESPONSES:
            identity = PlatformIdentity.create(
                PlatformType(context.platform_type), context.platform_user_id
            )
            await self._save_contact_state(
                identity=identity,
                context=context,
                state=state,
                pending_field="supplier_contact_name",
                references=(),
            )
            supplier_name = await self._selected_supplier_name(
                identity=identity, requirement_id=state.purchase_request_id
            )
            return await self._reply(
                context,
                external_message_id,
                f"请提供 {supplier_name} 的联系人姓名。",
            )
        selection = self._SELECTIONS.get(normalized)
        if selection is not None:
            if selection > len(references):
                return await self._reply(
                    context, external_message_id, "联系人序号无效，请重新选择。"
                )
            name, info = references[selection - 1].label.split("\n", maxsplit=1)
            _, result = await self._tool_executor.execute_result(
                name="update_review_draft",
                arguments_json=json.dumps(
                    {
                        "requirement_id": state.purchase_request_id,
                        "supplier_contact_name": name,
                        "supplier_contact_info": info,
                    },
                    ensure_ascii=False,
                ),
                tool_call_id="building-manager-contact-selection",
                context=context,
                allowed_names=frozenset({"update_review_draft"}),
            )
            if not isinstance(result, UpdateReviewDraftResult) or result.status != "SUCCESS":
                return await self._reply(
                    context,
                    external_message_id,
                    result.user_message or "联系人保存失败。",
                )
            return await self._review_update_response(
                result=result,
                context=context,
                external_message_id=external_message_id,
                recorded_contact=f"{name}, {info}",
            )
        parsed = self._parse_contact(user_text)
        if parsed is None:
            return await self._reply(
                context,
                external_message_id,
                "请提供该供应商的联系人姓名和联系方式，例如：张工 13800000000。",
            )
        return await self._save_contact(
            context=context,
            external_message_id=external_message_id,
            requirement_id=state.purchase_request_id,
            name=parsed[0],
            info=parsed[1],
        )

    async def _handle_pending_field(
        self,
        *,
        state: object,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        pending_field = getattr(state, "pending_field", None)
        requirement_id = getattr(state, "purchase_request_id", None)
        if not pending_field or requirement_id is None:
            return None
        normalized = user_text.strip().lower().rstrip(".!?")
        if normalized in self._SELECTIONS:
            return None
        value: object = user_text.strip()
        if pending_field == "expected_arrival_date":
            parsed_date = self._parse_expected_arrival_date(user_text)
            if parsed_date is None:
                return await self._reply(
                    context,
                    external_message_id,
                    "请按 YYYY-MM-DD 或 YYYY年M月D日提供预计到货日期。",
                )
            value = parsed_date
        if pending_field == "need_contract":
            if normalized in {"是", "需要", "要", "true", "yes"}:
                value = True
            elif normalized in {"否", "不需要", "不要", "false", "no"}:
                value = False
            else:
                return await self._reply(
                    context, external_message_id, self._missing_field_question(pending_field)
                )
        arguments: dict[str, object] = {"requirement_id": requirement_id, pending_field: value}
        recorded_contact: str | None = None
        if pending_field == "supplier_contact_name":
            parsed = self._parse_contact(user_text)
            if parsed is not None:
                arguments = {
                    "requirement_id": requirement_id,
                    "supplier_contact_name": parsed[0],
                    "supplier_contact_info": parsed[1],
                }
                recorded_contact = f"{parsed[0]}, {parsed[1]}"
        _, result = await self._tool_executor.execute_result(
            name="update_review_draft",
            arguments_json=json.dumps(arguments, ensure_ascii=False),
            tool_call_id="building-manager-pending-field",
            context=context,
            allowed_names=frozenset({"update_review_draft"}),
        )
        if not isinstance(result, UpdateReviewDraftResult):
            return None
        if result.status != "SUCCESS":
            return await self._reply(
                context,
                external_message_id,
                result.user_message or "审核信息保存失败, 请重新提供该字段。",
            )
        return await self._review_update_response(
            result=result,
            context=context,
            external_message_id=external_message_id,
            recorded_contact=recorded_contact,
        )

    @staticmethod
    def _parse_expected_arrival_date(text: str) -> str | None:
        compact_match = re.fullmatch(r"\s*(\d{4})(\d{2})(\d{2})\s*", text)
        match = compact_match or re.fullmatch(
            r"\s*(\d{4})\s*(?:-|/|\.|年)\s*(\d{1,2})\s*"
            r"(?:-|/|\.|月)\s*(\d{1,2})\s*[日号]?\s*",
            text,
        )
        if match is None:
            return None
        try:
            return date(*(int(part) for part in match.groups())).isoformat()
        except ValueError:
            return None

    async def _save_contact(
        self,
        *,
        context: AssistantToolContext,
        external_message_id: str,
        requirement_id: int | None,
        name: str,
        info: str,
    ) -> AssistantResponse:
        assert requirement_id is not None
        _, result = await self._tool_executor.execute_result(
            name="update_review_draft",
            arguments_json=json.dumps(
                {
                    "requirement_id": requirement_id,
                    "supplier_contact_name": name,
                    "supplier_contact_info": info,
                },
                ensure_ascii=False,
            ),
            tool_call_id="building-manager-contact-input",
            context=context,
            allowed_names=frozenset({"update_review_draft"}),
        )
        if not isinstance(result, UpdateReviewDraftResult) or result.status != "SUCCESS":
            return await self._reply(
                context,
                external_message_id,
                result.user_message or "联系人保存失败。",
            )
        return await self._review_update_response(
            result=result,
            context=context,
            external_message_id=external_message_id,
            recorded_contact=f"{name}, {info}",
        )

    @staticmethod
    def _parse_contact(text: str) -> tuple[str, str] | None:
        phone = re.search(r"(?:\+?\d[\d -]{5,}\d)", text)
        if phone is None:
            return None
        name = text[: phone.start()].strip(" ：:，,；;联系人")
        info = phone.group(0).strip()
        return (name, info) if name else None

    async def _handle_supplier_contact_query(
        self,
        *,
        state: object,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        normalized = user_text.replace(" ", "")
        if not any(marker in normalized for marker in ("联系人", "联系方式", "联系电话", "电话")):
            return None
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        requirement_id = getattr(state, "purchase_request_id", None)
        supplier_id: int | None = None
        supplier_name: str | None = None
        contact_name: str | None = None
        contact_info: str | None = None
        if requirement_id is not None:
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            if detail.review_fields is not None:
                supplier_id = detail.review_fields.proposed_supplier_id
                supplier_name = detail.review_fields.proposed_supplier_name
                contact_name = detail.review_fields.supplier_contact_name
                contact_info = detail.review_fields.supplier_contact_info
        if supplier_id is None:
            candidates = tuple(
                item
                for item in getattr(state, "last_recommendations", ())
                if item.kind == "SUPPLIER_RECOMMENDATION"
            )
            if len(candidates) != 1:
                return await self._reply(
                    context,
                    external_message_id,
                    "请先回复推荐供应商的序号，我再查询对应的联系人和联系方式。",
                )
            reference = candidates[0].reference_id
            try:
                supplier_id = int(reference.removeprefix("supplier:"))
            except ValueError:
                return None
            supplier_name = candidates[0].label
        supplier = await self._backend_client.get_supplier(
            identity=identity, supplier_id=supplier_id
        )
        contact = contact_info or supplier.contract_contact_info or "后端未提供"
        name = contact_name or "后端未提供独立联系人姓名"
        text = f"{supplier_name or supplier.supplier_name} 的联系人：{name}\n联系方式：{contact}"
        return await self._reply(context, external_message_id, text)

    async def _historical_contacts(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        supplier_id: int,
    ) -> tuple[tuple[str, str], ...]:
        current = await self._backend_client.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        history = await self._backend_client.list_purchase_records(
            identity=identity,
            supplier_id=supplier_id,
            device_name=current.applicant_fields.device_name,
            brand=current.applicant_fields.brand,
            page=1,
            page_size=100,
        )
        contacts: list[tuple[str, str]] = []
        for record in history.items:
            if record.status not in {
                RequirementStatus.PENDING_WAREHOUSE,
                RequirementStatus.COMPLETED,
            }:
                continue
            try:
                detail = await self._backend_client.get_requirement(
                    identity=identity, requirement_id=record.requirement_id
                )
            except BackendApplicationError:
                continue
            review = detail.review_fields
            if (
                review is None
                or not review.supplier_contact_name
                or not review.supplier_contact_info
            ):
                continue
            contact = (review.supplier_contact_name, review.supplier_contact_info)
            if contact not in contacts:
                contacts.append(contact)
        return tuple(contacts)

    async def _historical_unit_price_references(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
    ) -> tuple[str, ...]:
        current = await self._backend_client.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        review = current.review_fields
        if review is None or review.proposed_supplier_id is None:
            return ()
        history = await self._backend_client.list_purchase_records(
            identity=identity,
            supplier_id=review.proposed_supplier_id,
            device_name=current.applicant_fields.device_name,
            brand=current.applicant_fields.brand,
            page=1,
            page_size=100,
        )
        references: list[tuple[datetime, str]] = []
        for record in history.items:
            if (
                record.status
                not in {
                    RequirementStatus.PENDING_WAREHOUSE,
                    RequirementStatus.COMPLETED,
                }
                or not record.quantity
                or not record.actual_total_price
            ):
                continue
            try:
                quantity = Decimal(record.quantity)
                total = Decimal(record.actual_total_price)
            except InvalidOperation:
                continue
            if quantity <= 0:
                continue
            purchased_at = record.purchased_at or record.created_at
            unit_price = (total / quantity).quantize(Decimal("0.01"))
            references.append((purchased_at, f"{purchased_at.date().isoformat()}: {unit_price}"))
        references.sort(key=lambda item: item[0], reverse=True)
        return tuple(value for _, value in references[:3])

    async def _save_contact_state(
        self,
        *,
        identity: PlatformIdentity,
        context: AssistantToolContext,
        state: AgentSessionState,
        pending_field: str,
        references: tuple[RecommendationReference, ...],
    ) -> None:
        update = AgentSessionStateUpdate.model_validate(
            state.model_dump(
                exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
            )
        )
        await self._session_service.save_state(
            identity=identity,
            conversation_id=context.conversation_id,
            state=update.model_copy(
                update={
                    "pending_field": pending_field,
                    "focused_field": pending_field,
                    "last_recommendations": references,
                }
            ),
        )

    async def _selected_supplier_name(
        self, *, identity: PlatformIdentity, requirement_id: int | None
    ) -> str:
        if requirement_id is None:
            return "该供应商"
        detail = await self._backend_client.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        if detail.review_fields and detail.review_fields.proposed_supplier_name:
            return detail.review_fields.proposed_supplier_name
        return "该供应商"

    async def _review_update_response(
        self,
        *,
        result: UpdateReviewDraftResult,
        context: AssistantToolContext,
        external_message_id: str,
        recorded_supplier: str | None = None,
        recorded_contact: str | None = None,
    ) -> AssistantResponse:
        if result.fields_complete:
            identity = PlatformIdentity.create(
                PlatformType(context.platform_type), context.platform_user_id
            )
            requirement_id = result.requirement_id or context.active_requirement_id
            assert requirement_id is not None
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            notice = "审核信息已完整, 请在审核卡片中确认。"
            prefix = self._recorded_prefix(recorded_supplier, recorded_contact)
            if prefix:
                notice = f"{prefix}\n\n{notice}"
            await self._append_reply(context, external_message_id, notice)
            return AssistantInteractionResponse(
                view=BuildingManagerCardFactory().detail(detail, notice=notice)
            )
        field = result.next_missing_field or (
            result.missing_fields[0] if result.missing_fields else None
        )
        prefix = self._recorded_prefix(recorded_supplier, recorded_contact)
        if not prefix:
            prefix = self._updated_fields_prefix(result)
        prefix = f"{prefix}\n\n" if prefix else ""
        question = prefix + self._missing_field_question(field)
        if field == "estimated_unit_price":
            identity = PlatformIdentity.create(
                PlatformType(context.platform_type), context.platform_user_id
            )
            requirement_id = result.requirement_id or context.active_requirement_id
            if requirement_id is not None:
                references = await self._historical_unit_price_references(
                    identity=identity, requirement_id=requirement_id
                )
                if references:
                    question += "\n\n相关历史单价参考：\n" + "\n".join(
                        f"- {item}" for item in references
                    )
        await self._append_reply(context, external_message_id, question)
        return AssistantTextResponse(text=question)

    @staticmethod
    def _recorded_prefix(recorded_supplier: str | None, recorded_contact: str | None) -> str:
        if recorded_contact:
            return f"好的, 已为您记录联系人和联系方式：**{recorded_contact}**。"
        if recorded_supplier:
            return f"好的, 已为您记录拟供应商为**{recorded_supplier}**。"
        return ""

    @staticmethod
    def _updated_fields_prefix(result: UpdateReviewDraftResult) -> str:
        labels = {
            "estimated_unit_price": "预计单价",
            "need_contract": "是否需要合同",
            "contract_type": "合同类型",
            "payment_method": "付款方式",
            "expected_arrival_date": "预计到货日期",
            "warranty_info": "质保信息",
            "review_remark": "审核备注",
            "supplier_link": "供应商链接",
        }
        entries = [
            f"{labels.get(name, name)}为**{result.updated_values[name]}**"
            for name in result.updated_fields
            if name in result.updated_values and name in labels
        ]
        return f"好的，已为您记录{'；'.join(entries)}。" if entries else ""

    @staticmethod
    def _missing_field_question(field: str | None) -> str:
        labels = {
            "supplier_contact_name": "供应商联系人姓名",
            "supplier_contact_info": "供应商联系方式",
            "supplier_link": "供应商链接",
            "estimated_unit_price": "预计单价",
            "need_contract": "是否需要合同",
            "contract_type": "合同类型",
            "payment_method": "付款方式",
            "expected_arrival_date": "预计到货日期",
            "warranty_info": "质保信息",
            "review_remark": "审核备注",
        }
        return f"请提供{labels.get(field or '', field or '下一项审核信息')}。"

    @staticmethod
    def _recommendation_text(result: RecommendSuppliersForRequirementResult) -> str:
        if not result.candidates:
            return result.user_message or "暂未找到符合设备名称和品牌的历史供应商。"
        lines = ["根据当前设备名称和品牌的历史采购记录，推荐以下供应商："]
        for index, item in enumerate(result.candidates, start=1):
            lines.append(
                f"{index}. **{item.supplier_name}**\n"
                f"   历史采购 {item.historical_purchase_count} 次，"
                f"最近采购 {item.last_purchase_at.date().isoformat()}"
            )
        lines.append("请回复序号选择供应商，或直接告诉我您希望选择的供应商。")
        return "\n\n".join(lines)

    async def _reply(
        self, context: AssistantToolContext, external_message_id: str, text: str
    ) -> AssistantTextResponse:
        await self._append_reply(context, external_message_id, text)
        return AssistantTextResponse(text=text)
