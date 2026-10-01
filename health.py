#!/usr/bin/env python3
"""Health check for the Discogs API extension."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _module_loadable(path: Path, module_name: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"{path.name} not found"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            return False, f"{path.name} is not loadable"
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as exc:
        return False, str(exc)[:200]
    return True, ""


def main() -> int:
    root = Path(__file__).parent
    checks = []
    for filename, module_name in (
        ("main.py", "discogs_main"),
        ("handlers/router.py", "discogs_router"),
        ("handlers/actions.py", "discogs_actions"),
        ("handlers/queries.py", "discogs_queries"),
        ("handlers/discogs_client.py", "discogs_client"),
    ):
        ok, detail = _module_loadable(root / filename, module_name)
        checks.append(
            {
                "name": filename,
                "status": "healthy" if ok else "failed",
                "detail": detail or f"{filename} is importable",
            }
        )
    for rel_path in (
        "extension.yaml",
        "extension-descriptor.yaml",
        "contracts/connection_types.yaml",
        "contracts/operation_manifest.yaml",
        "contracts/step_ui_manifest.yaml",
        "contracts/resource_query_manifest.yaml",
        "contracts/artifact_policies.yaml",
    ):
        exists = (root / rel_path).is_file()
        checks.append(
            {
                "name": rel_path,
                "status": "healthy" if exists else "failed",
                "detail": "present" if exists else "missing",
            }
        )
    all_healthy = all(item["status"] == "healthy" for item in checks)
    print(
        json.dumps(
            {
                "ok": all_healthy,
                "status": "healthy" if all_healthy else "failed",
                "provider": "discogs",
                "runtime": "local_subprocess",
                "checks": checks,
            },
            sort_keys=True,
        )
    )
    return 0 if all_healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
