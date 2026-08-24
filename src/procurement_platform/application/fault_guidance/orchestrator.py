# ruff: noqa: E501, RUF001

import json
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from procurement_platform.domain.assistant import AssistantMessage
from procurement_platform.domain.assistant_errors import LlmInvalidResponseError
from procurement_platform.domain.enums import FaultAction, PurchaseItemKind
from procurement_platform.domain.fault_guidance import (
    CandidateItem,
    FaultContext,
    FaultDecision,
)
from procurement_platform.ports.llm_client import LlmClient

FAULT_GUIDANCE_SYSTEM_PROMPT = """你是故障采购引导助手，帮助用户从设备异常逐步形成可靠采购需求。
你不是故障诊断系统。不得猜测品牌、型号、数量或规格，也不得把知识内容当作现场事实。
每轮只能选择 ANSWER、ASK、PROPOSE_ITEM、DIRECT_TO_PROCUREMENT。
状态转换规则：
- fault_state.candidate_items 为空时，不得因“是/确认”等简短回复选择 DIRECT_TO_PROCUREMENT。
- 只有新整理出候选项或用户修改了候选项时才选择 PROPOSE_ITEM，并要求用户确认。
- workflow_stage=AWAITING_CANDIDATE_CONFIRMATION 且用户明确回复“是、是的、确认、对、可以、继续、按这个”时，必须选择 DIRECT_TO_PROCUREMENT；不得再次返回相同的 PROPOSE_ITEM。
- 上述确认场景不得修改、重复生成或猜测 candidate_items；candidate_items 返回空数组，服务会使用 fault_state 中已确认的候选项。
- 用户否定或修改数量或物品时，不得选择 DIRECT_TO_PROCUREMENT，应更新候选并选择 PROPOSE_ITEM。用户无需提供计量单位；候选项缺少 unit 时由服务使用默认单位“个”。
已确认的信息不要重复询问；信息不足时只问一个最关键问题。
数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。用户明确说“一个/1个”时，quantity 必须输出为 1。
CandidateItem 只是候选，不代表正式采购，也不得创建采购单。
只返回符合给定 JSON 结构的对象，不要返回额外字段或 Markdown。"""


class _CandidateItemOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_kind: PurchaseItemKind
    item_name: str
    quantity: Decimal | None = None
    unit: str | None = None
    brand: str | None = None
    model: str | None = None
    item_evidence: str | None = None
    quantity_evidence: str | None = None


class _FaultDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: FaultAction = Field(
        description=(
            "Use PROPOSE_ITEM only for a new or changed candidate. Use DIRECT_TO_PROCUREMENT "
            "when workflow_stage is AWAITING_CANDIDATE_CONFIRMATION and the user affirms it."
        )
    )
    reply: str = Field(min_length=1)
    issue_summary: str | None = None
    confirmed_facts_updates: dict[str, Any] = Field(default_factory=dict)
    knowledge_refs_add: list[str] = Field(default_factory=list)
    candidate_items: list[_CandidateItemOutput] = Field(default_factory=list)


