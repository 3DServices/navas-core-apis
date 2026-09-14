# OLIWA — New / Changed API Endpoints (for Apidog)

**Base URL:** `https://narvas.3dservices.co.ug` (prod) or `http://127.0.0.1:5000` (local)
**Auth:** unless noted, send `Authorization: Bearer <access_token>`.
**Response envelope (all JSON endpoints):**

```json
{ "status": "success" | "error", "message": "…", "data": <object|array|string> }
```

HTTP status codes accompany the body (200/201 success; 400/401/403/404/500 errors).

Covers: **Profile** (migration 024), **Auto Top-Up** (migration 025, extends
auto-renew), **Pause** (migration 026, new blueprint). Run migrations 024–026 and
redeploy before testing.

---

## 1. Profile

### 1.1 GET `/users/{account_uid}/details`  *(extended response)*
Auth required. Now returns `profile_pic` and `date_of_birth`.

**Response 200**
```json
{
  "status": "success",
  "message": "Account Found",
  "data": {
    "account_name": "OLIWA User",
    "account_type": "client",
    "account_role": "customer_tracker",
    "access_status": "active",
    "email": "user@example.com",
    "username": "customer_tracker",
    "billing_type": "prepaid",
    "primary_account": "acc-uid",
    "token_balance": "12",
    "date_created": "2026-01-01",
    "profile_pic": "/users/profile-photos/acc-uid_ab12cd34ef56.jpg",
    "date_of_birth": "1990-05-20"
  }
}
```

### 1.2 PUT `/users/{user_uid}/profile`  *(new)*
Auth required (self, or privileged account). Updates date of birth.

**Body**
```json
{ "data": { "date_of_birth": "1990-05-20" } }
```
`date_of_birth` must be `YYYY-MM-DD`, or `""` to clear it.

**Response 200**
```json
{ "status": "success", "message": "Profile updated", "data": { "date_of_birth": "1990-05-20" } }
```
Errors: `400` bad date format, `403` not your profile, `404` user not found.

### 1.3 POST `/users/{user_uid}/profile-photo`  *(new — multipart)*
Auth required (self/privileged). **Content-Type:** `multipart/form-data`.

| Field | Type | Notes |
|---|---|---|
| `photo` | file | jpg/jpeg/png/webp, max 5 MB |

**Response 200**
```json
{ "status": "success", "message": "Photo uploaded",
  "data": { "photo_url": "/users/profile-photos/uid_ab12cd34ef56.jpg" } }
```
Errors: `400` no file / bad type / >5 MB, `403` not your photo, `404` user not found.

### 1.4 GET `/users/profile-photos/{filename}`  *(new — no auth)*
Returns the raw image bytes (served file). Not a JSON envelope. `404` if missing.

---

## 2. Auto-Renew + Auto Top-Up  *(settings extended)*

### 2.1 GET `/subscriptions/auto-renew/{client_uid}`  *(extended)*
Auth required. Returns defaults (with `configured:false`) if never saved.

**Response 200**
```json
{
  "status": "success",
  "message": "Auto-renew settings",
  "data": {
    "enabled": true,
    "paused": false,
    "target_hours": 50,
    "renewal_period": 1,
    "top_up_enabled": true,
    "top_up_token_uid": "tok-123",
    "top_up_quantity": 2,
    "momo_number": "0770000000",
    "daily_topup_limit": 1,
    "channels": "in_app,sms",
    "consent": true,
    "configured": true
  }
}
```

### 2.2 POST `/subscriptions/auto-renew`  *(extended — upsert)*
Auth required. Creates/updates by `client_uid`.

**Body**
```json
{
  "data": {
    "client_uid": "client-uid",
    "enabled": true,
    "paused": false,
    "target_hours": 50,
    "renewal_period": 1,
    "top_up_enabled": true,
    "top_up_token_uid": "tok-123",
    "top_up_quantity": 2,
    "momo_number": "0770000000",
    "daily_topup_limit": 1,
    "channels": "in_app,sms,whatsapp",
    "consent": true
  }
}
```
Notes: `channels` is a CSV of `in_app,push,sms,whatsapp,email`. `consent` is
sticky (sent `true` records `consent_at`; not cleared by sending `false`).

**Response 200** — echoes the saved settings (same shape as 2.1, plus `configured:true`).

