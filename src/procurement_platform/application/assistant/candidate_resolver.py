from procurement_platform.domain.assistant_session import AgentSessionState


class CandidateResolver:
    """Resolve only stable references that were persisted in the current session."""

    @staticmethod
    def resolve(reference: str, *, kind: str, state: AgentSessionState) -> int:
        matched = next(
            (
                item
                for item in state.last_recommendations
                if item.reference_id == reference and item.kind == kind
            ),
            None,
        )
        if matched is None:
            raise ValueError("候选引用不存在或已过期")
        try:
            return int(reference.rsplit(":", 1)[1])
        except (IndexError, ValueError) as exc:
            raise ValueError("候选引用无效") from exc
