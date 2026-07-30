from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from procurement_platform.adapters.feishu.webhook_parser import (
    ChallengeResponse,
    IgnoredEvent,
)
from procurement_platform.bootstrap.container import ApplicationContainer
from procurement_platform.domain.errors import FeishuError, UnsupportedCardActionError
from procurement_platform.domain.inbound_event import CardInteractionEvent, TextMessageEvent
from procurement_platform.ports.event_dedup_store import EventStartResult


def build_feishu_webhook_router(path: str, container: ApplicationContainer) -> APIRouter:
    router = APIRouter()

    @router.post(path)
    async def feishu_webhook(request: Request) -> JSONResponse:
        parser = container.webhook_parser
        store = container.event_dedup_store
        if parser is None or store is None:
            raise HTTPException(status_code=503, detail="Feishu integration unavailable")
        try:
            parsed = parser.parse(
                body=await request.body(),
                timestamp=request.headers.get("X-Lark-Request-Timestamp"),
                nonce=request.headers.get("X-Lark-Request-Nonce"),
                signature=request.headers.get("X-Lark-Signature"),
            )
        except FeishuError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if isinstance(parsed, ChallengeResponse):
            return JSONResponse({"challenge": parsed.challenge})
        if isinstance(parsed, IgnoredEvent):
            return JSONResponse({"status": "ignored"})
        start = await store.try_start(event_id=parsed.event_id)
        if start in {EventStartResult.ALREADY_COMPLETED, EventStartResult.IN_PROGRESS}:
            return JSONResponse({"status": "accepted"})
        try:
            if isinstance(parsed, TextMessageEvent):
                assert container.message_handler is not None
                await container.message_handler.handle(parsed)
            elif isinstance(parsed, CardInteractionEvent):
                assert container.card_interaction_handler is not None
                await container.card_interaction_handler.handle(parsed)
            await store.mark_completed(event_id=parsed.event_id)
        except UnsupportedCardActionError:
            await store.mark_completed(event_id=parsed.event_id)
            return JSONResponse({"status": "unsupported_action"})
        except Exception:
            await store.mark_failed(event_id=parsed.event_id)
            raise HTTPException(status_code=500, detail="event handling failed") from None
        return JSONResponse({"status": "accepted"})

    return router
