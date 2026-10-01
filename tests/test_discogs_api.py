from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import yaml

BUNDLE_ROOT = Path(__file__).resolve().parents[1]
if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))


def _invoke(payload: dict, *, expect_ok: bool = True) -> dict:
    proc = subprocess.run(
        [sys.executable, str(BUNDLE_ROOT / "main.py")],
        cwd=str(BUNDLE_ROOT),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if expect_ok:
        assert proc.returncode == 0, proc.stderr or proc.stdout
    else:
        assert proc.returncode != 0
    return json.loads(proc.stdout)


def _forbidden_contract_json_files() -> list[str]:
    forbidden: list[str] = []
    for path in BUNDLE_ROOT.rglob("*.json"):
        rel = path.relative_to(BUNDLE_ROOT)
        if (
            path.name in {"extension.json", "manifest.json"}
            or rel.match("schemas/*.schema.json")
            or rel.match("ui/ui_manifest.json")
            or rel.match("ui/actions/actions.json")
            or rel.match("ui/queries/queries.json")
            or rel.match("ui/pages/*.json")
            or rel.match("ui/components/*.json")
            or rel.match("contracts/*.json")
        ):
            forbidden.append(rel.as_posix())
    return sorted(forbidden)


# The host compiling and validating this bundle is Core's own test
# (tests/unit/test_discogs_and_image_processing_bundle_contracts.py): a bundle's tests
# run standalone, without the monorepo.
def test_bundle_carries_no_json_contract_files() -> None:
    assert _forbidden_contract_json_files() == []


def test_bundled_discogs_workflows_are_read_only_and_declared() -> None:
    descriptor = yaml.safe_load((BUNDLE_ROOT / "extension-descriptor.yaml").read_text())
    workflows = descriptor["artifacts"]["workflows"]

    assert {item["workflow_id"] for item in workflows} == {
        "discogs_search_vinyl_releases",
        "discogs_artist_profile_and_releases",
    }

    operation_ids: set[str] = set()
    for item in workflows:
        workflow = yaml.safe_load((BUNDLE_ROOT / item["ref"]).read_text())
        assert workflow["workflow_id"] == item["workflow_id"]
        assert workflow["settings"]["callable"]["side_effects"] == []
        for phase in workflow["phases"]:
            for step in phase["steps"]:
                connector = step.get("override", {}).get("connector", {})
                if connector:
                    assert step["connector_id"] == "extension.com.discogs.api"
                    assert connector["extension_id"] == "com.discogs.api"
                    operation_ids.add(connector["operation_id"])

    assert operation_ids == {
        "discogs_search_database",
        "discogs_get_artist",
        "discogs_get_artist_releases",
    }


def test_health_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(BUNDLE_ROOT / "health.py")],
        cwd=str(BUNDLE_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["status"] == "healthy"
    assert payload["provider"] == "discogs"


def test_mock_search_and_release_enrichment() -> None:
    search = _invoke(
        {
            "mode": "query",
            "query": {
                "query_id": "discogs_search",
                "params": {
                    "query": "Daft Punk Discovery",
                    "type": "release",
                    "connection_config": {"mock_mode": True},
                },
            },
        }
    )
    assert search["ok"] is True
    assert search["items"][0]["id"] == 249504
    assert search["items"][0]["uri"].startswith("https://www.discogs.com/")

    release = _invoke(
        {
            "mode": "action",
            "action": {
                "action_id": "enrich_release_metadata",
                "input": {"release_id": 249504, "connection_config": {"mock_mode": True}},
            },
        }
    )
    assert release["ok"] is True
    assert release["result"]["release_id"] == 249504
    assert release["result"]["artists"][0]["name"] == "Daft Punk"


def test_connection_status_uses_payload_provider_secret() -> None:
    from handlers.router import handle_request

    payload = {
        "mode": "query",
        "query": {
            "query_id": "connection_status",
            "context": {"project_id": "proj-7"},
            "params": {"secrets": {"user_token": "provider-secret-token"}},
        },
    }
    result = handle_request(payload)
    assert result["ok"] is True
    assert result["result"]["auth_mode"] == "token"
    assert result["result"]["token_source"] == "connection"


def test_url_safety_blocks_unsafe_hosts_and_schemes() -> None:
    from handlers.discogs_client import DiscogsClient

    client = DiscogsClient.from_payload(
        {"base_url": "http://api.discogs.com", "allowed_hosts": ["api.discogs.com"]}
    )
    allowed, reason = client.validate_url("http://api.discogs.com/database/search")
    assert allowed is False
    assert "HTTPS" in reason

    client = DiscogsClient.from_payload(
        {"base_url": "https://evil.example", "allowed_hosts": ["api.discogs.com"]}
    )
    allowed, reason = client.validate_url("https://evil.example/database/search")
    assert allowed is False
    assert "allowed_hosts" in reason

    client = DiscogsClient.from_payload(
        {"base_url": "https://api.discogs.com", "allowed_hosts": ["api.discogs.com"]}
    )
    allowed, reason = client.validate_url("https://user:pass@api.discogs.com/database/search")
    assert allowed is False
    assert "credentials" in reason


def test_token_is_sent_only_in_headers_and_not_returned(monkeypatch) -> None:
    from handlers import discogs_client

    captured: dict[str, object] = {}

    class _FakeResponse:
        status = 200
        headers: ClassVar[dict[str, str]] = {
            "Discogs-Ratelimit": "60",
            "Discogs-Ratelimit-Used": "2",
            "Discogs-Ratelimit-Remaining": "58",
        }

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, _size: int = -1) -> bytes:
            return b'{"username":"flowsteward"}'

    def _fake_urlopen(request, timeout: int):
        captured["headers"] = dict(request.header_items())
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(discogs_client, "urlopen", _fake_urlopen)

    client = discogs_client.DiscogsClient.from_payload(
        {
            "base_url": "https://api.discogs.com",
            "allowed_hosts": ["api.discogs.com"],
            "mock_mode": False,
            "user_agent": "FlowStewardDiscogsExtension/0.1",
        },
        {"user_token": "secret-token"},
    )
    direct = client.identity()
    headers = {key.lower(): value for key, value in dict(captured["headers"]).items()}
    assert direct["ok"] is True
    assert headers["authorization"] == "Discogs token=secret-token"
    assert "secret-token" not in json.dumps(direct)


