# Discogs API Extension

Local Flow Steward extension for Discogs database, marketplace, collection, and
wantlist operations.

The extension runs as an isolated subprocess. It reads one JSON request from
stdin and writes one JSON response to stdout. Mock mode is enabled by default so
local validation and tests do not call the Discogs API.

## Requirements

This release speaks the host contract `extension_host_v2` with its final
execution scope (`group_id`, `for_each_id`, `step_id`, `step_execution_id`)
and is built on `flowsteward-extension-sdk` 0.4.0. A request with another
contract, a missing scope key, or both a Group and a For each as its owner is
refused before Discogs is called. Its bundled workflows use the final workflow
model (steps and one execution graph, no phases). Install it on a Flow Steward
Core that speaks this contract; an older Core does not run it.

## Logo

Logo: `icon.png` at the bundle root (the Flow Steward wave mark, PNG, 128x128).

## Capabilities

- Search Discogs database resources.
- Lookup release, master, artist, and label details.
- Fetch marketplace statistics for releases.
- Check authenticated collection and wantlist state.
- Add/remove wantlist entries and collection instances when write actions are
  explicitly enabled.

## Authentication

For self-hosted deployments, set one of these environment variables on the
extension runtime container:

```bash
DISCOGS_USER_TOKEN=...
```

Fallback names are also supported: `DISCOGS_API_TOKEN`, `DISCOGS_TOKEN`.

Project connection secrets still work and take precedence over environment
variables when a project needs its own Discogs account.

## Validation

```bash
.venv/bin/python -m core.entrypoints.cli tooling extensions validate com.discogs.api --root extensions --health --marketplace
.venv/bin/python extensions/com_discogs_api/scripts/smoke_check.py
.venv/bin/python -m pytest extensions/com_discogs_api/tests/test_discogs_api.py -q
```

## Safety

Live requests require HTTPS, an allowlisted host, a configured User-Agent, body
size caps, and short timeouts. Secret tokens are sent only in headers and are
never echoed in responses.
