from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

BUNDLE_ROOT = Path(__file__).resolve().parents[1]
if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))

# The final extension_host_v2 execution scope: all four keys, at most one owner.
ROOT_STEP_SCOPE = {
    "group_id": None,
    "for_each_id": None,
    "step_id": "search_vinyl_releases",
    "step_execution_id": "7c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d0001",
}
GROUP_STEP_SCOPE = {**ROOT_STEP_SCOPE, "group_id": "lookup_releases"}
FOR_EACH_STEP_SCOPE = {
    **ROOT_STEP_SCOPE,
    "for_each_id": "each_artist",
    "step_execution_id": "7c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d0002",
}


def _envelope(body: dict, scope: dict | None = None) -> dict:
    """A host request: the extension_host_v2 contract and its execution scope."""
    return {
        "contract_version": "extension_host_v2",
        "runtime_context": dict(ROOT_STEP_SCOPE if scope is None else scope),
        **body,
    }


def _invoke(payload: dict, *, expect_ok: bool = True) -> dict:
    proc = subprocess.run(
        [sys.executable, str(BUNDLE_ROOT / "main.py")],
        cwd=str(BUNDLE_ROOT),
        input=json.dumps(_envelope(payload)),
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
        # The final workflow model: steps and one execution graph, no phases.
        assert "phases" not in workflow
        assert workflow["settings"]["execution_graph"]["schema_version"] == 1
        for step in workflow["steps"]:
            assert "phase_id" not in step
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
    result = handle_request(_envelope(payload))
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

    captured: dict[str, Any] = {}

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


class _RecordingResponse:
    status = 200
    headers: ClassVar[dict[str, str]] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, _size: int = -1) -> bytes:
        return json.dumps(
            {
                "pagination": {"page": 1, "pages": 1, "items": 1},
                "results": [{"id": 249504, "title": "Daft Punk - Discovery"}],
            }
        ).encode("utf-8")


def _search_operation() -> dict[str, Any]:
    return {
        "mode": "action",
        "action": {
            "action_id": "discogs_search_database",
            "target": {
                "connection": {
                    "config": {"mock_mode": False},
                    "secrets": {"user_token": "secret-token"},
                }
            },
            "input": {"query": "Discovery", "type": "release", "page": 1, "per_page": 5},
        },
    }


@pytest.mark.parametrize("scope", [ROOT_STEP_SCOPE, GROUP_STEP_SCOPE, FOR_EACH_STEP_SCOPE])
def test_every_final_scope_owner_runs_the_workflow_search(monkeypatch, scope: dict) -> None:
    from handlers import discogs_client
    from handlers.router import handle_request

    requests: list[str] = []

    def _fake_urlopen(request, timeout: int):
        requests.append(request.full_url)
        return _RecordingResponse()

    monkeypatch.setattr(discogs_client, "urlopen", _fake_urlopen)

    response = handle_request(_envelope(_search_operation(), scope))

    assert response["ok"] is True, response
    assert response["result"]["data"]["result_count"] == 1
    assert len(requests) == 1
    assert requests[0].startswith("https://api.discogs.com/database/search?")


@pytest.mark.parametrize(
    ("contract_version", "scope", "reason"),
    [
        ("extension_host_v1", FOR_EACH_STEP_SCOPE, "Unsupported host contract"),
        ("", FOR_EACH_STEP_SCOPE, "Unsupported host contract"),
        (
            "extension_host_v2",
            {k: v for k, v in FOR_EACH_STEP_SCOPE.items() if k != "for_each_id"},
            "misses execution scope",
        ),
        (
            "extension_host_v2",
            {**FOR_EACH_STEP_SCOPE, "group_id": "lookup_releases"},
            "both a Group and a For each",
        ),
        (
            "extension_host_v2",
            {**ROOT_STEP_SCOPE, "step_execution_id": None},
            "without its logical execution",
        ),
    ],
)
def test_foreign_or_incomplete_envelope_is_refused_before_any_request(
    monkeypatch, contract_version: str, scope: dict, reason: str
) -> None:
    from handlers import discogs_client
    from handlers.router import handle_request

    def _no_request(*_args: Any, **_kwargs: Any):
        raise AssertionError("Discogs must not be called for a refused envelope")

    monkeypatch.setattr(discogs_client, "urlopen", _no_request)
    payload = _envelope(_search_operation(), scope)
    payload["contract_version"] = contract_version

    response = handle_request(payload)

    assert response["ok"] is False
    assert response["error"] == "invalid_host_envelope"
    assert reason in response["errors"][0]["message"]
    assert response["definitely_no_external_effect"] is True


def test_main_refuses_a_request_without_the_host_envelope() -> None:
    proc = subprocess.run(
        [sys.executable, str(BUNDLE_ROOT / "main.py")],
        cwd=str(BUNDLE_ROOT),
        input=json.dumps({"mode": "query", "query": {"query_id": "provider_health"}}),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert proc.returncode != 0
    response = json.loads(proc.stdout)
    assert response["error"] == "invalid_host_envelope"
    assert response["definitely_no_external_effect"] is True


def test_bundle_carries_a_valid_logo() -> None:
    import struct

    raw = (BUNDLE_ROOT / "icon.png").read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert raw[12:16] == b"IHDR"
    width, height = struct.unpack(">II", raw[16:24])
    assert width == height
    assert 32 <= width <= 512
    assert len(raw) <= 100 * 1024
