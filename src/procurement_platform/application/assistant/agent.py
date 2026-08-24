# ruff: noqa: RUF001

import json
import logging
from collections.abc import Mapping

from procurement_platform.application.assistant.capabilities.policy import CapabilityPolicy
from procurement_platform.application.assistant.grounding import GroundingPolicy
from procurement_platform.application.assistant.hybrid_routing import HybridRouteComparison
from procurement_platform.application.assistant.phase_input import (
    PhaseInputParser,
    PhaseParseResult,
)
from procurement_platform.application.assistant.presentation import LegacyToolResultPresenter
from procurement_platform.application.assistant.prompts.applicant import APPLICANT_PROMPT
from procurement_platform.application.assistant.prompts.building_manager import (
    BUILDING_MANAGER_PROMPT,
)
from procurement_platform.application.assistant.prompts.common import COMMON_PROMPT
from procurement_platform.application.assistant.prompts.procurement import PROCUREMENT_AGENT_PROMPT
from procurement_platform.application.assistant.prompts.purchaser import PURCHASER_PROMPT
from procurement_platform.application.assistant.prompts.warehouse import WAREHOUSE_PROMPT
from procurement_platform.application.assistant.role_skills import RoleSkillRegistry
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.turn_context import AgentTurnContext
from procurement_platform.application.assistant.workflow_coordinator import WorkflowTurnCoordinator
from procurement_platform.application.assistant.workflow_execution import WorkflowExecutionOutcome
from procurement_platform.application.assistant.workflow_router import (
    WorkflowRouteAction,
    WorkflowRouter,
)
from procurement_platform.application.assistant.workflow_state import (
    WorkflowRunState,
    WorkflowStateService,
    WorkflowStatus,
)
from procurement_platform.application.assistant.workflow_transition import (
    WorkflowTransitionEvent,
    WorkflowTransitionService,
)
from procurement_platform.domain.assistant import (
    AssistantClarificationResponse,
    AssistantMessage,
    AssistantOption,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.assistant_session import JsonValue
from procurement_platform.domain.enums import AgentMessageSender, PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import SelectedProduct


class ProcurementAgent:
    """Single procurement-domain agent; roles only affect capability authorization."""

    def __init__(
        self,
        *,
        runtime: AssistantRuntime,
        capability_policy: CapabilityPolicy,
        session_service: AssistantSessionService,
        result_presenter: LegacyToolResultPresenter,
        grounding_policy: GroundingPolicy | None = None,
        context_knowledge: str | None = None,
        role_skill_registry: RoleSkillRegistry | None = None,
        workflow_router: WorkflowRouter | None = None,
        workflow_state_service: WorkflowStateService | None = None,
        skill_routing_mode: str = "off",
        phase_input_parser: PhaseInputParser | None = None,
        transition_service: WorkflowTransitionService | None = None,
        turn_coordinator: WorkflowTurnCoordinator | None = None,
    ) -> None:
        self._runtime = runtime
        self._capability_policy = capability_policy
        self._session_service = session_service
        self._result_presenter = result_presenter
        self._grounding_policy = grounding_policy or GroundingPolicy()
        self._context_knowledge = context_knowledge
        self._role_skill_registry = role_skill_registry
        self._workflow_router = workflow_router
        self._workflow_state_service = workflow_state_service
        self._skill_routing_mode = skill_routing_mode
        self._phase_input_parser = phase_input_parser
        self._transitions = transition_service or WorkflowTransitionService()
        self._coordinator = turn_coordinator or WorkflowTurnCoordinator(capability_policy)

    async def run(
        self,
        *,
        turn_context: AgentTurnContext,
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse:
        role_allowed_names = (
            self._capability_policy.allowed_names_for_roles({turn_context.active_role})
            if self._role_skill_registry is not None
            and turn_context.current_user.status == "ACTIVE"
            else self._capability_policy.allowed_names_for(turn_context.current_user)
        )
        selection = None
        route = None
        legacy_selection = None
        skill = (
            self._role_skill_registry.get(turn_context.active_role)
            if self._role_skill_registry is not None
            else None
        )
        current = WorkflowStateService.from_session(turn_context.session_state)
        if self._skill_routing_mode == "hybrid" and self._role_skill_registry is not None:
            legacy_selection = self._role_skill_registry.select(
                role=turn_context.active_role, user_text=user_text
            )
        if (
            current is not None
            and current.status is WorkflowStatus.AWAITING_CARD
            and turn_context.active_requirement is not None
            and turn_context.active_requirement.status.value not in {"DRAFT", "REJECTED"}
        ):
            await self._save_workflow(
                turn_context,
                current.model_copy(update={"status": WorkflowStatus.COMPLETED}),
            )
            current = None
        parsed_continuation = False
        if (
            current is not None
            and current.status in {WorkflowStatus.ACTIVE, WorkflowStatus.AWAITING_USER}
            and _is_explicit_new_purchase(user_text)
        ):
            # A new purchase request must not inherit an in-flight recommendation,
            # candidate selection, or the previous requirement focus.
            await self._save_workflow(turn_context, None)
            current = None
        if (
            self._skill_routing_mode != "off"
            and current is not None
            and skill is not None
            and current.role is turn_context.active_role
        ):
            current_workflow = skill.workflows.get(current.workflow_name)
            current_phase = (
                current_workflow.phase(current.phase) if current_workflow is not None else None
            )
            if (
                current_phase is not None
                and current_phase.input_parser is not None
                and self._phase_input_parser is not None
            ):
                parsed = await self._phase_input_parser.parse(
                    parser_name=current_phase.input_parser,
                    user_text=user_text,
                    allowed_intents=_allowed_phase_intents(current_phase.input_parser),
                )
                if parsed.result is PhaseParseResult.NEW_GOAL:
                    await self._save_workflow(turn_context, None)
                    current = None
                elif parsed.result is PhaseParseResult.MATCH:
                    merged = dict(current.collected_inputs)
                    merged.update(parsed.collected_inputs)
                    merged = _with_candidate_draft_items(merged)
                    if current.phase == "await-selection":
                        selected = _selected_candidate_inputs(turn_context, parsed.collected_inputs)
                        if selected is not None:
                            merged.update(selected)
                    candidate_draft_ready = False
                    if (
                        current.workflow_name == "product-recommendation"
                        and current.phase == "await-selection"
                        and parsed.intent == "SELECT_AND_DRAFT"
                    ):
                        target = skill.workflows.get("create-draft")
                        candidate_inputs = _selected_candidate_inputs(
                            turn_context, parsed.collected_inputs
                        )
                        if target is None or candidate_inputs is None:
                            return AssistantTextResponse(
                                text="候选信息已失效，请重新查询产品候选后再选择。"
                            )
                        quantity = parsed.collected_inputs.get("candidate_quantity")
                        target_phase = (
                            "collect-reason" if isinstance(quantity, int) else "collect-items"
                        )
                        target_status = WorkflowStatus.AWAITING_USER
                        transition = self._transitions.switch_workflow(
                            state=current,
                            target_workflow=target,
                            target_phase=target_phase,
                            collected_inputs=candidate_inputs,
                            status=target_status,
                        )
                        current = transition.state
                        assert current is not None
                        await self._save_workflow(turn_context, current)
                        if target_status is WorkflowStatus.AWAITING_USER:
                            return AssistantTextResponse(
                                text=(
                                    _phase_input_hint(
                                        "applicant-application-reason", repeated=False
                                    )
                                    if target_phase == "collect-reason"
                                    else "已保留所选候选。请提供采购数量后再创建草稿。"
                                )
                            )
                        parsed_continuation = True
                        candidate_draft_ready = True
                    if not candidate_draft_ready:
                        next_phase = current_phase.on_success
                        if next_phase in {"COMPLETED", "FAILED"}:
                            await self._save_workflow(
                                turn_context,
                                current.model_copy(
                                    update={
                                        "status": WorkflowStatus(next_phase),
                                        "collected_inputs": merged,
                                    }
                                ),
                            )
                            return AssistantTextResponse(text="当前 Skill 任务已完成。")
                        assert skill is not None
                        active_workflow = skill.workflows[current.workflow_name]
                        next_phase_definition = active_workflow.phase(next_phase)
                        next_status = (
                            WorkflowStatus(next_phase_definition.terminal_status)
                            if next_phase_definition is not None
                            and next_phase_definition.terminal_status is not None
                            else WorkflowStatus.ACTIVE
                        )
                        current = current.model_copy(
                            update={
                                "phase": next_phase,
                                "status": next_status,
                                "collected_inputs": merged,
                                "clarification_count": 0,
                            }
                        )
                        await self._save_workflow(turn_context, current)
                        if next_status is WorkflowStatus.AWAITING_USER:
                            return AssistantTextResponse(
                                text=_phase_input_hint(
                                    next_phase_definition.input_parser
                                    if next_phase_definition is not None
                                    and next_phase_definition.input_parser is not None
                                    else "",
                                    repeated=False,
                                )
                            )
                        parsed_continuation = True
                elif parsed.result in {
                    PhaseParseResult.AMBIGUOUS,
                    PhaseParseResult.NO_MATCH,
                }:
                    count = current.clarification_count + 1
                    await self._save_workflow(
                        turn_context,
                        current.model_copy(
                            update={
                                "status": WorkflowStatus.AWAITING_USER,
                                "clarification_count": count,
                            }
                        ),
                    )
                    missing = "、".join(parsed.missing_inputs)
                    hint = (
                        f"请补充这些物品的数量：{missing}。"
                        if missing
                        else _phase_input_hint(current_phase.input_parser, repeated=count > 1)
                    )
                    return AssistantTextResponse(text=hint)
        if self._skill_routing_mode == "off":
            selection = (
                self._role_skill_registry.select(role=turn_context.active_role, user_text=user_text)
                if self._role_skill_registry is not None
                else None
            )
        elif parsed_continuation and skill is not None and current is not None:
            from procurement_platform.application.assistant.role_skills import RoleSkillSelection

            workflow = skill.workflows[current.workflow_name]
            selection = RoleSkillSelection(skill=skill, workflow=workflow)
        elif skill is not None and self._workflow_router is not None:
            if current is not None and (
                current.role is not turn_context.active_role
                or current.status in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}
            ):
                current = None
            route = await self._workflow_router.route(
                user_text=user_text,
                role=turn_context.active_role,
                skill=skill,
                current=current,
            )
            if route.action is WorkflowRouteAction.NO_TOOL:
                descriptions = "、".join(item.description for item in skill.workflows.values())
                return AssistantTextResponse(text=f"当前可协助：{descriptions}")
            if route.action is WorkflowRouteAction.SWITCH and route.workflow_name is None:
                await self._save_workflow(turn_context, None)
                return AssistantTextResponse(text="已结束当前任务，请描述你的新需求。")
            if route.action is WorkflowRouteAction.CLARIFY:
                likely = skill.workflows.get(route.workflow_name or "")
                if likely is not None:
                    await self._save_workflow(
                        turn_context,
                        WorkflowRunState(
                            role=turn_context.active_role,
                            skill_name=skill.name,
                            workflow_name=likely.name,
                            phase="route-clarification",
                            status=WorkflowStatus.AWAITING_USER,
                            route_confidence=route.confidence,
                        ),
                    )
                options = tuple(
                    AssistantOption(label=item.description[:30], value=item.name)
                    for item in list(skill.workflows.values())[:3]
                )
                return AssistantClarificationResponse(
                    question="你希望我处理哪一类采购任务？", options=options
                )
            if route.workflow_name is None:
                return AssistantTextResponse(text="请描述你希望处理的采购任务。")
            routed_workflow = skill.workflows.get(route.workflow_name)
            if routed_workflow is not None:
                from procurement_platform.application.assistant.role_skills import (
                    RoleSkillSelection,
                )

                selection = RoleSkillSelection(skill=skill, workflow=routed_workflow)
                current = WorkflowRunState(
                    role=turn_context.active_role,
                    skill_name=skill.name,
                    workflow_name=routed_workflow.name,
                    phase=routed_workflow.initial_phase.name,
                    status=WorkflowStatus.ACTIVE,
                    route_confidence=route.confidence,
                )
                initial = routed_workflow.initial_phase
                if initial.input_parser is not None and self._phase_input_parser is not None:
                    parsed = await self._phase_input_parser.parse(
                        parser_name=initial.input_parser,
                        user_text=user_text,
                        allowed_intents=_allowed_phase_intents(initial.input_parser),
                    )
                    if parsed.result is PhaseParseResult.MATCH:
                        current = current.model_copy(
                            update={
                                "phase": initial.on_success,
                                "collected_inputs": parsed.collected_inputs,
                            }
                        )
                    elif parsed.result is PhaseParseResult.AMBIGUOUS:
                        current = current.model_copy(
                            update={
                                "status": WorkflowStatus.AWAITING_USER,
                                "collected_inputs": parsed.collected_inputs,
                                "clarification_count": 1,
                            }
                        )
                await self._save_workflow(turn_context, current)
                if current.status is WorkflowStatus.AWAITING_USER:
                    return AssistantTextResponse(
                        text=_phase_input_hint(initial.input_parser or "", repeated=False)
                    )
        if self._skill_routing_mode != "off" and selection is None:
            return AssistantTextResponse(text="当前角色没有可执行的 Skill workflow。")
        active_phase = (
            selection.workflow.phase(current.phase)
            if selection is not None and current is not None
            else selection.workflow.initial_phase
            if selection is not None
            else None
        )
        allowed_names = (
            role_allowed_names.intersection(active_phase.capabilities)
            if selection is not None and active_phase is not None
            else role_allowed_names
        )
        # The gate requires authoritative evidence for factual claims but does not prescribe
        # a single first tool; the LLM remains free to plan among the relevant read abilities.
        grounding = self._grounding_policy.decide(user_text, available_tools=allowed_names)
        budget = self._coordinator.budget()
        outcome = None
        response: AssistantResponse
        while True:
            if not budget.begin_phase():
                response = AssistantTextResponse(
                    text="本轮 Skill 只读阶段已达到上限，请继续发送消息后再处理。"
                )
                outcome = WorkflowExecutionOutcome(
                    response=response,
                    last_error_code="PHASE_LIMIT_REACHED",
                    terminal_reason="PHASE_LIMIT_REACHED",
                    tool_call_count=budget.tool_call_count,
                    mutation_seen=budget.mutation_seen,
                    phase_steps=budget.phase_steps,
                )
                if current is not None:
                    current = current.model_copy(
                        update={
                            "last_error_code": "PHASE_LIMIT_REACHED",
                            "terminal_reason": "PHASE_LIMIT_REACHED",
                        }
                    )
                    await self._save_workflow(turn_context, current)
                break
            outcome = await self._runtime.run_with_outcome(
                agent=self,
                allowed_names=allowed_names,
                turn_context=turn_context,
                user_text=user_text,
                external_message_id=external_message_id,
                grounding=grounding,
                additional_system_context=(
                    _workflow_system_context(selection.system_context, current)
                    if selection is not None
                    else None
                ),
                stop_after_successful_tools=(
                    selection.workflow.stop_after_success if selection is not None else None
                ),
                turn_budget=budget,
            )
            response = outcome.response
            if selection is None or self._skill_routing_mode == "off":
                break
            assert current is not None and active_phase is not None
            succeeded = bool(outcome.successful_capabilities)
            if not succeeded and self._coordinator.can_retry(active_phase, current.phase_attempts):
                current = current.model_copy(update={"phase_attempts": current.phase_attempts + 1})
                continue
            transition = self._transitions.transition(
                state=current,
                workflow=selection.workflow,
                event=(
                    WorkflowTransitionEvent.CAPABILITY_SUCCESS
                    if succeeded
                    else WorkflowTransitionEvent.CAPABILITY_FAILURE
                ),
                evidence_refs=outcome.evidence_refs,
                error_code=outcome.last_error_code,
                terminal_reason=outcome.terminal_reason,
            )
            current = transition.state
            await self._save_workflow(turn_context, current)
            if (
                current is not None
                and current.status is WorkflowStatus.AWAITING_USER
                and current.phase == "collect-reason"
            ):
                waiting_phase = selection.workflow.phase(current.phase)
                response = AssistantTextResponse(
                    text=_phase_input_hint(
                        waiting_phase.input_parser
                        if waiting_phase is not None and waiting_phase.input_parser is not None
                        else "",
                        repeated=False,
                    )
                )
                break
            if current is None or current.status is not WorkflowStatus.ACTIVE:
                break
            active_phase = selection.workflow.phase(current.phase)
            if active_phase is None or not self._coordinator.can_continue(active_phase, budget):
                break
            allowed_names = role_allowed_names.intersection(active_phase.capabilities)
            grounding = self._grounding_policy.decide(user_text, available_tools=allowed_names)
        assert outcome is not None
        if route is not None:
            comparison = HybridRouteComparison.compare(
                structured_workflow=selection.workflow.name if selection else route.workflow_name,
                legacy_workflow=(
                    legacy_selection.workflow.name if legacy_selection is not None else None
                ),
            )
            logging.getLogger(__name__).info(
                "assistant_workflow_routed",
                extra={
                    "skill_name": selection.skill.name if selection else None,
                    "workflow_name": selection.workflow.name if selection else None,
                    "workflow_phase": "execute",
                    "route_action": route.action.value,
                    "route_confidence": route.confidence,
                    "fallback_mode": self._skill_routing_mode,
                    "allowed_capabilities": sorted(allowed_names),
                    "legacy_workflow_name": comparison.legacy_workflow,
                    "route_matched_legacy": comparison.matched,
                    "route_difference_type": comparison.difference_type.value,
                    "terminal_reason": outcome.terminal_reason,
                },
            )
        return response

    async def _save_workflow(
        self, turn_context: AgentTurnContext, workflow: WorkflowRunState | None
    ) -> None:
        if self._workflow_state_service is None:
            return
        context = turn_context.tool_context
        await self._workflow_state_service.save(
            identity=PlatformIdentity.create(
                PlatformType(context.platform_type), context.platform_user_id
            ),
            conversation_id=context.conversation_id,
            session=turn_context.session_state,
            workflow=workflow,
        )

    def build_messages(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        working_context: str | None = None,
        active_role: RoleCode | None = None,
    ) -> tuple[AssistantMessage, ...]:
        role_prompt = (
            _ROLE_PROMPTS[active_role]
            if active_role is not None and self._skill_routing_mode == "off"
            else ""
        )
        base_prompt = (
            f"{COMMON_PROMPT}{PROCUREMENT_AGENT_PROMPT}{role_prompt}"
            if self._skill_routing_mode == "off"
            else f"{COMMON_PROMPT}{_SKILL_RUNTIME_PROMPT}"
        )
        system = AssistantMessage(
            role="system",
            content=(
                f"{base_prompt}"
                f"当前激活角色:{active_role.value if active_role else 'UNKNOWN'}; "
                f"当前时区:{context.timezone_name}。"
            ),
        )
        context_messages = (
            (AssistantMessage(role="system", content=working_context),) if working_context else ()
        )
        # Fault-guidance documents are no longer force-injected into every prompt. They may
        # still be loaded for explicitly requested, read-only guidance flows, but ordinary
        # procurement conversations must receive only the current workflow context.
        return (system, *context_messages, *history)

    async def handle_content(
        self,
        *,
        content: str,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
        retry_count: int,
    ) -> AssistantResponse | None:
        del user_text, retry_count
        await self._session_service.append(
            identity=PlatformIdentity.create(
                PlatformType(context.platform_type), context.platform_user_id
            ),
            conversation_id=context.conversation_id,
            external_message_id=f"assistant:{external_message_id}",
            sender=AgentMessageSender.AGENT,
            content=content,
        )
        return AssistantTextResponse(text=content)

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        return await self._result_presenter.present(
            result=result,
            context=context,
            external_message_id=external_message_id,
        )


def _selected_candidate_inputs(
    turn_context: AgentTurnContext, parsed_inputs: Mapping[str, JsonValue]
) -> dict[str, JsonValue] | None:
    index = parsed_inputs.get("candidate_index")
    session = turn_context.session_state
    if not isinstance(index, int) or session is None:
        return None
    candidates = tuple(
        item
        for item in session.last_recommendations
        if item.kind in {"PRODUCT_RECOMMENDATION", "ITEM_PRODUCT_RECOMMENDATION"}
    )
    if index < 1 or index > len(candidates):
        return None
    reference = candidates[index - 1]
    raw = session.collected_data.get(f"recommendation:product:{reference.reference_id}")
    if not isinstance(raw, str):
        return None
    try:
        selected = SelectedProduct.model_validate_json(raw)
    except ValueError:
        return None
    inputs: dict[str, JsonValue] = {
        "candidate_reference": reference.reference_id,
        "selected_candidate_json": selected.model_dump_json(),
    }
    quantity = parsed_inputs.get("candidate_quantity")
    if isinstance(quantity, int):
        inputs["candidate_quantity"] = quantity
    return _with_candidate_draft_items(inputs)


def _with_candidate_draft_items(
    inputs: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    raw = inputs.get("selected_candidate_json")
    quantity = inputs.get("candidate_quantity")
    if not isinstance(raw, str):
        return dict(inputs)
    try:
        selected = SelectedProduct.model_validate_json(raw)
    except ValueError:
        return dict(inputs)
    existing_raw = inputs.get("items_json")
    if isinstance(existing_raw, str):
        try:
            existing = json.loads(existing_raw)
        except ValueError:
            existing = None
        if isinstance(existing, list) and len(existing) == 1 and isinstance(existing[0], dict):
            item = dict(existing[0])
            item.update(
                {
                    "item_name": selected.item_name,
                    "equipment_category_id": selected.equipment_category_id,
                    "equipment_model_id": selected.equipment_model_id,
                    "brand": selected.brand,
                    "model": selected.model,
                }
            )
            merged = dict(inputs)
            merged["items_json"] = json.dumps([item], ensure_ascii=False)
            return merged
    if not isinstance(quantity, int):
        return dict(inputs)
    item = {
        "item_name": selected.item_name,
        "quantity": str(quantity),
        "item_kind": "EQUIPMENT",
        "equipment_category_id": selected.equipment_category_id,
        "equipment_model_id": selected.equipment_model_id,
        "brand": selected.brand,
        "model": selected.model,
    }
    merged = dict(inputs)
    merged["items_json"] = json.dumps([item], ensure_ascii=False)
    return merged


def _workflow_system_context(base: str, state: WorkflowRunState | None) -> str:
    if state is None or (not state.collected_inputs and not state.evidence_refs):
        return base
    context = dict(state.collected_inputs)
    if state.evidence_refs:
        context["evidence_refs"] = list(state.evidence_refs)
    return (
        f"{base}\n<workflow_inputs>"
        f"{json.dumps(context, ensure_ascii=False, sort_keys=True)}"
        "</workflow_inputs>\n只能使用这些已解析输入，不得补写缺失字段。"
    )


def _is_explicit_new_purchase(text: str) -> bool:
    return text.strip().startswith(("我要买", "我要采购", "我要购买", "帮我买", "帮我采购"))


_ROLE_PROMPTS: dict[RoleCode, str] = {
    RoleCode.APPLICANT: APPLICANT_PROMPT,
    RoleCode.BUILDING_MANAGER: BUILDING_MANAGER_PROMPT,
    RoleCode.PURCHASER: PURCHASER_PROMPT,
    RoleCode.WAREHOUSE_MANAGER: WAREHOUSE_PROMPT,
}

_SKILL_RUNTIME_PROMPT = """
你只执行当前注入的角色 Skill 和 workflow。业务事实必须来自允许能力的证据，不得猜测
单据、历史、产品、供应商、金额或资格。每轮最多执行一个写能力；只读能力不能触发提交、
审批、驳回、采购执行或入库。正式状态流转只能由后端和飞书正式卡片完成。能力失败时说明
真实错误，不得伪造成功，也不得改道到未声明能力。
"""


def _allowed_phase_intents(parser_name: str) -> tuple[str, ...]:
    return {
        "applicant-items": ("SAVE_ITEMS",),
        "applicant-confirmed-items": ("CONFIRM_ITEMS",),
        "applicant-product-name": ("SEARCH_PRODUCT",),
        "applicant-candidate-selection": ("SELECT_ONLY", "SELECT_AND_DRAFT", "CANCEL"),
        "applicant-application-reason": ("SAVE_APPLICATION_REASON",),
    }.get(parser_name, ())


def _phase_input_hint(parser_name: str, *, repeated: bool) -> str:
    prefix = "仍无法识别。" if repeated else "需要补充信息。"
    examples = {
        "applicant-items": "请按“2个风扇、4个电容”提供每项数量。",
        "applicant-confirmed-items": "请按“2个风扇、4个电容都确认更换”回复。",
        "applicant-product-name": "请提供要推荐的物品名称，例如“推荐控制电源品牌型号”。",
        "applicant-candidate-selection": "请回复候选序号，例如“第一个”或“用第一个创建草稿”。",
        "applicant-application-reason": "请简要说明本次采购的申请原因或用途。",
    }
    return f"{prefix}{examples.get(parser_name, '请重新描述当前步骤需要的信息。')}"
