# VEBA Marketplace — API Reference

**Backend module:** `endpoints/marketplace.py`
**Migrations:** `database/migrations/014_marketplace_listings.sql`, `015_booking_requests.sql`
**Generated:** May 2026

This document is the apidog import reference for the twelve endpoints
that back the VEBA Marketplace feature. Every endpoint follows the
project's standard conventions:

- **Response envelope:** every response is wrapped in `{ status, message, data }`. On success `status="success"`; on error `status="error"` and `message` is a human-readable string.
- **Request body wrapper:** mutating endpoints expect `{ "data": { ... } }`.
- **Authentication:** Bearer JWT via `Authorization: Bearer <token>` header, or legacy `Auth-Key: <token>`.
- **Permission gates:** decorator-enforced via the catalog permissions seeded by migration 013. The caller's role must include the listed permission (or one of `super_admin`/`system` for bypass).
- **Tenancy:** every endpoint takes `account_root` from either the body or a query param. Server-side, the listing-side `owner_root` is **always derived from the listing** (never trusted from the request body) for the booking endpoints.

---

## Endpoint inventory

| # | Method | Path | Permission |
|---|--------|------|------------|
| 1 | POST | `/veba/listings/create` | `can_list_asset_on_marketplace` |
| 2 | GET | `/veba/listings` | `can_browse_asset_listings` |
| 3 | GET | `/veba/listings/<listing_uid>` | `can_browse_asset_listings` |
| 4 | GET | `/veba/listings/asset/<asset_uid>` | `can_view_unit_digital_twin` |
| 5 | PUT | `/veba/listings/<listing_uid>/update` | `can_edit_asset_listing` |
| 6 | PUT | `/veba/listings/<listing_uid>/pause` | `can_edit_asset_listing` |
| 7 | PUT | `/veba/listings/<listing_uid>/reactivate` | `can_edit_asset_listing` |
| 8 | PUT | `/veba/listings/<listing_uid>/archive` | `can_edit_asset_listing` |
| 9 | POST | `/veba/booking-requests/create` | `can_book_asset` |
| 10 | GET | `/veba/booking-requests` | `can_view_booking` |
| 11 | PUT | `/veba/booking-requests/<request_uid>/approve` | `can_approve_booking_request` |
| 12 | PUT | `/veba/booking-requests/<request_uid>/reject` | `can_reject_booking_request` |

---

## Shared schemas

### `VebaListing`

| Field | Type | Notes |
|-------|------|-------|
| `listing_uid` | string | PK, `lst_<uuid4>` |
| `asset_uid` | string | Reference to asset in registry (not FK-enforced) |
| `account_root` | string | Owning tenant |
| `created_by` | string | Account UID of creator |
| `created_at` | ISO timestamp | |
| `updated_at` | ISO timestamp | |
| `daily_rate` | number | Always > 0 |
| `currency` | string | ISO-4217 (e.g. `"UGX"`), max 8 chars |
| `pricing_basis` | enum | `per_day` \| `per_hour` \| `per_km` \| `per_trip` |
| `hourly_rate` | number\|null | Optional secondary basis, > 0 if present |
| `availability_start` | ISO date\|null | YYYY-MM-DD |
| `availability_end` | ISO date\|null | YYYY-MM-DD; if both set, must be >= start |
| `geographic_scope` | string\|null | Free text (e.g. `"Kampala"`, `"EAC"`) |
| `operator_included` | boolean | Default `false` |
| `notes` | string\|null | Free text |
| `visibility` | enum | `public` \| `tenant` |
| `status` | enum | `active` \| `paused` \| `archived` \| `draft` |
| `asset_summary` | object\|null | `{ display_name, asset_class, owner_org, country, photo_url }` |

### `BookingRequest`

| Field | Type | Notes |
|-------|------|-------|
| `request_uid` | string | PK, `req_<uuid4>` |
| `listing_uid` | string | FK to `dll_marketplace_listings.listing_uid` |
| `asset_uid` | string | Mirrored from listing |
| `requester_uid` | string | Account UID of requester |
| `requester_root` | string | Tenant of requester |
| `owner_root` | string | Tenant of listing owner — derived server-side |
| `start_date` | ISO date | YYYY-MM-DD |
| `end_date` | ISO date | YYYY-MM-DD; must be >= start_date |
| `notes` | string\|null | Free text |
| `status` | enum | `pending` (default) \| `approved` \| `rejected` \| `cancelled` \| `fulfilled` |
| `rate_snapshot` | object | `{ daily_rate, currency, pricing_basis }` — frozen at submission |
| `created_at` | ISO timestamp | |
| `updated_at` | ISO timestamp | |

