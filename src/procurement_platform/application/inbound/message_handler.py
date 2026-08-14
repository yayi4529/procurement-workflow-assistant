from typing import Protocol

from procurement_platform.application.applicant.workflow_service import ApplicantWorkflowService
from procurement_platform.application.building_manager.workflow_service import (
    BuildingManagerWorkflowService,
)
from procurement_platform.application.purchaser.workflow_service import PurchaserWorkflowService
from procurement_platform.application.warehouse.workflow_service import WarehouseWorkflowService
from procurement_platform.domain.assistant import (
    AssistantClarificationResponse,
    AssistantInteractionResponse,
    AssistantResponse,
    AssistantTextResponse,
)
from procurement_platform.domain.assistant_errors import AssistantError
from procurement_platform.domain.channel import StreamingCardHandle
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.interaction import InteractionView, MarkdownBlock
from procurement_platform.ports.backend_client import BackendClient
from procurement_platform.ports.channel import ChannelClient
from procurement_platform.ports.conversation_lock import ConversationLockManager


class AssistantHandler(Protocol):
    async def handle(self, event: TextMessageEvent) -> AssistantResponse: ...


class BaseMessageHandler:
    def __init__(
        self,
        channel_client: ChannelClient,
        *,
        debug_identity_probe_enabled: bool = False,
        backend_client: BackendClient | None = None,
        assistant_service: AssistantHandler | None = None,
        conversation_lock_manager: ConversationLockManager | None = None,
    ) -> None:
        self._channel_client = channel_client
        self._debug_identity_probe_enabled = debug_identity_probe_enabled
        self._backend_client = backend_client
        self._assistant_service = assistant_service
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
        if self._assistant_service is not None and self._conversation_lock_manager is not None:
            async with self._conversation_lock_manager.acquire(
                key=f"FEISHU:{event.external_user_id}"
            ):
                stream = await self._channel_client.begin_streaming_reply(
                    reply_to_message_id=event.external_message_id
                )
                try:
                    response = await self._assistant_service.handle(event)
                except AssistantError:
                    await self._send_assistant_failure(
                        reply_to_message_id=event.external_message_id,
                        stream=stream,
                    )
                    return
                if isinstance(response, AssistantTextResponse):
                    if stream is not None:
                        try:
                            await self._channel_client.update_streaming_reply(
                                handle=stream, text=response.text, finish=True
                            )
                        except Exception:
                            await self._channel_client.reply_interaction(
                                reply_to_message_id=event.external_message_id,
                                view=self._assistant_text_card(response.text),
                            )
                    else:
                        await self._channel_client.reply_interaction(
                            reply_to_message_id=event.external_message_id,
                            view=self._assistant_text_card(response.text),
                        )
                elif isinstance(response, AssistantInteractionResponse):
                    if stream is not None:
                        try:
                            await self._channel_client.update_streaming_reply(
                                handle=stream,
                                text="处理完成, 结果见下方业务卡片。",
                                finish=True,
                            )
                        except Exception:
                            pass
                    await self._channel_client.reply_interaction(
                        reply_to_message_id=event.external_message_id, view=response.view
                    )
                elif isinstance(response, AssistantClarificationResponse):
                    options = "\n".join(
                        f"{index}. {item.label}"
                        for index, item in enumerate(response.options, start=1)
                    )
                    text = response.question if not options else f"{response.question}\n{options}"
                    if stream is not None:
                        try:
                            await self._channel_client.update_streaming_reply(
                                handle=stream, text=text, finish=True
                            )
                        except Exception:
                            await self._channel_client.reply_interaction(
                                reply_to_message_id=event.external_message_id,
                                view=self._assistant_text_card(text, title="需要确认"),
                            )
                    else:
                        await self._channel_client.reply_interaction(
                            reply_to_message_id=event.external_message_id,
                            view=self._assistant_text_card(text, title="需要确认"),
                        )
            return
        await self._channel_client.reply_text(
            reply_to_message_id=event.external_message_id,
            text="采购中心已收到您的消息。智能助手当前未启用。",
        )

    async def _send_assistant_failure(
        self, *, reply_to_message_id: str, stream: StreamingCardHandle | None
    ) -> None:
        text = "智能助手本次响应超时或暂时不可用, 请稍后重新发送消息。"
        if stream is not None:
            try:
                await self._channel_client.update_streaming_reply(
                    handle=stream, text=text, finish=True
                )
                return
            except Exception:
                pass
        await self._channel_client.reply_interaction(
            reply_to_message_id=reply_to_message_id,
            view=self._assistant_text_card(text, title="处理失败"),
        )

    @staticmethod
    def _assistant_text_card(text: str, *, title: str = "采购助手") -> InteractionView:
        return InteractionView(
            title=title,
            subtitle="智能助手回复",
            elements=(MarkdownBlock(markdown=text),),
        )
