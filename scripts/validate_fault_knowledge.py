from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
VOCABULARY_PATH = Path("knowledge/catalog/procurement-vocabulary-v1.yaml")
COVERAGE_PATH = Path("knowledge/catalog/fault-knowledge-coverage-v1.yaml")
KNOWLEDGE_ROOT = Path("knowledge/fault-guidance")
BACKEND_CATEGORY_SOURCE = Path("backend/scripts/seed_demo_data.py")
VOCABULARY_VIEW = Path("docs/task07-procurement-vocabulary-v1.md")
COVERAGE_VIEW = Path("docs/fault-knowledge-coverage-v1.md")

GUIDANCE_MODES = {"FAULT_DRIVEN", "CONDITIONAL", "DIRECT_ONLY"}
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
PRIORITIES = {"P0", "P1", "P2"}
COVERAGE_STATUSES = {"PLANNED", "EXISTING", "REVIEW_REQUIRED", "DEFERRED"}
KNOWLEDGE_STATUSES = {"ACTIVE", "INACTIVE"}
OBSOLETE_CATEGORIES = {"HV_SWITCHGEAR_10KV", "ROW_AC", "MAINTENANCE_TOOL"}
REQUIRED_SECTIONS = (
    "场景说明",
    "典型现象",
    "需要关注的信息",
    "判断采购需求前建议确认的信息",
    "采购相关知识",
    "数量规则",
    "不应直接推断的内容",
    "安全与人工介入",
)
FORBIDDEN_CLAIMS = ("默认采购1", "默认数量1", "自动选择型号", "兼容所有", "通用兼容")
UPPER_SNAKE_CASE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")
LOWER_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
KNOWLEDGE_ID = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+-\d{3}$")
KEBAB_FILENAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
CANDIDATE_BLOCK = re.compile(
    r"^- canonical_item: `(?P<canonical>[A-Z][A-Z0-9_]*)`\s*$\n"
    r"^- display_name: `?(?P<display>[^`\n]+?)`?\s*$\n"
    r"^- procurement_category: `(?P<category>[A-Z][A-Z0-9_]*)`\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    level: str
    path: str
    field: str
    reason: str

    def render(self) -> str:
        return f"{self.level} {self.path} [{self.field}] {self.reason}"


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    path: str
    metadata: dict[str, Any]
    content: str
    candidates: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    categories: int
    coverage_entries: int
    knowledge_files: int
    canonical_items_referenced: int
    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.level == "ERROR")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.level == "WARNING")


def _issue(level: str, path: Path | str, field: str, reason: str) -> ValidationIssue:
    return ValidationIssue(level, Path(path).as_posix(), field, reason)


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("YAML root must be a mapping")
    return value


def load_backend_categories(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "equipment_category_rows"
    )
    assignment = next(
        node
        for node in function.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "types" for target in node.targets)
    )
    if not isinstance(assignment.value, (ast.List, ast.Tuple)):
        raise ValueError("equipment category types must be a literal list")
    categories = set()
    for element in assignment.value.elts:
        if not isinstance(element, (ast.List, ast.Tuple)) or len(element.elts) < 3:
            raise ValueError("invalid equipment category seed row")
        code = ast.literal_eval(element.elts[2])
        if not isinstance(code, str):
            raise ValueError("equipment category code must be a string")
        categories.add(code)
    return categories