class FaultGuidanceOrchestrator:
    def __init__(self, llm_client: LlmClient) -> None:
        self._llm_client = llm_client

    async def decide(self, context: FaultContext) -> FaultDecision:
        turn = await self._llm_client.complete(
            messages=self._messages(context),
            tools=(),
            tool_choice=None,
        )
        if turn.tool_calls or turn.content is None or not turn.content.strip():
            raise LlmInvalidResponseError(
                "fault guidance LLM must return one structured JSON object"
            )
        try:
            output = _FaultDecisionOutput.model_validate_json(self._strip_json_fence(turn.content))
        except ValidationError as exc:
            raise LlmInvalidResponseError("invalid fault guidance structured output") from exc
        self._validate_grounding(context, output)
        return FaultDecision(
            action=output.action,
            reply=output.reply,
            issue_summary=output.issue_summary,
            confirmed_facts_updates=output.confirmed_facts_updates,
            knowledge_refs_add=output.knowledge_refs_add,
            candidate_items=[
                CandidateItem(
                    item_kind=item.item_kind,
                    item_name=item.item_name,
                    quantity=item.quantity,
                    unit=item.unit,
                    brand=item.brand,
                    model=item.model,
                    item_evidence=item.item_evidence,
                    quantity_evidence=item.quantity_evidence,
                )
                for item in output.candidate_items
            ],
        )

    @staticmethod
    def structured_output_schema() -> dict[str, Any]:
        return _FaultDecisionOutput.model_json_schema()

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        stripped = content.strip()
        if not stripped.startswith("```") or not stripped.endswith("```"):
            return stripped
        lines = stripped.splitlines()
        if len(lines) < 3 or lines[0].strip().casefold() not in {"```", "```json"}:
            return stripped
        return "\n".join(lines[1:-1]).strip()

    @staticmethod
    def _validate_grounding(context: FaultContext, output: _FaultDecisionOutput) -> None:
        conversation_text = " ".join(item.content or "" for item in context.conversation_messages)
        user_evidence = f"{conversation_text} {context.user_message}"
        confirmed_evidence = json.dumps(
            context.fault_state.confirmed_facts,
            ensure_ascii=False,
            default=str,
        )
        for item in output.candidate_items:
            for field_name, value in (("brand", item.brand), ("model", item.model)):
                if (
                    value is not None
                    and value not in user_evidence
                    and value not in confirmed_evidence
                ):
                    raise LlmInvalidResponseError(
                        f"candidate {field_name} is not grounded in confirmed context"
                    )
            if item.quantity is None:
                continue
            quantity_text = str(item.quantity)
            evidence = item.quantity_evidence
            if evidence in {"USER_CONFIRMED", "USER_EXPLICIT_REQUEST"}:
                grounded = quantity_text in user_evidence or quantity_text in confirmed_evidence
            elif evidence == "BACKEND_FACT":
                grounded = quantity_text in confirmed_evidence
            else:
                grounded = True
            if not grounded:
                raise LlmInvalidResponseError(
                    "candidate quantity is not grounded in its declared evidence"
                )

    @staticmethod
    def _messages(context: FaultContext) -> tuple[AssistantMessage, ...]:
        runtime_context = {
            "user_message": context.user_message,
            "workflow_stage": (
                "AWAITING_CANDIDATE_CONFIRMATION"
                if context.fault_state.candidate_items
                else "COLLECTING_FAULT_FACTS"
            ),
            "source_asset": (
                {
                    "asset_ref": f"asset:{context.source_asset.asset_id}",
                    "asset_name": context.source_asset.asset_name,
                    "equipment_category": context.source_asset.category.category_code,
                }
                if context.source_asset is not None
                else None
            ),
            "fault_state": {
                "source_asset_ref": context.fault_state.source_asset_ref,
                "issue_summary": context.fault_state.issue_summary,
                "confirmed_facts": context.fault_state.confirmed_facts,
                "candidate_items": [
                    {
                        "item_kind": (item.item_kind.value if item.item_kind is not None else None),
                        "item_name": item.item_name,
                        "quantity": str(item.quantity) if item.quantity is not None else None,
                        "unit": item.unit,
                        "brand": item.brand,
                        "model": item.model,
                        "item_evidence": item.item_evidence,
                        "quantity_evidence": item.quantity_evidence,
                    }
                    for item in context.fault_state.candidate_items
                ],
                "knowledge_refs": context.fault_state.knowledge_refs,
            },
            "knowledge_results": [
                {
                    "knowledge_id": item.knowledge_id,
                    "title": item.title,
                    "equipment_category": item.equipment_category,
                    "risk_level": item.risk_level,
                    "matched_aliases": item.matched_aliases,
                    "content": item.content,
                }
                for item in context.knowledge_results
            ],
            "conversation_messages": [
                {"role": item.role, "content": item.content}
                for item in context.conversation_messages
            ],
            "required_output_schema": _FaultDecisionOutput.model_json_schema(),
        }
        return (
            AssistantMessage(role="system", content=FAULT_GUIDANCE_SYSTEM_PROMPT),
            AssistantMessage(
                role="user",
                content=json.dumps(runtime_context, ensure_ascii=False, default=str),
            ),
        )
