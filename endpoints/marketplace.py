"""
endpoints/marketplace.py — VEBA Marketplace listings + lifecycle.

Routes mounted by this blueprint (gated by catalog permissions):

    POST /veba/listings/create                 can_list_asset_on_marketplace
    GET  /veba/listings                        can_browse_asset_listings
    GET  /veba/listings/<uid>                  can_browse_asset_listings
    GET  /veba/listings/asset/<asset_uid>      can_view_unit_digital_twin
    PUT  /veba/listings/<uid>/update           can_edit_asset_listing
    PUT  /veba/listings/<uid>/pause            can_edit_asset_listing
    PUT  /veba/listings/<uid>/reactivate       can_edit_asset_listing
    PUT  /veba/listings/<uid>/archive          can_edit_asset_listing

Conventions:
  * Standard reply() envelope: { status, message, data }.
  * log_audit_event(...) for every mutation (domain="VEBA").
  * Generic 500 messages to the client; full traceback in the server log.
  * Visibility rule: a row is visible to the caller iff
      (visibility = 'public') OR (account_root = caller_root).
    Owner-scope endpoints additionally require account_root match.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

import psycopg2
import psycopg2.extras
from flask import Blueprint, current_app, g, request

from .globals import log_audit_event, reply, require_permission

marketplace_bp = Blueprint("marketplace", __name__)
_logger = logging.getLogger("marketplace")

# Allowed enum values — kept in sync with migration 014 CHECK constraints
# and src/api/types/veba.types.ts on the frontend.
_PRICING_BASIS = {"per_day", "per_hour", "per_km", "per_trip"}
_VISIBILITY = {"public", "tenant"}
_VALID_STATUSES = {"active", "paused", "archived", "draft"}
_INITIAL_STATUS = "active"

# Editable terms exposed via PUT /update. Status transitions go through the
# dedicated lifecycle endpoints (pause/reactivate/archive), not this list.
_UPDATABLE_FIELDS = {
    "daily_rate", "currency", "pricing_basis", "hourly_rate",
    "availability_start", "availability_end", "geographic_scope",
    "operator_included", "notes", "visibility",
}


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _new_listing_uid() -> str:
    """Listing UIDs are human-readable: 'lst_' + uuid4."""
    return f"lst_{uuid.uuid4()}"


def _missing(payload: dict, *required: str) -> Optional[str]:
    """Return the first missing required key, or None if all present."""
    for key in required:
        if key not in payload or payload[key] in (None, ""):
            return key
    return None


def _to_decimal_or_none(value: Any) -> Optional[float]:
    """Coerce numeric input safely. Empty/None returns None."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_to_listing(row: dict) -> dict:
    """Convert a RealDict row into the JSON shape the frontend expects.

    Matches src/api/types/veba.types.ts → VebaListing.
    """
    out = dict(row)
    summary = out.get("asset_summary")
    if isinstance(summary, str):
        try:
            out["asset_summary"] = json.loads(summary)
        except json.JSONDecodeError:
            out["asset_summary"] = None
    for k in ("daily_rate", "hourly_rate"):
        if out.get(k) is not None:
            out[k] = float(out[k])
    for k in ("availability_start", "availability_end", "created_at", "updated_at"):
        if out.get(k) is not None:
            out[k] = out[k].isoformat()
    return out


def _open_conn():
    """Convenience for opening a DB connection in the project's style."""
    return psycopg2.connect(current_app.config["db_link"])


