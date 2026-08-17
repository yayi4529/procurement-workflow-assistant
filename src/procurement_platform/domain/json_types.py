from typing import TypeAlias

from pydantic import JsonValue as PydanticJsonValue

JsonValue: TypeAlias = PydanticJsonValue
JsonObject: TypeAlias = dict[str, JsonValue]
