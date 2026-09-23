-- Waswa AI — the training loop (Portal Phase A)
-- Description: what an administrator or product manager needs in order to
-- correct Waswa without a developer.
--
--   dll_waswa_feedback          a person says an answer was wrong, unhelpful
--                               or good. The review queue is built from this.
--   dll_waswa_answers           corrections: a question and the answer staff
--                               want given, with a lifecycle
--                               draft -> pending -> approved -> retired.
--                               Checked before the documents on every turn.
--   dll_waswa_answer_approvals  who approved or rejected which correction.
--                               Nobody approves their own; the database
--                               refuses it, not just the endpoint.
--
-- And one change to what already exists:
--
--   dll_waswa_sources.audience  'staff' or 'everyone'. Every document loaded
--                               so far is internal — sales procedures,
--                               strategy papers, the CMS manual — and until
--                               now a fleet customer on OLIWA mobile could
--                               retrieve them. Existing rows become 'staff'.
--                               A document is shown to customers only after
--                               someone marks it 'everyone'.
--
-- Training here means curating what Waswa may read. The model is never
-- retrained, so every answer can be traced to a named author, a named approver
-- and a date, and undone.
--
-- Re-runnable: every object is IF NOT EXISTS or CREATE OR REPLACE, and the
-- seeds do nothing on conflict.

-- ── 1. Audience on documents ───────────────────────────────────────────────
ALTER TABLE dll_waswa_sources
    ADD COLUMN IF NOT EXISTS audience VARCHAR(16) NOT NULL DEFAULT 'staff';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'chk_waswa_src_audience') THEN
        ALTER TABLE dll_waswa_sources ADD CONSTRAINT chk_waswa_src_audience
            CHECK (audience IN ('staff', 'everyone'));
    END IF;
END
$$;

COMMENT ON COLUMN dll_waswa_sources.audience IS
    'staff = only people holding waswa.staff_knowledge (or an admin role) '
    'can retrieve it. everyone = customers too. Defaults to staff: a document '
    'reaches customers because someone decided it should, never by default.';

-- Appending a column is the one change CREATE OR REPLACE VIEW allows, so
-- audience goes last and everything before it is exactly as migration 035
-- wrote it.
CREATE OR REPLACE VIEW vw_waswa_retrievable AS
SELECT c.*, s.title AS source_title, s.version_label, s.document_date,
       s.review_status, a.label AS authority_label, a.may_quote,
       s.audience
FROM dll_waswa_chunks c
JOIN dll_waswa_sources s ON s.source_uid = c.source_uid
JOIN dll_waswa_authority_levels a ON a.authority_level = c.authority_level
WHERE s.active = TRUE
  AND s.superseded_by IS NULL
  AND a.may_quote = TRUE;

-- ── 2. Feedback ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dll_waswa_feedback (
    id                BIGSERIAL    PRIMARY KEY,
    feedback_uid      VARCHAR(64)  NOT NULL UNIQUE,
    message_uid       VARCHAR(64)  NOT NULL,       -- the assistant turn judged
    conversation_uid  VARCHAR(64)  NOT NULL,
    account_uid       VARCHAR(100) NOT NULL,       -- who gave the feedback
    surface           VARCHAR(20),
    verdict           VARCHAR(16)  NOT NULL
        CHECK (verdict IN ('wrong', 'unhelpful', 'good')),
    note              TEXT,
    status            VARCHAR(16)  NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_review', 'resolved', 'dismissed')),
    resolution        VARCHAR(20)
        CHECK (resolution IS NULL OR resolution IN
               ('correction', 'document', 'data_fix', 'dismissed')),
    resolution_note   TEXT,
    answer_uid        VARCHAR(64),                 -- the correction it led to
    assigned_to       VARCHAR(100),
    resolved_by       VARCHAR(100),
    resolved_at       TIMESTAMP,
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    -- One verdict per person per answer. Changing your mind updates the row;
    -- it does not add a second vote.
    UNIQUE (message_uid, account_uid)
);
CREATE INDEX IF NOT EXISTS idx_waswa_fb_status  ON dll_waswa_feedback(status);
CREATE INDEX IF NOT EXISTS idx_waswa_fb_message ON dll_waswa_feedback(message_uid);
CREATE INDEX IF NOT EXISTS idx_waswa_fb_created ON dll_waswa_feedback(created_at);

