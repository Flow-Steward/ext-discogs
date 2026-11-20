# Discogs workflow actions

Create a project **Discogs token account** connection. Store a personal user
token from Discogs Settings > Developers in the connection secret, and set the
Discogs username for account, collection and wantlist actions. Keep the live API
origin `https://api.discogs.com` and allowed host `api.discogs.com`. Set mock mode
according to whether you want built-in example responses or live Discogs data.
Connection testing always contacts live Discogs, even in mock mode. Test the
connection before building the workflow.

Select this connection on account actions. Public database reads may work
anonymously; private account data and modifications require the saved token and
Discogs permissions. Enable **Write actions** only for workflows that modify
Discogs. Every modification also requires **Confirm this change** = true.

Action IDs below identify the existing builder actions. Example numeric IDs show
formats; select or bind real IDs returned by Discogs.

## Identify a pressing and enrich your catalog

1. Choose **Search the Discogs music database** (`discogs_search_database`).
   Set **Type** to `release`, **Artist** to `Daft Punk`, **Release title** to
   `Discovery` and optionally **Year** to `2001`. A catalog number or barcode can
   narrow the edition more accurately than the album title alone.
2. Inspect the returned matches and choose a specific release. Pass its release
   ID into **Get a record release** (`discogs_get_release`) to read metadata.
3. To compare editions, use **Get a master release** and **List editions of a
   master release**. Master IDs group editions; release IDs identify a pressing.
4. Use **Get release marketplace statistics** or **Get suggested sale prices by
   condition** for pricing research. These reads do not create a sale listing.

Lists return one page. Set **Page** to 1 and **Results per page** to 25 initially;
continue with later page numbers according to the returned pagination. Inspect
the provider response under `result.data`; metadata and pagination depend on
the chosen endpoint.

## Add a wanted record or manage an owned copy

To save a wanted pressing, choose **Add or update a wanted release**
(`discogs_add_wantlist_release`) and supply its release ID, your username if it
is not configured on the connection, optional notes, and confirmation. For
example, notes might be `First pressing wanted.`. This changes the live wantlist
when mock mode is off and writes are enabled.

For the record collection, first use **List record collection folders** to get
the destination folder ID. **Add a release to a collection folder** takes that
folder ID and the release ID. To edit or remove one owned copy, list the folder's
records and keep the **Instance ID** as well as the release ID. Multiple owned
copies of the same release have different instance IDs.

For a custom field, run **List custom collection fields** to obtain its field
ID. **Set a custom field on a collection copy** requires username, folder,
release, instance and field IDs, plus the value to save, for example `Shelf B3`.
These IDs are separate and cannot be substituted for each other.

## Manage a marketplace listing and order

**Estimate a marketplace sale fee** (`discogs_calculate_marketplace_fee`) takes
the proposed price and an optional **Currency**, for example `EUR`. The fee is
calculated in that currency (`/marketplace/fee/{price}/{currency}`); without a
currency Discogs calculates it in USD. Discogs accepts USD, GBP, EUR, CAD, AUD,
JPY, CHF, MXN, BRL, NZD, SEK and ZAR; any other code is refused before Discogs
is called. The connection's **Default currency** setting does not supply a
currency to this action.

**Create a marketplace sale listing** (`discogs_create_marketplace_listing`)
offers a real sale copy. After identifying the release, enter its exact Discogs
condition, for example `Very Good Plus (VG+)`, sleeve condition `Very Good (VG)`,
price `19.90`, and status `For Sale` where appropriate. The seller's currency,
provider permissions and listing requirements apply. Review all details before
confirming. Updates and deletion address the **Listing ID**, not the release ID.

**List marketplace orders** and **Get a marketplace order** read existing orders.
Use the returned order ID, for example the format `12345-6789`, for subsequent
order actions. **Send a marketplace order message** posts real text to that
order's thread, for example `Your order has been packed and will ship tomorrow.`
Order status changes must be permitted by Discogs for the current order state.

