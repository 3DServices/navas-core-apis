# A2 — Credential rotation runbook

**Status:** not started. **Owner:** Agatha. **Branch:** `waswa-ai`.

Six secrets live in `.env`. Five of them are recoverable from this
repository's git history, so anyone who has ever cloned it — or been given
read access — can use them today. Rotation is the only remedy: rewriting
history does not un-disclose a secret, because every existing clone and fork
keeps the old objects.

Derived by `python scripts/a2_exposure_audit.py`, not from memory. Re-run it
after each step; a rotated secret should move to the "NOT in history" list.

| # | Secret | In history | Consumers | External portal |
|---|--------|-----------|-----------|-----------------|
| 1 | `JWT_SECRET` | yes — `24de1fd`, `1d630f3` | `config.py`, `endpoints/jwt_utils.py`, `scripts/waswa_ask.py` | no |
| 2 | `SANTRIPE_API_KEY` | yes — `24de1fd`, `b177269` | `endpoints/finance.py` | yes |
| 3 | `DISTANCEMATRIX_API_KEY` | yes — `24de1fd`, `f647b23`, `b177269` | `endpoints/data.py` | yes |
| 4 | `CASSANDRA_PASSWORD` | yes — `24de1fd`, `f647b23`, `b177269` | 6 endpoint modules + `config.py` | no |
| 5 | `DATABASE_URL` | yes — `24de1fd`, `1d630f3` | `config.py`, `scripts/run_migrations.py`, `tests/` | no |
| 6 | `OPENROUTER_API_KEY` | **no** | `endpoints/assistant.py` | yes |

`b177269` is titled "secrets out of source" and still contains three of them.
That is not a failure of that commit — removing a secret leaves it on the
removed side of the diff, permanently readable. It is exactly why rotation is
required.

The order below is by blast radius and by independence: each step is
self-contained, so you can stop after any one of them and be better off.

---

## 1. `JWT_SECRET` — do this first

The most serious of the six. With it, anyone can forge a valid access token
for any account. It defeats authentication outright — no password, no network
access to the database. The other five at least require reaching a service.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put the new value in `.env` as `JWT_SECRET`, then restart the API.

- **Breaks:** every live access and refresh token. Every signed-in user and
  device is logged out and must sign in again. Pick a low-traffic window —
  the Oliwa mobile app will show sign-in screens.
- **Verify:** an access token issued before the change returns 401; a fresh
  login returns 200 and a working token.
- **Rollback:** restore the old value and restart. Note this is a rollback for
  an *outage*, not a retreat — the old secret is still disclosed.

## 2. `SANTRIPE_API_KEY` — payment

Rotate in the Santripe dashboard. Most gateways let you create a second key
before revoking the first, which makes this zero-downtime:

1. Create a new key in their dashboard.
2. Put it in `.env`, restart the API.
3. Confirm a payment call succeeds (`endpoints/finance.py`).
4. **Then** revoke the old key.

Do not revoke before step 3. If the new key is wrong, collections fail.

## 3. `DISTANCEMATRIX_API_KEY`

Same create-then-revoke pattern, in the distancematrix.ai dashboard.

This is the key behind `Calculate_DistanceX` — the B8 ticket, 2.2s per call.
Worth noting the earlier B8 hypothesis blamed an unset `GOOGLE_MAPS_API_KEY`;
there is no Google Maps key in this repo at all, and this is the key that
route actually uses.

**Verify:** a trips request returns a non-zero distance.

## 4. `CASSANDRA_PASSWORD`

Six modules read it, all via `config.py`: `data.py`, `data_handler.py`,
`device_configs.py`, `devices.py`, `management.py`, `statistics.py`.

```sql
-- in cqlsh on 165.232.128.208
ALTER ROLE <username> WITH PASSWORD '<new>';
```

Existing Cassandra sessions keep working; only new connections need the new
password. So: change it, update `.env`, restart the API.

- **Verify:** `python scripts/b2_route_check.py` → 5/5 (it reads Cassandra).
- **Watch for:** the ~7s cluster handshake (B9) means the first request after
  a restart may 503. That is B9, not a rotation failure. Retry once.

## 5. `DATABASE_URL` — Postgres, last because it is the most coupled

The current password is 334 characters, user is 12, host/db 30 — one plain
`postgresql://user:pass@host:port/db` with no query string.

**The complication:** the API and the `3d-spartan-bi` BI tool share the
`flareconnect` role. A straight `ALTER ROLE ... PASSWORD` breaks the BI
tool's reconnects, and it holds a pool of ~22 connections.

### Recommended: split the roles (zero downtime, and it unblocks B11)

```sql
-- 1. a dedicated role for the API, with its own password
CREATE ROLE navas_api WITH LOGIN PASSWORD '<new long random>';

-- 2. copy flareconnect's grants (list them first, do not guess)
--    \du+ flareconnect   and   see scripts/waswa_grant_check.py
GRANT ... ;   -- fill from the actual grant list

-- 3. B11 falls out for free: the BI tool gets the big sort memory,
--    nothing else does
ALTER ROLE flareconnect SET work_mem = '2GB';
```

Then point `DATABASE_URL` at `navas_api`, restart the API, confirm, and
rotate `flareconnect`'s password separately for the BI tool alone.

This is worth the extra step: it removes the shared credential, gives B11 its
per-role `work_mem` without a global 10GB, and means neither service's
rotation can take down the other.

### Simpler alternative: rotate in place

```sql
ALTER ROLE flareconnect WITH PASSWORD '<new>';
```

Existing pooled connections survive; reconnects fail until every consumer has
the new value. So you must update `.env` **and** the BI tool's config
promptly. Window = however long that takes.

**Verify either way:** API responds, `b2_route_check.py` 5/5, and the BI tool
still connects.

## 6. `OPENROUTER_API_KEY` — hygiene

Not in git history; it has only ever lived in the gitignored `.env`. Rotate it
on general principle, at your convenience, not as an emergency.

---

## After all six

1. `python scripts/a2_exposure_audit.py` — every secret should now report as
   "NOT in history".
2. The other three repos are connected and **have not been audited**:
   `3d-cms-stable-v1`, `oliwa_v1_release`, `oliwa-mobile`. The Google Maps and
   Mapbox keys mentioned in the pre-commit hook's own header are not in this
   repo, so they are probably in those. Run the same audit there.
3. `.kilo/` is now gitignored. It was never committed, but only because a git
   worktree's `.git` pointer makes git treat it as a nested repo — nothing
   was actually excluding it.

## What this runbook cannot tell you

The audit proves whether a byte sequence is present in this clone's git
objects. It cannot see a secret pasted into a chat, a ticket, a CI log, a
screenshot, or a teammate's shell history. Treat "NOT in history" as "not
exposed *this* way", not as "safe".
