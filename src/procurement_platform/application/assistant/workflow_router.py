# ruff: noqa: RUF001

import json
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from procurement_platform.application.assistant.role_skills import RoleSkill
from procurement_platform.application.assistant.workflow_state import WorkflowRunState
from procurement_platform.domain.assistant import AssistantMessage
from procurement_platform.domain.enums import RoleCode
from procurement_platform.ports.llm_client import LlmClient


class WorkflowRouteAction(StrEnum):
    START = "START"
    CONTINUE = "CONTINUE"
    SWITCH = "SWITCH"
    CLARIFY = "CLARIFY"
    NO_TOOL = "NO_TOOL"


class WorkflowRouteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: WorkflowRouteAction
    workflow_name: str | None = None
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    reason_code: str

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: object) -> object:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "HIGH" if value >= 0.8 else "MEDIUM" if value >= 0.5 else "LOW"
        return value


class WorkflowRouter(Protocol):
    async def route(
        self,
        *,
        user_text: str,
        role: RoleCode,
        skill: RoleSkill,
        current: WorkflowRunState | None,
    ) -> WorkflowRouteOutput: ...


class LlmWorkflowRouter:
    def __init__(self, llm: LlmClient) -> None:
        self._llm = llm

    async def route(
        self,
        *,
        user_text: str,
        role: RoleCode,
        skill: RoleSkill,
        current: WorkflowRunState | None,
    ) -> WorkflowRouteOutput:
        deterministic = self._deterministic(user_text, role, skill, current)
        if deterministic is not None:
            return deterministic
        candidates = "\n".join(
            f"- {item.name}: {item.description}" for item in skill.workflows.values()
        )
        messages = (
            AssistantMessage(
                role="system",
                content=(
                    "你是采购 workflow 路由器，只做任务分类，不回答业务问题，也不调用工具。"
                    "workflow_name 只能取候选名称。新任务用 START；明确换任务用 SWITCH；"
                    "需要沿用当前任务用 CONTINUE；业务意图不明确用 CLARIFY；问候或一般流程说明"
                    "用 NO_TOOL。只输出 JSON，字段为 action、workflow_name、confidence、"
                    "reason_code。"
                    f"\n当前角色: {role.value}"
                    f"\n当前 workflow: {current.workflow_name if current else 'NONE'}"
                    f"\n候选:\n{candidates}"
                ),
            ),
            AssistantMessage(role="user", content=user_text),
        )
        try:
            turn = await self._llm.complete(messages=messages, tools=())
            if turn.tool_calls or turn.content is None:
                raise ValueError("router returned no JSON")
            output = WorkflowRouteOutput.model_validate(_load_json_object(turn.content))
        except Exception:
            return WorkflowRouteOutput(
                action=WorkflowRouteAction.CLARIFY,
                confidence="LOW",
                reason_code="ROUTER_INVALID_RESPONSE",
            )
        if output.workflow_name is not None and output.workflow_name not in skill.workflows:
            return WorkflowRouteOutput(
                action=WorkflowRouteAction.CLARIFY,
                confidence="LOW",
                reason_code="UNKNOWN_WORKFLOW",
            )
        if output.confidence == "LOW" and output.action not in {
            WorkflowRouteAction.NO_TOOL,
            WorkflowRouteAction.CLARIFY,
        }:
            return output.model_copy(update={"action": WorkflowRouteAction.CLARIFY})
        return output

    @staticmethod
    def _deterministic(
        text: str,
        role: RoleCode,
        skill: RoleSkill,
        current: WorkflowRunState | None,
    ) -> WorkflowRouteOutput | None:
        normalized = "".join(text.strip().split()).rstrip("。.!！")
        if normalized in {"重新开始", "清空上下文", "新会话", "开始新需求"}:
            return WorkflowRouteOutput(
                action=WorkflowRouteAction.SWITCH,
                confidence="HIGH",
                reason_code="EXPLICIT_RESET",
            )
        if normalized in {"你好", "您好", "你能做什么", "帮助", "采购流程是什么"}:
            return WorkflowRouteOutput(
                action=WorkflowRouteAction.NO_TOOL,
                confidence="HIGH",
                reason_code="GENERAL_HELP",
            )
        if (
            current is not None
            and current.role is role
            and current.status.value.startswith("AWAITING")
        ):
            if normalized and len(normalized) <= 80:
                return WorkflowRouteOutput(
                    action=WorkflowRouteAction.CONTINUE,
                    workflow_name=current.workflow_name,
                    confidence="HIGH",
                    reason_code="PENDING_WORKFLOW_REPLY",
                )
        return None


def _load_json_object(content: str) -> object:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return json.loads(stripped)
