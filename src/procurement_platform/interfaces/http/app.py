import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from procurement_platform.bootstrap.container import ApplicationContainer
from procurement_platform.bootstrap.logging import configure_logging
from procurement_platform.bootstrap.settings import Settings
from procurement_platform.interfaces.http.feishu_webhook import build_feishu_webhook_router
from procurement_platform.interfaces.http.notification_gateway import (
    build_notification_gateway_router,
)


def create_app(
    settings: Settings | None = None,
    container: ApplicationContainer | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_container = container or ApplicationContainer.build(resolved_settings)
    configure_logging(level=resolved_settings.log_level, log_format=resolved_settings.log_format)
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = resolved_container
        yield
        await resolved_container.aclose()

    app = FastAPI(title=resolved_settings.service_name, lifespan=lifespan)

    @app.middleware("http")
    async def request_log(request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = perf_counter()
        request_id = request.headers.get("X-Request-Id") or str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http_request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                    "backend_mode": resolved_settings.backend_mode.value,
                },
            )
            raise
        logger.info(
            "http_request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "backend_mode": resolved_settings.backend_mode.value,
            },
        )
        response.headers["X-Request-Id"] = request_id
        return response

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str | bool]:
        return {
            "status": "ready",
            "backend_mode": resolved_settings.backend_mode.value,
            "backend_configured": True,
            "feishu_enabled": resolved_settings.feishu.enabled,
            "feishu_configured": resolved_container.channel_client is not None,
            "llm_enabled": resolved_settings.llm_enabled,
            "llm_configured": resolved_container.procurement_assistant is not None,
            "llm_model_configured": resolved_settings.llm_model is not None,
            "agent_session_backend_configured": resolved_settings.backend_mode.value == "http",
            "conversation_lock_backend": "local",
            "notification_gateway_enabled": resolved_settings.notification_gateway.enabled,
            "notification_gateway_configured": (
                resolved_container.notification_gateway_service is not None
            ),
            "notification_delivery_store_backend": (
                resolved_settings.notification_gateway.delivery_store_backend
            ),
            "event_dedup_store_backend": resolved_settings.event_dedup_store_backend,
            "debug_identity_probe_enabled": (resolved_settings.debug_identity_probe_enabled),
        }

    if resolved_settings.feishu.enabled:
        app.include_router(
            build_feishu_webhook_router(resolved_settings.feishu.webhook_path, resolved_container)
        )
    if resolved_settings.notification_gateway.enabled:
        app.include_router(
            build_notification_gateway_router(
                resolved_settings.notification_gateway.path, resolved_container
            )
        )

    return app
