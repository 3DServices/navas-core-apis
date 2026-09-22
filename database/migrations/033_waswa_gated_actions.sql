-- Waswa AI — gated actions and their approvers
-- Description: the approval ladder Waswa must route proposals through, as data
-- rather than as a rule in someone's head.
--
-- Sources, recorded per row:
--   SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6  — the four approval levels
--   SALES PROCEDURES 3DS-QMS-PR-09 ver26 §30.4  — PFI workflow routing
--   Waswa master prompt v2.0 §B2.4               — actions needing a human
--
-- Two deliberate gaps are encoded as NULL rather than guessed:
--
--   1. threshold_value on the discount rows. The Sales Procedures document says
--      "up to approved threshold" and "above threshold" throughout and never
--      states the number. The nearest figures in it are KPIs (discount usage
--      <10% of deals; an early-warning flag at >10% without approval) — how
--      often you discount is not a mandate limit on how much, so neither is
--      used here. Until the business states it, Waswa treats any discount as
--      above threshold and routes to the CEO level.
--
--   2. approver_role on the §B2.4 actions. The master prompt lists what needs a
--      human; nothing approved names who. Those rows carry a NULL approver and
--      appear in vw_waswa_unassigned_approvals until someone fills them in.
--
-- country_scope is NULL on every row: §26.6 names roles, not countries, and
-- Uganda and Kenya may differ. A country-specific row can be added later
-- without changing this one.