## Read a seller inventory

**List a seller’s inventory** (`discogs_list_inventory`) reads one page of
listings with its `pagination` (`page`, `pages`, `per_page`, `items`). Filter by
**Status** (for example `For Sale`) and sort by `listed`, `price`, `item`,
`artist`, `label`, `catno`, `audio`, `status` or `location` in `asc` or `desc`
order. Without the owner’s token Discogs shows only listings that are For Sale.

**Read a seller’s whole inventory** (`discogs_list_all_inventory`) reads every
page, up to 100 listings per page, and checks each page against its pagination:
the page and page size must be the ones requested, the page must hold exactly
the number of listings the total promises, and no listing may repeat. The
result carries `listings`, `item_count`, `total_items`, `pages_read`,
`next_page`, `complete`, `stop_reason` and `warnings`:

- `complete: true` means the last page was read and `next_page` is empty.
- When the time budget (default 15 seconds), the result size or **Maximum
  listings** is reached, `complete` is false and `next_page` names the first
  page not yet read. Run the step again with **Start page** set to `next_page`
  and the same **Listings per page** to continue exactly where it stopped.
- If the inventory total changes while the pages are read, offsets have
  shifted: the result is incomplete, `next_page` is empty and `warnings`
  contains `inventory_changed_during_read`. Start again from page 1.

## Inventory exports and submissions

**Request an inventory export** (`discogs_request_inventory_export`) asks
Discogs to prepare a CSV export. Discogs only accepts the job, so the result
reports `processing: accepted`, `applied: false`, `check:
discogs_get_inventory_export` and the `export_id` from the Location header
Discogs returns. Pass that ID to **Get an inventory export status** until its
status is `success`, then to **Read an inventory export download**. List
earlier exports with **List seller inventory exports**. The download action
returns the provider response and does not create a workflow file artifact.

The inventory add/change/delete actions upload a CSV of listings as the file
Discogs documents (multipart field `upload`, `inventory.csv`, `text/csv`). Give
exactly one of `items` (objects turned into the CSV), `csv` (CSV text) or `file`
(a workflow file with the CSV). Columns: add takes `release_id`, `price`,
`media_condition` and optionally `sleeve_condition`, `comments`, `accept_offer`,
`location`, `external_id`, `weight`, `format_quantity`; change takes `release_id`
and at least one of the optional add columns or `price`/`media_condition`;
delete takes `listing_id`. An unknown column is refused before anything is sent;
prices are written as exact decimals. Discogs records
each submission as an upload: the result reports `processing: accepted`,
`check: discogs_get_inventory_upload` and the `upload_id`. **Get an inventory
upload status** returns the upload’s `status` and `results` text, and **List
recent inventory uploads** lists earlier uploads.

## Profiles, lists, collection value and ratings

**Edit a Discogs user profile** (`discogs_edit_user_profile`) changes the
supplied real name, website, location, biography or marketplace currency of the
account the token belongs to. **Get a saved list’s items**
(`discogs_get_list`) reads one list by the ID returned by **List a user’s saved
lists**. **Get collection value** (`discogs_get_collection_value`) returns the
minimum, median and maximum value of the collection; it needs the owner’s
token. **Get a release’s community rating**
(`discogs_get_community_release_rating`) returns the community average and the
number of ratings, separate from the account’s own rating.

**Find a release in a collection** (`discogs_get_collection_items_by_release`)
lists every owned copy of a release across folders with folder and instance
IDs. **Rate or move a collection copy** (`discogs_edit_collection_instance`)
takes those IDs: **Current folder ID** addresses the copy, **Move to folder ID**
moves it, and **Rating** sets its rating. **Edit a wanted release**
(`discogs_edit_wantlist_release`) changes the notes or rating of a release
already in the wantlist.

## Rate limit

