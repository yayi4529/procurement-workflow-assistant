from procurement_platform.application.applicant.workflow_service import ApplicantWorkflowService
from procurement_platform.application.assistant.procurement_assistant import ProcurementAssistant
from procurement_platform.application.building_manager.workflow_service import (
    BuildingManagerWorkflowService,
)
from procurement_platform.application.purchaser.workflow_service import PurchaserWorkflowService
from procurement_platform.application.warehouse.workflow_service import WarehouseWorkflowService
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.ports.backend_client import BackendClient
from procurement_platform.ports.channel import ChannelClient
from procurement_platform.ports.conversation_lock import ConversationLockManager


class BaseMessageHandler:
    def __init__(
        self,
        channel_client: ChannelClient,
        *,
        debug_identity_probe_enabled: bool = False,
        backend_client: BackendClient | None = None,
        procurement_assistant: ProcurementAssistant | None = None,
        conversation_lock_manager: ConversationLockManager | None = None,
    ) -> None:
        self._channel_client = channel_client
        self._debug_identity_probe_enabled = debug_identity_probe_enabled
        self._backend_client = backend_client
        self._procurement_assistant = procurement_assistant
        self._conversation_lock_manager = conversation_lock_manager

    async def handle(self, event: TextMessageEvent) -> None:
        if event.external_message_id is None:
            return
        if self._debug_identity_probe_enabled and event.text == "调试身份":
            await self._channel_client.reply_text(
                reply_to_message_id=event.external_message_id,
                text=(
                    "调试身份信息\n\n"
                    "platform_type: FEISHU\n"
                    f"platform_user_id: {event.external_user_id}\n"
                    f"message_id: {event.external_message_id}\n\n"
                    "请将 platform_user_id 写入 .local/fake-users.json。"
                ),
            )
            return
        if self._backend_client is not None and event.text == "采购测试":
            identity = PlatformIdentity.create(PlatformType.FEISHU, event.external_user_id)
            user = await self._backend_client.get_current_user(identity=identity)
            roles = {item.role_code for item in user.roles}
            if RoleCode.APPLICANT in roles:
                view = await ApplicantWorkflowService(self._backend_client).home()
            elif RoleCode.BUILDING_MANAGER in roles:
                view = await BuildingManagerWorkflowService(
                    self._backend_client
                ).list_pending_requirements(identity)
            elif RoleCode.PURCHASER in roles:
                view = await PurchaserWorkflowService(self._backend_client).list_pending(identity)
            elif RoleCode.WAREHOUSE_MANAGER in roles:
                view = await WarehouseWorkflowService(self._backend_client).list_pending(identity)
            else:
                await self._channel_client.reply_text(
                    reply_to_message_id=event.external_message_id,
                    text="当前身份没有可测试的采购角色。",
                )
                return
            await self._channel_client.reply_interaction(
                reply_to_message_id=event.external_message_id, view=view
            )
            return
        if self._procurement_assistant is not None and self._conversation_lock_manager is not None:
            async with self._conversation_lock_manager.acquire(
                key=f"FEISHU:{event.external_user_id}"
            ):
                response = await self._procurement_assistant.handle(event)
                await self._channel_client.reply_text(
                    reply_to_message_id=event.external_message_id, text=response.text
                )
            return
        await self._channel_client.reply_text(
            reply_to_message_id=event.external_message_id,
            text="采购中心已收到您的消息。智能助手当前未启用。",
        )
