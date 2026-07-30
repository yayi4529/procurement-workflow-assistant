from fastapi import APIRouter, Header, HTTPException, Response, status

from procurement_platform.bootstrap.container import ApplicationContainer
from procurement_platform.domain.errors import (
    FeishuDeliveryError,
    FeishuTimeoutError,
    NotificationAuthenticationError,
    NotificationEventUnsupportedError,
    NotificationHeaderMismatchError,
    NotificationIdempotencyConflictError,
    NotificationInProgressError,
    NotificationPayloadValidationError,
)
from procurement_platform.domain.notification import NotificationGatewayRequest


def build_notification_gateway_router(path: str, container: ApplicationContainer) -> APIRouter:
    router = APIRouter()

    @router.post(path, status_code=status.HTTP_204_NO_CONTENT)
    async def notification_gateway(
        body: NotificationGatewayRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        notification_id: str | None = Header(default=None, alias="X-Notification-Id"),
    ) -> Response:
        service = container.notification_gateway_service
        if service is None:
            raise HTTPException(status_code=503, detail="notification gateway unavailable")
        try:
            await service.deliver(
                request=body,
                authorization=authorization,
                idempotency_key=idempotency_key,
                notification_id_header=notification_id,
            )
        except NotificationAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except NotificationHeaderMismatchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except NotificationIdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except NotificationInProgressError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (NotificationEventUnsupportedError, NotificationPayloadValidationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FeishuTimeoutError as exc:
            raise HTTPException(status_code=503, detail="Feishu temporarily unavailable") from exc
        except FeishuDeliveryError as exc:
            raise HTTPException(status_code=502, detail="Feishu delivery failed") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="notification delivery failed") from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
