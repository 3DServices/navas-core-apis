-- 050_waswa_readonly_role.sql — a least-privilege database role for Waswa.
--
-- WHY THIS IS NOT "a read-only role for the API"
-- The API is not read-only. It writes payments, pause rules, subscriptions and
-- the token ledger constantly, so a read-only role for the whole application
-- would break it on the first request. The useful cut is narrower and comes
-- from the code rather than from a guess:
--
--   grep "INSERT INTO|UPDATE|DELETE FROM" endpoints/assistant.py endpoints/waswa_*.py
--
-- Every write the Waswa path performs is to a dll_waswa_* table. It writes to
-- no operational table at all. So Waswa can run with SELECT on the twenty-nine
-- tables and views it reads and write access to nothing except its own nine.
--
-- scripts/waswa_grant_check.py re-derives both lists from the source at run
-- time and fails if they drift from the grants below. As of this writing the
-- two match exactly: nothing granted is unused, nothing used is ungranted.
--
-- WHAT THIS BUYS
-- An attacker with code execution in the Waswa path can read customer records
-- it could already read through its tools, and cannot change, delete or insert
-- anything outside dll_waswa_*. No device can be deleted, no payment altered,
-- no pause rule flipped, no subscription changed.
--
-- WHAT IT DOES NOT BUY
-- Reading is still reading. This is a blast-radius reduction, not a privacy
-- control; the privacy control is Track H, where Waswa holds no credentials at
-- all. Do this first anyway: it is an hour of work and it stands on its own.
--
-- NOT RUN AUTOMATICALLY, AND DELIBERATELY NOT IN database/migrations/.
-- scripts/run_migrations.py globs that directory for ^(\d+)_.+\.sql$ and runs
-- everything it matches. A numbered file there would execute on the next deploy
-- with the placeholder password below still in it. Hence database/manual/ and
-- no numeric prefix: it cannot match the pattern even if it is moved.
--
-- This is a reviewed, deliberate script:
--   1. choose the password yourself and keep it out of git
--   2. run as a superuser against the NAVAS database
--   3. run scripts/waswa_grant_check.py BEFORE pointing any code at the role
--
-- Deliberately NOT included: ALTER DEFAULT PRIVILEGES. A table added next month
-- should need a deliberate grant, not inherit one. If Waswa later reads a new
-- table, waswa_grant_check.py fails and names it, which is the behaviour we
-- want from a privilege list.
--
-- Cassandra is separate. dll_device_basic_data, dll_pulse_status_registry and
-- dll_location_registry_by_record_ts live in Cassandra, which has its own role
-- system; they are absent below on purpose and need their own ticket.

BEGIN;

-- ── 1. The role ─────────────────────────────────────────────────────────────
-- Replace the password before running. NOLOGIN would be safer for a group role,
-- but Waswa connects as this role directly, so it needs LOGIN.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'navas_waswa') THEN
        CREATE ROLE navas_waswa LOGIN PASSWORD 'CHANGE_ME_BEFORE_RUNNING'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE current_database() TO navas_waswa;
GRANT USAGE ON SCHEMA public TO navas_waswa;

-- No table creation. Waswa has no reason to make one, and a role that can
-- create tables in a schema it can read is a role that can stage data there.
REVOKE CREATE ON SCHEMA public FROM navas_waswa;

-- ── 2. Read-only: the operational tables Waswa's tools and context read ─────
-- Enumerated rather than "ALL TABLES", so the list is auditable and a new
-- table is invisible until someone decides otherwise.
GRANT SELECT ON
    abi_products_manager,
    abi_product_aliases,
    abi_product_capabilities,
    abi_product_hardware,
    abi_product_segments,
    dll_access_relay,
    dll_client_accounts,
    dll_device_subscriptions,
    dll_event_notifications,
    dll_pause_rules,
    dll_payment_logs,
    dll_tokens_registry,
    dll_trips_auditor,
    dll_user_token_accounts
TO navas_waswa;

-- ── 3. Read-only: the views ─────────────────────────────────────────────────
-- A plain view runs with its owner's privileges on the base tables, so SELECT
-- on the view is enough.
GRANT SELECT ON
    vw_waswa_corpus,
    vw_waswa_retrievable,
    vw_waswa_review_queue,
    vw_waswa_unassigned_approvals
TO navas_waswa;

-- ── 4. Read and write: the tables Waswa owns ────────────────────────────────
-- Conversations, messages, evidence and the transparency log are written on
-- every turn. Answers, approvals, chunks, sources and feedback are written by
-- the review and ingestion paths.
GRANT SELECT, INSERT, UPDATE ON
    dll_waswa_conversations,
    dll_waswa_messages,
    dll_waswa_evidence,
    dll_waswa_transparency_log,
    dll_waswa_answers,
    dll_waswa_feedback,
    dll_waswa_chunks,
    dll_waswa_sources
TO navas_waswa;

-- Approvals are the one place the code deletes: an approver withdrawing their
-- approval removes the row rather than flagging it.
GRANT SELECT, INSERT, UPDATE, DELETE ON
    dll_waswa_answer_approvals
TO navas_waswa;

-- Read-only reference data for the authority ladder and the prompt.
GRANT SELECT ON
    dll_waswa_authority_levels,
    dll_waswa_prompts,
    dll_waswa_gated_actions
TO navas_waswa;

-- ── 5. Sequences for the tables it inserts into ─────────────────────────────
-- A BIGSERIAL primary key needs USAGE on its sequence, or every INSERT fails
-- with "permission denied for sequence". This is the step that is always
-- forgotten and always looks like a different bug.
DO $$
DECLARE
    seq record;
BEGIN
    FOR seq IN
        SELECT quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS name
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'S'
           AND n.nspname = 'public'
           AND c.relname LIKE 'dll_waswa%'
    LOOP
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO navas_waswa',
                       seq.name);
    END LOOP;
END
$$;

COMMIT;

-- ── Verify, before any code uses it ─────────────────────────────────────────
-- Expect: the first two succeed, the third and fourth are refused.
--
--   SET ROLE navas_waswa;
--   SELECT count(*) FROM dll_trips_auditor;                 -- allowed
--   SELECT count(*) FROM dll_waswa_messages;                -- allowed
--   DELETE FROM dll_device_subscriptions WHERE false;       -- must FAIL
--   UPDATE dll_payment_logs SET payment_status = payment_status WHERE false;
--                                                           -- must FAIL
--   RESET ROLE;
--
-- Then run the full check, which exercises every read the code performs:
--   python scripts/waswa_grant_check.py --role-url "postgresql://navas_waswa:...@host/db"
