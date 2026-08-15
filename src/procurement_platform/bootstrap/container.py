from dataclasses import dataclass

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.backend.fake_seed import FakeBackendSeedLoader
from procurement_platform.adapters.backend.http_client import HttpBackendClient
from procurement_platform.adapters.backend.signer import GatewayIdentitySigner
from procurement_platform.adapters.backend.transport import SignedBackendTransport
from procurement_platform.adapters.feishu.channel_client import FeishuChannelClient
from procurement_platform.adapters.feishu.interaction_renderer import FeishuInteractionRenderer
from procurement_platform.adapters.feishu.sdk_client import LarkOapiTransport
from procurement_platform.adapters.feishu.webhook_parser import FeishuWebhookParser
from procurement_platform.adapters.llm.openai_compatible_llm_client import OpenAICompatibleLlmClient
from procurement_platform.adapters.persistence.local_conversation_lock import (
    LocalConversationLockManager,
)
from procurement_platform.adapters.persistence.memory_event_dedup_store import (
    MemoryEventDedupStore,
)
from procurement_platform.adapters.persistence.memory_notification_delivery_store import (
    MemoryNotificationDeliveryStore,
)
from procurement_platform.application.applicant.action_router import ApplicantActionRouter
from procurement_platform.application.applicant.workflow_service import ApplicantWorkflowService
from procurement_platform.application.assistant.agent import ProcurementAgent
from procurement_platform.application.assistant.capabilities.adapters import (
    ExistingToolCapabilityAdapter,
)
from procurement_platform.application.assistant.capabilities.catalog import (
    DEFAULT_CAPABILITY_METADATA,
)
from procurement_platform.application.assistant.capabilities.intelligence import (
    CompareProductsCapability,
    CompareSuppliersCapability,
    DiagnoseProcurementNeedCapability,
    FindSimilarPurchasesCapability,
)
from procurement_platform.application.assistant.capabilities.policy import CapabilityPolicy
from procurement_platform.application.assistant.capabilities.registry import CapabilityRegistry
from procurement_platform.application.assistant.capabilities.v2 import (
    ApplySupplierProfileCapability,
    GetPurchaseRequestCapability,
    GetPurchaseTimelineCapability,
    GetSupplierProfileCapability,
    RecommendProductsCapability,
    RecommendSuppliersCapability,
    SearchPurchaseRequestsCapability,
    UpdateApplicantDraftCapability,
    UpdatePurchaseDraftCapability,
    UpdateWarehouseDraftCapability,
)
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.presentation import LegacyToolResultPresenter
from procurement_platform.application.assistant.procurement_assistant import ProcurementAssistant
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.service import AssistantService
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tooling import (
    PreparePurchasePrefillTool,
    PurchasePrefillNotificationService,
    UpdateReviewDraftTool,
)
from procurement_platform.application.assistant.tools import ToolExecutor
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
from procurement_platform.application.notifications.development_renderer import (
    DevelopmentNotificationRenderer,
)
from procurement_platform.application.notifications.gateway_service import (
    NotificationGatewayService,
)
from procurement_platform.application.notifications.pending_review_service import (
    PendingReviewNotificationService,
)
from procurement_platform.application.notifications.renderer_registry import (
    NotificationRendererRegistry,
)
from procurement_platform.application.notifications.workflow_assignment_renderer import (
    WorkflowAssignmentRenderer,
)
from procurement_platform.application.purchaser.action_router import PurchaserActionRouter
from procurement_platform.application.purchaser.workflow_service import PurchaserWorkflowService
from procurement_platform.application.warehouse.action_router import WarehouseActionRouter
from procurement_platform.application.warehouse.workflow_service import WarehouseWorkflowService
from procurement_platform.bootstrap.settings import Settings
from procurement_platform.domain.enums import BackendMode
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
    procurement_assistant: ProcurementAssistant | None = None
    assistant_service: AssistantService | None = None
    procurement_agent: ProcurementAgent | None = None
    conversation_lock_manager: LocalConversationLockManager | None = None
    capability_registry: CapabilityRegistry | None = None
    capability_policy: CapabilityPolicy | None = None

    @classmethod
    def build(cls, settings: Settings) -> "ApplicationContainer":
        if settings.backend_mode is BackendMode.FAKE:
            seed = FakeBackendSeedLoader.load(settings.fake_data_path)
            backend = FakeBackendClient(users_by_platform_id=FakeBackendSeedLoader.users(seed))
            backend.handler_candidates = backend.handler_candidates.model_copy(
                update={"items": FakeBackendSeedLoader.candidates(seed)}
            )
            backend.handler_candidates_by_role = {
                role: backend.handler_candidates.model_copy(update={"items": candidates})
                for role, candidates in FakeBackendSeedLoader.candidates_by_role(seed).items()
            }
            for supplier in FakeBackendSeedLoader.suppliers(seed):
                backend.seed_supplier(supplier)
            container = cls(settings=settings, backend_client=backend)
        else:
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
            lock_manager = LocalConversationLockManager()
            container.conversation_lock_manager = lock_manager
            if settings.llm_enabled:
                api_key = settings.llm_api_key
                model = settings.llm_model
                if api_key is None or not api_key.get_secret_value() or model is None:
                    raise ValueError("enabled LLM requires API key and model")
                if settings.environment == "production" and settings.llm_base_url is None:
                    raise ValueError("enabled production LLM requires base URL")
                capability_registry = _build_capability_registry(container.backend_client)
                capability_policy = CapabilityPolicy(capability_registry)
                container.capability_registry = capability_registry
                container.capability_policy = capability_policy
                tool_registry = capability_registry.tool_registry
                llm_client = OpenAICompatibleLlmClient(
                    api_key=api_key,
                    model=model,
                    timeout_seconds=settings.llm_timeout_seconds,
                    base_url=settings.llm_base_url,
                )
                session_service = AssistantSessionService(container.backend_client)
                tool_executor = ToolExecutor(
                    tool_registry, max_result_chars=settings.llm_max_tool_result_chars
                )
                runtime = AssistantRuntime(
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                    tool_executor=tool_executor,
                    max_tool_steps=settings.llm_max_tool_steps,
                )
                procurement_agent = ProcurementAgent(
                    runtime=runtime,
                    capability_policy=capability_policy,
                    session_service=session_service,
                    result_presenter=LegacyToolResultPresenter(
                        backend_client=container.backend_client,
                        session_service=session_service,
                    ),
                )
                container.procurement_agent = procurement_agent
                container.assistant_service = AssistantService(
                    backend_client=container.backend_client,
                    session_service=session_service,
                    context_builder=AssistantContextBuilder(),
                    procurement_agent=procurement_agent,
                    max_history_messages=settings.llm_max_history_messages,
                )
                container.procurement_assistant = ProcurementAssistant(container.assistant_service)
            container.message_handler = BaseMessageHandler(
                channel,
                debug_identity_probe_enabled=settings.debug_identity_probe_enabled,
                backend_client=container.backend_client,
                assistant_service=container.assistant_service,
                conversation_lock_manager=lock_manager,
            )
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
                for event_type in (
                    "REQUIREMENT_PENDING_REVIEW",
                    "REQUIREMENT_PENDING_PURCHASE",
                    "REQUIREMENT_PENDING_WAREHOUSE",
                ):
                    registry.register(WorkflowAssignmentRenderer(event_type))
                if settings.development_notification_renderer_enabled:
                    registry.register(DevelopmentNotificationRenderer())
                container.notification_delivery_store = delivery_store
                container.notification_renderer_registry = registry
                token = settings.notification_gateway.bearer_token
                container.notification_gateway_service = NotificationGatewayService(
                    channel_client=channel,
                    delivery_store=delivery_store,
                    renderer_registry=registry,
                    bearer_token=token.get_secret_value() if token is not None else None,
                    purchase_prefill_provider=PurchasePrefillNotificationService(
                        container.backend_client
                    ),
                    pending_review_provider=PendingReviewNotificationService(
                        container.backend_client
                    ),
                )
        elif settings.notification_gateway.enabled:
            raise ValueError("notification gateway requires Feishu integration")
        return container

    async def aclose(self) -> None:
        if self.channel_client is not None:
            await self.channel_client.aclose()
        await self.backend_client.aclose()


def _build_capability_registry(backend_client: BackendClient) -> CapabilityRegistry:
    metadata_by_name = {item.name: item for item in DEFAULT_CAPABILITY_METADATA}
    tools = (
        DiagnoseProcurementNeedCapability(backend_client),
        FindSimilarPurchasesCapability(backend_client),
        CompareProductsCapability(backend_client),
        CompareSuppliersCapability(backend_client),
        SearchPurchaseRequestsCapability(backend_client),
        GetPurchaseRequestCapability(backend_client),
        GetPurchaseTimelineCapability(backend_client),
        RecommendProductsCapability(backend_client),
        UpdateApplicantDraftCapability(backend_client),
        RecommendSuppliersCapability(backend_client),
        UpdateReviewDraftTool(backend_client),
        GetSupplierProfileCapability(backend_client),
        PreparePurchasePrefillTool(backend_client),
        ApplySupplierProfileCapability(backend_client),
        UpdatePurchaseDraftCapability(backend_client),
        UpdateWarehouseDraftCapability(backend_client),
    )
    registry = CapabilityRegistry()
    for tool in tools:
        registry.register(ExistingToolCapabilityAdapter(tool, metadata_by_name[tool.name]))
    return registry
