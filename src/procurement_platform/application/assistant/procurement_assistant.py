from procurement_platform.application.assistant.service import AssistantService
from procurement_platform.domain.assistant import AssistantResponse
from procurement_platform.domain.inbound_event import TextMessageEvent


class ProcurementAssistant:
    """Compatibility wrapper for callers migrating to AssistantService."""

    def __init__(self, service: AssistantService) -> None:
        self._service = service

    async def handle(self, event: TextMessageEvent) -> AssistantResponse:
        return await self._service.handle(event)
