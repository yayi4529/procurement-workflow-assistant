from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from procurement_platform.adapters.backend.fake_seed import FakeBackendSeedLoader  # noqa: E402
from procurement_platform.bootstrap.settings import Settings  # noqa: E402
from procurement_platform.domain.enums import BackendMode  # noqa: E402


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"env file not found: {path}")
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid env line {line_number}")
        name, value = line.split("=", 1)
        result[name.strip()] = value.strip().strip("'\"")
    return result


def validate(env_file: Path) -> None:
    values = dict(os.environ)
    values.update(load_env_file(env_file))
    settings = Settings.from_env(values)
    if settings.environment.lower() not in {"development", "test"}:
        raise ValueError("environment must be development or test")
    if settings.backend_mode is not BackendMode.FAKE:
        raise ValueError("backend mode must be fake")
    if settings.llm_enabled:
        raise ValueError("LLM must be disabled")
    if not settings.feishu.enabled:
        raise ValueError("Feishu integration must be enabled")
    if not settings.notification_gateway.enabled:
        raise ValueError("notification gateway must be enabled")
    if settings.notification_gateway.bearer_token is None:
        raise ValueError("notification gateway token is required for the debug harness")
    if not settings.debug_identity_probe_enabled:
        raise ValueError("debug identity probe must be enabled")
    if not settings.development_notification_renderer_enabled:
        raise ValueError("development notification renderer must be enabled")
    seed_path = Path(settings.fake_data_path)
    if not seed_path.is_absolute():
        seed_path = ROOT / seed_path
    FakeBackendSeedLoader.load(seed_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Feishu + Fake debug configuration")
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate(args.env_file)
    except (ValueError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: Feishu + Fake configuration is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