-- 'good' needs no review, so it is born resolved and never reaches the queue.
COMMENT ON TABLE dll_waswa_feedback IS
    'Verdicts on Waswa answers. wrong and unhelpful open a review item; good '
    'is recorded for the numbers only.';

-- ── 3. Corrections ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dll_waswa_answers (
    id                    BIGSERIAL    PRIMARY KEY,
    answer_uid            VARCHAR(64)  NOT NULL UNIQUE,
    question              TEXT         NOT NULL,
    -- Other ways people ask the same thing, one per line. Plain text rather
    -- than TEXT[] because the search vector below is a generated column and
    -- array_to_string is not immutable.
    question_variants     TEXT,
    answer                TEXT         NOT NULL,
    audience              VARCHAR(16)  NOT NULL DEFAULT 'staff'
        CHECK (audience IN ('staff', 'everyone')),
    country_scope         VARCHAR(60),             -- NULL = all countries
    product_uid           VARCHAR(100),            -- NULL = not product-specific
    -- routine: one approver. policy: two. The endpoint raises routine to
    -- policy when the text is about money, approvals or account actions, and
    -- nobody can lower it again.
    sensitivity           VARCHAR(16)  NOT NULL DEFAULT 'routine'
        CHECK (sensitivity IN ('routine', 'policy')),
    approvals_required    SMALLINT     NOT NULL DEFAULT 1
        CHECK (approvals_required BETWEEN 1 AND 3),
    status                VARCHAR(16)  NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'pending', 'approved', 'rejected', 'retired')),
    version               INTEGER      NOT NULL DEFAULT 1,
    supersedes_answer_uid VARCHAR(64),             -- the approved answer this revises
    source_feedback_uid   VARCHAR(64),             -- the flag that prompted it
    source_message_uid    VARCHAR(64),             -- the answer it corrects
    based_on_source_uid   VARCHAR(64),             -- a document it relies on
    based_on_note         TEXT,                    -- e.g. 'Sales Procedures §26.6'
    authored_by           VARCHAR(100) NOT NULL,
    submitted_at          TIMESTAMP,
    approved_at           TIMESTAMP,
    retired_at            TIMESTAMP,
    retired_by            VARCHAR(100),
    retired_reason        TEXT,
    review_due            DATE,
    needs_recheck         BOOLEAN      NOT NULL DEFAULT FALSE,
    recheck_reason        TEXT,
    -- Times this correction was matched to a question and offered to the
    -- model. Matched, not "used": whether the model relied on it is in the
    -- evidence trail for that turn.
    match_count           INTEGER      NOT NULL DEFAULT 0,
    last_matched_at       TIMESTAMP,
    created_at            TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMP    NOT NULL DEFAULT NOW()
);

ALTER TABLE dll_waswa_answers
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english'::regconfig, coalesce(question, '')), 'A') ||
        setweight(to_tsvector('english'::regconfig, coalesce(question_variants, '')), 'A') ||
        setweight(to_tsvector('english'::regconfig, coalesce(answer, '')), 'C')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_waswa_ans_fts    ON dll_waswa_answers USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_waswa_ans_status ON dll_waswa_answers(status);
CREATE INDEX IF NOT EXISTS idx_waswa_ans_based  ON dll_waswa_answers(based_on_source_uid);
CREATE INDEX IF NOT EXISTS idx_waswa_ans_due    ON dll_waswa_answers(review_due)
    WHERE status = 'approved';

COMMENT ON TABLE dll_waswa_answers IS
    'Corrections written by staff. An approved, unretired row is checked '
    'before the document corpus on every turn and is labelled to the user as '
    'a verified answer. Editing an approved row creates a new version that '
    'retires it on approval, so what was said last month stays traceable.';
COMMENT ON COLUMN dll_waswa_answers.search_vector IS
    'Question and variants weigh A, the answer C: a correction should be '
    'found by what people ask, not by words that happen to be in the reply.';