---

# 1. Create Listing

**`POST /veba/listings/create`**

Creates a new VEBA marketplace listing for an asset. Side-effect: flips the asset's `veba_status` to `'available'` in `dll_veba_enabled_units` if the asset has an IMEI-keyed device record.

**Permission:** `can_list_asset_on_marketplace`

### Request body

```json
{
  "data": {
    "asset_uid":          "KLA-DOZER-D6-019",
    "account_root":       "TEPU-3D-OPS",
    "created_by":         "user-account-uid-001",
    "daily_rate":         250000,
    "currency":           "UGX",
    "pricing_basis":      "per_day",
    "hourly_rate":        35000,
    "availability_start": "2026-06-01",
    "availability_end":   "2026-12-31",
    "geographic_scope":   "Uganda",
    "operator_included":  true,
    "notes":              "Good condition, recent service.",
    "visibility":         "public",
    "asset_summary": {
      "display_name": "KLA-DOZER-D6-019",
      "asset_class":  "VEH",
      "owner_org":    "3D Services • TEPU",
      "country":      "UG",
      "photo_url":    null
    }
  }
}
```

**Required:** `asset_uid`, `account_root`, `created_by`, `daily_rate`, `currency`, `pricing_basis`, `visibility`.
**Optional:** all other fields shown above.

### Responses

**201 Created**
```json
{
  "status":  "success",
  "message": "Listing created",
  "data":    { "listing_uid": "lst_3f1c9d2a-..." }
}
```

**400 Bad Request** — missing or invalid input
```json
{ "status": "error", "message": "Required field missing: daily_rate", "data": "" }
{ "status": "error", "message": "daily_rate must be a positive number", "data": "" }
{ "status": "error", "message": "pricing_basis must be one of: per_day, per_hour, per_km, per_trip", "data": "" }
{ "status": "error", "message": "visibility must be 'public' or 'tenant'", "data": "" }
{ "status": "error", "message": "availability_end must not be before availability_start", "data": "" }
```

**401 Unauthorized** — missing/invalid token
**403 Forbidden** — role lacks `can_list_asset_on_marketplace`
**500 Internal Server Error**
```json
{ "status": "error", "message": "Could not create listing", "data": "" }
```

---

# 2. List Listings (browse / owner)

**`GET /veba/listings?account_root=…&scope=…&status=…`**

Lists marketplace listings scoped by visibility.

**Permission:** `can_browse_asset_listings`

### Query parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `account_root` | string | Required for non-marketplace scopes | Caller's tenant |
| `scope` | enum | optional, default `marketplace` | `marketplace` \| `tenant` \| `owner` |
| `status` | enum | optional | Only meaningful for `scope=owner`; ignored otherwise |

- `marketplace` — only public listings in `active` status (the public browse).
- `tenant` — public listings + the caller's tenant-private listings, all in `active` status.
- `owner` — only the caller's own listings, any status.

### Responses

**200 OK**
```json
{
  "status":  "success",
  "message": "3 listings",
  "data": [
    { /* VebaListing */ },
    { /* VebaListing */ },
    { /* VebaListing */ }
  ]
}
```

**400 Bad Request**
```json
{ "status": "error", "message": "scope must be 'marketplace', 'tenant', or 'owner'", "data": "" }
{ "status": "error", "message": "account_root is required for non-marketplace scopes", "data": "" }
```

**500**
```json
{ "status": "error", "message": "Could not load listings", "data": "" }
```

---

# 3. Get Listing By UID

**`GET /veba/listings/<listing_uid>?account_root=…`**

Single-listing fetch. Visibility filter applied per-row — non-visible listings return 404.

**Permission:** `can_browse_asset_listings`

### Query parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `account_root` | string | optional | Required to see tenant-private listings owned by this account |

### Responses

**200 OK**
```json
{
  "status":  "success",
  "message": "Listing found",
  "data":    { /* VebaListing */ }
}
```

