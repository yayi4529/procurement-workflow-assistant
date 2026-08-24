# ruff: noqa: RUF001

import logging
from dataclasses import dataclass
from typing import Protocol

from procurement_platform.application.assistant.capabilities.assets import (
    AssetResolver,
    ResolveAssetArgs,
)
from procurement_platform.application.assistant.entity_references import (
    asset_reference,
    parse_asset_reference,
    requirement_reference,
)
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.fault_guidance.knowledge import MarkdownKnowledgeSearch
from procurement_platform.application.fault_guidance.orchestrator import (
    FaultGuidanceOrchestrator,
)
from procurement_platform.application.fault_guidance.validator import FaultDraftValidator
from procurement_platform.domain.assets import AssetSummary
from procurement_platform.domain.assistant import AssistantMessage
from procurement_platform.domain.enums import (
    AgentMessageSender,
    FaultAction,
    RequestType,
    RoleCode,
    ValidationStatus,
)
from procurement_platform.domain.fault_guidance import (
    CandidateItem,
    FaultContext,
    FaultDecision,
    FaultDraftCandidate,
    FaultGuidanceResponse,
    FaultState,
    ProcurementDraftResult,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import ApplicantFieldsPatch, RequestItemDraft
from procurement_platform.ports.backend_client import BackendClient

logger = logging.getLogger(__name__)

_RESET_MESSAGES = {"重新开始", "这是另一个问题", "不是刚才那个故障"}
_CANCEL_MESSAGES = {"算了", "不要采购了", "取消"}


class FaultStateStore(Protocol):
    async def get(self, conversation_id: int | str) -> FaultState | None: ...

    async def save(self, conversation_id: int | str, state: FaultState) -> None: ...

    async def delete(self, conversation_id: int | str) -> None: ...

    async def reset(self, conversation_id: int | str) -> None: ...


class FaultDecisionProvider(Protocol):
    async def decide(self, context: FaultContext) -> FaultDecision: ...


@dataclass(frozen=True, slots=True)
class AssetResolution:
    asset: AssetSummary | None
    identified_in_message: bool = False


class AssetContextProvider(Protocol):
    async def resolve(
        self,
        *,
        identity: PlatformIdentity,
        user_message: str,
        current_asset_ref: str | None,
    ) -> AssetResolution: ...


class ConversationHistoryProvider(Protocol):
    async def recent(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> list[AssistantMessage]: ...


class ProcurementDraftCreator(Protocol):
    async def create_from_fault(
        self, *, identity: PlatformIdentity, candidate: FaultDraftCandidate
    ) -> ProcurementDraftResult: ...


class BackendAssetContextProvider:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._resolver = AssetResolver(backend)

    async def resolve(
        self,
        *,
        identity: PlatformIdentity,
        user_message: str,
        current_asset_ref: str | None,
    ) -> AssetResolution:
        resolved = await self._resolver.resolve_for_identity(
            identity=identity, args=ResolveAssetArgs(phrase=user_message)
        )
        if resolved.resolution == "RESOLVED" and resolved.asset is not None:
            asset_id = parse_asset_reference(resolved.asset.asset_ref)
            return AssetResolution(
                asset=await self._backend.get_asset(identity=identity, asset_id=asset_id),
                identified_in_message=True,
            )
        if current_asset_ref is None:
            return AssetResolution(asset=None)
        asset_id = parse_asset_reference(current_asset_ref)
        return AssetResolution(
            asset=await self._backend.get_asset(identity=identity, asset_id=asset_id)
        )


class BackendConversationHistoryProvider:
    def __init__(self, backend: BackendClient, *, page_size: int = 20) -> None:
        self._backend = backend
        self._page_size = page_size
        self._sessions = AssistantSessionService(backend)

    async def recent(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> list[AssistantMessage]:
        page = await self._sessions.messages(identity=identity, conversation_id=conversation_id)
        role_by_sender = {
            AgentMessageSender.USER: "user",
            AgentMessageSender.AGENT: "assistant",
            AgentMessageSender.SYSTEM: "system",
        }
        return [
            AssistantMessage(role=role_by_sender[item.sender_type], content=item.content)
            for item in page.items[-self._page_size :]
        ]


class ProcurementDraftService:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def create_from_fault(
        self, *, identity: PlatformIdentity, candidate: FaultDraftCandidate
    ) -> ProcurementDraftResult:
        user = await self._backend.get_current_user(identity=identity)
        if user.status != "ACTIVE" or not any(
            role.role_code is RoleCode.APPLICANT for role in user.roles
        ):
            raise ValueError("current user cannot create procurement drafts")
        primary = [item for item in user.buildings if item.is_primary]
        building = (
            user.buildings[0]
            if len(user.buildings) == 1
            else primary[0]
            if len(primary) == 1
            else None
        )
        if building is None:
            raise ValueError("a unique applicant building is required")
        source_asset_id = (
            parse_asset_reference(candidate.source_asset_ref)
            if candidate.source_asset_ref is not None
            else None
        )
        summary = await self._backend.create_requirement(
            identity=identity, building_id=building.building_id
        )
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=summary.requirement_id
        )
        await self._backend.update_applicant_fields(
            identity=identity,
            requirement_id=summary.requirement_id,
            expected_version=detail.version,
            fields=ApplicantFieldsPatch(application_reason=candidate.application_reason),
        )
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=summary.requirement_id
        )
        await self._backend.replace_request_items(
            identity=identity,
            requirement_id=summary.requirement_id,
            expected_version=detail.version,
            request_type=RequestType.FAULT,
            source_asset_id=source_asset_id,
            items=tuple(self._request_item(item) for item in candidate.items),
        )
        saved = await self._backend.get_requirement(
            identity=identity, requirement_id=summary.requirement_id
        )
        return ProcurementDraftResult(
            requirement_id=saved.requirement_id,
            requirement_no=saved.requirement_no,
            version=saved.version,
        )

    @staticmethod
    def _request_item(item: CandidateItem) -> RequestItemDraft:
        if item.item_kind is None or item.quantity is None or not item.unit:
            raise ValueError("validated fault candidate item is incomplete")
        return RequestItemDraft(
            item_kind=item.item_kind,
            item_name=item.item_name,
            quantity=str(item.quantity),
            unit=item.unit,
            brand_snapshot=item.brand,
            model_snapshot=item.model,
            item_reason=item.item_evidence,
        )


class FaultGuidanceService:
    def __init__(
        self,
        *,
        state_repository: FaultStateStore,
        asset_provider: AssetContextProvider,
        knowledge_search: MarkdownKnowledgeSearch,
        orchestrator: FaultGuidanceOrchestrator | FaultDecisionProvider,
        validator: FaultDraftValidator,
        procurement_draft_service: ProcurementDraftCreator,
        history_provider: ConversationHistoryProvider,
    ) -> None:
        self._state_repository = state_repository
        self._asset_provider = asset_provider
        self._knowledge_search = knowledge_search
        self._orchestrator = orchestrator
        self._validator = validator
        self._procurement_drafts = procurement_draft_service
        self._history = history_provider

    async def reset(self, conversation_id: int | str) -> None:
        await self._state_repository.reset(conversation_id)

    async def start(self, conversation_id: int | str) -> None:
        await self._state_repository.save(conversation_id, FaultState())

    async def is_active(self, conversation_id: int | str) -> bool:
        return await self._state_repository.get(conversation_id) is not None

    async def handle_message(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        user_message: str,
    ) -> FaultGuidanceResponse:
        normalized = user_message.strip()
        if normalized in _CANCEL_MESSAGES:
            await self._state_repository.reset(conversation_id)
            logger.info("fault guidance state reset after cancellation")
            return FaultGuidanceResponse(
                reply="已取消当前故障采购引导。",
                action=FaultAction.ANSWER,
            )
        if normalized in _RESET_MESSAGES:
            await self._state_repository.reset(conversation_id)
            logger.info("fault guidance state explicitly reset")
            return FaultGuidanceResponse(
                reply="已清除上一故障上下文，可以重新描述当前问题。",
                action=FaultAction.ANSWER,
            )

        state = await self._state_repository.get(conversation_id) or FaultState()
        resolution = await self._asset_provider.resolve(
            identity=identity,
            user_message=user_message,
            current_asset_ref=state.source_asset_ref,
        )
        source_asset = resolution.asset
        resolved_ref = asset_reference(source_asset.asset_id) if source_asset is not None else None
        if (
            resolution.identified_in_message
            and resolved_ref is not None
            and state.source_asset_ref is not None
            and state.source_asset_ref != resolved_ref
        ):
            await self._state_repository.reset(conversation_id)
            state = FaultState(source_asset_ref=resolved_ref)
            logger.info("fault guidance state reset for a new asset")
        elif resolved_ref is not None:
            state.source_asset_ref = resolved_ref

        query = " ".join(value for value in (user_message.strip(), state.issue_summary) if value)
        knowledge_results = self._knowledge_search.search(
            query=query,
            equipment_category=(
                source_asset.category.category_code if source_asset is not None else None
            ),
        )
        context = FaultContext(
            user_message=user_message,
            source_asset=source_asset,
            fault_state=state,
            knowledge_results=knowledge_results,
            conversation_messages=await self._history.recent(
                identity=identity, conversation_id=conversation_id
            ),
        )
        decision = await self._orchestrator.decide(context)
        self._apply_updates(state, decision)
        logger.info(
            "fault guidance action=%s knowledge_ids=%s",
            decision.action,
            [item.knowledge_id for item in knowledge_results],
        )

        if decision.action in {FaultAction.ANSWER, FaultAction.ASK}:
            await self._state_repository.save(conversation_id, state)
            return FaultGuidanceResponse(reply=decision.reply, action=decision.action)
        if decision.action is FaultAction.PROPOSE_ITEM:
            return await self._handle_proposal(conversation_id, state, decision)
        return await self._handle_direct(
            identity=identity,
            conversation_id=conversation_id,
            state=state,
            decision=decision,
        )

    async def _handle_proposal(
        self,
        conversation_id: int,
        state: FaultState,
        decision: FaultDecision,
    ) -> FaultGuidanceResponse:
        self._apply_default_units(decision.candidate_items)
        status, missing, errors = self._validate_items(decision.candidate_items)
        logger.info("fault candidate validation status=%s", status)
        if status is not ValidationStatus.VALID:
            await self._state_repository.save(conversation_id, state)
            return self._validation_response(status, missing, errors)
        state.candidate_items = list(decision.candidate_items)
        await self._state_repository.save(conversation_id, state)
        return FaultGuidanceResponse(
            reply=self._confirmation_reply(state),
            action=FaultAction.PROPOSE_ITEM,
        )

    async def _handle_direct(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        state: FaultState,
        decision: FaultDecision,
    ) -> FaultGuidanceResponse:
        if not state.candidate_items:
            self._apply_default_units(decision.candidate_items)
            status, missing, errors = self._validate_items(decision.candidate_items)
            if status is not ValidationStatus.VALID:
                await self._state_repository.save(conversation_id, state)
                return self._validation_response(status, missing, errors)
            state.candidate_items = list(decision.candidate_items)
            await self._state_repository.save(conversation_id, state)
            return FaultGuidanceResponse(
                reply=self._confirmation_reply(state),
                action=FaultAction.PROPOSE_ITEM,
            )

        self._apply_default_units(state.candidate_items)
        status, missing, errors = self._validate_items(state.candidate_items)
        if status is not ValidationStatus.VALID:
            await self._state_repository.save(conversation_id, state)
            return self._validation_response(status, missing, errors)
        candidate = FaultDraftCandidate(
            source_asset_ref=state.source_asset_ref,
            application_reason=self._application_reason(state),
            items=list(state.candidate_items),
        )
        logger.info("fault procurement handoff started")
        try:
            draft = await self._procurement_drafts.create_from_fault(
                identity=identity, candidate=candidate
            )
        except Exception:
            logger.exception("fault procurement handoff failed; state retained")
            raise
        await self._state_repository.delete(conversation_id)
        logger.info("fault procurement handoff succeeded requirement_id=%s", draft.requirement_id)
        return FaultGuidanceResponse(
            reply=self._success_reply(state, draft),
            action=FaultAction.DIRECT_TO_PROCUREMENT,
            procurement_draft_ref=requirement_reference(draft.requirement_id),
        )

    def _validate_items(
        self, items: list[CandidateItem]
    ) -> tuple[ValidationStatus, list[str], list[str]]:
        if not items:
            return ValidationStatus.INVALID, [], ["candidate_items_required"]
        missing: list[str] = []
        errors: list[str] = []
        for item in items:
            result = self._validator.validate(item)
            for field in result.missing_fields:
                if field not in missing:
                    missing.append(field)
            errors.extend(result.errors)
        status = (
            ValidationStatus.INVALID
            if errors
            else ValidationStatus.NEEDS_CLARIFICATION
            if missing
            else ValidationStatus.VALID
        )
        return status, missing, errors

    @staticmethod
    def _apply_default_units(items: list[CandidateItem]) -> None:
        """Units are backend-required, but users only need to provide quantity."""
        for item in items:
            if item.unit is None or not item.unit.strip():
                item.unit = "个"

    @staticmethod
    def _apply_updates(state: FaultState, decision: FaultDecision) -> None:
        if decision.issue_summary is not None:
            state.issue_summary = decision.issue_summary
        state.confirmed_facts.update(decision.confirmed_facts_updates)
        state.knowledge_refs = list(
            dict.fromkeys((*state.knowledge_refs, *decision.knowledge_refs_add))
        )

    @staticmethod
    def _validation_response(
        status: ValidationStatus, missing: list[str], errors: list[str]
    ) -> FaultGuidanceResponse:
        if status is ValidationStatus.NEEDS_CLARIFICATION:
            labels = {
                "quantity": "采购数量（quantity）",
            }
            detail = "、".join(labels.get(field, field) for field in missing)
            reply = f"候选采购项还缺少必要信息：{detail}。请补充后再确认。"
        else:
            logger.warning("invalid fault candidate errors=%s", errors)
            reply = "候选采购项未通过安全校验，请重新说明物品和数量。"
        return FaultGuidanceResponse(reply=reply, action=FaultAction.ASK)

    @staticmethod
    def _confirmation_reply(state: FaultState) -> str:
        lines = ["根据目前确认的信息，我整理为：", ""]
        lines.extend(
            f"{item.item_name} × {item.quantity}{item.unit or ''}" for item in state.candidate_items
        )
        lines.extend(["", "是否按这个采购需求继续？"])
        return "\n".join(lines)

    @staticmethod
    def _application_reason(state: FaultState) -> str:
        parts = [state.issue_summary.strip()] if state.issue_summary else []
        if state.confirmed_facts:
            facts = "，".join(
                f"{key}={value}" for key, value in sorted(state.confirmed_facts.items())
            )
            parts.append(f"现场确认信息：{facts}")
        items = "，".join(
            f"{item.item_name}×{item.quantity}{item.unit or ''}" for item in state.candidate_items
        )
        parts.append(f"拟采购：{items}，用于故障处理")
        return "；".join(parts) + "。"

    @staticmethod
    def _success_reply(state: FaultState, draft: ProcurementDraftResult) -> str:
        items = "\n".join(
            f"- {item.item_name} × {item.quantity}{item.unit or ''}"
            for item in state.candidate_items
        )
        return (
            f"采购草稿已创建（{draft.requirement_no}）。\n\n"
            f"采购项：\n{items}\n\n你可以继续查看并确认采购草稿。"
        )
