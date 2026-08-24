"""Hybrid fault-intent routing without requiring a command prefix."""

# ruff: noqa: RUF001

import logging
from typing import Protocol

from procurement_platform.domain.assistant import AssistantMessage
from procurement_platform.domain.assistant_errors import AssistantError
from procurement_platform.ports.llm_client import LlmClient

logger = logging.getLogger(__name__)

_STRONG_FAULT_TERMS = (
    "报警",
    "告警",
    "故障",
    "异常",
    "失效",
    "不转",
    "不制冷",
    "漏水",
    "过温",
    "高温",
    "异响",
    "fault",
    " fail",
)
_NON_FAULT_TERMS = (
    "采购报警器",
    "购买报警器",
    "买报警器",
    "报警器采购",
    "查询报警",
    "查看报警",
    "报警记录",
    "历史报警",
    "告警记录",
    "历史告警",
    "故障知识",
    "故障统计",
)
_AMBIGUOUS_TERMS = (
    "不对劲",
    "不正常",
    "有问题",
    "声音不对",
    "温度偏高",
    "运行不稳",
)


class FaultIntentClassifier(Protocol):
    async def is_fault_intent(self, text: str) -> bool: ...


class LlmFaultIntentClassifier:
    def __init__(self, llm_client: LlmClient) -> None:
        self._llm_client = llm_client

    async def is_fault_intent(self, text: str) -> bool:
        turn = await self._llm_client.complete(
            messages=(
                AssistantMessage(
                    role="system",
                    content=(
                        "判断用户是否正在描述当前设备或环境故障。"
                        "采购请求、历史查询、知识问答不是故障引导。"
                        "只回答 FAULT 或 NON_FAULT。"
                    ),
                ),
                AssistantMessage(role="user", content=text),
            ),
            tools=(),
            tool_choice=None,
        )
        return (turn.content or "").strip().upper() == "FAULT"


class FaultIntentRouter:
    def __init__(self, classifier: FaultIntentClassifier | None = None) -> None:
        self._classifier = classifier

    async def is_fault_intent(self, text: str) -> bool:
        normalized = text.strip().casefold().rstrip("】]}）)")
        purchase_device_query = any(term in normalized for term in ("采购", "购买", "买")) and any(
            term in normalized for term in ("报警器", "告警器")
        )
        history_query = any(
            term in normalized for term in ("查询", "查看", "历史", "记录", "统计")
        ) and any(term in normalized for term in ("报警", "告警", "故障"))
        if (
            not normalized
            or purchase_device_query
            or history_query
            or any(term in normalized for term in _NON_FAULT_TERMS)
        ):
            return False
        if any(term in normalized for term in _STRONG_FAULT_TERMS):
            return True
        if self._classifier is None or not any(term in normalized for term in _AMBIGUOUS_TERMS):
            return False
        try:
            return await self._classifier.is_fault_intent(text)
        except AssistantError as exc:
            logger.warning(
                "fault_intent_classification_failed",
                extra={"error_type": type(exc).__name__},
            )
            return False