Every action returns `result.rate_limit` with `limit`, `used` and `remaining`
from Discogs’ `X-Discogs-Ratelimit`, `X-Discogs-Ratelimit-Used` and
`X-Discogs-Ratelimit-Remaining` headers, also when Discogs refuses a request
with 429 (`rate_limited`). Bind it in a workflow to pause before `remaining`
reaches 0.

For read-only reporting, user profile, submissions, contributions, saved-list
and collection/wantlist actions supply their own data without modifying it.
Review the selected action's field help and the connected account before writes;
confirmation is required even when writes are enabled on the connection.

## Action reference

Every Discogs action, as the workflow editor shows it: its name, its action ID and what it does. Actions that change data on Discogs need enabled write actions and `confirm: true`. Every action also returns `result.rate_limit`.

### Account

- **Get the connected Discogs account** (`discogs_identity`): Read the username and account details associated with the saved Discogs token.

### Database

- **Search the Discogs music database** (`discogs_search_database`): Find releases, masters, artists or labels using text and music catalog filters. Returns one page of matches; use a release ID from the results to look up a particular pressing.
- **Get a record release** (`discogs_get_release`): Read one specific release or pressing by its Discogs release ID, including the metadata returned by Discogs.
- **Get an account’s release rating** (`discogs_get_release_rating`): Read the selected account’s personal rating for a specific release; this is separate from community statistics.
- **Set an account’s release rating** (`discogs_update_release_rating`): Save the selected account’s personal rating for a release. Requires a token, enabled write actions and confirmation.
- **Remove an account’s release rating** (`discogs_delete_release_rating`): Remove the selected account’s personal rating for a release. Requires a token, enabled write actions and confirmation.
- **Get release collection and wantlist statistics** (`discogs_get_release_stats`): Read community collection and wantlist statistics for a release to support music catalog research.
- **Get a master release** (`discogs_get_master`): Read the master record that groups editions of an album or single. A master ID is different from a particular release ID.
- **List editions of a master release** (`discogs_get_master_versions`): Read one page of releases grouped under a master. Narrow by format, label, country or release date to identify a pressing.
- **Get an artist** (`discogs_get_artist`): Read a Discogs artist profile using an artist ID from search results.
- **List an artist’s releases** (`discogs_get_artist_releases`): Read one page of releases associated with a Discogs artist for discography research.
- **Get a record label** (`discogs_get_label`): Read a Discogs record label profile using its label ID.
- **List a label’s releases** (`discogs_get_label_releases`): Read one page of releases associated with a Discogs record label.
- **Get a release’s community rating** (`discogs_get_community_release_rating`): Read the average rating and the number of ratings the Discogs community has given a release.

### Marketplace

- **Get a marketplace sale listing** (`discogs_get_marketplace_listing`): Read one seller listing by listing ID, including the price and condition returned by Discogs. A listing ID is different from a release ID.
- **Create a marketplace sale listing** (`discogs_create_marketplace_listing`): Offer a specific release for sale using its condition, price and listing details. Creates a real seller listing and requires enabled writes and confirmation.
- **Update a marketplace sale listing** (`discogs_update_marketplace_listing`): Change the price, condition or other supplied details of an existing seller listing. Requires enabled writes and confirmation.
- **Delete a marketplace sale listing** (`discogs_delete_marketplace_listing`): Remove an existing seller listing by listing ID. Requires enabled writes and confirmation.
- **Get release marketplace statistics** (`discogs_get_marketplace_stats`): Read marketplace availability and pricing statistics for a release to support pricing research.
- **Get suggested sale prices by condition** (`discogs_get_price_suggestions`): Read Discogs price suggestions for a release by condition. These are suggestions, not a change to your listings.
- **Estimate a marketplace sale fee** (`discogs_calculate_marketplace_fee`): Calculate the Discogs marketplace fee for a proposed price without creating a listing or order. With a currency the fee is calculated in that currency; without one Discogs uses USD.

### Orders