**404 Not Found** — listing doesn't exist OR isn't visible to caller
```json
{ "status": "error", "message": "Listing not found", "data": "" }
```

**500** — same generic message as above.

---

# 4. Get Listing By Asset

**`GET /veba/listings/asset/<asset_uid>`**

Returns the active or paused listing for the given asset, or `null` if there is none. Used by the asset detail blade to render "Currently listed" state.

**Permission:** `can_view_unit_digital_twin`

### Responses

**200 OK — asset has a listing**
```json
{
  "status":  "success",
  "message": "Listing found",
  "data":    { /* VebaListing */ }
}
```

**200 OK — asset has no active listing**
```json
{
  "status":  "success",
  "message": "No active listing for asset",
  "data":    null
}
```

**500** — generic.

---

# 5. Update Listing

**`PUT /veba/listings/<listing_uid>/update`**

Partial update of editable commercial terms. **Status cannot be changed here** — use the pause / reactivate / archive endpoints. Pending booking requests keep their snapshotted rate; new requests pick up the updated rate.

**Permission:** `can_edit_asset_listing`

### Request body

```json
{
  "data": {
    "account_root": "TEPU-3D-OPS",
    "updated_by":   "user-account-uid-001",

    "daily_rate":         275000,
    "currency":           "UGX",
    "pricing_basis":      "per_day",
    "hourly_rate":        null,
    "availability_start": "2026-07-01",
    "availability_end":   "2027-06-30",
    "geographic_scope":   "EAC",
    "operator_included":  true,
    "notes":              "Updated price for peak season.",
    "visibility":         "public"
  }
}
```

**Required:** `account_root` (used to verify ownership).
**All commercial fields are optional** — only the ones included in the payload get updated.

### Responses

**200 OK**
```json
{
  "status":  "success",
  "message": "Listing updated",
  "data":    { "listing_uid": "lst_..." }
}
```

**400 Bad Request** — same validation errors as create (`daily_rate` must be positive, `pricing_basis` valid, etc.) plus:
```json
{ "status": "error", "message": "account_root is required", "data": "" }
{ "status": "error", "message": "No editable fields provided", "data": "" }
```

**404 Not Found** — listing doesn't exist OR caller doesn't own it (same 404 surface for both).

**500** — generic.

---

# 6, 7, 8. Pause / Reactivate / Archive

Three endpoints sharing the same body shape and ownership check, differing only in target status:

| Endpoint | New status | Audit severity |
|----------|-----------|----------------|
| `PUT /veba/listings/<uid>/pause` | `paused` | Info |
| `PUT /veba/listings/<uid>/reactivate` | `active` | Info |
| `PUT /veba/listings/<uid>/archive` | `archived` | Alarm (destructive) |

**Permission (all three):** `can_edit_asset_listing`

**Side-effect:** mirrors to `dll_veba_enabled_units.veba_status` (`paused → suspended`, `active → available`, `archived → unavailable`) when the asset has a device record. No-op for non-device assets.

### Request body (same for all three)

```json
{
  "data": {
    "account_root": "TEPU-3D-OPS",
    "updated_by":   "user-account-uid-001"
  }
}
```

**Required:** `account_root` (owner verification).
**Optional:** `updated_by` (audit metadata).

### Responses

**200 OK**
```json
{
  "status":  "success",
  "message": "Listing paused",
  "data": {
    "listing_uid": "lst_...",
    "status":      "paused"
  }
}
```

**404 Not Found** — listing doesn't exist OR caller doesn't own it.
**500** — generic ("Could not update listing status").

---

# 9. Create Booking Request

**`POST /veba/booking-requests/create`**

Creates a booking request against a published listing. The rate the requester saw is **frozen into `rate_snapshot`** at submission time — owner rate edits never retroactively change pending requests.

**Permission:** `can_book_asset`

### Request body

```json
{
  "data": {
    "listing_uid":    "lst_3f1c9d2a-...",
    "requester_uid":  "user-account-uid-042",
    "requester_root": "VEBA-PARTNER-NRB",
    "start_date":     "2026-07-15",
    "end_date":       "2026-07-20",
    "notes":          "Pickup at the depot, will return cleaned."
  }
}
```

