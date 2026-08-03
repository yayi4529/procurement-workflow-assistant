from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.assistant_session import AgentSessionState
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.user import CurrentUser


def _beijing_timezone() -> timezone | ZoneInfo:
    try:
        return ZoneInfo("Asia/Shanghai")
    except ZoneInfoNotFoundError:
        # Windows Python installations may not include the IANA tzdata package.
        # China Standard Time has a stable UTC+08:00 offset and no DST.
        return timezone(timedelta(hours=8), name="Asia/Shanghai")


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
            current_time=datetime.now(_beijing_timezone()),
            timezone_name="Asia/Shanghai",
            current_user=current_user,
            active_requirement_id=state.purchase_request_id if state else None,
        )
