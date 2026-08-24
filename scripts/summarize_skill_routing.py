"""Summarize JSON assistant routing logs into the local strict acceptance report."""

import argparse
import json
from pathlib import Path


def summarize(lines: list[str]) -> dict[str, object]:
    routes: list[dict[str, object]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            payload.get("event") == "assistant_workflow_routed"
            or payload.get("message") == "assistant_workflow_routed"
        ):
            routes.append(payload)
    compared = [item for item in routes if "route_matched_legacy" in item]
    matched = sum(item.get("route_matched_legacy") is True for item in compared)
    rate = matched / len(compared) if compared else 0.0
    safety_failures = sum(
        bool(item.get("unauthorized_capability")) or bool(item.get("full_tool_fallback"))
        for item in routes
    )
    return {
        "route_count": len(routes),
        "compared_count": len(compared),
        "matched_count": matched,
        "workflow_match_rate": rate,
        "safety_failures": safety_failures,
        "routing_gate_passed": bool(compared) and rate >= 0.95 and safety_failures == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_file", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".local/skill-routing-acceptance.json"))
    args = parser.parse_args()
    result = summarize(args.log_file.read_text(encoding="utf-8").splitlines())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
