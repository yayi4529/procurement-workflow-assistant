from typing import cast

import pytest

from procurement_platform.adapters.feishu.fake_client import FakeFeishuClient
from procurement_platform.application.applicant.action_router import ApplicantActionRouter
from procurement_platform.application.inbound.card_interaction_handler import (
    BaseCardInteractionHandler,
)
from procurement_platform.domain.inbound_event import CardInteractionEvent
from procurement_platform.domain.interaction import InteractionView, PlainTextBlock


class ApplicantRouterStub:
    def __init__(self) -> None:
        self.calls = 0

    async def route(self, event: CardInteractionEvent) -> InteractionView:
        del event
        self.calls += 1
        return InteractionView(title="提交成功", elements=(PlainTextBlock(text="正式业务已完成"),))


class FailingObserver:
    def __init__(self) -> None:
        self.calls = 0

    async def completed(self, *, platform_user_id: str) -> None:
        del platform_user_id
        self.calls += 1
        raise RuntimeError("observer unavailable")


@pytest.mark.asyncio
async def test_completion_observer_failure_does_not_rollback_formal_card_result() -> None:
    router = ApplicantRouterStub()
    observer = FailingObserver()
    handler = BaseCardInteractionHandler(
        FakeFeishuClient(),
        applicant_router=cast(ApplicantActionRouter, router),
        completion_observer=observer,
    )
    event = CardInteractionEvent(
        event_id="TEST-CARD-COMPLETE",
        external_user_id="ou_test",
        message_id="om_test",
        action_id="applicant.confirm_submit",
    )

    view = await handler.handle(event)

    assert view.title == "提交成功"
    assert router.calls == 1
    assert observer.calls == 1


@pytest.mark.asyncio
async def test_non_terminal_applicant_card_does_not_notify_completion_observer() -> None:
    router = ApplicantRouterStub()
    observer = FailingObserver()
    handler = BaseCardInteractionHandler(
        FakeFeishuClient(),
        applicant_router=cast(ApplicantActionRouter, router),
        completion_observer=observer,
    )
    event = CardInteractionEvent(
        event_id="TEST-CARD-SAVE",
        external_user_id="ou_test",
        message_id="om_test",
        action_id="applicant.save_fields",
    )

    view = await handler.handle(event)

    assert view.title == "提交成功"
    assert observer.calls == 0