- **List marketplace orders** (`discogs_list_orders`): Read one page of the connected account’s marketplace orders, optionally filtered by status, creation date and archive state.
- **Get a marketplace order** (`discogs_get_order`): Read an existing marketplace order by its Discogs order ID for fulfillment or reporting.
- **Update a marketplace order** (`discogs_update_order`): Change the supplied status, shipping amount or archive state of an existing order. Requires enabled writes and confirmation; Discogs controls allowed status transitions.
- **Read marketplace order messages** (`discogs_list_order_messages`): Read the message history for an existing Discogs marketplace order.
- **Send a marketplace order message** (`discogs_add_order_message`): Post a message on an existing order, optionally with a status value. Sends a real order message and requires enabled writes and confirmation.

### Users

- **Get a Discogs user profile** (`discogs_get_user_profile`): Read the profile of the named Discogs account.
- **List a user’s database submissions** (`discogs_get_user_submissions`): Read one page of music database submissions associated with the named Discogs account.
- **List a user’s database contributions** (`discogs_get_user_contributions`): Read one page of music database contributions associated with the named Discogs account.
- **List a user’s saved lists** (`discogs_get_user_lists`): Read one page of lists belonging to the named Discogs account.
- **Edit a Discogs user profile** (`discogs_edit_user_profile`): Change the supplied profile fields of the connected Discogs account: real name, website, location, biography or marketplace currency. Requires authentication as that user, enabled writes and confirmation.
- **Get a saved list’s items** (`discogs_get_list`): Read the items of one Discogs list by its list ID. Private lists are visible only to their owner’s token.

### Collection

- **List record collection folders** (`discogs_get_collection_folders`): Read the named account’s collection folders and their IDs before selecting a folder in another collection action.
- **Create a record collection folder** (`discogs_create_collection_folder`): Create a named folder in the account’s record collection. Requires enabled writes and confirmation.
- **Get a record collection folder** (`discogs_get_collection_folder`): Read details of one collection folder using its folder ID.
- **Rename a record collection folder** (`discogs_update_collection_folder`): Change the name of an existing collection folder. Requires enabled writes and confirmation.
- **Delete a record collection folder** (`discogs_delete_collection_folder`): Request deletion of an existing collection folder. Requires enabled writes and confirmation; Discogs decides whether the folder can be deleted.
- **List records in a collection folder** (`discogs_get_collection_releases`): Read one page of release instances in a collection folder. Keep each instance ID when later editing or removing an individual copy.
- **Get collection copies of a release** (`discogs_get_collection_release`): Read the account’s collection instances for one release in a folder. Each instance identifies one owned copy.
- **Add a release to a collection folder** (`discogs_add_collection_release`): Add a copy of a specific release to the account’s collection folder, with optional notes and rating. Requires enabled writes and confirmation.
- **Remove one copy from a collection** (`discogs_delete_collection_instance`): Remove a particular owned copy using its release, folder and instance IDs. Requires enabled writes and confirmation.
- **List custom collection fields** (`discogs_get_collection_fields`): Read the account’s custom collection field definitions and IDs before updating a field on an owned copy.
- **Set a custom field on a collection copy** (`discogs_edit_collection_field_value`): Save a value for one custom collection field on a specific owned copy. Requires folder, release, instance and field IDs, enabled writes and confirmation.
- **Find a release in a collection** (`discogs_get_collection_items_by_release`): Read every owned copy of one release in the account’s collection, across all folders, with folder and instance IDs. A private collection requires the owner’s token.
- **Rate or move a collection copy** (`discogs_edit_collection_instance`): Change the rating of one owned copy and/or move it to another folder, using its current folder, release and instance IDs. Requires enabled writes and confirmation.
- **Get collection value** (`discogs_get_collection_value`): Read the minimum, median and maximum value of the account’s collection. Requires the collection owner’s token.

### Wantlist

