import pytest

from procurement_platform.application.fault_guidance.intent_router import FaultIntentRouter


class StubClassifier:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.messages: list[str] = []

    async def is_fault_intent(self, text: str) -> bool:
        self.messages.append(text)
        return self.result


@pytest.mark.asyncio
async def test_ambiguous_fault_language_uses_classifier() -> None:
    classifier = StubClassifier(True)

    result = await FaultIntentRouter(classifier).is_fault_intent("冷机运行有点不对劲")

    assert result is True
    assert classifier.messages == ["冷机运行有点不对劲"]


@pytest.mark.asyncio
async def test_clear_fault_and_clear_exclusion_do_not_spend_classifier_call() -> None:
    classifier = StubClassifier(True)
    router = FaultIntentRouter(classifier)

    assert await router.is_fault_intent("UPS风扇不转") is True
    assert await router.is_fault_intent("查询UPS历史报警") is False
    assert classifier.messages == []
