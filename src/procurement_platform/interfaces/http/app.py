from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from procurement_platform.bootstrap.container import ApplicationContainer
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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = resolved_container
        yield
        await resolved_container.aclose()

    app = FastAPI(title=resolved_settings.service_name, lifespan=lifespan)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str | bool]:
        if not (resolved_settings.feishu.enabled or resolved_settings.notification_gateway.enabled):
            return {"status": "ready"}
        return {
            "status": "ready",
            "backend_client_configured": True,
            "feishu_enabled": resolved_settings.feishu.enabled,
            "feishu_configured": resolved_container.channel_client is not None,
            "notification_gateway_enabled": resolved_settings.notification_gateway.enabled,
            "notification_gateway_configured": (
                resolved_container.notification_gateway_service is not None
            ),
            "notification_delivery_store_backend": (
                resolved_settings.notification_gateway.delivery_store_backend
            ),
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
