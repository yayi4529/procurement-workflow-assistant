from datetime import datetime
from zoneinfo import ZoneInfo

from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.assistant_session import AgentSessionState
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.user import CurrentUser


class AssistantContextBuilder:
    def build(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        external_conversation_id: str | None,
        current_user: CurrentUser,
        state: AgentSessionState | None,
    ) -> AssistantToolContext:
        return AssistantToolContext(
            platform_type=identity.platform_type.value,
            platform_user_id=identity.platform_user_id,
            conversation_id=conversation_id,
            external_conversation_id=external_conversation_id or identity.platform_user_id,
            external_message_id=external_message_id,
            current_time=datetime.now(ZoneInfo("Asia/Shanghai")),
            timezone_name="Asia/Shanghai",
            current_user=current_user,
            active_requirement_id=state.purchase_request_id if state else None,
        )
