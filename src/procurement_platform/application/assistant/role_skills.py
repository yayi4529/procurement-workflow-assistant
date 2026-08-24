from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from procurement_platform.domain.enums import RoleCode


@dataclass(frozen=True, slots=True)
class WorkflowPhaseDefinition:
    name: str
    capabilities: frozenset[str]
    input_parser: str | None = None
    retry: int = 0
    on_success: str = "COMPLETED"
    on_failure: str = "FAILED"
    terminal_status: str | None = None


@dataclass(frozen=True, slots=True)
class RoleWorkflow:
    name: str
    description: str
    instructions: str
    triggers: tuple[str, ...]
    capability_names: frozenset[str]
    priority: int = 0
    stop_after_success: frozenset[str] = frozenset()
    phases: tuple[WorkflowPhaseDefinition, ...] = ()

    def __post_init__(self) -> None:
        if not self.phases:
            object.__setattr__(
                self,
                "phases",
                (WorkflowPhaseDefinition("execute", self.capability_names),),
            )
        names = {phase.name for phase in self.phases}
        if len(names) != len(self.phases):
            raise ValueError(f"duplicate workflow phase: {self.name}")
        for phase in self.phases:
            if not phase.capabilities.issubset(self.capability_names):
                raise ValueError(f"phase capability escapes workflow: {self.name}/{phase.name}")
            for target in (phase.on_success, phase.on_failure):
                if target not in names and target not in {"COMPLETED", "FAILED"}:
                    raise ValueError(
                        f"unknown workflow transition: {self.name}/{phase.name}->{target}"
                    )

    @property
    def initial_phase(self) -> WorkflowPhaseDefinition:
        return self.phases[0]

    def phase(self, name: str) -> WorkflowPhaseDefinition | None:
        return next((phase for phase in self.phases if phase.name == name), None)

    def match_score(self, user_text: str) -> tuple[int, int, int]:
        normalized = "".join(user_text.casefold().split())
        matches = tuple(
            trigger
            for trigger in self.triggers
            if "".join(trigger.casefold().split()) in normalized
        )
        return len(matches), sum(len(item) for item in matches), self.priority


@dataclass(frozen=True, slots=True)
class RoleSkill:
    name: str
    role: RoleCode
    description: str
    instructions: str
    workflows: Mapping[str, RoleWorkflow]

    def __post_init__(self) -> None:
        object.__setattr__(self, "workflows", MappingProxyType(dict(self.workflows)))


@dataclass(frozen=True, slots=True)
class RoleSkillSelection:
    skill: RoleSkill
    workflow: RoleWorkflow

    @property
    def system_context(self) -> str:
        return (
            "以下是当前角色和当前任务唯一生效的业务 Skill。遵守其中的业务边界、"
            "执行顺序和停止条件; 不要加载或切换到其他 workflow。\n"
            f'<role_skill name="{self.skill.name}">\n'
            f"{self.skill.instructions}\n"
            "</role_skill>\n"
            f'<workflow name="{self.workflow.name}">\n'
            f"{self.workflow.instructions}\n"
            "</workflow>"
        )


class RoleSkillRegistry:
    def __init__(self, skills: tuple[RoleSkill, ...]) -> None:
        by_role: dict[RoleCode, RoleSkill] = {}
        for skill in skills:
            if skill.role in by_role:
                raise ValueError(f"duplicate role skill: {skill.role.value}")
            if not skill.workflows:
                raise ValueError(f"role skill has no workflows: {skill.name}")
            by_role[skill.role] = skill
        self._by_role = MappingProxyType(by_role)

    def get(self, role: RoleCode) -> RoleSkill | None:
        return self._by_role.get(role)

    def validate_capabilities(self, known_names: frozenset[str]) -> "RoleSkillRegistry":
        unknown = sorted(
            {
                name
                for skill in self._by_role.values()
                for workflow in skill.workflows.values()
                for name in workflow.capability_names
                if name not in known_names
            }
        )
        if unknown:
            raise ValueError(f"role skills reference unknown capabilities: {', '.join(unknown)}")
        invalid_stops = sorted(
            {
                name
                for skill in self._by_role.values()
                for workflow in skill.workflows.values()
                for name in workflow.stop_after_success
                if name not in workflow.capability_names
            }
        )
        if invalid_stops:
            raise ValueError(
                "stop-after-success must reference workflow capabilities: "
                + ", ".join(invalid_stops)
            )
        return self

    def select(self, *, role: RoleCode, user_text: str) -> RoleSkillSelection | None:
        skill = self.get(role)
        if skill is None:
            return None
        ranked = sorted(
            ((workflow.match_score(user_text), workflow) for workflow in skill.workflows.values()),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0][0] == 0:
            return None
        return RoleSkillSelection(skill=skill, workflow=ranked[0][1])