### 2.3 POST `/subscriptions/auto-renew/run`  *(existing)*
Auth + permission `subscriptions.renew`. Triggers one sweep (renew + top-up).

**Body** *(optional)*
```json
{ "data": { "live": false } }
```
**Response 200** — summary:
```json
{ "status": "success", "message": "…", "data": {
  "clients": 3, "renewed": 0, "would_renew": 2, "skipped_no_tokens": 0,
  "low_balance": 1, "would_top_up": 1, "top_up_initiated": 0,
  "top_up_failed": 0, "topup_capped": 0, "errors": 0, "dry_run": true } }
```

---

## 3. Pause (unit-level)  *(new blueprint)*

### 3.1 POST `/pause/action`
Auth required. Pause/resume specific devices and/or groups now.

**Body**
```json
{
  "data": {
    "owner_uid": "client-uid",
    "action": "pause",
    "reason": "manual",
    "targets": [
      { "scope": "device", "target": "123456789012345" },
      { "scope": "group",  "target": "group-local-uid" }
    ]
  }
}
```
`action`: `pause` | `resume`. `scope`: `device` (target = IMEI) | `group`
(target = `group_local_uid`, expanded to its devices). `reason` optional
(default `manual`).

**Response 200**
```json
{ "status": "success", "message": "Paused 4 unit(s)", "data": { "changed": 4, "skipped": 1 } }
```

### 3.2 GET `/pause/rules/{owner_uid}`
Auth required. Lists auto-pause rules.

**Response 200**
```json
{ "status": "success", "message": "Pause rules", "data": [
  { "id": 7, "scope": "device", "target_uid": "123456789012345",
    "mode": "until", "resume_at": "2026-09-15T08:00:00", "balance_threshold": null, "active": true },
  { "id": 8, "scope": "device", "target_uid": "356789012345678",
    "mode": "balance", "resume_at": "", "balance_threshold": 5.0, "active": true }
] }
```

### 3.3 POST `/pause/rules`
Auth required. Create/update a rule (one per `owner+scope+target`).
A `until` rule **pauses the target immediately** and auto-resumes at `resume_at`.

**Body — timed pause**
```json
{ "data": { "owner_uid": "client-uid", "scope": "device",
  "target": "123456789012345", "mode": "until",
  "resume_at": "2026-09-15T08:00:00", "active": true } }
```
**Body — balance pause**
```json
{ "data": { "owner_uid": "client-uid", "scope": "device",
  "target": "123456789012345", "mode": "balance",
  "balance_threshold": 5, "active": true } }
```
`mode`: `until` (needs ISO-8601 `resume_at`) | `balance` (needs
`balance_threshold`, in tokens).

**Response 200** `{ "status": "success", "message": "Pause rule saved", "data": "" }`

### 3.4 DELETE `/pause/rules/{rule_id}`
Auth required. Path param is the integer rule id. No body.
**Response 200** `{ "status": "success", "message": "Pause rule removed", "data": "" }`
(`404` if not found.)

### 3.5 POST `/pause/rules/run`
Auth required. Enforcement pass (schedule this, e.g. every 15 min).
Auto-resumes expired `until` rules; pauses units for `balance` rules at/below threshold.

**Body** *(optional)* `{ "data": { "live": false } }`
**Response 200**
```json
{ "status": "success", "message": "Pause rules evaluated",
  "data": { "resumed": 1, "paused": 2, "dry_run": true } }
```

### 3.6 GET `/pause/analytics/{owner_uid}`
Auth required. Owner-facing pause analytics (last 30 days).

**Response 200**
```json
{ "status": "success", "message": "Pause analytics", "data": {
  "window_days": 30,
  "pauses": 12,
  "resumes": 9,
  "by_reason": [ { "reason": "low_balance", "count": 7 },
                 { "reason": "manual", "count": 5 } ],
  "avg_balance_at_pause": 3.4,
  "currently_paused": 2
} }
```

---

## Notes for Apidog
- Add a global header `Authorization: Bearer {{token}}` and a `{{baseUrl}}` variable.
- The photo upload (1.3) is the only `multipart/form-data` request; everything
  else is `application/json` and wraps its payload in a top-level `data` object.
- VEBA endpoints (`/veba/enable`, `/veba/disable`, `/veba/status/{imei}`,
  `/veba/units/{client_uid}`) already existed before this session — document
  separately if not yet in Apidog.
