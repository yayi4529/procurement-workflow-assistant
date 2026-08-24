"""Optional plain-text context loading for the conversational procurement agent."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_optional_context(path_value: str | None) -> str | None:
    if path_value is None or not path_value.strip():
        return None
    path = Path(path_value)
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning("LLM context knowledge unavailable path=%s reason=%s", path, exc)
        return None
    if not content:
        logger.warning("LLM context knowledge is empty path=%s", path)
        return None
    logger.info("LLM context knowledge loaded path=%s chars=%d", path, len(content))
    return content
