import logging

from procurement_platform.application.applicant.action_router import ApplicantActionRouter
from procurement_platform.application.assistant.workflow_completion import (
    WorkflowCompletionObserver,
)
from procurement_platform.application.building_manager.action_router import (
    BuildingManagerActionRouter,
)
from procurement_platform.application.purchaser.action_router import PurchaserActionRouter
from procurement_platform.application.warehouse.action_router import WarehouseActionRouter
from procurement_platform.domain.errors import UnsupportedCardActionError
from procurement_platform.domain.inbound_event import CardInteractionEvent
from procurement_platform.domain.interaction import InteractionView, PlainTextBlock
from procurement_platform.ports.channel import ChannelClient

logger = logging.getLogger(__name__)


class BaseCardInteractionHandler:
    def __init__(
        self,
        channel_client: ChannelClient,
        applicant_router: ApplicantActionRouter | None = None,
        building_manager_router: BuildingManagerActionRouter | None = None,
        purchaser_router: PurchaserActionRouter | None = None,
        warehouse_router: WarehouseActionRouter | None = None,
        completion_observer: WorkflowCompletionObserver | None = None,
    ) -> None:
        self._channel_client = channel_client
        self._applicant_router = applicant_router
        self._building_manager_router = building_manager_router
        self._purchaser_router = purchaser_router
        self._warehouse_router = warehouse_router
        self._completion_observer = completion_observer

    async def handle(self, event: CardInteractionEvent) -> InteractionView:
        if event.action_id.startswith("applicant.") and self._applicant_router is not None:
            view = await self._applicant_router.route(event)
            if event.action_id in {"applicant.confirm_submit", "applicant.confirm_resubmit"}:
                try:
                    if self._completion_observer is not None:
                        await self._completion_observer.completed(
                            platform_user_id=event.external_user_id
                        )
                except Exception:
                    logger.exception("assistant_workflow_completion_observer_failed")
            return view
        if event.action_id.startswith("purchaser.") and self._purchaser_router is not None:
            return await self._purchaser_router.route(event)
        if event.action_id.startswith("warehouse.") and self._warehouse_router is not None:
            return await self._warehouse_router.route(event)
        if (
            event.action_id.startswith("building_manager.")
            and self._building_manager_router is not None
        ):
            return await self._building_manager_router.route(event)
        if event.action_id != "foundation.echo":
            raise UnsupportedCardActionError("不支持的卡片操作")
        view = InteractionView(
            title="基础链路验证",
            elements=(PlainTextBlock(text="卡片操作已收到。"),),
        )
        return view
