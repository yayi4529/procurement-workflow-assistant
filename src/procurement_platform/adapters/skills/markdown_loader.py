from pathlib import Path
from typing import cast

import yaml

from procurement_platform.application.assistant.role_skills import (
    RoleSkill,
    RoleSkillRegistry,
    RoleWorkflow,
    WorkflowPhaseDefinition,
)
from procurement_platform.domain.enums import RoleCode


class MarkdownRoleSkillLoader:
    """Load governed role skills without executing files contained in skill folders."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def load(self) -> RoleSkillRegistry:
        if not self._root.is_dir():
            raise ValueError(f"role skills directory does not exist: {self._root}")
        skills = tuple(
            self._load_skill(path)
            for path in sorted(self._root.iterdir())
            if path.is_dir() and (path / "SKILL.md").is_file()
        )
        if not skills:
            raise ValueError(f"role skills directory contains no skills: {self._root}")
        return RoleSkillRegistry(skills)

    def _load_skill(self, skill_path: Path) -> RoleSkill:
        metadata, instructions = self._read_markdown(skill_path / "SKILL.md")
        name = self._required_string(metadata, "name")
        description = self._required_string(metadata, "description")
        skill_metadata = metadata.get("metadata")
        if not isinstance(skill_metadata, dict):
            raise ValueError(f"skill metadata must be a mapping: {skill_path / 'SKILL.md'}")
        role_value = self._required_string(cast(dict[str, object], skill_metadata), "role")
        try:
            role = RoleCode(role_value)
        except ValueError as exc:
            raise ValueError(f"invalid role in {skill_path / 'SKILL.md'}: {role_value}") from exc
        workflows_path = skill_path / "workflows"
        workflows = {
            workflow.name: workflow
            for workflow in (
                self._load_workflow(path)
                for path in sorted(workflows_path.glob("*.md"))
                if path.is_file()
            )
        }
        return RoleSkill(
            name=name,
            role=role,
            description=description,
            instructions=instructions,
            workflows=workflows,
        )

    def _load_workflow(self, path: Path) -> RoleWorkflow:
        metadata, instructions = self._read_markdown(path)
        name = self._required_string(metadata, "name")
        description = self._required_string(metadata, "description")
        triggers = self._string_list(metadata, "triggers", path)
        capabilities = self._string_list(metadata, "capabilities", path)
        stop_after_success = self._optional_string_list(metadata, "stop-after-success", path)
        priority = metadata.get("priority", 0)
        if not isinstance(priority, int):
            raise ValueError(f"priority must be an integer: {path}")
        phases = self._phases(metadata.get("phases"), capabilities, path)
        return RoleWorkflow(
            name=name,
            description=description,
            instructions=instructions,
            triggers=triggers,
            capability_names=frozenset(capabilities),
            priority=priority,
            stop_after_success=frozenset(stop_after_success),
            phases=phases,
        )

    @staticmethod
    def _phases(
        value: object, capabilities: tuple[str, ...], path: Path
    ) -> tuple[WorkflowPhaseDefinition, ...]:
        if value is None:
            return (WorkflowPhaseDefinition("execute", frozenset(capabilities)),)
        if not isinstance(value, list) or not value:
            raise ValueError(f"phases must be a non-empty list: {path}")
        phases: list[WorkflowPhaseDefinition] = []
        for raw in value:
            if not isinstance(raw, dict):
                raise ValueError(f"phase must be a mapping: {path}")
            name = raw.get("name")
            phase_capabilities = raw.get("capabilities")
            retry = raw.get("retry", 0)
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"phase name must be a string: {path}")
            if not isinstance(phase_capabilities, list) or not all(
                isinstance(item, str) for item in phase_capabilities
            ):
                raise ValueError(f"phase capabilities must be a string list: {path}")
            if not isinstance(retry, int) or retry < 0:
                raise ValueError(f"phase retry must be a non-negative integer: {path}")
            phases.append(
                WorkflowPhaseDefinition(
                    name=name.strip(),
                    capabilities=frozenset(cast(list[str], phase_capabilities)),
                    input_parser=(
                        str(raw["input-parser"]).strip()
                        if raw.get("input-parser") is not None
                        else None
                    ),
                    retry=retry,
                    on_success=str(raw.get("on-success", "COMPLETED")),
                    on_failure=str(raw.get("on-failure", "FAILED")),
                    terminal_status=(
                        str(raw["terminal-status"]).strip()
                        if raw.get("terminal-status") is not None
                        else None
                    ),
                )
            )
        return tuple(phases)

    def _read_markdown(self, path: Path) -> tuple[dict[str, object], str]:
        resolved = path.resolve()
        if self._root not in resolved.parents:
            raise ValueError(f"skill path escapes configured root: {path}")
        text = resolved.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError(f"missing YAML frontmatter: {path}")
        try:
            closing_index = next(
                index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
            )
        except StopIteration as exc:
            raise ValueError(f"unterminated YAML frontmatter: {path}") from exc
        parsed = yaml.safe_load("\n".join(lines[1:closing_index]))
        if not isinstance(parsed, dict):
            raise ValueError(f"frontmatter must be a mapping: {path}")
        metadata = cast(dict[str, object], parsed)
        instructions = "\n".join(lines[closing_index + 1 :]).strip()
        if not instructions:
            raise ValueError(f"skill instructions are empty: {path}")
        return metadata, instructions

    @staticmethod
    def _required_string(metadata: dict[str, object], key: str) -> str:
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"frontmatter field must be a non-empty string: {key}")
        return value.strip()

    @staticmethod
    def _string_list(metadata: dict[str, object], key: str, path: Path) -> tuple[str, ...]:
        value = metadata.get(key)
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) and item.strip() for item in value)
        ):
            raise ValueError(f"{key} must be a non-empty string list: {path}")
        return tuple(cast(str, item).strip() for item in value)

    @staticmethod
    def _optional_string_list(metadata: dict[str, object], key: str, path: Path) -> tuple[str, ...]:
        value = metadata.get(key, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise ValueError(f"{key} must be a string list: {path}")
        return tuple(cast(str, item).strip() for item in value)
