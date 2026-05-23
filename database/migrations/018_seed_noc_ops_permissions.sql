-- ============================================================
-- 018_seed_noc_ops_permissions.sql
-- ============================================================
-- Seeds permissions for two newly cataloged modules:
--   - NOC & Network Operations (18 permissions)
--   - Ops War Room & Device Management (21 permissions)
--
-- These were added to the frontend permissionCatalog.ts and linked
-- via modules.ts. The master seed (013) was also regenerated but
-- may have already been applied; this migration ensures the new
-- permissions exist regardless.
--
-- Idempotent: ON CONFLICT (permission_uid) DO NOTHING.
-- ============================================================

-- Module: NOC & Network Operations (18 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_hitl_action', 'can_approve_hitl_action', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_chat_with_waswa', 'can_chat_with_waswa', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_end_server_task', 'can_end_server_task', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_export_noc_report', 'can_export_noc_report', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_mute_ai_alerts', 'can_mute_ai_alerts', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_reject_hitl_action', 'can_reject_hitl_action', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_retry_gateway_webhooks', 'can_retry_gateway_webhooks', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_simulate_hitl_action', 'can_simulate_hitl_action', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_trigger_hic_override', 'can_trigger_hic_override', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_view_gateway_history', 'can_view_gateway_history', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_view_gateway_status', 'can_view_gateway_status', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_view_hitl_queue', 'can_view_hitl_queue', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_view_hitl_runbook', 'can_view_hitl_runbook', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_view_noc_dashboard', 'can_view_noc_dashboard', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_view_server_metrics', 'can_view_server_metrics', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_view_system_kpis', 'can_view_system_kpis', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_view_task_manager', 'can_view_task_manager', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system'),
    ('perm_can_view_veba_statistics', 'can_view_veba_statistics', 'NAVAS catalog permission', 'NOC & Network Operations', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Ops War Room & Device Management (21 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_acknowledge_ops_alarm', 'can_acknowledge_ops_alarm', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_add_device', 'can_add_device', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_approve_ops_recommendation', 'can_approve_ops_recommendation', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_assign_device_client', 'can_assign_device_client', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_delete_device', 'can_delete_device', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_edit_device_configs', 'can_edit_device_configs', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_edit_device_properties', 'can_edit_device_properties', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_export_ops_brief', 'can_export_ops_brief', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_register_unit', 'can_register_unit', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_reject_ops_recommendation', 'can_reject_ops_recommendation', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_renew_device_payment', 'can_renew_device_payment', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_rerun_ops_webhooks', 'can_rerun_ops_webhooks', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_send_ops_brief_whatsapp', 'can_send_ops_brief_whatsapp', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_set_token_cap', 'can_set_token_cap', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_view_device_details', 'can_view_device_details', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_view_device_table', 'can_view_device_table', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_view_ops_alarms', 'can_view_ops_alarms', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_view_ops_brief', 'can_view_ops_brief', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_view_ops_dashboard', 'can_view_ops_dashboard', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_view_ops_gateways', 'can_view_ops_gateways', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system'),
    ('perm_can_view_token_burn_chart', 'can_view_token_burn_chart', 'NAVAS catalog permission', 'Ops War Room & Device Management', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;
