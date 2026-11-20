"""The action names and descriptions people read match the operation manifest."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

BUNDLE_ROOT = Path(__file__).resolve().parents[1]


def _operations() -> list[dict]:
    manifest = yaml.safe_load(
        (BUNDLE_ROOT / "contracts" / "operation_manifest.yaml").read_text(encoding="utf-8")
    )
    return manifest["operations"] if isinstance(manifest, dict) else manifest


def test_the_capabilities_page_shows_every_action_with_its_manifest_description() -> None:
    text = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted((BUNDLE_ROOT / "ui" / "components").glob("capabilities_*.yaml"))
    )
    for operation in _operations():
        line = f"**{operation['display_name']}**: {operation['description']}"
        assert line in text, operation["operation_id"]


def test_the_action_reference_lists_every_action_with_its_manifest_description() -> None:
    text = (BUNDLE_ROOT / "docs" / "workflow-actions.md").read_text(encoding="utf-8")
    reference = text.split("## Action reference", 1)[1]
    listed = re.findall(r"^- \*\*.+?\*\* \(`([a-z_]+)`\): ", reference, flags=re.M)
    operations = _operations()
    assert sorted(listed) == sorted(o["operation_id"] for o in operations)
    for operation in operations:
        line = (
            f"- **{operation['display_name']}** (`{operation['operation_id']}`): "
            f"{operation['description']}"
        )
        assert line in reference, operation["operation_id"]


def test_the_workflow_editor_descriptions_match_the_manifest() -> None:
    actions = yaml.safe_load(
        (BUNDLE_ROOT / "ui" / "actions" / "actions.yaml").read_text(encoding="utf-8")
    )["actions"]
    described = {a["action_id"]: a.get("description") for a in actions}
    for operation in _operations():
        assert described.get(operation["operation_id"]) == operation["description"]
