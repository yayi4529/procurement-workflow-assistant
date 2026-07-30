from fastapi.testclient import TestClient
from pydantic import SecretStr

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.bootstrap.container import ApplicationContainer
from procurement_platform.bootstrap.settings import Settings
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserRole
from procurement_platform.interfaces.http.app import create_app


def test_health_and_lifecycle() -> None:
    settings = Settings(
        environment="test",
        service_name="test-service",
        backend_base_url="http://backend",
        backend_request_timeout_seconds=1,
        identity_gateway_secret=SecretStr("secret"),
        allow_test_platform=True,
    )
    fake = FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="test",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=RoleCode.APPLICANT),),
            buildings=(),
        )
    )
    container = ApplicationContainer(settings=settings, backend_client=fake)
    with TestClient(create_app(settings, container)) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"status": "ready"}
    assert fake.call_counts["aclose"] == 1