-- ── 4. Approvals ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dll_waswa_answer_approvals (
    id                    BIGSERIAL    PRIMARY KEY,
    answer_uid            VARCHAR(64)  NOT NULL
        REFERENCES dll_waswa_answers(answer_uid) ON DELETE CASCADE,
    approver_account_uid  VARCHAR(100) NOT NULL,
    decision              VARCHAR(10)  NOT NULL
        CHECK (decision IN ('approve', 'reject')),
    note                  TEXT,
    created_at            TIMESTAMP    NOT NULL DEFAULT NOW(),
    -- Two approvals from one person are one approval.
    UNIQUE (answer_uid, approver_account_uid)
);
CREATE INDEX IF NOT EXISTS idx_waswa_appr_answer ON dll_waswa_answer_approvals(answer_uid);

-- The rule that matters most, held where a bug in an endpoint cannot skip it.
CREATE OR REPLACE FUNCTION waswa_no_self_approval() RETURNS trigger AS $$
DECLARE
    author VARCHAR(100);
BEGIN
    SELECT authored_by INTO author FROM dll_waswa_answers
     WHERE answer_uid = NEW.answer_uid;
    IF author IS NOT NULL AND author = NEW.approver_account_uid THEN
        RAISE EXCEPTION 'The author of a correction cannot approve it'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_waswa_no_self_approval ON dll_waswa_answer_approvals;
CREATE TRIGGER trg_waswa_no_self_approval
    BEFORE INSERT OR UPDATE ON dll_waswa_answer_approvals
    FOR EACH ROW EXECUTE FUNCTION waswa_no_self_approval();

-- ── 5. A changed document flags the corrections that lean on it ───────────
CREATE OR REPLACE FUNCTION waswa_flag_dependent_answers() RETURNS trigger AS $$
DECLARE
    why TEXT;
BEGIN
    IF NEW.superseded_by IS NOT NULL AND OLD.superseded_by IS NULL THEN
        why := 'The document it relies on was replaced by a newer version';
    ELSIF NEW.active = FALSE AND OLD.active = TRUE THEN
        why := 'The document it relies on was withdrawn';
    ELSIF OLD.review_status = 'approved' AND NEW.review_status <> 'approved' THEN
        why := 'The document it relies on is no longer approved';
    END IF;

    IF why IS NOT NULL THEN
        UPDATE dll_waswa_answers
           SET needs_recheck = TRUE, recheck_reason = why, updated_at = NOW()
         WHERE based_on_source_uid = NEW.source_uid
           AND status = 'approved';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_waswa_flag_dependents ON dll_waswa_sources;
CREATE TRIGGER trg_waswa_flag_dependents
    AFTER UPDATE OF superseded_by, active, review_status ON dll_waswa_sources
    FOR EACH ROW EXECUTE FUNCTION waswa_flag_dependent_answers();

-- ── 6. The review queue ────────────────────────────────────────────────────
-- One list for the console and the CMS triage badge. item_kind says what kind
-- of work each row is; item_uid is the row to act on.
CREATE OR REPLACE VIEW vw_waswa_review_queue AS
SELECT 'flag'::text                     AS item_kind,
       f.feedback_uid                   AS item_uid,
       f.verdict                        AS badge,
       (SELECT u.content FROM dll_waswa_messages u
         WHERE u.conversation_uid = m.conversation_uid
           AND u.role = 'user' AND u.turn_index < m.turn_index
         ORDER BY u.turn_index DESC LIMIT 1) AS title,
       m.content                        AS detail,
       f.note                           AS note,
       f.surface                        AS surface,
       f.status                         AS status,
       f.created_at                     AS raised_at,
       f.message_uid                    AS message_uid,
       f.conversation_uid               AS conversation_uid
FROM dll_waswa_feedback f
LEFT JOIN dll_waswa_messages m ON m.message_uid = f.message_uid
WHERE f.status IN ('open', 'in_review')

UNION ALL
SELECT 'approval', a.answer_uid,
       a.sensitivity || ' ' ||
         (SELECT COUNT(*) FROM dll_waswa_answer_approvals p
           WHERE p.answer_uid = a.answer_uid AND p.decision = 'approve')
         || '/' || a.approvals_required,
       a.question, a.answer, NULL, NULL, a.status,
       COALESCE(a.submitted_at, a.created_at), a.source_message_uid, NULL
