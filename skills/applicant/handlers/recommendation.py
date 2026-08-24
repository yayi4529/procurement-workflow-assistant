"""Coarse-grained applicant recommendation operation used by the applicant skill."""

from procurement_platform.application.assistant.capabilities.products.recommend import (
    RecommendProductsByNameArgs,
    RecommendProductsByNameCapability,
    RecommendProductsByNameResult,
)
from procurement_platform.domain.assistant import AssistantToolContext


class ApplicantRecommendationSkillHandler:
    """Hide product lookup endpoint details from the role-level agent."""

    def __init__(self, capability: RecommendProductsByNameCapability) -> None:
        self._capability = capability

    async def recommend_by_name(
        self,
        *,
        args: RecommendProductsByNameArgs,
        context: AssistantToolContext,
    ) -> RecommendProductsByNameResult:
        return await self._capability.execute(args=args, context=context)