def load_vocabulary(path: Path) -> tuple[dict[str, dict[str, str]], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    try:
        data = _load_yaml(path)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        return {}, [_issue("ERROR", path, "yaml", str(exc))]
    if data.get("schema_version") != 1:
        issues.append(_issue("ERROR", path, "schema_version", "must equal 1"))
    raw_categories = data.get("categories")
    if not isinstance(raw_categories, dict):
        return {}, [*issues, _issue("ERROR", path, "categories", "must be a mapping")]
    items: dict[str, dict[str, str]] = {}
    for category, raw_items in raw_categories.items():
        if not isinstance(category, str) or not isinstance(raw_items, list):
            issues.append(_issue("ERROR", path, "categories", "invalid category entry"))
            continue
        for index, raw_item in enumerate(raw_items):
            field = f"categories.{category}[{index}]"
            if not isinstance(raw_item, dict):
                issues.append(_issue("ERROR", path, field, "must be a mapping"))
                continue
            canonical = raw_item.get("canonical_item")
            display = raw_item.get("display_name")
            aliases = raw_item.get("aliases")
            if not isinstance(canonical, str) or not canonical:
                issues.append(_issue("ERROR", path, f"{field}.canonical_item", "must be non-empty"))
                continue
            if canonical in items:
                issues.append(
                    _issue("ERROR", path, f"{field}.canonical_item", f"duplicate {canonical}")
                )
            if not isinstance(display, str) or not display.strip():
                issues.append(_issue("ERROR", path, f"{field}.display_name", "must be non-empty"))
            if (
                not isinstance(aliases, list)
                or not aliases
                or not all(isinstance(alias, str) and alias.strip() for alias in aliases)
            ):
                issues.append(
                    _issue("ERROR", path, f"{field}.aliases", "must be a non-empty string list")
                )
            items[canonical] = {"category": category, "display_name": display}
    return items, issues


def load_vocabulary_view(path: Path) -> dict[str, dict[str, object]]:
    document = path.read_text(encoding="utf-8")
    items: dict[str, dict[str, object]] = {}
    category: str | None = None
    for line in document.splitlines():
        heading = re.match(r"^## ([A-Z][A-Z0-9_]*) — ", line)
        if heading:
            category = heading.group(1)
            continue
        row = re.match(
            r"^\| `(?P<canonical>[A-Z][A-Z0-9_]*)` \| (?P<display>[^|]+) \| "
            r"(?P<aliases>[^|]+) \|$",
            line,
        )
        if row is not None and category is not None:
            items[row.group("canonical")] = {
                "category": category,
                "display_name": row.group("display").strip(),
                "aliases": [alias.strip() for alias in row.group("aliases").split("、")],
            }
    return items


def _parse_front_matter(path: Path, root: Path) -> KnowledgeDocument:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("YAML front matter opening delimiter is missing")
    try:
        closing = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("YAML front matter closing delimiter is missing") from exc
    metadata = yaml.safe_load("\n".join(lines[1:closing]))
    if not isinstance(metadata, dict):
        raise ValueError("YAML front matter must be a mapping")
    content = "\n".join(lines[closing + 1 :]).strip()
    candidates = tuple(
        (match.group("canonical"), match.group("display").strip(), match.group("category"))
        for match in CANDIDATE_BLOCK.finditer(content)
    )
    return KnowledgeDocument(path.relative_to(root).as_posix(), metadata, content, candidates)


def _validate_document(
    document: KnowledgeDocument,
    categories: set[str],
    vocabulary: dict[str, dict[str, str]],
) -> list[ValidationIssue]:
    path = Path(document.path)
    metadata = document.metadata
    issues: list[ValidationIssue] = []
    if metadata.get("schema_version") != 1:
        issues.append(_issue("ERROR", path, "schema_version", "must equal 1"))
    for field in (
        "knowledge_id",
        "title",
        "equipment_category",
        "knowledge_type",
        "risk_level",
        "status",
    ):
        if not isinstance(metadata.get(field), str) or not str(metadata[field]).strip():
            issues.append(_issue("ERROR", path, field, "must be a non-empty string"))
    category = metadata.get("equipment_category")
    if isinstance(category, str) and category not in categories:
        issues.append(_issue("ERROR", path, "equipment_category", f"unknown category: {category}"))
    if metadata.get("knowledge_type") != "FAULT_GUIDE":
        issues.append(_issue("ERROR", path, "knowledge_type", "must equal FAULT_GUIDE"))
    aliases = metadata.get("aliases")
    if (
        not isinstance(aliases, list)
        or not aliases
        or not all(isinstance(alias, str) and alias.strip() for alias in aliases)
    ):
        issues.append(_issue("ERROR", path, "aliases", "must be a non-empty string list"))
    if metadata.get("risk_level") not in RISK_LEVELS:
        issues.append(_issue("ERROR", path, "risk_level", f"must be one of {sorted(RISK_LEVELS)}"))
    if metadata.get("status") not in KNOWLEDGE_STATUSES:
        issues.append(
            _issue("ERROR", path, "status", f"must be one of {sorted(KNOWLEDGE_STATUSES)}")
        )
    version = metadata.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        issues.append(_issue("ERROR", path, "version", "must be a positive integer"))
    if not document.content:
        issues.append(_issue("ERROR", path, "content", "must be non-empty"))
    if metadata.get("status") == "ACTIVE":
        title = metadata.get("title")
        if isinstance(title, str) and not re.search(
            rf"^#\s+{re.escape(title)}\s*$", document.content, re.MULTILINE
        ):
            issues.append(
                _issue("ERROR", path, "title", "body must contain a matching level-1 title")
            )
        for section in REQUIRED_SECTIONS:
            match = re.search(
                rf"^##\s+{re.escape(section)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
                document.content,
                re.MULTILINE | re.DOTALL,
            )
            if match is None or not match.group("body").strip():
                issues.append(
                    _issue(
                        "ERROR", path, f"section:{section}", "required non-empty section is missing"
                    )
                )
    canonical_mentions = re.findall(r"canonical_item:\s*`([^`]+)`", document.content)
    if len(canonical_mentions) != len(document.candidates):
        issues.append(
            _issue(
                "ERROR",
                path,
                "candidate",
                "each canonical_item must use one complete standard candidate block",
            )
        )
    for canonical, display, procurement_category in document.candidates:
        item = vocabulary.get(canonical)
        if item is None:
            issues.append(
                _issue("ERROR", path, "canonical_item", f"unknown canonical_item: {canonical}")
            )
            continue
        if display != item["display_name"]:
            issues.append(
                _issue(
                    "ERROR",
                    path,
                    "display_name",
                    f"{canonical} expects {item['display_name']!r}, got {display!r}",
                )
            )
        if procurement_category != item["category"]:
            issues.append(
                _issue(
                    "ERROR",
                    path,
                    "procurement_category",
                    f"{canonical} belongs to {item['category']}, got {procurement_category}",
                )
            )
    knowledge_id = metadata.get("knowledge_id")
    if isinstance(knowledge_id, str) and not KNOWLEDGE_ID.fullmatch(knowledge_id):
        issues.append(
            _issue("WARNING", path, "knowledge_id", "recommended format is CATEGORY-TOPIC-NNN")
        )
    if not KEBAB_FILENAME.fullmatch(path.name):
        issues.append(_issue("WARNING", path, "filename", "recommended format is kebab-case.md"))
    for claim in FORBIDDEN_CLAIMS:
        if claim in document.content.replace(" ", ""):
            issues.append(
                _issue("WARNING", path, "content", f"review potentially forbidden claim: {claim}")
            )
    return issues


def _render_coverage(data: dict[str, Any]) -> str:
    entries = data.get("entries", [])
    lines = [
        "# Fault Knowledge Coverage V1",
        "",
        (
            "> Generated from `knowledge/catalog/fault-knowledge-coverage-v1.yaml`. "
            "Do not edit this view independently."
        ),
        "",
        (
            "| source_category | fault_topic_id | candidate_items | guidance_mode | risk | "
            "priority | status | planned_knowledge_file |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for entry in entries:
        candidates = ", ".join(item["canonical_item"] for item in entry["candidate_items"]) or "-"
        path = entry.get("planned_knowledge_file") or "-"
        lines.append(
            f"| `{entry['source_category']}` | `{entry['fault_topic_id']}` | {candidates} | "
            f"{entry['guidance_mode']} | {entry['risk_level']} | {entry['priority']} | "
            f"{entry['status']} | {path} |"
        )
    counts = Counter(entry["status"] for entry in entries)
    lines += [
        "",
        "## Summary",
        "",
        f"- Entries: {len(entries)}",
        f"- EXISTING: {counts['EXISTING']}",
        f"- PLANNED: {counts['PLANNED']}",
        f"- REVIEW_REQUIRED: {counts['REVIEW_REQUIRED']}",
        f"- DEFERRED: {counts['DEFERRED']}",
        "",
    ]
    return "\n".join(lines)


def render_coverage_view(root: Path = ROOT) -> str:
    return _render_coverage(_load_yaml(root / COVERAGE_PATH))


def validate_repository(root: Path = ROOT) -> ValidationReport:
    issues: list[ValidationIssue] = []
    try:
        categories = load_backend_categories(root / BACKEND_CATEGORY_SOURCE)
    except (OSError, UnicodeError, ValueError, StopIteration, SyntaxError) as exc:
        return ValidationReport(
            0, 0, 0, 0, (_issue("ERROR", BACKEND_CATEGORY_SOURCE, "categories", str(exc)),)
        )
    if len(categories) != 17:
        issues.append(
            _issue(
                "ERROR",
                BACKEND_CATEGORY_SOURCE,
                "categories",
                f"expected 17, got {len(categories)}",
            )
        )
    if categories & OBSOLETE_CATEGORIES:
        issues.append(
            _issue(
                "ERROR",
                BACKEND_CATEGORY_SOURCE,
                "categories",
                f"obsolete categories: {sorted(categories & OBSOLETE_CATEGORIES)}",
            )
        )

    vocabulary, vocabulary_issues = load_vocabulary(root / VOCABULARY_PATH)
    issues.extend(vocabulary_issues)
    for canonical, item in vocabulary.items():
        if item["category"] not in categories:
            issues.append(
                _issue("ERROR", VOCABULARY_PATH, canonical, f"unknown category: {item['category']}")
            )

    try:
        vocabulary_view = load_vocabulary_view(root / VOCABULARY_VIEW)
        machine_categories = _load_yaml(root / VOCABULARY_PATH).get("categories", {})
        flattened_machine = {
            item["canonical_item"]: {
                "category": category,
                "display_name": item["display_name"],
                "aliases": item["aliases"],
            }
            for category, raw_items in machine_categories.items()
            for item in raw_items
        }
        if vocabulary_view != flattened_machine:
            issues.append(
                _issue(
                    "ERROR",
                    VOCABULARY_VIEW,
                    "generated_view",
                    "does not match machine Vocabulary YAML",
                )
            )
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        issues.append(_issue("ERROR", VOCABULARY_VIEW, "generated_view", str(exc)))

    try:
        coverage = _load_yaml(root / COVERAGE_PATH)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        return ValidationReport(
            len(categories),
            0,
            0,
            0,
            tuple([*issues, _issue("ERROR", COVERAGE_PATH, "yaml", str(exc))]),
        )
    if coverage.get("schema_version") != 1:
        issues.append(_issue("ERROR", COVERAGE_PATH, "schema_version", "must equal 1"))
    raw_entries = coverage.get("entries")
    if not isinstance(raw_entries, list):
        raw_entries = []
        issues.append(_issue("ERROR", COVERAGE_PATH, "entries", "must be a list"))

    topic_ids: list[str] = []
    planned_files: list[str] = []
    referenced: set[str] = set()
    coverage_by_path: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(raw_entries):
        field = f"entries[{index}]"
        if not isinstance(entry, dict):
            issues.append(_issue("ERROR", COVERAGE_PATH, field, "must be a mapping"))
            continue
        required = {
            "source_category",
            "fault_topic_id",
            "fault_topic",
            "candidate_items",
            "guidance_mode",
            "minimum_confirmed_facts",
            "risk_level",
            "priority",
            "planned_knowledge_file",
            "status",
        }
        for missing in sorted(required - entry.keys()):
            issues.append(
                _issue("ERROR", COVERAGE_PATH, f"{field}.{missing}", "required field is missing")
            )
        source = entry.get("source_category")
        topic_id = entry.get("fault_topic_id")
        if source not in categories:
            issues.append(
                _issue(
                    "ERROR",
                    COVERAGE_PATH,
                    f"{field}.source_category",
                    f"unknown category: {source}",
                )
            )
        if not isinstance(topic_id, str) or not UPPER_SNAKE_CASE.fullmatch(topic_id):
            issues.append(
                _issue(
                    "ERROR", COVERAGE_PATH, f"{field}.fault_topic_id", "must be UPPER_SNAKE_CASE"
                )
            )
        else:
            topic_ids.append(topic_id)
        if not isinstance(entry.get("fault_topic"), str) or not entry["fault_topic"].strip():
            issues.append(
                _issue("ERROR", COVERAGE_PATH, f"{field}.fault_topic", "must be non-empty")
            )
        if entry.get("guidance_mode") not in GUIDANCE_MODES:
            issues.append(
                _issue(
                    "ERROR",
                    COVERAGE_PATH,
                    f"{field}.guidance_mode",
                    f"must be one of {sorted(GUIDANCE_MODES)}",
                )
            )
        facts = entry.get("minimum_confirmed_facts")
        if (
            not isinstance(facts, list)
            or not facts
            or not all(isinstance(fact, str) and LOWER_SNAKE_CASE.fullmatch(fact) for fact in facts)
        ):
            issues.append(
                _issue(
                    "ERROR",
                    COVERAGE_PATH,
                    f"{field}.minimum_confirmed_facts",
                    "must be a non-empty lower_snake_case list",
                )
            )
        if entry.get("risk_level") not in RISK_LEVELS:
            issues.append(
                _issue(
                    "ERROR",
                    COVERAGE_PATH,
                    f"{field}.risk_level",
                    f"must be one of {sorted(RISK_LEVELS)}",
                )
            )
        if entry.get("priority") not in PRIORITIES:
            issues.append(
                _issue(
                    "ERROR",
                    COVERAGE_PATH,
                    f"{field}.priority",
                    f"must be one of {sorted(PRIORITIES)}",
                )
            )
        if entry.get("status") not in COVERAGE_STATUSES:
            issues.append(
                _issue(
                    "ERROR",
                    COVERAGE_PATH,
                    f"{field}.status",
                    f"must be one of {sorted(COVERAGE_STATUSES)}",
                )
            )
        raw_candidates = entry.get("candidate_items")
        if not isinstance(raw_candidates, list):
            issues.append(
                _issue("ERROR", COVERAGE_PATH, f"{field}.candidate_items", "must be a list")
            )
            raw_candidates = []
        for candidate_index, candidate in enumerate(raw_candidates):
            candidate_field = f"{field}.candidate_items[{candidate_index}]"
            if not isinstance(candidate, dict):
                issues.append(_issue("ERROR", COVERAGE_PATH, candidate_field, "must be a mapping"))
                continue
            canonical = candidate.get("canonical_item")
            procurement = candidate.get("procurement_category")
            item = vocabulary.get(canonical) if isinstance(canonical, str) else None
            if item is None:
                issues.append(
                    _issue(
                        "ERROR",
                        COVERAGE_PATH,
                        f"{candidate_field}.canonical_item",
                        f"unknown canonical_item: {canonical}",
                    )
                )
                continue
            referenced.add(canonical)
            if procurement != item["category"]:
                issues.append(
                    _issue(
                        "ERROR",
                        COVERAGE_PATH,
                        f"{candidate_field}.procurement_category",
                        f"{canonical} belongs to {item['category']}, got {procurement}",
                    )
                )
        planned = entry.get("planned_knowledge_file")
        if planned is not None and not isinstance(planned, str):
            issues.append(
                _issue(
                    "ERROR",
                    COVERAGE_PATH,
                    f"{field}.planned_knowledge_file",
                    "must be a path string or null",
                )
            )
        elif isinstance(planned, str):
            normalized = PurePosixPath(planned).as_posix()
            planned_files.append(normalized)
            coverage_by_path[normalized] = entry
            if entry.get("status") == "EXISTING" and not (root / normalized).is_file():
                issues.append(
                    _issue(
                        "ERROR",
                        COVERAGE_PATH,
                        f"{field}.planned_knowledge_file",
                        f"EXISTING file does not exist: {normalized}",
                    )
                )
        elif entry.get("status") == "EXISTING":
            issues.append(
                _issue(
                    "ERROR",
                    COVERAGE_PATH,
                    f"{field}.planned_knowledge_file",
                    "EXISTING entry requires a file",
                )
            )

    for value, count in Counter(topic_ids).items():
        if count > 1:
            issues.append(_issue("ERROR", COVERAGE_PATH, "fault_topic_id", f"duplicate {value}"))
    for value, count in Counter(planned_files).items():
        if count > 1:
            issues.append(
                _issue("ERROR", COVERAGE_PATH, "planned_knowledge_file", f"duplicate {value}")
            )
    for canonical in sorted(set(vocabulary) - referenced):
        issues.append(
            _issue(
                "ERROR", COVERAGE_PATH, "coverage", f"canonical_item is not covered: {canonical}"
            )
        )

    documents: list[KnowledgeDocument] = []
    knowledge_root = root / KNOWLEDGE_ROOT
    for path in sorted(knowledge_root.rglob("*.md")):
        try:
            document = _parse_front_matter(path, root)
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
            issues.append(_issue("ERROR", path.relative_to(root), "front_matter", str(exc)))
            continue
        documents.append(document)
        issues.extend(_validate_document(document, categories, vocabulary))
        coverage_entry = coverage_by_path.get(document.path)
        if document.metadata.get("status") == "ACTIVE" and coverage_entry is None:
            issues.append(
                _issue("ERROR", document.path, "coverage", "active knowledge has no Coverage entry")
            )
        if coverage_entry is not None:
            allowed = {
                candidate["canonical_item"]
                for candidate in coverage_entry.get("candidate_items", [])
                if isinstance(candidate, dict) and isinstance(candidate.get("canonical_item"), str)
            }
            actual = {candidate[0] for candidate in document.candidates}
            if actual != allowed:
                issues.append(
                    _issue(
                        "ERROR",
                        document.path,
                        "candidate_items",
                        f"Coverage allows {sorted(allowed)}, Markdown declares {sorted(actual)}",
                    )
                )

    knowledge_ids = [
        document.metadata.get("knowledge_id")
        for document in documents
        if isinstance(document.metadata.get("knowledge_id"), str)
    ]
    for value, count in Counter(knowledge_ids).items():
        if count > 1:
            issues.append(_issue("ERROR", KNOWLEDGE_ROOT, "knowledge_id", f"duplicate {value}"))

    try:
        view = (root / COVERAGE_VIEW).read_text(encoding="utf-8")
        expected_view = _render_coverage(coverage)
        if view != expected_view:
            issues.append(
                _issue(
                    "ERROR",
                    COVERAGE_VIEW,
                    "generated_view",
                    "does not match Coverage YAML; run scripts/render_fault_knowledge_coverage.py",
                )
            )
    except OSError as exc:
        issues.append(_issue("ERROR", COVERAGE_VIEW, "generated_view", str(exc)))

    return ValidationReport(
        len(categories), len(raw_entries), len(documents), len(referenced), tuple(issues)
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Fault Knowledge catalogs and Markdown")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--verbose", action="store_true", help="print warnings and summary details")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = validate_repository(args.root.resolve())
    for issue in report.issues:
        if issue.level == "ERROR" or args.verbose:
            print(issue.render())
    if report.errors:
        print("Fault knowledge validation failed.")
    else:
        print("Fault knowledge validation passed.")
    print(f"Categories: {report.categories}")
    print(f"Coverage entries: {report.coverage_entries}")
    print(f"Knowledge files: {report.knowledge_files}")
    print(f"Canonical items referenced: {report.canonical_items_referenced}")
    print(f"Errors: {len(report.errors)}")
    print(f"Warnings: {len(report.warnings)}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
