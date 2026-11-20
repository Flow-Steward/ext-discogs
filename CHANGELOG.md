# Changelog

## 0.2.7

### Added

- **Action reference** in `docs/workflow-actions.md`: every action with its name, ID and description, grouped as on the Capabilities page; a test keeps it, the Capabilities page and the workflow editor descriptions equal to the operation manifest.
- **List a seller’s inventory** (`discogs_list_inventory`) and **Read a seller’s whole inventory** (`discogs_list_all_inventory`): all pages up to 100 listings each, every page checked against its pagination, an exact `next_page` when the time, size or item limit stops the read, and `complete: false` with a warning when the inventory total changes during the read.
- **Request an inventory export** (`discogs_request_inventory_export`): returns `processing: accepted`, `applied: false`, the export ID from Discogs’ Location header and `check: discogs_get_inventory_export`.
- **List recent inventory uploads** (`discogs_list_inventory_uploads`) and **Get an inventory upload status** (`discogs_get_inventory_upload`).
- **Get a release’s community rating**, **Get collection value**, **Find a release in a collection**, **Rate or move a collection copy**, **Edit a wanted release**, **Edit a Discogs user profile** and **Get a saved list’s items**.
- `result.rate_limit` (`limit`, `used`, `remaining`) is a declared output of every action, also returned with a 429 refusal.
- The Discogs developer documentation is pinned as extracted facts (`tests/reference/discogs_api_endpoints.json`, `scripts/extract_api_reference.py`); a test checks that every documented method and address is an action or an explained exclusion.

### Fixed

- Inventory add, change and delete uploads now send the CSV file Discogs documents (multipart field `upload`), built from `items`, `csv` or a workflow `file`; columns are checked against the documentation before anything is sent. Before, these actions sent a JSON body, which the documentation does not describe for these endpoints.
- The rate limit is read from Discogs’ `X-Discogs-Ratelimit`, `X-Discogs-Ratelimit-Used` and `X-Discogs-Ratelimit-Remaining` headers; it was always empty before.
- **Estimate a marketplace sale fee** calls `/marketplace/fee/{price}/{currency}` when a currency is given, so the fee is calculated in that currency instead of always USD; the currency must be one Discogs documents.
- The inventory add, change and delete actions return the upload ID from Discogs’ Location header with `processing: accepted` and `check: discogs_get_inventory_upload`.

[Changes from 0.2.6](https://github.com/Flow-Steward/ext-discogs/compare/v0.2.6...v0.2.7)

## 0.2.6

- Identify Flow Steward as the extension publisher and direct extension support to this repository's issues. Discogs developer documentation remains linked from the README.

[Changes from 0.2.5](https://github.com/Flow-Steward/ext-discogs/compare/v0.2.5...v0.2.6)

## 0.2.5

### Added

- Added a Support tab with links for reporting a problem, asking a question or requesting a feature in this extension's GitHub repository, and what to include in a report.

## 0.2.4

- Clarify workflow field guidance and examples, with a setup and workflow action guide. Existing action IDs, input contracts and behavior are unchanged.
