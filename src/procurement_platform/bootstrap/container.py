from dataclasses import dataclass

from procurement_platform.adapters.backend.http_client import HttpBackendClient
from procurement_platform.adapters.backend.signer import GatewayIdentitySigner
from procurement_platform.adapters.backend.transport import SignedBackendTransport
from procurement_platform.bootstrap.settings import Settings
from procurement_platform.ports.backend_client import BackendClient


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    backend_client: BackendClient

    @classmethod
    def build(cls, settings: Settings) -> "ApplicationContainer":
        signer = GatewayIdentitySigner(
            secret=settings.identity_gateway_secret,
            allow_test_platform=settings.allow_test_platform,
        )
        transport = SignedBackendTransport(
            base_url=settings.backend_base_url,
            timeout_seconds=settings.backend_request_timeout_seconds,
            signer=signer,
        )
        return cls(settings=settings, backend_client=HttpBackendClient(transport))

    async def aclose(self) -> None:
        await self.backend_client.aclose()
