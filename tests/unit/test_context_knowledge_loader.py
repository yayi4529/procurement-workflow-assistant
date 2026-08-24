from pathlib import Path

from procurement_platform.adapters.knowledge import load_optional_context


def test_optional_context_loads_utf8_markdown(tmp_path: Path) -> None:
    path = tmp_path / "fault-context.md"
    path.write_text("# UPS 故障\n\n风扇和电容需分别确认。", encoding="utf-8")

    assert load_optional_context(str(path)) == "# UPS 故障\n\n风扇和电容需分别确认。"


def test_optional_context_missing_file_does_not_block_startup(tmp_path: Path) -> None:
    assert load_optional_context(str(tmp_path / "missing.md")) is None
