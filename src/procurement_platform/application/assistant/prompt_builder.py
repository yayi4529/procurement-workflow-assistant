from procurement_platform.domain.assistant import AssistantMessage, AssistantToolContext


class PromptBuilder:
    def build(
        self, *, context: AssistantToolContext, history: tuple[AssistantMessage, ...]
    ) -> tuple[AssistantMessage, ...]:
        roles = ", ".join(role.role_code.value for role in context.current_user.roles)
        system = AssistantMessage(
            role="system",
            content=(
                "你是采购流程助手。只能依据系统上下文和工具结果回答;不得编造采购单、状态、金额、处理人或供应商。"
                "用户角色来自系统。多条结果不得擅自选择。正式操作必须通过飞书正式卡片。"
                f"当前角色:{roles};时区:{context.timezone_name}。"
            ),
        )
        return (system, *history)
