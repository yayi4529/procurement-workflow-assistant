from pathlib import Path

from validate_fault_knowledge import COVERAGE_VIEW, ROOT, render_coverage_view


def main() -> None:
    output = ROOT / COVERAGE_VIEW
    output.write_text(render_coverage_view(), encoding="utf-8")
    print(f"Rendered {Path(COVERAGE_VIEW).as_posix()}")


if __name__ == "__main__":
    main()
