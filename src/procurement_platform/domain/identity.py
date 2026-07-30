from dataclasses import dataclass
from uuid import uuid4

from procurement_platform.domain.enums import PlatformType


@dataclass(frozen=True, slots=True)
class PlatformIdentity:
    platform_type: PlatformType
    platform_user_id: str
    request_id: str

    def __post_init__(self) -> None:
        if not self.platform_user_id.strip():
            raise ValueError("platform_user_id must not be empty")
        if not self.request_id.strip():
            raise ValueError("request_id must not be empty")

    @classmethod
    def create(cls, platform_type: PlatformType, platform_user_id: str) -> "PlatformIdentity":
        return cls(platform_type, platform_user_id, str(uuid4()))
