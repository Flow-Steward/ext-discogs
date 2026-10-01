#!/usr/bin/env python3
"""Discogs API extension entrypoint."""

from __future__ import annotations

import json
import sys

from handlers.common import fail
from handlers.router import handle_request


def main() -> int:
    raw = sys.stdin.read().strip()
    try:
        request_payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(json.dumps(fail("invalid_payload", "Request payload must be valid JSON.")))
        return 2

    if not isinstance(request_payload, dict):
        print(json.dumps(fail("invalid_payload", "Request payload must be an object.")))
        return 2

    response = handle_request(request_payload)
    print(json.dumps(response, sort_keys=True))
    return 0 if bool(response.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
