import json
import logging
from datetime import UTC, datetime


def mask_platform_user_id(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:7]}…{value[-4:]}"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in (
            "request_id",
            "event_id",
            "external_message_id",
            "event_type",
            "action_id",
            "masked_platform_user_id",
            "backend_mode",
            "notification_id",
            "dedup_key",
            "duration_ms",
            "status_code",
            "method",
            "path",
            "error_code",
        ):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(*, level: str, log_format: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if log_format == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
