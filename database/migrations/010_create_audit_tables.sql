-- Migration 010: Create Audit Tables
-- Audit events, hash chain, approvals, and compliance

-- ==========================================
-- AUDIT EVENTS
-- ==========================================
CREATE TABLE IF NOT EXISTS dll_audit_events (
    id VARCHAR(100) PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    actor VARCHAR(200) NOT NULL,
    action VARCHAR(50) NOT NULL,
    object TEXT,
    domain VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'Info',
    tenant_id VARCHAR(100),
    ip_address VARCHAR(50),
    hash_prev VARCHAR(200),
    hash_this VARCHAR(200),
    meta JSONB DEFAULT '{}',
    flagged BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Add flagged column if table already exists
ALTER TABLE dll_audit_events ADD COLUMN IF NOT EXISTS flagged BOOLEAN DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_audit_events_domain ON dll_audit_events(domain);
CREATE INDEX IF NOT EXISTS idx_audit_events_severity ON dll_audit_events(severity);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor ON dll_audit_events(actor);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON dll_audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_id ON dll_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON dll_audit_events(timestamp);

-- ==========================================
-- AUDIT HASH CHAIN
-- ==========================================
CREATE TABLE IF NOT EXISTS dll_audit_hash_chain (
    block_id SERIAL PRIMARY KEY,
    hash VARCHAR(200) NOT NULL,
    prev_hash VARCHAR(200) NOT NULL,
    event_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'valid'
);

CREATE INDEX IF NOT EXISTS idx_audit_hash_chain_status ON dll_audit_hash_chain(status);

-- ==========================================
-- AUDIT APPROVALS
-- ==========================================
CREATE TABLE IF NOT EXISTS dll_audit_approvals (
    id VARCHAR(100) PRIMARY KEY,
    type VARCHAR(10) NOT NULL,
    title VARCHAR(500) NOT NULL,
    domain VARCHAR(50) NOT NULL,
    tenant_name VARCHAR(200),
    requirement TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT NOW(),
    requested_by VARCHAR(200),
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(200),
    meta JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_audit_approvals_status ON dll_audit_approvals(status);
CREATE INDEX IF NOT EXISTS idx_audit_approvals_type ON dll_audit_approvals(type);
CREATE INDEX IF NOT EXISTS idx_audit_approvals_domain ON dll_audit_approvals(domain);

-- ==========================================
-- AUDIT COMPLIANCE
-- ==========================================
CREATE TABLE IF NOT EXISTS dll_audit_compliance (
    id SERIAL PRIMARY KEY,
    key VARCHAR(200) NOT NULL,
    value VARCHAR(500),
    status VARCHAR(20) NOT NULL DEFAULT 'ok',
    checked_at TIMESTAMP DEFAULT NOW()
);

-- ==========================================
-- AUDIT EXPORTS
-- ==========================================
CREATE TABLE IF NOT EXISTS dll_audit_exports (
    export_id VARCHAR(100) PRIMARY KEY,
    approval_id VARCHAR(100),
    tenant_id VARCHAR(100),
    date_range VARCHAR(50),
    include_sub_tenants BOOLEAN DEFAULT FALSE,
    formats JSONB DEFAULT '[]',
    redact_pii BOOLEAN DEFAULT TRUE,
    include_raw_payloads BOOLEAN DEFAULT FALSE,
    approver_ids JSONB DEFAULT '[]',
    status VARCHAR(50) NOT NULL DEFAULT 'pending_approval',
    requested_by VARCHAR(200),
    requested_at TIMESTAMP DEFAULT NOW()
);
