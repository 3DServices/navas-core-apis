-- Waswa AI — documents managed from the AI Console
-- Description: lets a product manager, CEO or administrator upload a new
-- document, upload a new version of an existing one, and remove one, from the
-- CMS rather than a developer's command line.
--
-- The lifecycle a document now follows:
--
--   upload            lands 'pending', not searchable. Currency amounts are
--                     withheld before anything is stored.
--   approve           becomes searchable. If it was uploaded as a new version
--                     of another document, THAT document is superseded at this
--                     moment — not at upload — so Waswa keeps answering from
--                     the old version until someone signs off the new one.
--   remove            active = FALSE: Waswa stops using it at once. Nothing is
--                     deleted; the rows stay so any past answer can still be
--                     traced to what it was read from. Can be restored.
--
-- Corrections that rely on a document are flagged for recheck whenever it is
-- superseded, removed or unapproved (trigger from migration 041).

ALTER TABLE dll_waswa_sources ADD COLUMN IF NOT EXISTS replaces_source_uid VARCHAR(64);
ALTER TABLE dll_waswa_sources ADD COLUMN IF NOT EXISTS original_filename   VARCHAR(300);
ALTER TABLE dll_waswa_sources ADD COLUMN IF NOT EXISTS stored_path         VARCHAR(500);
ALTER TABLE dll_waswa_sources ADD COLUMN IF NOT EXISTS redactions          INTEGER NOT NULL DEFAULT 0;
ALTER TABLE dll_waswa_sources ADD COLUMN IF NOT EXISTS removed_by          VARCHAR(100);
ALTER TABLE dll_waswa_sources ADD COLUMN IF NOT EXISTS removed_at          TIMESTAMP;
ALTER TABLE dll_waswa_sources ADD COLUMN IF NOT EXISTS removed_reason      TEXT;

COMMENT ON COLUMN dll_waswa_sources.replaces_source_uid IS
    'Set when this document was uploaded as a new version of another. On '
    'approval the other document is marked superseded_by this one.';
COMMENT ON COLUMN dll_waswa_sources.stored_path IS
    'Where the uploaded original and its converted text were saved, relative '
    'to the API working directory, so a reviewer can read exactly what was '
    'ingested.';
COMMENT ON COLUMN dll_waswa_sources.redactions IS
    'Currency amounts withheld at upload. Waswa never states prices.';

CREATE INDEX IF NOT EXISTS idx_waswa_src_replaces ON dll_waswa_sources(replaces_source_uid);

-- The queue's document rows now say whether the upload is new or a version.
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
SELECT 'document', s.source_uid,
       CASE WHEN s.replaces_source_uid IS NOT NULL THEN 'new version'
            ELSE 'new document' END,
       s.title,
       CASE WHEN s.replaces_source_uid IS NOT NULL
            THEN 'Replaces: ' || COALESCE((SELECT o.title FROM dll_waswa_sources o
                                           WHERE o.source_uid = s.replaces_source_uid), '?')
            ELSE s.document_type END,
       s.notes, NULL, s.review_status,
       s.ingested_at, NULL, NULL
FROM dll_waswa_sources s
WHERE s.active = TRUE AND s.review_status = 'pending';
