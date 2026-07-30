from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from procurement_platform.bootstrap.container import ApplicationContainer
from procurement_platform.bootstrap.settings import Settings


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
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    return app
