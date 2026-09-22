-- Waswa AI — Phase 3: the knowledge corpus
-- Description: the approved documents Waswa may answer from, split into
-- retrievable chunks, each carrying where it came from and how much weight it
-- carries. Phase 1 gave Waswa an account context and product tools; this gives
-- it everything else the company has written down.
--
-- Three decisions worth recording, because each one is a fork we took
-- deliberately and someone will wonder later:
--
-- 1. NO pgvector. `SELECT * FROM pg_available_extensions WHERE name='vector'`
--    returned no rows on this server (PostgreSQL 16.9, Ubuntu 24.10,
--    self-hosted). It could be installed — apt install postgresql-16-pgvector
--    — but at this corpus size it buys nothing: the whole approved corpus is
--    on the order of a couple of thousand chunks, and brute-force cosine over
--    that in numpy costs single-digit milliseconds. So retrieval starts as
--    PostgreSQL full-text search, which needs no extension and is exact on the
--    terms that matter here (product names, document codes, KPI names).
--    The embedding column below is reserved now so that adding semantic search
--    later is a backfill, not a migration.
--
-- 2. De-duplication at TWO levels, because the corpus duplicates at two levels.
--      * file_hash UNIQUE on sources. The document folder holds
--        NAVAS_ECO-SYSTEM_VISION_SCOPE_DOC_v26.03.15.pdf and
--        NAVAS_ECO-SYSTEM_VISION_SCOPE_DOC_v26.03.15 (1).pdf — byte-identical,
--        md5 d73bc6fb…. Ingesting both would double every vision-scope chunk
--        and make retrieval return the same paragraph twice, which reads to a
--        customer as corroboration when it is one document counted twice.
--      * (source_uid, content_hash) UNIQUE on chunks, for the repeated
--        boilerplate inside a single document (headers, the same acceptance
--        criteria restated per user story).
--    Cross-document repetition is NOT blocked — two different approved
--    documents may legitimately say the same sentence — but it is visible in
--    vw_waswa_chunk_echoes so it can be judged rather than assumed.
--
-- 3. Authority is required, never defaulted. A chunk with no authority level
--    cannot be ranked against one that has it, and a silent default of 1 would
--    quietly promote a working draft to the level of approved product data.
--    So authority_level is NOT NULL with no default, and ingestion refuses a
--    source that does not state one.

