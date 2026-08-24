# ruff: noqa: RUF001

import json
import re
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from procurement_platform.domain.assistant import AssistantMessage
from procurement_platform.domain.assistant_session import JsonValue
from procurement_platform.ports.llm_client import LlmClient


class PhaseParseResult(StrEnum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    NEW_GOAL = "NEW_GOAL"


class PhaseParseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result: PhaseParseResult
    intent: str | None = None
    collected_inputs: dict[str, JsonValue] = Field(default_factory=dict)
    missing_inputs: tuple[str, ...] = ()
    reason_code: str


class PhaseInputParser(Protocol):
    async def parse(
        self, *, parser_name: str, user_text: str, allowed_intents: tuple[str, ...]
    ) -> PhaseParseOutput: ...


class ApplicantPhaseInputParser:
    """Parse constrained applicant replies without exposing business capabilities."""

    def __init__(self, llm: LlmClient) -> None:
        self._llm = llm

    async def parse(
        self, *, parser_name: str, user_text: str, allowed_intents: tuple[str, ...] = ()
    ) -> PhaseParseOutput:
        deterministic = self._deterministic(parser_name, user_text)
        if deterministic.result is not PhaseParseResult.NO_MATCH:
            return deterministic
        return await self._llm_fallback(parser_name, user_text, allowed_intents)

    @staticmethod
    def _deterministic(parser_name: str, text: str) -> PhaseParseOutput:
        normalized = "".join(text.strip().split())
        if normalized in {"重新开始", "清空上下文", "新会话", "开始新需求"}:
            return PhaseParseOutput(result="NEW_GOAL", reason_code="EXPLICIT_RESET")
        if _looks_like_new_purchase(normalized, parser_name):
            return PhaseParseOutput(result="NEW_GOAL", reason_code="EXPLICIT_NEW_PURCHASE")
        if parser_name == "applicant-application-reason":
            reason = re.sub(r"^(?:申请原因|采购原因|用途)(?:是|为|[:：])?", "", text.strip())
            if reason:
                return PhaseParseOutput(
                    result="MATCH",
                    intent="SAVE_APPLICATION_REASON",
                    collected_inputs={"application_reason": reason},
                    reason_code="APPLICATION_REASON_PARSED",
                )
            return PhaseParseOutput(
                result="AMBIGUOUS",
                intent="SAVE_APPLICATION_REASON",
                missing_inputs=("application_reason",),
                reason_code="APPLICATION_REASON_MISSING",
            )
        if parser_name in {"applicant-items", "applicant-confirmed-items"}:
            quantity_only = re.fullmatch(
                r"(?:数量)?(\d+|一|二|两|三|四|五|六|七|八|九|十)(?:个|台|只|块|套|件|组|支|根)?",
                normalized,
            )
            if parser_name == "applicant-items" and quantity_only is not None:
                return PhaseParseOutput(
                    result="MATCH",
                    intent="SAVE_ITEMS",
                    collected_inputs={"candidate_quantity": _quantity(quantity_only.group(1))},
                    reason_code="CANDIDATE_QUANTITY_PARSED",
                )
            items = _parse_items(text)
            if items:
                missing = tuple(
                    str(item["item_name"]) for item in items if item["quantity"] is None
                )
                return PhaseParseOutput(
                    result="AMBIGUOUS" if missing else "MATCH",
                    intent="CONFIRM_ITEMS"
                    if parser_name.endswith("confirmed-items")
                    else "SAVE_ITEMS",
                    collected_inputs={"items_json": json.dumps(items, ensure_ascii=False)},
                    missing_inputs=missing,
                    reason_code="ITEMS_MISSING_QUANTITY" if missing else "ITEMS_PARSED",
                )
        if parser_name == "applicant-product-name":
            match = re.search(
                r"(?:推荐|查询|看看|查一下)?([^，。,.]{2,30}?)(?:的)?(?:品牌|型号|产品)", text
            )
            if match:
                return PhaseParseOutput(
                    result="MATCH",
                    intent="SEARCH_PRODUCT",
                    collected_inputs={"product_name": match.group(1).strip()},
                    reason_code="PRODUCT_NAME_PARSED",
                )
        if parser_name == "applicant-candidate-selection":
            if normalized in {"算了", "取消", "不用了", "不需要"}:
                return PhaseParseOutput(
                    result="MATCH", intent="CANCEL", reason_code="SELECTION_CANCELLED"
                )
            index = _candidate_index(normalized)
            if index is not None:
                write_requested = any(
                    term in normalized for term in ("采购", "购买", "写入草稿", "创建草稿", "就买")
                )
                collected: dict[str, JsonValue] = {"candidate_index": index}
                quantity = _selection_quantity(normalized)
                if quantity is not None:
                    collected["candidate_quantity"] = quantity
                return PhaseParseOutput(
                    result="MATCH",
                    intent="SELECT_AND_DRAFT" if write_requested else "SELECT_ONLY",
                    collected_inputs=collected,
                    reason_code="CANDIDATE_SELECTED",
                )
        return PhaseParseOutput(result="NO_MATCH", reason_code="DETERMINISTIC_NO_MATCH")

    async def _llm_fallback(
        self, parser_name: str, text: str, allowed_intents: tuple[str, ...]
    ) -> PhaseParseOutput:
        messages = (
            AssistantMessage(
                role="system",
                content=(
                    "你是采购 workflow 阶段输入解析器，不回答用户、不调用工具。"
                    "只输出 JSON: result、intent、collected_inputs、missing_inputs、reason_code。"
                    "result 只能是 MATCH、NO_MATCH、AMBIGUOUS、NEW_GOAL。"
                    f"当前 parser: {parser_name}; 允许 intent: "
                    f"{','.join(allowed_intents) or 'NONE'}。"
                    "不得补写用户未提供的数量、品牌、型号或候选序号。"
                ),
            ),
            AssistantMessage(role="user", content=text),
        )
        try:
            turn = await self._llm.complete(messages=messages, tools=())
            if turn.tool_calls or turn.content is None:
                raise ValueError("phase parser returned no JSON")
            parsed = PhaseParseOutput.model_validate(_load_json_object(turn.content))
            if (
                parsed.intent is not None
                and allowed_intents
                and parsed.intent not in allowed_intents
            ):
                raise ValueError("phase parser returned forbidden intent")
            return parsed
        except (ValueError, ValidationError, json.JSONDecodeError):
            return PhaseParseOutput(result="AMBIGUOUS", reason_code="LLM_PHASE_PARSE_INVALID")


def _parse_items(text: str) -> list[dict[str, str | int | None]]:
    normalized = re.sub(
        r"^(?:我要买|我要采购|我要购买|帮我买|帮我采购|购买|采购|更换|需要)",
        "",
        text.strip(),
    )
    normalized = re.sub(r"(?:都)?(?:已)?确认(?:损坏|需要更换)?", "", normalized)
    normalized = re.sub(r"[，、；;和及]", ",", normalized)
    matches = re.findall(
        r"(?:(\d+|一|二|两|三|四|五|六|七|八|九|十)\s*(?:个|台|只|块|套|件|组|支|根)?\s*)?"
        r"([\u4e00-\u9fffA-Za-z0-9_-]{2,30}?)(?=,|都|已|确认|损坏|需要|$)",
        normalized,
    )
    items: list[dict[str, str | int | None]] = []
    for raw_quantity, raw_name in matches:
        name = re.sub(r"^(?:我要买|我要采购|购买|采购|更换|需要)", "", raw_name).strip()
        name = re.sub(r"(?:都)?(?:确认)?(?:损坏|需要更换)$", "", name).strip()
        if not name:
            continue
        items.append(
            {
                "item_name": name,
                "quantity": _quantity(raw_quantity),
                "item_kind": _item_kind(name),
            }
        )
    return items


def _item_kind(name: str) -> str:
    component_terms = ("风扇", "电容", "电池", "模块", "滤芯", "轴承", "保险丝")
    return "COMPONENT" if any(term in name for term in component_terms) else "EQUIPMENT"


def _quantity(value: str) -> int | None:
    if not value:
        return None
    if value.isdigit():
        return int(value)
    return {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }.get(value)


def _candidate_index(text: str) -> int | None:
    match = re.search(r"第?(\d+|一|二|三|四|五)个?", text)
    if match is None:
        return None
    return _quantity(match.group(1))


def _selection_quantity(text: str) -> int | None:
    match = re.search(
        r"(?:数量|买|采购|购买)(\d+|一|二|两|三|四|五|六|七|八|九|十)"
        r"(?:个|台|只|块|套|件|组|支|根)?",
        text,
    )
    return _quantity(match.group(1)) if match is not None else None


def _looks_like_new_purchase(text: str, parser_name: str) -> bool:
    if parser_name == "applicant-items":
        return False
    return text.startswith(("我要买", "我要采购", "我要购买", "帮我买", "帮我采购"))


def _load_json_object(content: str) -> object:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return json.loads(stripped)
