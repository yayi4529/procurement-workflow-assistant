from contextlib import AbstractAsyncContextManager
from typing import Protocol


class ConversationLockManager(Protocol):
    def acquire(self, *, key: str) -> AbstractAsyncContextManager[None]: ...
