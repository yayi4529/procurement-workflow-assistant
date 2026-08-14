"""Immutable facts prepared once for one assistant turn."""

from dataclasses import dataclass

from procurement_platform.domain.assistant import AssistantMessage, AssistantToolContext
from procurement_platform.domain.assistant_session import AgentSessionState, RecommendationReference
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.requirement import RequirementDetail
from procurement_platform.domain.user import CurrentUser


@dataclass(frozen=True, slots=True)
class AgentTurnContext:
    """Read-only application snapshot; never persisted or mutated after creation."""

    current_user: CurrentUser
    active_role: RoleCode
    session_state: AgentSessionState | None
    active_requirement: RequirementDetail | None
    recent_history: tuple[AssistantMessage, ...]
    current_recommendations: tuple[RecommendationReference, ...]
    tool_context: AssistantToolContext
