from collections.abc import Mapping
from typing import cast

import httpx

from procurement_platform.adapters.backend.dto import BackendRawResponse
from procurement_platform.adapters.backend.signer import GatewayIdentitySigner
from procurement_platform.domain.errors import (
    BackendProtocolError,
    BackendTimeoutError,
    BackendUnavailableError,
)
from procurement_platform.domain.identity import PlatformIdentity

QueryValue = str | int | None


class SignedBackendTransport:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        signer: GatewayIdentitySigner,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._signer = signer
        self._client = client or httpx.AsyncClient()

    async def request(
        self,
        *,
        method: str,
        path: str,
        identity: PlatformIdentity,
        query: Mapping[str, QueryValue] | None = None,
        json_body: object | None = None,
    ) -> BackendRawResponse:
        if not path.startswith("/"):
            raise ValueError("path must start with '/'")
        headers = self._signer.sign(method, path, identity)
        params = (
            {key: value for key, value in query.items() if value is not None}
            if query is not None
            else None
        )
        try:
            response = await self._client.request(
                method.upper(),
                f"{self._base_url}{path}",
                params=params,
                json=json_body,
                headers=headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError("BACKEND_TIMEOUT", "采购后端请求超时") from exc
        except httpx.RequestError as exc:
            raise BackendUnavailableError("BACKEND_UNAVAILABLE", "采购后端暂不可用") from exc
        try:
            payload = cast(object, response.json())
        except ValueError as exc:
            trace_id = response.headers.get("X-Trace-Id")
            raise BackendProtocolError(
                "BACKEND_NON_JSON",
                "采购后端返回了无效响应",
                trace_id,
            ) from exc
        return BackendRawResponse(
            status_code=response.status_code,
            payload=payload,
            trace_id=response.headers.get("X-Trace-Id"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
