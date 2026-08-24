"""Coarse-grained applicant draft operation used by the applicant skill."""

from procurement_platform.application.assistant.capabilities.drafts import (
    UpdateMultiItemDraftCapability,
)
from procurement_platform.application.assistant.tooling.multi_item import (
    UpdateMultiItemDraftArgs,
    UpdateMultiItemDraftResult,
)
from procurement_platform.domain.assistant import AssistantToolContext


class ApplicantDraftSkillHandler:
    """Keep backend draft mechanics behind one skill-level operation."""

    def __init__(self, capability: UpdateMultiItemDraftCapability) -> None:
        self._capability = capability

    async def save(
        self,
        *,
        args: UpdateMultiItemDraftArgs,
        context: AssistantToolContext,
    ) -> UpdateMultiItemDraftResult:
        return await self._capability.execute(args=args, context=context)