CREATE TABLE IF NOT EXISTS dll_waswa_gated_actions (
    id              SERIAL PRIMARY KEY,
    action_key      VARCHAR(64)  NOT NULL UNIQUE,
    description     TEXT         NOT NULL,
    approval_level  SMALLINT,               -- 0 automated .. 3 CEO; NULL = unassigned
    approver_role   VARCHAR(80),            -- NULL = nobody named yet
    country_scope   VARCHAR(60),            -- NULL = all countries
    threshold_kind  VARCHAR(32),            -- e.g. discount_percent
    threshold_value NUMERIC,                -- NULL = not stated by the business
    threshold_note  TEXT,
    waswa_may_act   BOOLEAN      NOT NULL DEFAULT FALSE,
    source_ref      VARCHAR(200) NOT NULL,
    active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_waswa_gated_level ON dll_waswa_gated_actions(approval_level);
CREATE INDEX IF NOT EXISTS idx_waswa_gated_active ON dll_waswa_gated_actions(active) WHERE active = TRUE;

-- DO NOTHING on conflict: a re-run must never overwrite a threshold or an
-- approver the business has since filled in.
INSERT INTO dll_waswa_gated_actions
    (action_key, description, approval_level, approver_role, threshold_kind,
     threshold_value, threshold_note, waswa_may_act, source_ref) VALUES

-- ── Level 0: automated. The only actions Waswa may take on its own. ────────
 ('schedule_demo','Schedule a product demonstration',0,'automated',NULL,NULL,NULL,TRUE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 0'),
 ('send_followup_reminder','Send a follow-up reminder',0,'automated',NULL,NULL,NULL,TRUE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 0'),
 ('send_renewal_reminder','Send a renewal reminder',0,'automated',NULL,NULL,NULL,TRUE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 0'),
 ('assign_lead','Assign a lead to a salesperson',0,'automated',NULL,NULL,NULL,TRUE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 0'),

-- ── Level 1: sales staff ──────────────────────────────────────────────────
 ('issue_standard_pfi','Issue a standard PFI with PPMM pricing',1,'sales_staff',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 1'),
 ('move_pipeline_stage','Move a deal between pipeline stages',1,'sales_staff',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 1'),
 ('schedule_installation','Schedule an installation',1,'sales_staff',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 1'),

-- ── Level 2: sales manager (SMU / KCM / SMN) ──────────────────────────────
 ('apply_discount_within_threshold','Apply a discount up to the approved threshold',2,'sales_manager',
  'discount_percent',NULL,
  'Threshold not stated in the source document. Until it is, treat every discount as above threshold.',
  FALSE,'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 2'),
 ('qualify_enterprise_deal','Qualify a deal for an enterprise account',2,'sales_manager',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 2'),
 ('approve_travel','Approve sales travel',2,'sales_manager',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 2'),
 ('validate_iss_alignment','Validate ISS bundle alignment',2,'sales_manager',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 2'),
 ('validate_pfi_discount','Validate a discount on a PFI',2,'sales_manager',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §30.4 routing (SMU/KCM)'),
 ('approve_installation','Approve an installation',2,'cso_team_lead',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §30.4 routing'),
 ('approve_commissioning','Approve commissioning',2,'customer_success',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §30.4 routing'),

-- ── Level 3: CEO ──────────────────────────────────────────────────────────
 ('apply_discount_above_threshold','Apply a discount above the approved threshold',3,'ceo',
  'discount_percent',NULL,
  'Threshold not stated. Every discount routes here until the business names the number.',
  FALSE,'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 3'),
 ('multi_country_deal','Approve a multi-country deal',3,'ceo',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 3'),
 ('strategic_partnership','Approve a strategic partnership',3,'ceo',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 3'),
 ('custom_integration','Approve a custom integration',3,'ceo',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 3'),
 ('pricing_deviation_from_ppmm','Any pricing deviation from the PPMM matrix',3,'ceo',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §26.6 Level 3'),
 ('cross_border_pricing','Cross-border pricing',3,'ceo',NULL,NULL,NULL,FALSE,
  'SALES PROCEDURES 3DS-QMS-PR-09 ver26 §30.4 routing'),

-- ── Master prompt §B2.4: gated, approver not yet named ────────────────────
 ('immobilise_or_device_command','Immobilisation or any command that touches a vehicle or device',
  NULL,NULL,NULL,NULL,NULL,FALSE,'Waswa master prompt v2.0 §B2.4'),
 ('suspend_account','Suspend an account',NULL,NULL,NULL,NULL,NULL,FALSE,
  'Waswa master prompt v2.0 §B2.4'),
 ('resume_account','Resume a suspended account',NULL,NULL,NULL,NULL,NULL,FALSE,
  'Waswa master prompt v2.0 §B2.4'),
 ('billing_adjustment','Adjust billing',NULL,NULL,NULL,NULL,NULL,FALSE,
  'Waswa master prompt v2.0 §B2.4'),
 ('issue_credit','Issue a credit',NULL,NULL,NULL,NULL,NULL,FALSE,
  'Waswa master prompt v2.0 §B2.4'),
 ('bulk_customer_messaging','Outbound customer messaging at scale',NULL,NULL,NULL,NULL,NULL,FALSE,
  'Waswa master prompt v2.0 §B2.4'),
 ('change_message_template','Change a branded message template',NULL,NULL,NULL,NULL,NULL,FALSE,
  'Waswa master prompt v2.0 §B2.4'),
 ('publish_knowledge_base','Publish knowledge-base content',NULL,NULL,NULL,NULL,NULL,FALSE,
  'Waswa master prompt v2.0 §B2.4'),
 ('legal_or_insurance_narrative','Legal, insurance or incident narrative for a third party',
  NULL,NULL,NULL,NULL,NULL,FALSE,'Waswa master prompt v2.0 §B2.4'),
 ('destructive_action','Anything destructive',NULL,NULL,NULL,NULL,NULL,FALSE,
  'Waswa master prompt v2.0 §B2.4'),
 ('change_service_state_top_tier','Change service state on a Diamond or Platinum account',
  NULL,NULL,NULL,NULL,NULL,FALSE,'Waswa master prompt v2.0 §B2.4')

ON CONFLICT (action_key) DO NOTHING;

-- ── What still needs a human named against it ───────────────────────────────
CREATE OR REPLACE VIEW vw_waswa_unassigned_approvals AS
SELECT action_key, description, source_ref,
       CASE WHEN approver_role IS NULL THEN 'no approver role named' END AS approver_gap,
       CASE WHEN threshold_kind IS NOT NULL AND threshold_value IS NULL
            THEN 'threshold not stated' END                              AS threshold_gap
FROM dll_waswa_gated_actions
WHERE active = TRUE
  AND (approver_role IS NULL
       OR (threshold_kind IS NOT NULL AND threshold_value IS NULL));

COMMENT ON TABLE dll_waswa_gated_actions IS
    'Actions Waswa may only propose, and who approves each. waswa_may_act = TRUE '
    'marks the Level 0 actions it may take alone.';
COMMENT ON VIEW vw_waswa_unassigned_approvals IS
    'Gated actions still missing an approver or a threshold — the business '
    'decisions blocking Phase 8 routing.';
