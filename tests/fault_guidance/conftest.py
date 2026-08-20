from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def validation_root(tmp_path: Path) -> Path:
    for relative in (
        "knowledge/catalog",
        "knowledge/fault-guidance",
        "backend/scripts/seed_demo_data.py",
        "docs/fault-knowledge-coverage-v1.md",
    ):
        source = REPOSITORY_ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    return tmp_path
