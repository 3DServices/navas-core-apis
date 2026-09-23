-- Waswa AI — Phase 1 foundation
-- Description: the persistence Waswa needs before it is given any knowledge:
-- conversations and messages (so intent, outcomes and analytics have a home),
-- the evidence behind every answer, the offers it makes and how they ended,
-- the AI transparency log (CMS-B-11), and versioned storage for the runtime
-- system prompt so prompt changes are data changes with a history.
--
-- Nothing here makes Waswa smarter. It makes everything after it auditable.

-- ── Versioned runtime prompt ────────────────────────────────────────────────
-- One row per version. Exactly one version per prompt_key may be active.
CREATE TABLE IF NOT EXISTS dll_waswa_prompts (
    id           SERIAL PRIMARY KEY,
    prompt_key   VARCHAR(64)  NOT NULL,          -- 'runtime_system'
    version      INTEGER      NOT NULL,
    body         TEXT         NOT NULL,
    notes        TEXT,
    is_active    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_by   VARCHAR(100),
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (prompt_key, version)
);

-- Only one active version per key, enforced by the database rather than by care.
CREATE UNIQUE INDEX IF NOT EXISTS idx_waswa_prompt_active
    ON dll_waswa_prompts(prompt_key) WHERE is_active = TRUE;

-- ── Conversations ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dll_waswa_conversations (
    conversation_uid  VARCHAR(64)  PRIMARY KEY,
    account_uid       VARCHAR(100) NOT NULL,
    account_root      VARCHAR(100),                       -- tenant scope
    client_uid        VARCHAR(100),
    surface           VARCHAR(20)  NOT NULL DEFAULT 'mobile',  -- mobile|cms|eshop|marketplace|whatsapp|web
    language          VARCHAR(16),
    status            VARCHAR(16)  NOT NULL DEFAULT 'open',    -- open|closed
    started_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    last_activity_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_waswa_conv_account ON dll_waswa_conversations(account_uid);
CREATE INDEX IF NOT EXISTS idx_waswa_conv_tenant  ON dll_waswa_conversations(account_root);
CREATE INDEX IF NOT EXISTS idx_waswa_conv_active  ON dll_waswa_conversations(last_activity_at);

-- ── Messages ────────────────────────────────────────────────────────────────
-- intent / router_tier / blocked_reason are filled by later phases; they exist
-- now so no phase has to migrate live conversation data to add them.
CREATE TABLE IF NOT EXISTS dll_waswa_messages (
    id                BIGSERIAL PRIMARY KEY,
    message_uid       VARCHAR(64)  NOT NULL UNIQUE,
    conversation_uid  VARCHAR(64)  NOT NULL
        REFERENCES dll_waswa_conversations(conversation_uid) ON DELETE CASCADE,
    turn_index        INTEGER      NOT NULL,
    role              VARCHAR(16)  NOT NULL,      -- user | assistant
    content           TEXT         NOT NULL,
    intent            VARCHAR(48),                -- Phase 4
    intent_confidence NUMERIC(4,3),
    router_tier       SMALLINT,                   -- 1 rules | 2 local SLM | 3 external
    model             VARCHAR(100),
    prompt_version    INTEGER,
    blocked_reason    VARCHAR(64),                -- guardrail / validator refusal
    latency_ms        INTEGER,
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_waswa_msg_conv    ON dll_waswa_messages(conversation_uid);
CREATE INDEX IF NOT EXISTS idx_waswa_msg_intent  ON dll_waswa_messages(intent);
CREATE INDEX IF NOT EXISTS idx_waswa_msg_created ON dll_waswa_messages(created_at);

-- ── Evidence behind each answer ─────────────────────────────────────────────
-- What the answer was built from: a tool result, a retrieved document chunk,
-- or the account context. The fabrication validator (Phase 4) checks the draft
-- answer against these rows.
CREATE TABLE IF NOT EXISTS dll_waswa_evidence (
    id               BIGSERIAL PRIMARY KEY,
    message_uid      VARCHAR(64)  NOT NULL,
    source_kind      VARCHAR(32)  NOT NULL,   -- tool | document | account_context
    source_ref       VARCHAR(256) NOT NULL,   -- tool name, document id, 'account_context'
    authority_level  SMALLINT,                -- 1..6, per the master prompt's ladder
    detail           JSONB,
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_waswa_evidence_msg ON dll_waswa_evidence(message_uid);

-- ── Offers and their outcome ────────────────────────────────────────────────
-- Phase 6 reads this to honour two rules that are otherwise unimplementable:
-- one opportunity per response, and a declined offer stays closed.
CREATE TABLE IF NOT EXISTS dll_waswa_offers (
    id                BIGSERIAL PRIMARY KEY,
    offer_uid         VARCHAR(64)  NOT NULL UNIQUE,
    conversation_uid  VARCHAR(64)  NOT NULL,
    message_uid       VARCHAR(64),
    account_uid       VARCHAR(100) NOT NULL,
    client_uid        VARCHAR(100),
    motion            VARCHAR(16)  NOT NULL,   -- upsell|cross_sell|deep_sell|repeat_sell
    product_uid       VARCHAR(100),
    trigger_evidence  TEXT         NOT NULL,   -- why this was raised, in words
    outcome           VARCHAR(16)  NOT NULL DEFAULT 'raised',  -- raised|accepted|deferred|declined
    outcome_at        TIMESTAMP,
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_waswa_offers_conv    ON dll_waswa_offers(conversation_uid);
CREATE INDEX IF NOT EXISTS idx_waswa_offers_client  ON dll_waswa_offers(client_uid);
CREATE INDEX IF NOT EXISTS idx_waswa_offers_outcome ON dll_waswa_offers(outcome);

-- ── AI transparency log (CMS-B-11) ──────────────────────────────────────────
-- Every suggestion, confidence note, approval, override and blocked action,
-- retrievable per tenant, per user, per action.
CREATE TABLE IF NOT EXISTS dll_waswa_transparency_log (
    id                    BIGSERIAL PRIMARY KEY,
    entry_uid             VARCHAR(64)  NOT NULL UNIQUE,
    account_uid           VARCHAR(100),
    account_root          VARCHAR(100),
    client_uid            VARCHAR(100),
    conversation_uid      VARCHAR(64),
    message_uid           VARCHAR(64),
    entry_type            VARCHAR(32)  NOT NULL,   -- suggestion|confidence_note|gated_proposal|approval|override|blocked_action
    action                VARCHAR(64),
    rationale             TEXT,
    approver_account_uid  VARCHAR(100),
    approved_at           TIMESTAMP,
    detail                JSONB,
    created_at            TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_waswa_log_tenant  ON dll_waswa_transparency_log(account_root);
CREATE INDEX IF NOT EXISTS idx_waswa_log_account ON dll_waswa_transparency_log(account_uid);
CREATE INDEX IF NOT EXISTS idx_waswa_log_type    ON dll_waswa_transparency_log(entry_type);
CREATE INDEX IF NOT EXISTS idx_waswa_log_created ON dll_waswa_transparency_log(created_at);

-- ── Seed: v1 of the runtime prompt ──────────────────────────────────────────
-- This is the prompt that has been hard-coded in endpoints/assistant.py, moved
-- into the table unchanged, so deploying Phase 1 does not change what Waswa
-- says. The master prompt's Part B goes in as v2 through the admin loader,
-- once the context service has been verified against real accounts.
INSERT INTO dll_waswa_prompts (prompt_key, version, body, notes, is_active, created_by)
SELECT 'runtime_system', 1,
'You are Waswa, the in-app assistant for OLIWA — a smart fleet-tracking service (powered by the NAVAS IoT engine) used mainly in East Africa. You help users understand vehicle tracking, token billing, alerts, and reports.

Key facts about OLIWA:
- Tracking is paid for with prepaid TOKENS. Tokens are billed per event / per hour depending on the token package.
- Users buy tokens via mobile money (MTN, Airtel, etc.).
- Domains include GPS tracking, fuel monitoring, driver behaviour, and compliance.

Rules:
- Be concise, friendly, and practical. Prefer short answers.
- Only use figures (token balances, vehicle counts, etc.) that are given to you in the ''Live account context''. NEVER invent numbers, prices, or account details. If you don''t have a figure, say so and tell the user where to find it in the app.
- You cannot perform actions yourself (you cannot buy tokens, pause tracking, or generate reports). Guide the user to the relevant screen instead, and never ask for PINs, passwords, or full payment details.
- Stay on OLIWA / fleet-tracking topics. Politely decline unrelated requests.',
       'Migrated verbatim from the assistant.py constant. Behaviour-preserving.',
       TRUE, 'migration_030'
WHERE NOT EXISTS (
    SELECT 1 FROM dll_waswa_prompts WHERE prompt_key = 'runtime_system' AND version = 1
);

COMMENT ON TABLE dll_waswa_prompts IS
    'Versioned Waswa runtime system prompts; one active version per prompt_key.';
COMMENT ON TABLE dll_waswa_conversations IS
    'Waswa conversations, scoped to an account and its tenant.';
COMMENT ON TABLE dll_waswa_messages IS
    'Every Waswa turn, with detected intent, router tier and guardrail outcome.';
COMMENT ON TABLE dll_waswa_evidence IS
    'What each Waswa answer was built from — the basis of the no-fabrication check.';
COMMENT ON TABLE dll_waswa_offers IS
    'Sales opportunities Waswa raised and how they ended; enforces the declined-offer rule.';
COMMENT ON TABLE dll_waswa_transparency_log IS
    'AI transparency log (CMS-B-11): suggestions, approvals, overrides, blocked actions.';
