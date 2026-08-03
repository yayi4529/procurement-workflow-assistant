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
                "用户角色来自系统。多条结果不得擅自选择。正式提交、审批、驳回、开始采购、提交仓库和完成入库"
                "必须通过飞书正式卡片,不得调用工具执行。"
                "查询采购单列表、详情、状态或时间线时必须调用query_purchase_requests。"
                "需求人提供采购字段或要求整理草稿时必须调用update_purchase_draft;不得在工具成功前声称已保存。"
                "产品推荐、供应商推荐、供应商精确资料、采购预填和各角色草稿保存均必须调用对应可用工具。"
                "工具返回NOT_FOUND时不得自行补造结果;返回MULTIPLE_MATCHES时必须让用户选择;"
                "返回NEED_MORE_INFORMATION时一次只追问一个字段。"
                "精确供应商字段由系统直接渲染,不得改写、补全或解除脱敏。"
                f"当前角色:{roles};时区:{context.timezone_name}。"
            ),
        )
        return (system, *history)
