# Discogs API Extension

See [Workflow actions and examples](docs/workflow-actions.md) for connection setup, action inputs and end-to-end examples.

For the upstream API reference, see [Discogs developer documentation](https://www.discogs.com/developers/).

Research record releases, enrich a music catalog and manage Discogs account tasks from Flow Steward workflows. Search releases, masters, artists and labels using filters such as artist, release title, year, barcode or catalog number. Look up individual records, explore master versions and artist or label releases, and return result objects with pagination for subsequent workflow steps.

Marketplace operations cover listings, release sales statistics, price suggestions, fee calculations, orders and order messages. Collection and wantlist operations let workflows inspect folders, release instances and custom collection fields, then add, update or remove supported items. The release also exposes user profiles and profile edits, contributions, submissions, lists and their items, personal and community release ratings, collection value, seller inventory reads, and inventory export or upload operations with their status.

Use these functions to enrich a record catalog, research a pressing, compare collection holdings against a wantlist, or connect record-selling tasks to other systems. Write operations require a token, explicit enablement and confirmation. Discogs permissions and rate limits still apply. This is a Flow Steward-maintained integration with Discogs; the returned marketplace information does not itself place a purchase.

The extension runs as an isolated subprocess. It reads one JSON request from
stdin and writes one JSON response to stdout. Mock mode returns built-in example responses when enabled. Live connections
default to mock mode off; tests configure their own mock responses.

## Requirements

This release speaks the host contract `extension_host_v2` with its final
execution scope (`group_id`, `for_each_id`, `step_id`, `step_execution_id`)
and is built on `flowsteward-extension-sdk` 0.4.0. A request with another
contract, a missing scope key, or both a Group and a For each as its owner is
refused before Discogs is called. Its bundled workflows use the final workflow
model (steps and one execution graph, no phases). Install it on a Flow Steward
Core that speaks this contract; an older Core does not run it.

## Logo

Logo: `icon.png` at the bundle root (the original Discogs vinyl-record mark; PNG, 128x128).

## Capabilities

- Search Discogs database resources.
- Lookup release, master, artist, and label details.
- Fetch marketplace statistics for releases.
- Check authenticated collection and wantlist state.
- Add/remove wantlist entries and collection instances when write actions are
  explicitly enabled.
- Read a seller inventory one page at a time or completely, with an exact
  continuation page and a check of every page against its pagination.
- Request inventory exports and follow exports and inventory uploads by ID.
- Read community release ratings, collection value, the copies of a release in
  a collection and the items of a saved list; rate or move a collection copy,
  edit a wanted release and edit the account profile.
- Return the Discogs rate-limit window (`result.rate_limit`) from every action.

## API coverage

Every method and address in the Discogs developer documentation is a workflow
action, except the two OAuth 1.0a login addresses (`GET /oauth/request_token`,
`POST /oauth/access_token`): the extension authenticates with a personal user
token. `tests/test_api_reference_coverage.py` checks this against
`tests/reference/discogs_api_endpoints.json`, the facts extracted from a saved
copy of the documentation by `scripts/extract_api_reference.py` (SHA-256 of the
copy recorded in the file).

`tests/test_live_discogs.py` reads Discogs live, with GET requests only, when
`DISCOGS_TOKEN_FILE` names a file holding a user token; otherwise it is
skipped.

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

Logo sources and attribution: [BRANDING.md](BRANDING.md).