def test_redirects_are_rejected_before_credentials_can_be_forwarded() -> None:
    from urllib.request import Request

    from handlers.discogs_client import _RejectRedirectHandler

    request = Request(
        "https://api.discogs.com/oauth/identity",
        headers={"Authorization": "Discogs token=secret-token"},
    )
    redirected = _RejectRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {"Location": "https://attacker.example/collect"},
        "https://attacker.example/collect",
    )

    assert redirected is None


def test_write_actions_are_guarded() -> None:
    blocked = _invoke(
        {
            "mode": "action",
            "action": {
                "action_id": "add_release_to_wantlist",
                "input": {"release_id": 249504, "confirm": True},
            },
        },
        expect_ok=False,
    )
    assert blocked["error"] == "write_actions_disabled"

    missing_confirm = _invoke(
        {
            "mode": "action",
            "action": {
                "action_id": "delete_collection_instance",
                "target": {
                    "connection": {
                        "config": {
                            "enable_write_actions": True,
                            "mock_mode": True,
                            "username": "demo",
                        },
                        "secrets": {"user_token": "secret-token"},
                    }
                },
                "input": {"release_id": 249504, "instance_id": 10},
            },
        },
        expect_ok=False,
    )
    assert missing_confirm["error"] == "confirmation_required"

    allowed = _invoke(
        {
            "mode": "action",
            "action": {
                "action_id": "add_release_to_wantlist",
                "target": {
                    "connection": {
                        "config": {
                            "enable_write_actions": True,
                            "mock_mode": True,
                            "username": "demo",
                        },
                        "secrets": {"user_token": "secret-token"},
                    }
                },
                "input": {"release_id": 249504, "confirm": True},
            },
        }
    )
    assert allowed["result"]["added"] is True


def test_router_rejects_unknown_ids() -> None:
    unknown_query = _invoke(
        {"mode": "query", "query": {"query_id": "missing"}},
        expect_ok=False,
    )
    assert unknown_query["error"] == "invalid_payload"

    unknown_action = _invoke(
        {"mode": "action", "action": {"action_id": "missing"}},
        expect_ok=False,
    )
    assert unknown_action["error"] == "invalid_payload"
