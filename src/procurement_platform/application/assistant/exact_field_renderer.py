from collections.abc import Mapping, Sequence


class ExactFieldRenderer:
    """Render sensitive/exact backend values without passing them back through an LLM."""

    @staticmethod
    def render(*, supplier_name: str, fields: Sequence[tuple[str, str | None]]) -> str:
        lines = [f"供应商: {supplier_name}"]
        lines.extend(
            f"{label}: {value if value not in {None, ''} else '未提供'}" for label, value in fields
        )
        return "\n".join(lines)

    @staticmethod
    def render_mapping(title: str, values: Mapping[str, str | None]) -> str:
        return "\n".join(
            [
                title,
                *(
                    f"{name}: {value if value not in {None, ''} else '未提供'}"
                    for name, value in values.items()
                ),
            ]
        )
