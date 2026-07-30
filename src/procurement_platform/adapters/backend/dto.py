from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

DataT = TypeVar("DataT")


class BackendEnvelope(BaseModel, Generic[DataT]):
    model_config = ConfigDict(extra="forbid")

    success: bool
    code: str
    message: str
    data: DataT | None
    trace_id: str


@dataclass(frozen=True, slots=True)
class BackendRawResponse:
    status_code: int
    payload: object
    trace_id: str | None
