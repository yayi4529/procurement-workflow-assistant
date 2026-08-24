from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class HybridDifferenceType(StrEnum):
    MATCH = "MATCH"
    LEGACY_NO_MATCH = "LEGACY_NO_MATCH"
    STRUCTURED_NO_WORKFLOW = "STRUCTURED_NO_WORKFLOW"
    WORKFLOW_MISMATCH = "WORKFLOW_MISMATCH"


class HybridRouteComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    structured_workflow: str | None
    legacy_workflow: str | None
    matched: bool
    difference_type: HybridDifferenceType

    @classmethod
    def compare(
        cls, *, structured_workflow: str | None, legacy_workflow: str | None
    ) -> "HybridRouteComparison":
        if structured_workflow == legacy_workflow:
            difference = HybridDifferenceType.MATCH
        elif legacy_workflow is None:
            difference = HybridDifferenceType.LEGACY_NO_MATCH
        elif structured_workflow is None:
            difference = HybridDifferenceType.STRUCTURED_NO_WORKFLOW
        else:
            difference = HybridDifferenceType.WORKFLOW_MISMATCH
        return cls(
            structured_workflow=structured_workflow,
            legacy_workflow=legacy_workflow,
            matched=difference is HybridDifferenceType.MATCH,
            difference_type=difference,
        )