def _load_listing_owner(cursor, listing_uid: str) -> Optional[str]:
    """Return account_root of the listing, or None if it doesn't exist."""
    cursor.execute(
        "SELECT account_root FROM dll_marketplace_listings WHERE listing_uid = %s",
        (str(listing_uid),),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    # row may be a tuple or a RealDict depending on cursor factory.
    if isinstance(row, dict):
        return row.get("account_root")
    return row[0]


def _enforce_owner(cursor, listing_uid: str, claimed_account_root: str):
    """Verify the listing exists and the caller owns it.

    Returns (status_code, reply_body) on failure, or None on success.
    Pattern lets endpoints early-return cleanly:

        err = _enforce_owner(cursor, uid, account_root)
        if err: return err
    """
    owner_root = _load_listing_owner(cursor, listing_uid)
    if owner_root is None:
        return reply("error", 404, "Listing not found", "")
    if not claimed_account_root or owner_root != claimed_account_root:
        # Same 404 surface as missing-row to avoid leaking listing existence
        # to non-owners.
        return reply("error", 404, "Listing not found", "")
    return None


# Map listing status → asset's veba_status in dll_veba_enabled_units.
# This is the dual-state-machine bridge: a listing being paused implies the
# underlying asset is "suspended" on the operational tracker; archiving the
# listing implies the asset is "unavailable" again. Drafts don't affect the
# asset state (the asset isn't published anywhere yet).
_LISTING_STATUS_TO_ASSET_STATE = {
    "active":   "available",
    "paused":   "suspended",
    "archived": "unavailable",
    "draft":    None,
}


def _sync_asset_veba_state_by_asset(cursor, asset_uid: str, asset_state: Optional[str]) -> None:
    """Best-effort mirror of asset.veba_status into dll_veba_enabled_units.

    The asset_uid → device_imei mapping is informal (assets keyed by IMEI
    will match; non-device assets like personnel won't). 0 rows affected
    counts as a successful no-op so non-device listings don't fail.

    Same DB transaction as the caller — the caller's ``with dbconnect:``
    block makes both writes atomic.
    """
    if asset_state is None or not asset_uid:
        return
    cursor.execute(
        """
        UPDATE dll_veba_enabled_units
        SET veba_status = %s, updated_at = NOW()
        WHERE device_imei_number = %s
        """,
        (asset_state, str(asset_uid)),
    )
    affected = cursor.rowcount
    if affected:
        _logger.info(
            "veba_status sync (by asset): %s -> %s (%d row(s))",
            asset_uid, asset_state, affected,
        )
    else:
        _logger.debug(
            "veba_status sync (by asset): no row for %s — likely a non-device asset",
            asset_uid,
        )


def _sync_asset_veba_state_by_listing(cursor, listing_uid: str, asset_state: Optional[str]) -> None:
    """Same as above, keyed via the listing's asset_uid (subquery).

    Used by lifecycle endpoints where we have the listing_uid but not the
    asset_uid in scope. One query covers both the lookup and the update.
    """
    if asset_state is None:
        return
    cursor.execute(
        """
        UPDATE dll_veba_enabled_units
        SET veba_status = %s, updated_at = NOW()
        WHERE device_imei_number = (
            SELECT asset_uid FROM dll_marketplace_listings WHERE listing_uid = %s
        )
        """,
        (asset_state, str(listing_uid)),
    )
    affected = cursor.rowcount
    if affected:
        _logger.info(
            "veba_status sync (by listing): %s -> %s (%d row(s))",
            listing_uid, asset_state, affected,
        )
    else:
        _logger.debug(
            "veba_status sync (by listing): no veba row for listing %s",
            listing_uid,
        )


def _set_status(
    listing_uid: str,
    new_status: str,
    account_root: str,
    updated_by: str,
    *,
    audit_action: str,
    audit_severity: str = "Info",
) -> Any:
    """Common implementation for pause / reactivate / archive.

    Validates ownership, updates status, audit-logs the transition, replies
    with the canonical envelope.
    """
    assert new_status in _VALID_STATUSES, f"_set_status called with bad status: {new_status}"

    try:
        dbconnect = _open_conn()
        with dbconnect:
            with dbconnect.cursor() as cursor:
                err = _enforce_owner(cursor, listing_uid, account_root)
                if err:
                    return err

                cursor.execute(
                    """
                    UPDATE dll_marketplace_listings
                    SET status = %s, updated_at = NOW()
                    WHERE listing_uid = %s
                    """,
                    (new_status, str(listing_uid)),
                )

                # Side-effect: mirror the listing's new status onto the
                # asset's operational state (best-effort).
                _sync_asset_veba_state_by_listing(
                    cursor,
                    listing_uid,
                    _LISTING_STATUS_TO_ASSET_STATE.get(new_status),
                )

        log_audit_event(
            actor=g.current_user["account_uid"],
            action=audit_action,
            obj=f"Listing {listing_uid} → status={new_status}",
            domain="VEBA",
            severity=audit_severity,
            ip_address=request.remote_addr,
            meta={
                "listing_uid": listing_uid,
                "new_status": new_status,
                "updated_by": updated_by,
            },
        )
        return reply("success", 200, f"Listing {new_status}", {"listing_uid": listing_uid, "status": new_status})

    except Exception as err:
        _logger.exception("_set_status(%s → %s) failed: %s", listing_uid, new_status, err)
        return reply("error", 500, "Could not update listing status", "")
    finally:
        try:
            dbconnect.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# POST /veba/listings/create
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/listings/create", methods=["POST"])
@require_permission("can_list_asset_on_marketplace")
def create_listing():
    """Create a new VEBA marketplace listing for an asset.

    Body matches src/api/types/veba.types.ts → CreateVebaListingRequest.
    Returns { listing_uid }.
    """
    payload = request.get_json() or {}
    data = payload.get("data") or {}

    # ── Tenant isolation: derive account_root and created_by from the
    # authenticated JWT — never trust the request body for these. ──
    auth_account_root = g.current_user.get("account_root", "")
    auth_account_uid  = g.current_user.get("account_uid", "")
    if not auth_account_root:
        return reply("error", 403, "Cannot determine your tenant from the session", "")

    # Override body values so downstream code always uses the trusted source.
    data["account_root"] = auth_account_root
    data["created_by"]   = auth_account_uid

    missing = _missing(
        data,
        "asset_uid",
        "daily_rate", "currency", "pricing_basis", "visibility",
    )
    if missing:
        return reply("error", 400, f"Required field missing: {missing}", "")

    daily_rate = _to_decimal_or_none(data.get("daily_rate"))
    if daily_rate is None or daily_rate <= 0:
        return reply("error", 400, "daily_rate must be a positive number", "")

    hourly_rate = _to_decimal_or_none(data.get("hourly_rate"))
    if data.get("hourly_rate") not in (None, "") and (hourly_rate is None or hourly_rate <= 0):
        return reply("error", 400, "hourly_rate, if provided, must be positive", "")

    pricing_basis = str(data["pricing_basis"])
    if pricing_basis not in _PRICING_BASIS:
        return reply(
            "error", 400,
            f"pricing_basis must be one of: {', '.join(sorted(_PRICING_BASIS))}",
            ""
        )

    visibility = str(data["visibility"])
    if visibility not in _VISIBILITY:
        return reply("error", 400, "visibility must be 'public' or 'tenant'", "")

    availability_start = data.get("availability_start") or None
    availability_end = data.get("availability_end") or None
    if availability_start and availability_end and availability_end < availability_start:
        return reply("error", 400, "availability_end must not be before availability_start", "")

    asset_summary = data.get("asset_summary")
    asset_summary_json = (
        psycopg2.extras.Json(asset_summary)
        if isinstance(asset_summary, dict)
        else None
    )

    listing_uid = _new_listing_uid()

    try:
        dbconnect = _open_conn()
        with dbconnect:
            with dbconnect.cursor() as cursor:
                # ── Guard: only one active/paused listing per asset ──
                cursor.execute(
                    """
                    SELECT listing_uid FROM dll_marketplace_listings
                    WHERE asset_uid = %s AND status IN ('active', 'paused')
                    LIMIT 1
                    """,
                    (str(data["asset_uid"]),),
                )
                existing = cursor.fetchone()
                if existing:
                    dup_uid = existing[0] if not isinstance(existing, dict) else existing.get("listing_uid")
                    return reply(
                        "error", 409,
                        f"This asset already has an active listing ({dup_uid}). "
                        "Pause or archive it before creating a new one.",
                        "",
                    )

                cursor.execute(
                    """
                    INSERT INTO dll_marketplace_listings (
                        listing_uid, asset_uid, account_root, created_by,
                        daily_rate, currency, pricing_basis, hourly_rate,
                        availability_start, availability_end,
                        geographic_scope, operator_included, notes,
                        visibility, status, asset_summary
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s
                    )
                    """,
                    (
                        listing_uid,
                        str(data["asset_uid"]),
                        str(data["account_root"]),
                        str(data["created_by"]),
                        daily_rate,
                        str(data["currency"]).strip().upper()[:8],
                        pricing_basis,
                        hourly_rate,
                        availability_start,
                        availability_end,
                        (data.get("geographic_scope") or None),
                        bool(data.get("operator_included", False)),
                        (data.get("notes") or None),
                        visibility,
                        _INITIAL_STATUS,
                        asset_summary_json,
                    ),
                )

                # Side-effect: mirror the asset's veba_status so the
                # operational asset tracker stays consistent with the
                # marketplace listing. Same transaction = atomic.
                _sync_asset_veba_state_by_asset(
                    cursor, str(data["asset_uid"]), "available",
                )

        log_audit_event(
            actor=g.current_user["account_uid"],
            action="CREATE",
            obj=f"Listed asset {data['asset_uid']} on VEBA (uid={listing_uid})",
            domain="VEBA",
            severity="Info",
            ip_address=request.remote_addr,
            meta={
                "listing_uid": listing_uid,
                "asset_uid": data["asset_uid"],
                "account_root": data["account_root"],
                "daily_rate": daily_rate,
                "currency": data["currency"],
                "pricing_basis": pricing_basis,
                "visibility": visibility,
            },
        )
        return reply("success", 201, "Listing created", {"listing_uid": listing_uid})

    except Exception as err:
        _logger.exception("create_listing failed: %s", err)
        return reply("error", 500, "Could not create listing", "")
    finally:
        try:
            dbconnect.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# GET /veba/listings   (with scope)
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/listings", methods=["GET"])
@require_permission("can_browse_asset_listings")
def list_listings():
    """List marketplace listings, scoped by visibility.

    Query params:
        account_root  — required; used to resolve tenant scope.
        scope         — "marketplace" (default), "tenant", or "owner".

            marketplace: public listings, status='active' (the public browse).
            tenant:      public listings + the caller's tenant-private ones,
                         all in active status.
            owner:       only the caller's own listings, any status.

        status        — optional filter (active|paused|archived|draft). Only
                        meaningful for scope=owner; ignored otherwise.
    """
    account_root = request.args.get("account_root") or ""
    scope = (request.args.get("scope") or "marketplace").lower()
    status_filter = request.args.get("status")

    if scope not in ("marketplace", "tenant", "owner"):
        return reply("error", 400, "scope must be 'marketplace', 'tenant', or 'owner'", "")
    if scope != "marketplace" and not account_root:
        return reply("error", 400, "account_root is required for non-marketplace scopes", "")

    try:
        dbconnect = _open_conn()
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                if scope == "owner":
                    if status_filter and status_filter in _VALID_STATUSES:
                        cursor.execute(
                            """
                            SELECT * FROM dll_marketplace_listings
                            WHERE account_root = %s AND status = %s
                            ORDER BY created_at DESC
                            """,
                            (account_root, status_filter),
                        )
                    else:
                        cursor.execute(
                            """
                            SELECT * FROM dll_marketplace_listings
                            WHERE account_root = %s
                            ORDER BY created_at DESC
                            """,
                            (account_root,),
                        )
                elif scope == "tenant":
                    cursor.execute(
                        """
                        SELECT * FROM dll_marketplace_listings
                        WHERE status = 'active'
                          AND (visibility = 'public' OR account_root = %s)
                        ORDER BY created_at DESC
                        """,
                        (account_root,),
                    )
                else:  # marketplace
                    cursor.execute(
                        """
                        SELECT * FROM dll_marketplace_listings
                        WHERE status = 'active' AND visibility = 'public'
                        ORDER BY created_at DESC
                        """
                    )
                rows = cursor.fetchall()

        listings = [_row_to_listing(dict(r)) for r in rows]
        return reply("success", 200, f"{len(listings)} listings", listings)

    except Exception as err:
        _logger.exception("list_listings failed: %s", err)
        return reply("error", 500, "Could not load listings", "")
    finally:
        try:
            dbconnect.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# GET /veba/listings/<uid>
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/listings/<listing_uid>", methods=["GET"])
@require_permission("can_browse_asset_listings")
def get_listing_by_uid(listing_uid: str):
    """Single-listing fetch, respecting visibility rules.

    Query params:
        account_root — optional. If provided, tenant-private listings owned
                       by this account are also returned. Without it, only
                       public listings are visible.
    """
    account_root = request.args.get("account_root") or ""

    try:
        dbconnect = _open_conn()
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM dll_marketplace_listings
                    WHERE listing_uid = %s
                      AND (visibility = 'public' OR account_root = %s)
                    """,
                    (str(listing_uid), account_root),
                )
                row = cursor.fetchone()

        if not row:
            return reply("error", 404, "Listing not found", "")
        return reply("success", 200, "Listing found", _row_to_listing(dict(row)))

    except Exception as err:
        _logger.exception("get_listing_by_uid failed: %s", err)
        return reply("error", 500, "Could not load listing", "")
    finally:
        try:
            dbconnect.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# GET /veba/listings/asset/<asset_uid>
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/listings/asset/<asset_uid>", methods=["GET"])
@require_permission("can_view_unit_digital_twin")
def get_listing_for_asset(asset_uid: str):
    """Return the active/paused listing for the given asset, or null."""
    try:
        dbconnect = _open_conn()
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM dll_marketplace_listings
                    WHERE asset_uid = %s AND status IN ('active', 'paused')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(asset_uid),),
                )
                row = cursor.fetchone()

        listing = _row_to_listing(dict(row)) if row else None
        return reply(
            "success", 200,
            "Listing found" if listing else "No active listing for asset",
            listing,
        )

    except Exception as err:
        _logger.exception("get_listing_for_asset failed: %s", err)
        return reply("error", 500, "Could not load listing", "")
    finally:
        try:
            dbconnect.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# PUT /veba/listings/<uid>/update
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/listings/<listing_uid>/update", methods=["PUT"])
@require_permission("can_edit_asset_listing")
def update_listing(listing_uid: str):
    """Partial update of a listing's commercial terms.

    Status is NOT updatable here — use pause/reactivate/archive endpoints.
    Pending booking requests keep their snapshotted rate; new requests pick
    up the new one (the snapshot logic lives in the booking-create endpoint).
    """
    payload = request.get_json() or {}
    data = payload.get("data") or {}

    # ── Tenant isolation: derive from JWT, not request body ──
    account_root = g.current_user.get("account_root", "")
    updated_by   = g.current_user.get("account_uid", "") or str(data.get("updated_by", ""))

    if not account_root:
        return reply("error", 403, "Cannot determine your tenant from the session", "")

    # Build SET clause dynamically from the supplied editable fields.
    set_clauses: list[str] = []
    values: list[Any] = []

    if "daily_rate" in data:
        rate = _to_decimal_or_none(data["daily_rate"])
        if rate is None or rate <= 0:
            return reply("error", 400, "daily_rate must be a positive number", "")
        set_clauses.append("daily_rate = %s")
        values.append(rate)

    if "currency" in data:
        set_clauses.append("currency = %s")
        values.append(str(data["currency"]).strip().upper()[:8])

    if "pricing_basis" in data:
        pb = str(data["pricing_basis"])
        if pb not in _PRICING_BASIS:
            return reply("error", 400, f"pricing_basis must be one of: {', '.join(sorted(_PRICING_BASIS))}", "")
        set_clauses.append("pricing_basis = %s")
        values.append(pb)

    if "hourly_rate" in data:
        hr = _to_decimal_or_none(data["hourly_rate"])
        if data["hourly_rate"] not in (None, "") and (hr is None or hr <= 0):
            return reply("error", 400, "hourly_rate, if provided, must be positive", "")
        set_clauses.append("hourly_rate = %s")
        values.append(hr)

    if "availability_start" in data:
        set_clauses.append("availability_start = %s")
        values.append(data["availability_start"] or None)

    if "availability_end" in data:
        set_clauses.append("availability_end = %s")
        values.append(data["availability_end"] or None)

    if "geographic_scope" in data:
        set_clauses.append("geographic_scope = %s")
        values.append(data["geographic_scope"] or None)

    if "operator_included" in data:
        set_clauses.append("operator_included = %s")
        values.append(bool(data["operator_included"]))

    if "notes" in data:
        set_clauses.append("notes = %s")
        values.append(data["notes"] or None)

    if "visibility" in data:
        vis = str(data["visibility"])
        if vis not in _VISIBILITY:
            return reply("error", 400, "visibility must be 'public' or 'tenant'", "")
        set_clauses.append("visibility = %s")
        values.append(vis)

    # Validate cross-field constraint (availability_end >= start) if both
    # ended up in the SET list.
    a_start = data.get("availability_start")
    a_end = data.get("availability_end")
    if a_start and a_end and a_end < a_start:
        return reply("error", 400, "availability_end must not be before availability_start", "")

    if not set_clauses:
        return reply("error", 400, "No editable fields provided", "")

    set_clauses.append("updated_at = NOW()")

    try:
        dbconnect = _open_conn()
        with dbconnect:
            with dbconnect.cursor() as cursor:
                err = _enforce_owner(cursor, listing_uid, account_root)
                if err:
                    return err

                query = (
                    "UPDATE dll_marketplace_listings SET "
                    + ", ".join(set_clauses)
                    + " WHERE listing_uid = %s"
                )
                values.append(str(listing_uid))
                cursor.execute(query, tuple(values))

        log_audit_event(
            actor=g.current_user["account_uid"],
            action="UPDATE",
            obj=f"Listing {listing_uid} updated",
            domain="VEBA",
            severity="Info",
            ip_address=request.remote_addr,
            meta={
                "listing_uid": listing_uid,
                "fields": [c.split(" = ")[0] for c in set_clauses if c != "updated_at = NOW()"],
                "updated_by": updated_by,
            },
        )
        return reply("success", 200, "Listing updated", {"listing_uid": listing_uid})

    except Exception as err:
        _logger.exception("update_listing failed: %s", err)
        return reply("error", 500, "Could not update listing", "")
    finally:
        try:
            dbconnect.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Lifecycle: PUT /veba/listings/<uid>/{pause|reactivate|archive}
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/listings/<listing_uid>/pause", methods=["PUT"])
@require_permission("can_edit_asset_listing")
def pause_listing(listing_uid: str):
    # Derive tenant from JWT — ignore body account_root
    account_root = g.current_user.get("account_root", "")
    updated_by   = g.current_user.get("account_uid", "")
    return _set_status(
        listing_uid,
        "paused",
        account_root,
        updated_by,
        audit_action="PAUSE",
        audit_severity="Info",
    )


@marketplace_bp.route("/veba/listings/<listing_uid>/reactivate", methods=["PUT"])
@require_permission("can_edit_asset_listing")
def reactivate_listing(listing_uid: str):
    account_root = g.current_user.get("account_root", "")
    updated_by   = g.current_user.get("account_uid", "")
    return _set_status(
        listing_uid,
        "active",
        account_root,
        updated_by,
        audit_action="REACTIVATE",
        audit_severity="Info",
    )


@marketplace_bp.route("/veba/listings/<listing_uid>/archive", methods=["PUT"])
@require_permission("can_edit_asset_listing")
def archive_listing(listing_uid: str):
    account_root = g.current_user.get("account_root", "")
    updated_by   = g.current_user.get("account_uid", "")
    return _set_status(
        listing_uid,
        "archived",
        account_root,
        updated_by,
        audit_action="ARCHIVE",
        audit_severity="Alarm",  # destructive — higher severity for the audit trail
    )


# ======================================================================
# Booking requests (Phase 4)
# ======================================================================
#
# A booking request is created when a marketplace browser ("requester")
# wants to book a published listing. The listing's owner then approves or
# rejects. The rate the requester saw is frozen into rate_snapshot at
# submission time — owner-side rate edits don't retroactively change
# pending requests.


def _new_request_uid() -> str:
    """Booking-request UIDs are human-readable: 'req_' + uuid4."""
    return f"req_{uuid.uuid4()}"


def _row_to_request(row: dict) -> dict:
    """Convert a RealDict row → frontend BookingRequest JSON shape.

    Mirrors src/api/types/booking.types.ts → BookingRequest. Parses
    rate_snapshot JSONB; ISO-formats dates and timestamps.
    """
    out = dict(row)
    snapshot = out.get("rate_snapshot")
    if isinstance(snapshot, str):
        try:
            out["rate_snapshot"] = json.loads(snapshot)
        except json.JSONDecodeError:
            out["rate_snapshot"] = None
    # rate_snapshot.daily_rate might come back as Decimal — coerce so jsonify
    # doesn't blow up.
    if isinstance(out.get("rate_snapshot"), dict):
        rs = out["rate_snapshot"]
        if rs.get("daily_rate") is not None:
            try:
                rs["daily_rate"] = float(rs["daily_rate"])
            except (TypeError, ValueError):
                pass
    for k in ("start_date", "end_date", "created_at", "updated_at"):
        if out.get(k) is not None:
            out[k] = out[k].isoformat()
    return out


def _load_listing_for_booking(cursor, listing_uid: str) -> Optional[dict]:
    """Fetch the listing fields needed to construct a booking request.

    Returns None if the listing doesn't exist. The caller is responsible
    for checking ``status == 'active'`` and replying appropriately.
    """
    cursor.execute(
        """
        SELECT account_root, asset_uid, daily_rate, currency, pricing_basis, status
        FROM dll_marketplace_listings
        WHERE listing_uid = %s
        """,
        (str(listing_uid),),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    # Tuple cursor — name the columns manually so the caller doesn't care.
    return {
        "account_root":  row[0],
        "asset_uid":     row[1],
        "daily_rate":    row[2],
        "currency":      row[3],
        "pricing_basis": row[4],
        "status":        row[5],
    }


def _enforce_request_ownership(cursor, request_uid: str, claimed_account_root: str):
    """Verify a booking request exists AND the caller owns the listing.

    Returns either ``(request_row, None)`` on success, or
    ``(None, reply_response)`` on failure. The reply_response is the
    canonical 404 envelope — non-owners cannot distinguish "doesn't exist"
    from "not yours".
    """
    cursor.execute(
        """
        SELECT request_uid, owner_root, status, listing_uid, asset_uid
        FROM dll_booking_requests
        WHERE request_uid = %s
        """,
        (str(request_uid),),
    )
    row = cursor.fetchone()
    if row is None:
        return None, reply("error", 404, "Booking request not found", "")
    # row may be a tuple or RealDict
    if isinstance(row, dict):
        owner_root = row.get("owner_root")
        request = row
    else:
        owner_root = row[1]
        request = {
            "request_uid": row[0],
            "owner_root":  row[1],
            "status":      row[2],
            "listing_uid": row[3],
            "asset_uid":   row[4],
        }
    if not claimed_account_root or owner_root != claimed_account_root:
        return None, reply("error", 404, "Booking request not found", "")
    return request, None


def _enforce_request_requester(cursor, request_uid: str, claimed_requester_root: str):
    """Like _enforce_request_ownership but checks **requester_root** instead.

    Used for actions the requester performs (cancel).
    """
    cursor.execute(
        """
        SELECT request_uid, requester_root, owner_root, status, listing_uid, asset_uid
        FROM dll_booking_requests
        WHERE request_uid = %s
        """,
        (str(request_uid),),
    )
    row = cursor.fetchone()
    if row is None:
        return None, reply("error", 404, "Booking request not found", "")
    if isinstance(row, dict):
        requester_root = row.get("requester_root")
        req = row
    else:
        requester_root = row[1]
        req = {
            "request_uid": row[0],
            "requester_root": row[1],
            "owner_root": row[2],
            "status": row[3],
            "listing_uid": row[4],
            "asset_uid": row[5],
        }
    if not claimed_requester_root or requester_root != claimed_requester_root:
        return None, reply("error", 404, "Booking request not found", "")
    return req, None


def _set_request_status(
    request_uid: str,
    new_status: str,
    account_root: str,
    updated_by: str,
    *,
    audit_action: str,
    audit_severity: str = "Info",
    allowed_from: str = "pending",
    ownership_check: str = "owner",
) -> Any:
    """Shared engine for approve / reject / cancel / fulfill.

    ``allowed_from`` controls which current status is valid for the transition.
    ``ownership_check`` is "owner" (default) or "requester".

    Returns the standard reply() envelope.
    """
    try:
        dbconnect = _open_conn()
        with dbconnect:
            with dbconnect.cursor() as cursor:
                if ownership_check == "requester":
                    req_row, err = _enforce_request_requester(cursor, request_uid, account_root)
                else:
                    req_row, err = _enforce_request_ownership(cursor, request_uid, account_root)
                if err:
                    return err

                if req_row["status"] != allowed_from:
                    return reply(
                        "error", 409,
                        f"Request is {req_row['status']} — can only transition from {allowed_from}",
                        "",
                    )

                cursor.execute(
                    """
                    UPDATE dll_booking_requests
                    SET status = %s, updated_at = NOW()
                    WHERE request_uid = %s
                    """,
                    (new_status, str(request_uid)),
                )

        log_audit_event(
            actor=g.current_user["account_uid"],
            action=audit_action,
            obj=f"Booking request {request_uid} → {new_status}",
            domain="VEBA",
            severity=audit_severity,
            ip_address=request.remote_addr,
            meta={
                "request_uid": request_uid,
                "listing_uid": req_row["listing_uid"],
                "asset_uid":   req_row["asset_uid"],
                "new_status":  new_status,
                "updated_by":  updated_by,
            },
        )
        return reply(
            "success", 200,
            f"Booking request {new_status}",
            {"request_uid": request_uid, "status": new_status},
        )
    except Exception as err:
        _logger.exception("_set_request_status(%s -> %s) failed: %s", request_uid, new_status, err)
        return reply("error", 500, "Could not update booking request", "")
    finally:
        try:
            dbconnect.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# POST /veba/booking-requests/create
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/booking-requests/create", methods=["POST"])
@require_permission("can_book_asset")
def create_booking_request():
    """Create a booking request against a published listing.

    Body matches CreateBookingRequest (src/api/types/booking.types.ts).
    The listing's account_root + rate are derived server-side from the
    listing row, NOT trusted from the request body.
    """
    payload = request.get_json() or {}
    data = payload.get("data") or {}

    missing = _missing(
        data,
        "listing_uid", "requester_uid", "requester_root", "start_date", "end_date",
    )
    if missing:
        return reply("error", 400, f"Required field missing: {missing}", "")

    start_date = str(data["start_date"])
    end_date = str(data["end_date"])
    if end_date < start_date:
        return reply("error", 400, "end_date must not be before start_date", "")

    request_uid = _new_request_uid()

    try:
        dbconnect = _open_conn()
        with dbconnect:
            with dbconnect.cursor() as cursor:
                listing = _load_listing_for_booking(cursor, str(data["listing_uid"]))
                if listing is None:
                    return reply("error", 404, "Listing not found", "")
                if listing["status"] != "active":
                    return reply(
                        "error", 409,
                        f"Listing is {listing['status']} — only active listings can be booked",
                        "",
                    )

                # Build the immutable rate snapshot from the listing's *current*
                # commercial terms. Owner rate edits after this point won't
                # affect the request — that's the policy.
                rate_snapshot = {
                    "daily_rate":    float(listing["daily_rate"]) if listing["daily_rate"] is not None else 0.0,
                    "currency":      listing["currency"],
                    "pricing_basis": listing["pricing_basis"],
                }

                cursor.execute(
                    """
                    INSERT INTO dll_booking_requests (
                        request_uid, listing_uid, asset_uid,
                        requester_uid, requester_root, owner_root,
                        start_date, end_date, notes,
                        status, rate_snapshot
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s
                    )
                    """,
                    (
                        request_uid,
                        str(data["listing_uid"]),
                        listing["asset_uid"],
                        str(data["requester_uid"]),
                        str(data["requester_root"]),
                        listing["account_root"],  # owner_root: trust the listing, not the request
                        start_date,
                        end_date,
                        (data.get("notes") or None),
                        "pending",
                        psycopg2.extras.Json(rate_snapshot),
                    ),
                )

        log_audit_event(
            actor=g.current_user["account_uid"],
            action="CREATE",
            obj=f"Booking request {request_uid} created for listing {data['listing_uid']}",
            domain="VEBA",
            severity="Info",
            ip_address=request.remote_addr,
            meta={
                "request_uid":  request_uid,
                "listing_uid":  data["listing_uid"],
                "asset_uid":    listing["asset_uid"],
                "requester_root": data["requester_root"],
                "owner_root":   listing["account_root"],
                "rate_snapshot": rate_snapshot,
            },
        )
        return reply("success", 201, "Booking request created", {"request_uid": request_uid})

    except Exception as err:
        _logger.exception("create_booking_request failed: %s", err)
        return reply("error", 500, "Could not create booking request", "")
    finally:
        try:
            dbconnect.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# GET /veba/booking-requests
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/booking-requests", methods=["GET"])
@require_permission("can_view_booking")
def list_booking_requests():
    """List booking requests scoped by direction.

    Query params:
        account_root  — required unless direction=all.
        direction     — "incoming" (default), "outgoing", "both", or "all".

            incoming: requests TO the caller (owner_root match) — the
                      review queue.
            outgoing: requests FROM the caller (requester_root match) —
                      "what I've asked for".
            both:     union of both directions for the given account_root.
            all:      every booking request (CMS operator view) — ignores
                      account_root entirely.

        status        — optional filter (any BookingRequestStatus).
    """
    account_root = request.args.get("account_root") or ""
    direction = (request.args.get("direction") or "incoming").lower()
    status_filter = request.args.get("status")

    if direction not in ("incoming", "outgoing", "both", "all"):
        return reply("error", 400, "direction must be 'incoming', 'outgoing', 'both', or 'all'", "")
    if direction != "all" and not account_root:
        return reply("error", 400, "account_root is required (unless direction=all)", "")

    where_clauses: list[str] = []
    params: list[Any] = []
    if direction == "incoming":
        where_clauses.append("owner_root = %s")
        params.append(account_root)
    elif direction == "outgoing":
        where_clauses.append("requester_root = %s")
        params.append(account_root)
    elif direction == "both":
        where_clauses.append("(owner_root = %s OR requester_root = %s)")
        params.extend([account_root, account_root])
    # direction == "all" → no account filter, returns everything

    if status_filter:
        where_clauses.append("status = %s")
        params.append(status_filter)

    if where_clauses:
        sql = (
            "SELECT * FROM dll_booking_requests "
            "WHERE " + " AND ".join(where_clauses) + " "
            "ORDER BY created_at DESC"
        )
    else:
        sql = "SELECT * FROM dll_booking_requests ORDER BY created_at DESC"

    try:
        dbconnect = _open_conn()
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()

        requests_out = [_row_to_request(dict(r)) for r in rows]
        return reply("success", 200, f"{len(requests_out)} booking requests", requests_out)

    except Exception as err:
        _logger.exception("list_booking_requests failed: %s", err)
        return reply("error", 500, "Could not load booking requests", "")
    finally:
        try:
            dbconnect.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# PUT /veba/booking-requests/<uid>/approve | /reject
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/booking-requests/<request_uid>/approve", methods=["PUT"])
@require_permission("can_approve_booking_request")
def approve_booking_request(request_uid: str):
    account_root = g.current_user.get("account_root", "")
    updated_by   = g.current_user.get("account_uid", "")
    return _set_request_status(
        request_uid,
        "approved",
        account_root,
        updated_by,
        audit_action="APPROVE",
        audit_severity="Info",
    )


@marketplace_bp.route("/veba/booking-requests/<request_uid>/reject", methods=["PUT"])
@require_permission("can_reject_booking_request")
def reject_booking_request(request_uid: str):
    account_root = g.current_user.get("account_root", "")
    updated_by   = g.current_user.get("account_uid", "")
    return _set_request_status(
        request_uid,
        "rejected",
        account_root,
        updated_by,
        audit_action="REJECT",
        audit_severity="Info",
    )


# ----------------------------------------------------------------------
# PUT /veba/booking-requests/<uid>/cancel   (requester cancels own request)
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/booking-requests/<request_uid>/cancel", methods=["PUT"])
@require_permission("can_book_asset")
def cancel_booking_request(request_uid: str):
    """Requester cancels their own pending booking request.

    Uses requester-side ownership check so only the person who submitted
    the request can cancel it (not the listing owner).
    """
    account_root = g.current_user.get("account_root", "")
    updated_by   = g.current_user.get("account_uid", "")
    return _set_request_status(
        request_uid,
        "cancelled",
        account_root,
        updated_by,
        audit_action="CANCEL",
        audit_severity="Info",
        allowed_from="pending",
        ownership_check="requester",
    )


# ----------------------------------------------------------------------
# PUT /veba/booking-requests/<uid>/fulfill  (owner marks as fulfilled)
# ----------------------------------------------------------------------

@marketplace_bp.route("/veba/booking-requests/<request_uid>/fulfill", methods=["PUT"])
@require_permission("can_approve_booking_request")
def fulfill_booking_request(request_uid: str):
    """Owner marks an approved booking request as fulfilled.

    Only approved requests can transition to fulfilled — the booking has
    been completed and the asset returned (or the service delivered).
    """
    account_root = g.current_user.get("account_root", "")
    updated_by   = g.current_user.get("account_uid", "")
    return _set_request_status(
        request_uid,
        "fulfilled",
        account_root,
        updated_by,
        audit_action="FULFILL",
        audit_severity="Info",
        allowed_from="approved",
        ownership_check="owner",
    )