**Required:** `listing_uid`, `requester_uid`, `requester_root`, `start_date`, `end_date`.
**Optional:** `notes`.

**Server-derived (never trusted from the body):** `owner_root`, `asset_uid`, `rate_snapshot` — all sourced from the target listing.

### Responses

**201 Created**
```json
{
  "status":  "success",
  "message": "Booking request created",
  "data":    { "request_uid": "req_8a4e02b5-..." }
}
```

**400 Bad Request**
```json
{ "status": "error", "message": "Required field missing: start_date", "data": "" }
{ "status": "error", "message": "end_date must not be before start_date", "data": "" }
```

**404 Not Found** — listing doesn't exist:
```json
{ "status": "error", "message": "Listing not found", "data": "" }
```

**409 Conflict** — listing isn't `active`:
```json
{
  "status": "error",
  "message": "Listing is paused — only active listings can be booked",
  "data":    ""
}
```

**500** — generic ("Could not create booking request").

---

# 10. List Booking Requests

**`GET /veba/booking-requests?account_root=…&direction=…&status=…`**

Lists booking requests scoped by direction.

**Permission:** `can_view_booking`

### Query parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `account_root` | string | Required | Caller's tenant |
| `direction` | enum | optional, default `incoming` | `incoming` \| `outgoing` \| `both` |
| `status` | enum | optional | Any `BookingRequestStatus` value |

- `incoming` — requests TO the caller (`owner_root` match): the review queue.
- `outgoing` — requests FROM the caller (`requester_root` match): "what I've asked for".
- `both` — union.

### Responses

**200 OK**
```json
{
  "status":  "success",
  "message": "5 booking requests",
  "data": [
    { /* BookingRequest */ },
    /* ... */
  ]
}
```

**400 Bad Request**
```json
{ "status": "error", "message": "account_root is required", "data": "" }
{ "status": "error", "message": "direction must be 'incoming', 'outgoing', or 'both'", "data": "" }
```

**500** — generic ("Could not load booking requests").

---

# 11, 12. Approve / Reject Booking Request

Two endpoints sharing the same body, differing only in target status:

| Endpoint | New status | Permission |
|----------|-----------|------------|
| `PUT /veba/booking-requests/<request_uid>/approve` | `approved` | `can_approve_booking_request` |
| `PUT /veba/booking-requests/<request_uid>/reject` | `rejected` | `can_reject_booking_request` |

Both require the caller's `account_root` to match the request's `owner_root`. Both refuse non-`pending` transitions.

### Request body (same for both)

```json
{
  "data": {
    "account_root": "TEPU-3D-OPS",
    "updated_by":   "user-account-uid-001",
    "notes":        "Approved for the requested window."
  }
}
```

**Required:** `account_root`.
**Optional:** `updated_by`, `notes`.

### Responses

**200 OK**
```json
{
  "status":  "success",
  "message": "Booking request approved",
  "data": {
    "request_uid": "req_8a4e02b5-...",
    "status":      "approved"
  }
}
```

**404 Not Found** — request doesn't exist OR caller isn't the listing owner (same surface for both).

**409 Conflict** — request isn't `pending`:
```json
{
  "status": "error",
  "message": "Request is approved — only pending requests can change state",
  "data":    ""
}
```

**500** — generic ("Could not update booking request").

---

## Permissions required (catalog cheat-sheet)

| Permission | Source |
|------------|--------|
| `can_list_asset_on_marketplace` | Migration 013 (catalog) |
| `can_browse_asset_listings` | Migration 013 |
| `can_view_unit_digital_twin` | Migration 013 |
| `can_edit_asset_listing` | Migration 013 |
| `can_book_asset` | Migration 013 |
| `can_view_booking` | Migration 013 |
| `can_approve_booking_request` | Migration 013 |
| `can_reject_booking_request` | Migration 013 |

All eight ship in the global permission catalog under `account_root='engine'`. Any role with one of these permissions assigned can hit the corresponding endpoint. `super_admin` and `system` roles bypass all checks.

---

## Common error envelope (reference)

Every non-success response uses:

```json
{
  "status":  "error",
  "message": "<human readable>",
  "data":    "" | <optional structured details>
}
```

Status codes used by these endpoints: **200**, **201**, **400**, **401**, **403**, **404**, **409**, **500**.

