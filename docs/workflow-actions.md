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

The inventory add/change/delete actions submit the supplied `items` array or
`csv` text value to the corresponding fixed Discogs endpoint. Discogs records
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