-- ── The authority ladder ────────────────────────────────────────────────────
-- Level 1 is the highest. Only level 1 is confirmed: migration 032 already
-- encodes it ("Source-priority ladder: 1 = PPMM/approved product data").
-- Levels 2-6 below are this repo's working reading of the master prompt's
-- ladder and are marked confirmed = FALSE until the business signs them off.
-- They are seeded rather than left empty so ingestion can proceed; the view
-- vw_waswa_authority_unconfirmed keeps the gap visible rather than letting it
-- harden into fact by being used.
CREATE TABLE IF NOT EXISTS dll_waswa_authority_levels (
    authority_level SMALLINT PRIMARY KEY CHECK (authority_level BETWEEN 1 AND 6),
    label           VARCHAR(80)  NOT NULL,
    description     TEXT         NOT NULL,
    may_quote       BOOLEAN      NOT NULL DEFAULT TRUE,
    confirmed       BOOLEAN      NOT NULL DEFAULT FALSE,
    source_ref      VARCHAR(200),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

INSERT INTO dll_waswa_authority_levels
    (authority_level, label, description, may_quote, confirmed, source_ref) VALUES
 (1, 'Approved product and rate data',
     'PPMM catalogue, token rate card, approved product attributes. The '
     'highest authority: a figure here outranks any prose that contradicts it.',
     TRUE,  TRUE,  'Migration 032 COMMENT ON abi_products_manager.authority_level'),
 (2, 'Approved company procedure',
     'Signed QMS procedure documents (3DS-QMS-PR-nn) — sales procedure, '
     'commission structure, approval ladders.',
     TRUE,  FALSE, 'Proposed — awaiting confirmation'),
 (3, 'Approved strategy and scope',
     'Ecosystem vision and scope documents, published strategy papers. '
     'Describes intent and direction, not commitments to a customer.',
     TRUE,  FALSE, 'Proposed — awaiting confirmation'),
 (4, 'Specification and user stories',
     'Product user stories, dashboard KPI definitions, functional specs. '
     'Accurate about how a feature is meant to behave; not a promise that it '
     'is built, so answers from here say what is specified, not what is live.',
     TRUE,  FALSE, 'Proposed — awaiting confirmation'),
 (5, 'Internal working material',
     'Drafts, working notes, internal automation strategy. Waswa may use it '
     'to understand a question; it may not quote it to a customer.',
     FALSE, FALSE, 'Proposed — awaiting confirmation'),
 (6, 'Unverified',
     'Ingested but not yet reviewed by anyone. Retrieval excludes level 6 by '
     'default; it exists so a document can be loaded before it is approved.',
     FALSE, FALSE, 'Proposed — awaiting confirmation')
ON CONFLICT (authority_level) DO NOTHING;

-- ── Source documents ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dll_waswa_sources (
    source_uid       VARCHAR(64)  PRIMARY KEY,
    title            VARCHAR(300) NOT NULL,
    filename         VARCHAR(300),
    document_type    VARCHAR(48),              -- procedure|strategy|user_stories|kpi|catalogue|faq
    authority_level  SMALLINT     NOT NULL
        REFERENCES dll_waswa_authority_levels(authority_level),
    version_label    VARCHAR(60),              -- as printed on the document
    document_date    DATE,
    country_scope    VARCHAR(160),             -- NULL = all countries
    customer_class_scope VARCHAR(160),         -- NULL = all classes
    language         VARCHAR(16)  NOT NULL DEFAULT 'en',
    product_uid      VARCHAR(100),             -- NULL = not product-specific
    service_type     VARCHAR(80),
    category         VARCHAR(80),
    file_hash        CHAR(64)     NOT NULL UNIQUE,   -- sha256 of the source file
    chunk_count      INTEGER      NOT NULL DEFAULT 0,
    active           BOOLEAN      NOT NULL DEFAULT TRUE,
    superseded_by    VARCHAR(64)  REFERENCES dll_waswa_sources(source_uid),
    review_status    VARCHAR(20)  NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
    reviewed_by      VARCHAR(100),
    reviewed_at      TIMESTAMP,
    ingested_by      VARCHAR(100),
    ingested_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    notes            TEXT
);
CREATE INDEX IF NOT EXISTS idx_waswa_src_active  ON dll_waswa_sources(active) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_waswa_src_type    ON dll_waswa_sources(document_type);
CREATE INDEX IF NOT EXISTS idx_waswa_src_product ON dll_waswa_sources(product_uid);

COMMENT ON COLUMN dll_waswa_sources.file_hash IS
    'sha256 of the original file. UNIQUE: re-ingesting the same bytes under a '
    'different filename is a no-op, not a second copy of the document.';
COMMENT ON COLUMN dll_waswa_sources.superseded_by IS
    'Set when a newer version of the same document is ingested. The old rows '
    'are kept, not deleted, so an answer given last month can still be traced '
    'to what was approved at the time.';
COMMENT ON COLUMN dll_waswa_sources.review_status IS
    'pending until a human approves the document for customer-facing answers. '
    'Deliberately NOT filtered in vw_waswa_retrievable: on day one nothing is '
    'approved, and a view that returned nothing would look like a broken '
    'index rather than an unreviewed corpus. The endpoint applies it instead, '
    'and says which of the two it is.';

-- ── Chunks ──────────────────────────────────────────────────────────────────
-- Metadata is denormalised from the source onto every chunk on purpose:
-- retrieval filters and ranks on it in the same query that scores the text,
-- and a join per candidate row is the difference between one index scan and a
-- nested loop over the whole corpus.
CREATE TABLE IF NOT EXISTS dll_waswa_chunks (
    chunk_uid        VARCHAR(64)  PRIMARY KEY,
    source_uid       VARCHAR(64)  NOT NULL
        REFERENCES dll_waswa_sources(source_uid) ON DELETE CASCADE,
    ordinal          INTEGER      NOT NULL,       -- position within the source
    heading_path     VARCHAR(500),                -- 'Section > Subsection'
    page_from        INTEGER,
    page_to          INTEGER,
    body             TEXT         NOT NULL,
    char_count       INTEGER      NOT NULL,
    content_hash     CHAR(64)     NOT NULL,

    -- denormalised from dll_waswa_sources
    authority_level  SMALLINT     NOT NULL
        REFERENCES dll_waswa_authority_levels(authority_level),
    document_type    VARCHAR(48),
    country_scope    VARCHAR(160),
    customer_class_scope VARCHAR(160),
    language         VARCHAR(16)  NOT NULL DEFAULT 'en',
    product_uid      VARCHAR(100),
    service_type     VARCHAR(80),
    category         VARCHAR(80),

    -- reserved for Phase 3b; NULL until a backfill fills it
    embedding        REAL[],
    embedding_model  VARCHAR(80),
    embedded_at      TIMESTAMP,

    created_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP    NOT NULL DEFAULT NOW(),

    UNIQUE (source_uid, content_hash),
    UNIQUE (source_uid, ordinal)
);

-- The search vector. 'english'::regconfig is written explicitly because
-- to_tsvector with an unqualified literal is only stable, not immutable, and a
-- generated column requires immutability.
--
-- The corpus is English. Where a Swahili or Luganda document is ingested later
-- its chunks still index under 'english' — stemming will be wrong but the
-- terms that actually get searched here (product names, codes, KPI names) are
-- not stemmed anyway. The language column records the truth so a per-language
-- config can be added without re-chunking.
ALTER TABLE dll_waswa_chunks
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english'::regconfig, coalesce(heading_path, '')), 'A') ||
        setweight(to_tsvector('english'::regconfig, coalesce(body, '')), 'B')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_waswa_chunk_fts     ON dll_waswa_chunks USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_waswa_chunk_source  ON dll_waswa_chunks(source_uid);
CREATE INDEX IF NOT EXISTS idx_waswa_chunk_auth    ON dll_waswa_chunks(authority_level);
CREATE INDEX IF NOT EXISTS idx_waswa_chunk_product ON dll_waswa_chunks(product_uid);
CREATE INDEX IF NOT EXISTS idx_waswa_chunk_echo    ON dll_waswa_chunks(content_hash);
-- Partial index on the rows Phase 3b has to find: the ones not yet embedded.
CREATE INDEX IF NOT EXISTS idx_waswa_chunk_unembedded
    ON dll_waswa_chunks(chunk_uid) WHERE embedding IS NULL;

COMMENT ON COLUMN dll_waswa_chunks.embedding IS
    'Reserved for Phase 3b. REAL[] rather than a pgvector column because the '
    'extension is not available on this server; similarity is computed in '
    'Python. Swapping to vector(n) later is an ALTER, not a re-chunk.';
COMMENT ON COLUMN dll_waswa_chunks.content_hash IS
    'sha256 of the normalised body. Unique per source, so a document that '
    'repeats a paragraph stores it once. Repetition ACROSS sources is allowed '
    'and surfaced in vw_waswa_chunk_echoes.';

-- ── What retrieval is allowed to see ────────────────────────────────────────
-- One definition of "quotable", used by the endpoint rather than restated in
-- Python, so tightening it is a migration and not a code change in four places.
CREATE OR REPLACE VIEW vw_waswa_retrievable AS
SELECT c.*, s.title AS source_title, s.version_label, s.document_date,
       s.review_status, a.label AS authority_label, a.may_quote
FROM dll_waswa_chunks c
JOIN dll_waswa_sources s ON s.source_uid = c.source_uid
JOIN dll_waswa_authority_levels a ON a.authority_level = c.authority_level
WHERE s.active = TRUE
  AND s.superseded_by IS NULL
  AND a.may_quote = TRUE;

-- ── Visible gaps ────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_waswa_authority_unconfirmed AS
SELECT authority_level, label, source_ref
FROM dll_waswa_authority_levels
WHERE confirmed = FALSE
ORDER BY authority_level;

CREATE OR REPLACE VIEW vw_waswa_sources_unreviewed AS
SELECT source_uid, title, document_type, authority_level, chunk_count, ingested_at
FROM dll_waswa_sources
WHERE active = TRUE AND review_status = 'pending'
ORDER BY ingested_at;

-- The same text in two different documents. Not an error — but if one says
-- something a customer relies on, we should know it is one claim, not two.
CREATE OR REPLACE VIEW vw_waswa_chunk_echoes AS
SELECT content_hash,
       COUNT(DISTINCT source_uid) AS sources,
       MIN(LEFT(body, 120))       AS sample
FROM dll_waswa_chunks
GROUP BY content_hash
HAVING COUNT(DISTINCT source_uid) > 1;

CREATE OR REPLACE VIEW vw_waswa_corpus AS
SELECT s.source_uid, s.title, s.document_type, s.authority_level,
       a.label AS authority_label, a.confirmed AS authority_confirmed,
       s.review_status, s.language, s.country_scope, s.product_uid,
       s.chunk_count,
       (SELECT COUNT(*) FROM dll_waswa_chunks c
         WHERE c.source_uid = s.source_uid AND c.embedding IS NOT NULL) AS embedded_chunks,
       s.ingested_at
FROM dll_waswa_sources s
JOIN dll_waswa_authority_levels a ON a.authority_level = s.authority_level
WHERE s.active = TRUE
ORDER BY s.authority_level, s.title;

COMMENT ON VIEW vw_waswa_retrievable IS
    'The only rows retrieval may return. Excludes superseded documents, '
    'deactivated ones, and authority levels marked not quotable.';
COMMENT ON VIEW vw_waswa_chunk_echoes IS
    'Identical text appearing in more than one source document.';
