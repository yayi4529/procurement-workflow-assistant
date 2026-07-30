from dataclasses import dataclass

from procurement_platform.adapters.backend.http_client import HttpBackendClient
from procurement_platform.adapters.backend.signer import GatewayIdentitySigner
from procurement_platform.adapters.backend.transport import SignedBackendTransport
from procurement_platform.adapters.feishu.channel_client import FeishuChannelClient
from procurement_platform.adapters.feishu.interaction_renderer import FeishuInteractionRenderer
from procurement_platform.adapters.feishu.sdk_client import LarkOapiTransport
from procurement_platform.adapters.feishu.webhook_parser import FeishuWebhookParser
from procurement_platform.adapters.persistence.memory_event_dedup_store import (
    MemoryEventDedupStore,
)
from procurement_platform.adapters.persistence.memory_notification_delivery_store import (
    MemoryNotificationDeliveryStore,
)
from procurement_platform.application.applicant.action_router import ApplicantActionRouter
from procurement_platform.application.applicant.workflow_service import ApplicantWorkflowService
from procurement_platform.application.building_manager.action_router import (
    BuildingManagerActionRouter,
)
from procurement_platform.application.building_manager.workflow_service import (
    BuildingManagerWorkflowService,
)
from procurement_platform.application.inbound.card_interaction_handler import (
    BaseCardInteractionHandler,
)
from procurement_platform.application.inbound.message_handler import BaseMessageHandler
from procurement_platform.application.notifications.gateway_service import (
    NotificationGatewayService,
)
from procurement_platform.application.notifications.renderer_registry import (
    NotificationRendererRegistry,
)
from procurement_platform.application.purchaser.action_router import PurchaserActionRouter
from procurement_platform.application.purchaser.workflow_service import PurchaserWorkflowService
from procurement_platform.application.warehouse.action_router import WarehouseActionRouter
from procurement_platform.application.warehouse.workflow_service import WarehouseWorkflowService
from procurement_platform.bootstrap.settings import Settings
from procurement_platform.ports.backend_client import BackendClient
from procurement_platform.ports.channel import ChannelClient


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    backend_client: BackendClient
    channel_client: ChannelClient | None = None
    webhook_parser: FeishuWebhookParser | None = None
    event_dedup_store: MemoryEventDedupStore | None = None
    message_handler: BaseMessageHandler | None = None
    card_interaction_handler: BaseCardInteractionHandler | None = None
    notification_delivery_store: MemoryNotificationDeliveryStore | None = None
    notification_renderer_registry: NotificationRendererRegistry | None = None
    notification_gateway_service: NotificationGatewayService | None = None

    @classmethod
    def build(cls, settings: Settings) -> "ApplicationContainer":
        signer = GatewayIdentitySigner(
            secret=settings.identity_gateway_secret,
            allow_test_platform=settings.allow_test_platform,
        )
        transport = SignedBackendTransport(
            base_url=settings.backend_base_url,
            timeout_seconds=settings.backend_request_timeout_seconds,
            signer=signer,
        )
        container = cls(settings=settings, backend_client=HttpBackendClient(transport))
        if settings.feishu.enabled:
            sdk = LarkOapiTransport(
                settings.feishu.app_id,
                settings.feishu.app_secret.get_secret_value(),
            )
            channel = FeishuChannelClient(sdk, FeishuInteractionRenderer())
            container.channel_client = channel
            container.webhook_parser = FeishuWebhookParser(
                verification_token=settings.feishu.verification_token.get_secret_value(),
                encrypt_key=(
                    settings.feishu.encrypt_key.get_secret_value()
                    if settings.feishu.encrypt_key is not None
                    else None
                ),
            )
            container.event_dedup_store = MemoryEventDedupStore()
            container.message_handler = BaseMessageHandler(channel)
            container.card_interaction_handler = BaseCardInteractionHandler(
                channel,
                ApplicantActionRouter(ApplicantWorkflowService(container.backend_client)),
                BuildingManagerActionRouter(
                    BuildingManagerWorkflowService(container.backend_client)
                ),
                PurchaserActionRouter(PurchaserWorkflowService(container.backend_client)),
                WarehouseActionRouter(WarehouseWorkflowService(container.backend_client)),
            )
            if settings.notification_gateway.enabled:
                delivery_store = MemoryNotificationDeliveryStore()
                registry = NotificationRendererRegistry()
                container.notification_delivery_store = delivery_store
                container.notification_renderer_registry = registry
                token = settings.notification_gateway.bearer_token
                container.notification_gateway_service = NotificationGatewayService(
                    channel_client=channel,
                    delivery_store=delivery_store,
                    renderer_registry=registry,
                    bearer_token=token.get_secret_value() if token is not None else None,
                )
        elif settings.notification_gateway.enabled:
            raise ValueError("notification gateway requires Feishu integration")
        return container

    async def aclose(self) -> None:
        if self.channel_client is not None:
            await self.channel_client.aclose()
        await self.backend_client.aclose()
