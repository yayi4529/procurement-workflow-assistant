"""Best-effort semantic role selection for users who already own multiple roles."""

# ruff: noqa: RUF001

import json
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.domain.assistant import AssistantMessage
from procurement_platform.domain.enums import RoleCode
from procurement_platform.ports.llm_client import LlmClient

RoleIntentConfidence = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass(frozen=True, slots=True)
class RoleIntentResolution:
    role: RoleCode | None
    confidence: RoleIntentConfidence


class RoleIntentResolver(Protocol):
    async def resolve(
        self,
        *,
        user_text: str,
        allowed_roles: tuple[RoleCode, ...],
        focused_role: RoleCode,
    ) -> RoleIntentResolution: ...


class _RoleIntentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_index: int | None = Field(default=None, ge=1)
    confidence: RoleIntentConfidence


class LlmRoleIntentResolver:
    """Maps an LLM-selected index back into the backend-authorized role tuple."""

    def __init__(self, llm_client: LlmClient) -> None:
        self._llm_client = llm_client

    async def resolve(
        self,
        *,
        user_text: str,
        allowed_roles: tuple[RoleCode, ...],
        focused_role: RoleCode,
    ) -> RoleIntentResolution:
        if len(allowed_roles) < 2 or focused_role not in allowed_roles:
            return RoleIntentResolution(role=focused_role, confidence="LOW")
        candidates = "\n".join(
            f"{index}: {role.value}" for index, role in enumerate(allowed_roles, start=1)
        )
        messages = (
            AssistantMessage(
                role="system",
                content=(
                    "你只判断当前消息是否明确属于另一个工作角色。"
                    "候选仅限下方编号，不得输出角色名或新增角色。"
                    "如果当前角色可以合理处理、消息有歧义或无法判断，返回 LOW 且"
                    "selection_index 为当前角色编号。"
                    "只输出 JSON："
                    '{"selection_index":整数或null,"confidence":"HIGH|MEDIUM|LOW"}。'
                    f"\n当前角色: {focused_role.value}\n允许候选:\n{candidates}"
                ),
            ),
            AssistantMessage(role="user", content=user_text),
        )
        try:
            turn = await self._llm_client.complete(messages=messages, tools=())
            if turn.tool_calls or turn.content is None:
                return RoleIntentResolution(role=focused_role, confidence="LOW")
            output = _RoleIntentOutput.model_validate(json.loads(turn.content))
            if output.selection_index is None:
                return RoleIntentResolution(role=focused_role, confidence=output.confidence)
            index = output.selection_index - 1
            if not 0 <= index < len(allowed_roles):
                return RoleIntentResolution(role=focused_role, confidence="LOW")
            return RoleIntentResolution(role=allowed_roles[index], confidence=output.confidence)
        except Exception:
            return RoleIntentResolution(role=focused_role, confidence="LOW")


"""Deprecated text role resolver; ProcurementAgent production flow does not use it."""