- **List wanted releases** (`discogs_get_wantlist`): Read one page of the account’s wantlist to compare wanted records with a catalog or collection.
- **Get one wanted release** (`discogs_get_wantlist_release`): Read the account’s wantlist entry for a particular release.
- **Add or update a wanted release** (`discogs_add_wantlist_release`): Add a release to the account’s wantlist, or update its supplied notes and rating. Requires enabled writes and confirmation.
- **Remove a wanted release** (`discogs_delete_wantlist_release`): Remove a specific release from the account’s wantlist. Requires enabled writes and confirmation.
- **Edit a wanted release** (`discogs_edit_wantlist_release`): Change the notes or rating of a release already in the account’s wantlist. Requires enabled writes and confirmation.

### Inventory

- **List seller inventory exports** (`discogs_get_inventory_exports`): Read the inventory export jobs available to the connected seller account.
- **Get an inventory export status** (`discogs_get_inventory_export`): Read metadata and status for an existing seller inventory export using its export ID.
- **Read an inventory export download** (`discogs_download_inventory_export`): Request the download response for an existing seller inventory export. Returns the provider response through this action’s result; it does not create a workflow file artifact.
- **Submit inventory additions** (`discogs_inventory_upload_add`): Upload a CSV of listings to Discogs’ inventory add endpoint as the file Discogs documents (multipart field upload, inventory.csv). Give exactly one of items (objects turned into the CSV), csv (CSV text) or file (a workflow file with the CSV); columns: release_id, price and media_condition; optional sleeve_condition, comments, accept_offer, location, external_id, weight, format_quantity. An unknown column is refused before anything is sent. Discogs records the submission as an upload: the result reports processing accepted and the upload ID; check the outcome with Get an inventory upload status. Requires enabled writes and confirmation.
- **Submit inventory changes** (`discogs_inventory_upload_change`): Upload a CSV of listings to Discogs’ inventory change endpoint as the file Discogs documents (multipart field upload, inventory.csv). Give exactly one of items (objects turned into the CSV), csv (CSV text) or file (a workflow file with the CSV); columns: release_id and at least one of price, media_condition, sleeve_condition, comments, accept_offer, external_id, location, weight, format_quantity. An unknown column is refused before anything is sent. Discogs records the submission as an upload: the result reports processing accepted and the upload ID; check the outcome with Get an inventory upload status. Requires enabled writes and confirmation.
- **Submit inventory removals** (`discogs_inventory_upload_delete`): Upload a CSV of listings to Discogs’ inventory delete endpoint as the file Discogs documents (multipart field upload, inventory.csv). Give exactly one of items (objects turned into the CSV), csv (CSV text) or file (a workflow file with the CSV); columns: listing_id. An unknown column is refused before anything is sent. Discogs records the submission as an upload: the result reports processing accepted and the upload ID; check the outcome with Get an inventory upload status. Requires enabled writes and confirmation.
- **List a seller’s inventory** (`discogs_list_inventory`): Read one page of a seller’s marketplace listings with its pagination. Without the owner’s token only listings that are For Sale are visible.
- **Read a seller’s whole inventory** (`discogs_list_all_inventory`): Read the seller’s listings page by page, up to 100 per page, checking every page against its pagination so no listing is skipped or repeated. Stops at the time or result-size limit with next_page to continue from, and returns complete true only when the last page was read. If the inventory total changes during the read, the result is incomplete with a warning.
- **Request an inventory export** (`discogs_request_inventory_export`): Ask Discogs to prepare a CSV export of the seller’s inventory. Discogs only accepts the job: the result reports processing accepted, applied false and the export ID; check it with Get an inventory export status. Requires enabled writes and confirmation.
- **List recent inventory uploads** (`discogs_list_inventory_uploads`): Read one page of the seller’s recent inventory uploads with their status and processing results.
- **Get an inventory upload status** (`discogs_get_inventory_upload`): Read the status and processing results of one inventory upload using its upload ID.
