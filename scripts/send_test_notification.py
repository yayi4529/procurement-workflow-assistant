from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from urllib import error, request


def post(url: str, body: dict[str, object], headers: dict[str, str], timeout: float) -> int:
    payload = json.dumps(body, ensure_ascii=False).encode()
    req = request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return int(response.status)
    except error.HTTPError as exc:
        return exc.code


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the notification gateway")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--receiver-open-id", required=True)
    parser.add_argument("--requirement-id", type=int, required=True)
    parser.add_argument("--requirement-no", required=True)
    parser.add_argument("--notification-id", type=int)
    parser.add_argument("--dedup-key")
    parser.add_argument(
        "--mode", choices=("send", "duplicate", "conflict", "unauthorized"), default="send"
    )
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    token = os.environ.get("PROCUREMENT_NOTIFICATION_GATEWAY_TOKEN", "")
    if not token and args.mode != "unauthorized":
        print("FAIL: PROCUREMENT_NOTIFICATION_GATEWAY_TOKEN is missing", file=sys.stderr)
        return 2
    notification_id = args.notification_id or uuid.uuid4().int % 2_000_000_000 + 1
    dedup_key = args.dedup_key or f"dev-smoke-{uuid.uuid4()}"
    notification_payload: dict[str, object] = {
        "requirement_id": args.requirement_id,
        "requirement_no": args.requirement_no,
        "title": "真实飞书通知链路验证",
        "message": "仅用于开发环境 Smoke Test",
    }
    body: dict[str, object] = {
        "notification_id": notification_id,
        "dedup_key": dedup_key,
        "event_type": "DEV_NOTIFICATION_TEST",
        "platform_type": "FEISHU",
        "receiver_platform_user_id": args.receiver_open_id,
        "payload": notification_payload,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token if args.mode != 'unauthorized' else 'invalid'}",
        "Idempotency-Key": dedup_key,
        "X-Notification-Id": str(notification_id),
    }
    url = args.base_url.rstrip("/") + "/internal/notifications"
    expected = {"send": 204, "duplicate": 204, "conflict": 409, "unauthorized": 401}
    try:
        first = post(url, body, headers, args.timeout)
        if args.mode == "duplicate":
            status = post(url, body, headers, args.timeout)
        elif args.mode == "conflict":
            conflict = {
                **body,
                "payload": {**notification_payload, "title": "冲突负载"},
            }
            status = post(url, conflict, headers, args.timeout)
        else:
            status = first
    except (error.URLError, TimeoutError) as exc:
        print(f"FAIL: request failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"mode={args.mode} status={status} expected={expected[args.mode]}")
    return 0 if status == expected[args.mode] else 1


if __name__ == "__main__":
    raise SystemExit(main())
