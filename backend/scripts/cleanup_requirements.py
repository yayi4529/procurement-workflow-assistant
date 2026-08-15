"""Precisely remove development/test procurement requirements by ID.

This script deliberately refuses to run outside development/test environments.
It removes only the selected requirements and their dependent workflow/session
records; employees and external identity bindings are never touched.
"""

import argparse
import asyncio

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import engine
from app.integrations.agent_state_store import AgentStateStore
from app.models.agent import AgentConversation, AgentMessage, AgentSessionState
from app.models.notification import NotificationOutbox
from app.models.procurement import (
    PurchaseExecution,
    PurchaseOperationLog,
    PurchaseRequest,
    PurchaseReview,
    SupplierBlacklist,
    WarehouseReceipt,
)


async def cleanup(requirement_ids: tuple[int, ...]) -> None:
    settings = get_settings()
    if settings.app_env.lower() not in {"development", "test", "testing"}:
        raise RuntimeError("cleanup_requirements.py is only allowed in development/test")
    if not requirement_ids or any(requirement_id <= 0 for requirement_id in requirement_ids):
        raise ValueError("at least one positive requirement ID is required")

    async with engine.begin() as connection:
        found = tuple(
            (
                await connection.execute(
                    select(PurchaseRequest.request_id).where(
                        PurchaseRequest.request_id.in_(requirement_ids)
                    )
                )
            ).scalars()
        )
        if set(found) != set(requirement_ids):
            raise RuntimeError(f"requirement ID mismatch: requested={requirement_ids}, found={found}")

        conversation_ids = tuple(
            (
                await connection.execute(
                    select(AgentConversation.conversation_id).where(
                        AgentConversation.purchase_request_id.in_(requirement_ids)
                    )
                )
            ).scalars()
        )
        if conversation_ids:
            await connection.execute(
                delete(AgentSessionState).where(
                    AgentSessionState.conversation_id.in_(conversation_ids)
                )
            )
            await connection.execute(
                delete(AgentMessage).where(AgentMessage.conversation_id.in_(conversation_ids))
            )
            await connection.execute(
                delete(AgentConversation).where(
                    AgentConversation.conversation_id.in_(conversation_ids)
                )
            )
        await connection.execute(
            delete(NotificationOutbox).where(NotificationOutbox.request_id.in_(requirement_ids))
        )
        await connection.execute(
            delete(WarehouseReceipt).where(WarehouseReceipt.request_id.in_(requirement_ids))
        )
        await connection.execute(
            delete(SupplierBlacklist).where(
                SupplierBlacklist.source_request_id.in_(requirement_ids)
            )
        )
        await connection.execute(
            delete(PurchaseReview).where(PurchaseReview.request_id.in_(requirement_ids))
        )
        await connection.execute(
            delete(PurchaseExecution).where(PurchaseExecution.request_id.in_(requirement_ids))
        )
        await connection.execute(
            delete(PurchaseOperationLog).where(PurchaseOperationLog.request_id.in_(requirement_ids))
        )
        await connection.execute(
            delete(PurchaseRequest).where(PurchaseRequest.request_id.in_(requirement_ids))
        )

    store = AgentStateStore(settings)
    for conversation_id in conversation_ids:
        await store.delete(conversation_id)
    print(f"deleted requirements={requirement_ids}, conversations={conversation_ids}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirement_ids", nargs="+", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(cleanup(tuple(dict.fromkeys(args.requirement_ids))))