FROM dll_waswa_answers a
WHERE a.status = 'pending'

UNION ALL
SELECT 'recheck', a.answer_uid,
       CASE WHEN a.needs_recheck THEN 'source changed' ELSE 'review due' END,
       a.question, a.answer,
       COALESCE(a.recheck_reason, 'Review date ' || a.review_due::text || ' has passed'),
       NULL, a.status, COALESCE(a.review_due::timestamp, a.updated_at),
       a.source_message_uid, NULL
FROM dll_waswa_answers a
WHERE a.status = 'approved'
  AND (a.needs_recheck OR (a.review_due IS NOT NULL AND a.review_due <= CURRENT_DATE))

UNION ALL
SELECT 'document', s.source_uid, 'document review',
       s.title, s.document_type, s.notes, NULL, s.review_status,
       s.ingested_at, NULL, NULL
FROM dll_waswa_sources s
WHERE s.active = TRUE AND s.review_status = 'pending';

COMMENT ON VIEW vw_waswa_review_queue IS
    'Everything waiting on a person: flagged answers, corrections awaiting '
    'approval, corrections due for review or whose document changed, and '
    'documents awaiting review.';

-- ── 7. Permissions ─────────────────────────────────────────────────────────
-- Three, so the people who read internal knowledge, the people who write
-- corrections and the people who sign them off can be different people.
--
--   waswa.staff_knowledge  Waswa may answer this person from staff-only
--                          documents and corrections.
--   waswa.review           see the queue and conversations, write corrections,
--                          resolve flags.
--   waswa.approve          approve or reject corrections and documents.
--
-- dll_permissions is not defined in this repository's migrations, so its
-- columns are checked before inserting. If it needs a column this does not
-- know about, the seed is skipped with a NOTICE and the three names are added
-- through the RBAC screen instead. Nothing is granted to any role here:
-- deciding who is an approver is the business's call, not a migration's.
DO $$
DECLARE
    unknown_required text;
    has_description  boolean;
    perm             record;
BEGIN
    IF to_regclass('dll_permissions') IS NULL THEN
        RAISE NOTICE 'dll_permissions does not exist; permissions not seeded';
        RETURN;
    END IF;

    SELECT string_agg(column_name, ', ') INTO unknown_required
    FROM information_schema.columns
    WHERE table_name = 'dll_permissions'
      AND table_schema = current_schema()
      AND is_nullable = 'NO'
      AND column_default IS NULL
      AND column_name NOT IN ('permission_uid', 'permission_name');

    IF unknown_required IS NOT NULL THEN
        RAISE NOTICE 'dll_permissions requires % which this migration cannot '
                     'fill; add waswa.staff_knowledge, waswa.review and '
                     'waswa.approve through the RBAC screen', unknown_required;
        RETURN;
    END IF;

    SELECT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'dll_permissions'
                     AND column_name = 'description') INTO has_description;

    FOR perm IN
        SELECT * FROM (VALUES
          ('waswa.staff_knowledge',
           'Waswa may answer from staff-only documents and corrections'),
          ('waswa.review',
           'See Waswa conversations and the review queue; write corrections'),
          ('waswa.approve',
           'Approve or reject Waswa corrections and documents')
        ) AS v(name, description)
    LOOP
        IF EXISTS (SELECT 1 FROM dll_permissions
                   WHERE permission_name = perm.name) THEN
            CONTINUE;
        END IF;
        IF has_description THEN
            EXECUTE 'INSERT INTO dll_permissions (permission_uid, permission_name, description) '
                    'VALUES ($1, $2, $3)'
            USING 'perm-' || replace(perm.name, '.', '-'), perm.name, perm.description;
        ELSE
            EXECUTE 'INSERT INTO dll_permissions (permission_uid, permission_name) '
                    'VALUES ($1, $2)'
            USING 'perm-' || replace(perm.name, '.', '-'), perm.name;
        END IF;
        RAISE NOTICE 'added permission %', perm.name;
    END LOOP;
END
$$;
