-- ==========================================
-- Seed: Compliance Snapshot
-- ==========================================
-- Run this once to populate the compliance dashboard

INSERT INTO dll_audit_compliance (key, value, status, checked_at) VALUES
('Retention OK',  '180/180 days', 'ok',    NOW()),
('Crypto seal',   'valid',        'ok',    NOW()),
('Gaps',          '0 incidents',  'ok',    NOW()),
('Approvals',     'HIC backlog: 0', 'ok',  NOW())
ON CONFLICT DO NOTHING;


-- ==========================================
-- Seed: Initial Hash Chain Block
-- ==========================================
-- Creates the genesis block for the tamper-evidence chain

INSERT INTO dll_audit_hash_chain (hash, prev_hash, event_count, created_at, status) VALUES
(
    'genesis-0000000000000000000000000000000000000000000000000000000000000000',
    '0000000000000000000000000000000000000000000000000000000000000000',
    0,
    NOW(),
    'valid'
)
ON CONFLICT DO NOTHING;
