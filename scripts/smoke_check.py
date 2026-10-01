#!/usr/bin/env python3
"""Smoke check for the Discogs API extension."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str], payload: dict[str, Any] | None = None, *, expect_ok: bool = True) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    output = proc.stdout.strip()
    if expect_ok and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or output or f"{args} failed")
    return json.loads(output) if output else {}


def main() -> int:
    health = _run(["health.py"])
    if health.get("status") != "healthy":
        raise RuntimeError(f"health failed: {health}")

    provider_health = _run(
        ["main.py"],
        {"mode": "query", "query": {"query_id": "provider_health"}},
    )
    if provider_health.get("ok") is not True:
        raise RuntimeError(f"provider_health failed: {provider_health}")

    search = _run(
        ["main.py"],
        {
            "mode": "query",
            "query": {
                "query_id": "discogs_search",
                "params": {"query": "Daft Punk Discovery", "type": "release"},
            },
        },
    )
    if not search.get("items"):
        raise RuntimeError(f"search failed: {search}")

    release = _run(
        ["main.py"],
        {
            "mode": "action",
            "action": {"action_id": "enrich_release_metadata", "input": {"release_id": 249504}},
        },
    )
    if release.get("result", {}).get("release_id") != 249504:
        raise RuntimeError(f"release enrichment failed: {release}")

    blocked_write = _run(
        ["main.py"],
        {
            "mode": "action",
            "action": {
                "action_id": "add_release_to_wantlist",
                "input": {"release_id": 249504, "confirm": True},
            },
        },
        expect_ok=False,
    )
    if blocked_write.get("error") != "write_actions_disabled":
        raise RuntimeError(f"write guard failed: {blocked_write}")

    print(json.dumps({"ok": True, "checked": ["health", "search", "release", "write_guard"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
