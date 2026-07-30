from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from procurement_platform.adapters.backend.http_client import HttpBackendClient
from procurement_platform.adapters.backend.signer import GatewayIdentitySigner
from procurement_platform.adapters.backend.transport import SignedBackendTransport
from procurement_platform.domain.assistant_session import AgentSessionStateUpdate
from procurement_platform.domain.enums import AgentMessageSender, PlatformType, RoleCode
from procurement_platform.domain.errors import (
    BackendApplicationError,
    BackendProtocolError,
    SessionExpiredError,
    UnknownBackendError,
    UserDisabledError,
    UserNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from tests.unit.test_signer import FixedClock, SequenceNonce

NOW = datetime(2026, 7, 30, tzinfo=UTC).isoformat()


def identity() -> PlatformIdentity:
    return PlatformIdentity(PlatformType.FEISHU, "ou_test", "request-test")


def envelope(data: object, *, success: bool = True, code: str = "OK") -> dict[str, object]:
    return {
        "success": success,
        "code": code,
        "message": "message",
        "data": data,
        "trace_id": "trace-test",
    }


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    nonce_count: int = 20,
) -> tuple[HttpBackendClient, httpx.AsyncClient]:
    nonces = tuple(f"{index:016d}" for index in range(nonce_count))
    signer = GatewayIdentitySigner(
        SecretStr("secret"),
        clock=FixedClock(),
        nonce_factory=SequenceNonce(*nonces),
    )
    raw_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = SignedBackendTransport(
        base_url="http://backend",
        timeout_seconds=2,
        signer=signer,
        client=raw_client,
    )
    return HttpBackendClient(transport), raw_client


@pytest.mark.asyncio
async def test_get_current_user_contract_and_unknown_role_rejection() -> None:
    requests: list[httpx.Request] = []
    data = {
        "employee_id": 7,
        "name": "张三",
        "mobile": None,
        "status": "ACTIVE",
        "roles": [{"role_code": "APPLICANT", "role_name": "需求人"}],
        "buildings": [
            {"building_id": 1, "building_name": "一号楼", "is_primary": True},
            {"building_id": 2, "building_name": "二号楼", "is_primary": False},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=envelope(data))

    client, raw_client = make_client(handler)
    user = await client.get_current_user(identity=identity())
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/v1/users/me"
    assert requests[0].headers["x-platform-type"] == "FEISHU"
    assert user.roles[0].role_code is RoleCode.APPLICANT
    assert len(user.buildings) == 2
    assert user.mobile is None
    await raw_client.aclose()

    data["roles"] = [{"role_code": "LEGACY_REQUESTER"}]
    client, raw_client = make_client(handler)
    with pytest.raises(BackendProtocolError):
        await client.get_current_user(identity=identity())
    await raw_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "error_type"),
    [
        ("USER_NOT_FOUND", UserNotFoundError),
        ("USER_DISABLED", UserDisabledError),
        ("SESSION_EXPIRED", SessionExpiredError),
        ("NEW_UNKNOWN_CODE", UnknownBackendError),
    ],
)
async def test_business_error_mapping(code: str, error_type: type[BackendApplicationError]) -> None:
    client, raw_client = make_client(
        lambda request: httpx.Response(400, json=envelope(None, success=False, code=code))
    )
    with pytest.raises(error_type) as exc_info:
        await client.get_current_user(identity=identity())
    assert exc_info.value.trace_id == "trace-test"
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_agent_conversation_endpoint_contracts() -> None:
    requests: list[httpx.Request] = []
    responses: list[object] = [
        {
            "conversation_id": 10,
            "current_action": "CARD_HELP",
            "status": "ACTIVE",
            "created_at": NOW,
            "updated_at": NOW,
        },
        {"message_id": 11, "created_at": NOW, "duplicate": False},
        {
            "items": [
                {
                    "message_id": 11,
                    "conversation_id": 10,
                    "external_message_id": "om_1",
                    "sender_type": "USER",
                    "content": "帮助",
                    "created_at": NOW,
                }
            ],
            "page": 1,
            "page_size": 50,
            "total": 1,
        },
        {
            "conversation_id": 10,
            "expires_in_seconds": 259200,
            "purchase_request_id": None,
            "current_action": "CARD_HELP",
        },
        {"conversation_id": 10, "expires_in_seconds": 259200, "updated_at": NOW},
        {
            "snapshot_id": 3,
            "conversation_id": 10,
            "snapshot_reason": "confirm",
            "created_at": NOW,
        },
        {
            "conversation_id": 10,
            "status": "COMPLETED",
            "redis_state_deleted": True,
            "completed_at": NOW,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=envelope(responses[len(requests) - 1]))

    client, raw_client = make_client(handler)
    await client.get_or_create_agent_conversation(identity=identity(), current_action="CARD_HELP")
    write = await client.append_agent_message(
        identity=identity(),
        conversation_id=10,
        external_message_id="om_1",
        sender_type=AgentMessageSender.USER,
        content="帮助",
    )
    page = await client.list_agent_messages(identity=identity(), conversation_id=10)
    await client.get_agent_state(identity=identity(), conversation_id=10)
    await client.update_agent_state(
        identity=identity(),
        conversation_id=10,
        state=AgentSessionStateUpdate(current_action="CARD_HELP"),
    )
    await client.snapshot_agent_state(
        identity=identity(), conversation_id=10, snapshot_reason="confirm"
    )
    completion = await client.complete_agent_conversation(
        identity=identity(), conversation_id=10, purchase_request_id=None
    )
    assert write.duplicate is False
    assert page.items[0].content == "帮助"
    assert completion.redis_state_deleted is True
    assert [(r.method, r.url.path) for r in requests] == [
        ("POST", "/api/v1/agent/conversations/active"),
        ("POST", "/api/v1/agent/conversations/10/messages"),
        ("GET", "/api/v1/agent/conversations/10/messages"),
        ("GET", "/api/v1/agent/conversations/10/state"),
        ("PUT", "/api/v1/agent/conversations/10/state"),
        ("POST", "/api/v1/agent/conversations/10/snapshot"),
        ("POST", "/api/v1/agent/conversations/10/complete"),
    ]
    assert requests[2].url.query == b"page=1&page_size=50"
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_invalid_pagination_is_rejected_before_http() -> None:
    client, raw_client = make_client(lambda request: httpx.Response(200, json=envelope({})))
    with pytest.raises(ValueError):
        await client.list_agent_messages(identity=identity(), conversation_id=1, page_size=201)
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_success_without_data_and_invalid_envelope_are_protocol_errors() -> None:
    def response_handler(value: object) -> Callable[[httpx.Request], httpx.Response]:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=value)

        return handler

    for payload in (envelope(None), {"success": True}):
        client, raw_client = make_client(response_handler(payload))
        with pytest.raises(BackendProtocolError):
            await client.get_current_user(identity=identity())
        await raw_client.aclose()
