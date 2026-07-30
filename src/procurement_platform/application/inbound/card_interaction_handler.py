from procurement_platform.application.applicant.action_router import ApplicantActionRouter
from procurement_platform.application.building_manager.action_router import (
    BuildingManagerActionRouter,
)
from procurement_platform.application.purchaser.action_router import PurchaserActionRouter
from procurement_platform.application.warehouse.action_router import WarehouseActionRouter
from procurement_platform.domain.errors import UnsupportedCardActionError
from procurement_platform.domain.inbound_event import CardInteractionEvent
from procurement_platform.domain.interaction import InteractionView, PlainTextBlock
from procurement_platform.ports.channel import ChannelClient


class BaseCardInteractionHandler:
    def __init__(
        self,
        channel_client: ChannelClient,
        applicant_router: ApplicantActionRouter | None = None,
        building_manager_router: BuildingManagerActionRouter | None = None,
        purchaser_router: PurchaserActionRouter | None = None,
        warehouse_router: WarehouseActionRouter | None = None,
    ) -> None:
        self._channel_client = channel_client
        self._applicant_router = applicant_router
        self._building_manager_router = building_manager_router
        self._purchaser_router = purchaser_router
        self._warehouse_router = warehouse_router

    async def handle(self, event: CardInteractionEvent) -> None:
        if event.action_id.startswith("applicant.") and self._applicant_router is not None:
            view = await self._applicant_router.route(event)
            await self._channel_client.update_interaction(message_id=event.message_id, view=view)
            return
        if event.action_id.startswith("purchaser.") and self._purchaser_router is not None:
            view = await self._purchaser_router.route(event)
            await self._channel_client.update_interaction(message_id=event.message_id, view=view)
            return
        if event.action_id.startswith("warehouse.") and self._warehouse_router is not None:
            view = await self._warehouse_router.route(event)
            await self._channel_client.update_interaction(message_id=event.message_id, view=view)
            return
        if (
            event.action_id.startswith("building_manager.")
            and self._building_manager_router is not None
        ):
            view = await self._building_manager_router.route(event)
            await self._channel_client.update_interaction(message_id=event.message_id, view=view)
            return
        if event.action_id != "foundation.echo":
            raise UnsupportedCardActionError("不支持的卡片操作")
        await self._channel_client.update_interaction(
            message_id=event.message_id,
            view=InteractionView(
                title="基础链路验证",
                elements=(PlainTextBlock(text="卡片操作已收到。"),),
            ),
        )
