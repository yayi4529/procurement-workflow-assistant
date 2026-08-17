from procurement_platform.domain.errors import NotificationEventUnsupportedError
from procurement_platform.ports.notification_renderer import NotificationRenderer


class NotificationRendererRegistry:
    def __init__(self) -> None:
        self._renderers: dict[str, NotificationRenderer] = {}

    def register(self, renderer: NotificationRenderer) -> None:
        if renderer.event_type in self._renderers:
            raise ValueError(f"renderer already registered: {renderer.event_type}")
        self._renderers[renderer.event_type] = renderer

    def resolve(self, event_type: str) -> NotificationRenderer:
        try:
            return self._renderers[event_type]
        except KeyError as exc:
            raise NotificationEventUnsupportedError(
                f"unsupported notification event type: {event_type}"
            ) from exc

    @property
    def registered_event_types(self) -> tuple[str, ...]:
        return tuple(self._renderers)
