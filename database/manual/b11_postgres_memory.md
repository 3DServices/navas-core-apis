# B11 — Postgres memory and connection limits

**Status:** not started. **Owner:** Agatha. **Host:** `165.232.128.208`.

Two settings on the production Postgres are set to values that cannot be
honoured by the machine they run on. Neither is a code change; both are done
in `psql` as a superuser.

Every number below was measured, not recalled — by
`scripts/b11_workmem_audit.py`, `scripts/b11_probe2.py` and
`scripts/pg_connect_cost.py`. Re-run `pg_connect_cost.py` after the change to
confirm the server's own view.

---

## The finding

| Setting | Current | Where |
|---|---|---|
| `work_mem` | **10GB** | `/etc/postgresql/16/main/postgresql.conf:144` |
| `max_connections` | **50000** | same file |
| `shared_buffers` | 3GB | same file |
| Machine RAM | **31.3 GB** | |
| Backends open (08-10-2026) | **53** | `pg_stat_activity` |

**`work_mem` is granted per sort or hash node, not per connection and not per
server.** One query with two sorts may claim 20 GB — 64% of the machine. The
53 backends currently open, at two nodes each, are a notional claim of
**1,000 GB on a 31.3 GB box**.

`vm.overcommit_memory = 0`, so Linux grants those requests on paper and the
OOM killer takes a backend later. From the API that appears as
`server closed the connection unexpectedly` — which is the symptom this
ticket exists to remove.

`postgresql.conf` carries only the stock comments on both lines, so there is
no record of why 10GB was chosen. Treat it as a mistake, not a decision.

### Why 64 MB

Measured sort cost on this data: **~74 bytes per row**, linear.

| Rows sorted | Memory |
|---|---|
| 100,000 | 7.1 MB |
| 500,000 | 35.7 MB |

64 MB therefore holds about **907,000 rows** in memory. Beyond that a sort
spills to disk, which is **slower, not broken** — and far better than an
OOM-killed backend, which loses the whole query and the connection with it.

---

## Step 1 — `work_mem` → 64MB (no restart, reversible in seconds)

`work_mem` is a `SIGHUP` setting, so a reload is enough. `ALTER SYSTEM`
writes `postgresql.auto.conf`, which takes precedence over
`postgresql.conf` — so the 10GB line is left in place and simply overridden,
and the change is undone by one statement rather than by editing a file back.

```sql
-- before
SHOW work_mem;
SELECT count(*) FROM pg_stat_activity;

ALTER SYSTEM SET work_mem = '64MB';
SELECT pg_reload_conf();

-- after: must print 64MB
SHOW work_mem;
```

Existing sessions pick this up on their next statement; nothing is
disconnected.

**Rollback**, if anything looks wrong:

```sql
ALTER SYSTEM RESET work_mem;
SELECT pg_reload_conf();
```

---

## Step 2 — give the heavy reports their own allowance

Lowering the global value should not punish the one workload that genuinely
needs a large sort. Set it on the role that runs reports, so that memory is
reserved for it and nothing else can claim it:

```sql
-- substitute the actual reporting/BI role
ALTER ROLE bi_reports SET work_mem = '512MB';
```

A per-role setting applies to that role's sessions only, and takes effect on
their next connection.

**Rollback:** `ALTER ROLE bi_reports RESET work_mem;`

---

## Step 3 — `max_connections` → 200 (needs a restart; pick a window)

This one is `postmaster`-level: it takes a **full restart**, which drops every
connection. Do it in a maintenance window, not alongside step 1.

Sizing: Gunicorn workers × connections held per worker, plus headroom for
reports, migrations and your own `psql`. The application currently opens **2
Postgres connections per request** (see
`claude/trips-history-latency-finding.md`), and 53 backends is the observed
steady state. 200 is roughly 4× headroom over today.

**Before changing it, confirm nothing needs more:**

```sql
-- the high-water mark, if your Postgres has been up long enough to be useful
SELECT count(*) AS now_open,
       (SELECT setting FROM pg_settings WHERE name = 'max_connections') AS limit_now
FROM pg_stat_activity;

-- who is actually holding connections
SELECT usename, application_name, state, count(*)
FROM pg_stat_activity
GROUP BY 1, 2, 3
ORDER BY 4 DESC;
```

If any pooler (pgbouncer) or client is **configured** for a pool larger than
200, fix that first — it will fail to open connections after the restart.

```sql
ALTER SYSTEM SET max_connections = 200;
```

```bash
sudo systemctl restart postgresql
```

Lowering this value *reduces* the shared memory Postgres must allocate, so
unlike raising it, the restart cannot fail for lack of shared memory.

**Rollback:** `ALTER SYSTEM RESET max_connections;` then restart again.

---

## Verifying it worked

**Immediately** — the settings are what you asked for:

```sql
SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN ('work_mem', 'max_connections', 'shared_buffers');
```

`source` should read `configuration file` for the ones you set via
`ALTER SYSTEM` (it reports the auto.conf as a configuration file).

**Over the following days** — the two things that should change:

1. **No more `server closed the connection unexpectedly`** in the API logs.
   That error was the OOM killer taking a backend; it should stop.
2. **Sorts spilling to disk is expected and fine.** Watch the volume, not the
   fact:

```sql
SELECT datname, temp_files, temp_bytes
FROM pg_stat_database
WHERE datname = current_database();
```

Record those two numbers before the change. Afterwards they will rise — that
is the intended trade. They are only a problem if a report becomes
unacceptably slow, and the fix for that is step 2's per-role allowance, not
reverting step 1.

To see a specific query's behaviour:

```sql
EXPLAIN (ANALYZE, BUFFERS) <the heaviest report query>;
-- look for:  Sort Method: external merge  Disk: NNNNkB
```

---

## What this does NOT change

- **`vm.overcommit_memory = 0`** is left alone. Setting it to 2 would make
  Linux refuse oversized allocations instead of granting them and killing a
  process later, which is arguably more honest — but it is a host-wide change
  affecting every service on the box, and it deserves its own decision rather
  than being bundled here.
- **The application's 2 connections per request.** That is a code fact and is
  tracked separately; it is not a reason to keep `max_connections` high.

---

## While you are in `psql`

`database/manual/waswa_readonly_role.sql` (ticket A1b) is the natural
companion — it creates the read-only role Waswa should be using instead of
the application's own credentials. Running it in the same session saves a
round trip, but it is a separate change with its own verification; do not
let it ride on B11's rollback.
