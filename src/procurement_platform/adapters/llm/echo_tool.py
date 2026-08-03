from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult


class EchoToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)


class EchoToolResult(AssistantToolResult):
    model_config = ConfigDict(extra="forbid")
    echoed_text: str


class EchoTool:
    name = "echo_tool"
    description = "Echo text for development and test only."
    args_model = EchoToolArgs

    async def execute(self, *, args: EchoToolArgs, context: AssistantToolContext) -> EchoToolResult:
        del context
        return EchoToolResult(status="SUCCESS", echoed_text=args.text)
