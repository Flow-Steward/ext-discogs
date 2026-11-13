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
an explicit **Currency**, for example `EUR`, together with the proposed price.
The connection's **Default currency** setting is currently unused and does not
supply a currency to this action.

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

## Inventory exports and submissions

List seller inventory exports, inspect an export's status and pass its returned
export ID to **Read an inventory export download**. The action returns the
provider response and does not create a workflow file artifact.

The inventory add/change/delete actions submit the supplied `items` array or
`csv` text value to the corresponding fixed Discogs endpoint. Follow Discogs'
format for that endpoint and inspect the provider response. These actions do not
validate or reconcile every inventory row, upload an arbitrary local file, or
wait for all provider processing to finish.

For read-only reporting, user profile, submissions, contributions, saved-list
and collection/wantlist actions supply their own data without modifying it.
Review the selected action's field help and the connected account before writes;
confirmation is required even when writes are enabled on the connection.
