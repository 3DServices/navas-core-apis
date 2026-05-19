-- ============================================================
-- 013_seed_permission_catalog.sql
-- ============================================================
-- Seeds the NAVAS catalog permissions into dll_permissions under
-- account_root='engine' (the existing 'system-global' sentinel).
--
-- Source of truth: src/auth/permissionCatalog.ts (frontend).
-- Idempotent: ON CONFLICT (permission_uid) DO NOTHING.
-- Total: 531 permissions across 47 modules.
-- ============================================================

-- Module: AI & Video (15 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_video_action', 'can_approve_video_action', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_configure_cameras', 'can_configure_cameras', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_configure_video_bandwidth_rules', 'can_configure_video_bandwidth_rules', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_configure_video_upload_rules', 'can_configure_video_upload_rules', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_export_video_clips', 'can_export_video_clips', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_manage_video_retention_policy', 'can_manage_video_retention_policy', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_manage_video_storage_policy', 'can_manage_video_storage_policy', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_mask_video_data', 'can_mask_video_data', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_redact_video_clip', 'can_redact_video_clip', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_request_video_snapshot', 'can_request_video_snapshot', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_share_video_evidence', 'can_share_video_evidence', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_view_live_video_stream', 'can_view_live_video_stream', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_view_video_analytics', 'can_view_video_analytics', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_view_video_by_role', 'can_view_video_by_role', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system'),
    ('perm_can_watermark_video_evidence', 'can_watermark_video_evidence', 'NAVAS catalog permission', 'AI & Video', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: API & Integration Hub (8 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_access_command_api', 'can_access_command_api', 'NAVAS catalog permission', 'API & Integration Hub', 'engine', 'system'),
    ('perm_can_configure_mfa', 'can_configure_mfa', 'NAVAS catalog permission', 'API & Integration Hub', 'engine', 'system'),
    ('perm_can_configure_webhook', 'can_configure_webhook', 'NAVAS catalog permission', 'API & Integration Hub', 'engine', 'system'),
    ('perm_can_generate_api_token', 'can_generate_api_token', 'NAVAS catalog permission', 'API & Integration Hub', 'engine', 'system'),
    ('perm_can_manage_integration_settings', 'can_manage_integration_settings', 'NAVAS catalog permission', 'API & Integration Hub', 'engine', 'system'),
    ('perm_can_revoke_api_token', 'can_revoke_api_token', 'NAVAS catalog permission', 'API & Integration Hub', 'engine', 'system'),
    ('perm_can_view_api_call_cost', 'can_view_api_call_cost', 'NAVAS catalog permission', 'API & Integration Hub', 'engine', 'system'),
    ('perm_can_view_api_token_burn', 'can_view_api_token_burn', 'NAVAS catalog permission', 'API & Integration Hub', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Alerts & Incident Feed (12 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_acknowledge_alert', 'can_acknowledge_alert', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_configure_alert_channels', 'can_configure_alert_channels', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_configure_alert_escalation', 'can_configure_alert_escalation', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_configure_alert_quiet_hours', 'can_configure_alert_quiet_hours', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_create_alert_rule', 'can_create_alert_rule', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_delete_alert_rule', 'can_delete_alert_rule', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_edit_alert_rule', 'can_edit_alert_rule', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_export_alert_report', 'can_export_alert_report', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_set_alert_sensitivity_thresholds', 'can_set_alert_sensitivity_thresholds', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_subscribe_to_alerts', 'can_subscribe_to_alerts', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_suppress_alert_rule', 'can_suppress_alert_rule', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system'),
    ('perm_can_view_alerts', 'can_view_alerts', 'NAVAS catalog permission', 'Alerts & Incident Feed', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Assets & Unit Registry (16 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_allocate_tokens_to_asset', 'can_allocate_tokens_to_asset', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_archive_unit', 'can_archive_unit', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_assign_unit_to_branch', 'can_assign_unit_to_branch', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_bulk_manage_units', 'can_bulk_manage_units', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_configure_unit_connectivity', 'can_configure_unit_connectivity', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_configure_unit_depreciation', 'can_configure_unit_depreciation', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_create_unit', 'can_create_unit', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_delete_unit', 'can_delete_unit', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_edit_unit', 'can_edit_unit', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_list_asset_on_marketplace', 'can_list_asset_on_marketplace', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_register_unit_device', 'can_register_unit_device', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_transfer_tokens_between_assets', 'can_transfer_tokens_between_assets', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_view_unit', 'can_view_unit', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_view_unit_digital_twin', 'can_view_unit_digital_twin', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_view_unit_health', 'can_view_unit_health', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system'),
    ('perm_can_view_unit_productivity', 'can_view_unit_productivity', 'NAVAS catalog permission', 'Assets & Unit Registry', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Billing Plans & Invoicing (8 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_assign_billing_plan', 'can_assign_billing_plan', 'NAVAS catalog permission', 'Billing Plans & Invoicing', 'engine', 'system'),
    ('perm_can_create_billing_plan', 'can_create_billing_plan', 'NAVAS catalog permission', 'Billing Plans & Invoicing', 'engine', 'system'),
    ('perm_can_create_invoice', 'can_create_invoice', 'NAVAS catalog permission', 'Billing Plans & Invoicing', 'engine', 'system'),
    ('perm_can_edit_billing_plan', 'can_edit_billing_plan', 'NAVAS catalog permission', 'Billing Plans & Invoicing', 'engine', 'system'),
    ('perm_can_export_billing_data', 'can_export_billing_data', 'NAVAS catalog permission', 'Billing Plans & Invoicing', 'engine', 'system'),
    ('perm_can_manage_billing_audit_trail', 'can_manage_billing_audit_trail', 'NAVAS catalog permission', 'Billing Plans & Invoicing', 'engine', 'system'),
    ('perm_can_view_billing_plan', 'can_view_billing_plan', 'NAVAS catalog permission', 'Billing Plans & Invoicing', 'engine', 'system'),
    ('perm_can_view_invoice', 'can_view_invoice', 'NAVAS catalog permission', 'Billing Plans & Invoicing', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Dashboards & BI Studio (11 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_kpi_cards', 'can_configure_kpi_cards', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_create_dashboard', 'can_create_dashboard', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_delete_dashboard', 'can_delete_dashboard', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_edit_dashboard', 'can_edit_dashboard', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_export_report', 'can_export_report', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_schedule_report', 'can_schedule_report', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_share_report', 'can_share_report', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_view_bi_studio', 'can_view_bi_studio', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_view_burnrate_dashboard', 'can_view_burnrate_dashboard', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_view_compliance_dashboard', 'can_view_compliance_dashboard', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system'),
    ('perm_can_view_dashboard', 'can_view_dashboard', 'NAVAS catalog permission', 'Dashboards & BI Studio', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Dealer Branding & White-Label (11 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_clone_account_template', 'can_clone_account_template', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_create_client_account', 'can_create_client_account', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_customize_branding', 'can_customize_branding', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_edit_client_account', 'can_edit_client_account', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_manage_dealer_scope', 'can_manage_dealer_scope', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_manage_whitelabel_catalog', 'can_manage_whitelabel_catalog', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_provision_apps_for_client', 'can_provision_apps_for_client', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_segment_client_portfolio', 'can_segment_client_portfolio', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_set_discount_bands', 'can_set_discount_bands', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_view_client_account', 'can_view_client_account', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system'),
    ('perm_can_view_client_payment_status', 'can_view_client_payment_status', 'NAVAS catalog permission', 'Dealer Branding & White-Label', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Device Lifecycle & Firmware (6 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_decommission_device', 'can_decommission_device', 'NAVAS catalog permission', 'Device Lifecycle & Firmware', 'engine', 'system'),
    ('perm_can_manage_firmware_update', 'can_manage_firmware_update', 'NAVAS catalog permission', 'Device Lifecycle & Firmware', 'engine', 'system'),
    ('perm_can_manage_warranty_record', 'can_manage_warranty_record', 'NAVAS catalog permission', 'Device Lifecycle & Firmware', 'engine', 'system'),
    ('perm_can_register_device_serial', 'can_register_device_serial', 'NAVAS catalog permission', 'Device Lifecycle & Firmware', 'engine', 'system'),
    ('perm_can_view_device_compatibility', 'can_view_device_compatibility', 'NAVAS catalog permission', 'Device Lifecycle & Firmware', 'engine', 'system'),
    ('perm_can_view_device_lifecycle', 'can_view_device_lifecycle', 'NAVAS catalog permission', 'Device Lifecycle & Firmware', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Dispatch & Job Board (13 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_assign_job', 'can_assign_job', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_cancel_job', 'can_cancel_job', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_configure_dispatch_rules', 'can_configure_dispatch_rules', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_contact_driver_from_job', 'can_contact_driver_from_job', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_create_job', 'can_create_job', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_dispatch_asset', 'can_dispatch_asset', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_edit_job', 'can_edit_job', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_manage_yard_map', 'can_manage_yard_map', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_override_dispatch_block', 'can_override_dispatch_block', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_reroute_job', 'can_reroute_job', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_view_job', 'can_view_job', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_view_job_board', 'can_view_job_board', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system'),
    ('perm_can_view_job_funnel', 'can_view_job_funnel', 'NAVAS catalog permission', 'Dispatch & Job Board', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Driver Scorecard (8 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_scorecard_by_profile', 'can_configure_scorecard_by_profile', 'NAVAS catalog permission', 'Driver Scorecard', 'engine', 'system'),
    ('perm_can_configure_scorecard_weights', 'can_configure_scorecard_weights', 'NAVAS catalog permission', 'Driver Scorecard', 'engine', 'system'),
    ('perm_can_dispute_score_event', 'can_dispute_score_event', 'NAVAS catalog permission', 'Driver Scorecard', 'engine', 'system'),
    ('perm_can_export_driver_risk_summary', 'can_export_driver_risk_summary', 'NAVAS catalog permission', 'Driver Scorecard', 'engine', 'system'),
    ('perm_can_override_score_event', 'can_override_score_event', 'NAVAS catalog permission', 'Driver Scorecard', 'engine', 'system'),
    ('perm_can_review_score_before_punitive_action', 'can_review_score_before_punitive_action', 'NAVAS catalog permission', 'Driver Scorecard', 'engine', 'system'),
    ('perm_can_view_driver_scorecard', 'can_view_driver_scorecard', 'NAVAS catalog permission', 'Driver Scorecard', 'engine', 'system'),
    ('perm_can_view_scorecard_leaderboard', 'can_view_scorecard_leaderboard', 'NAVAS catalog permission', 'Driver Scorecard', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Drivers (17 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_assign_driver_to_asset', 'can_assign_driver_to_asset', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_blacklist_driver', 'can_blacklist_driver', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_bulk_manage_drivers', 'can_bulk_manage_drivers', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_configure_driver_coaching', 'can_configure_driver_coaching', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_create_driver', 'can_create_driver', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_deactivate_driver', 'can_deactivate_driver', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_edit_driver', 'can_edit_driver', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_export_driver_data', 'can_export_driver_data', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_manage_driver_documents', 'can_manage_driver_documents', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_manage_driver_training_record', 'can_manage_driver_training_record', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_reinstate_driver', 'can_reinstate_driver', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_suspend_driver', 'can_suspend_driver', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_unassign_driver_from_asset', 'can_unassign_driver_from_asset', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_view_driver', 'can_view_driver', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_view_driver_compliance_status', 'can_view_driver_compliance_status', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_view_driver_fatigue_data', 'can_view_driver_fatigue_data', 'NAVAS catalog permission', 'Drivers', 'engine', 'system'),
    ('perm_can_view_driver_safety_score', 'can_view_driver_safety_score', 'NAVAS catalog permission', 'Drivers', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: E-Shop & Bundle Builder (8 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_browse_eshop', 'can_browse_eshop', 'NAVAS catalog permission', 'E-Shop & Bundle Builder', 'engine', 'system'),
    ('perm_can_configure_bundle_dependencies', 'can_configure_bundle_dependencies', 'NAVAS catalog permission', 'E-Shop & Bundle Builder', 'engine', 'system'),
    ('perm_can_create_bundle', 'can_create_bundle', 'NAVAS catalog permission', 'E-Shop & Bundle Builder', 'engine', 'system'),
    ('perm_can_edit_bundle', 'can_edit_bundle', 'NAVAS catalog permission', 'E-Shop & Bundle Builder', 'engine', 'system'),
    ('perm_can_manage_eshop_catalog', 'can_manage_eshop_catalog', 'NAVAS catalog permission', 'E-Shop & Bundle Builder', 'engine', 'system'),
    ('perm_can_manage_eshop_returns', 'can_manage_eshop_returns', 'NAVAS catalog permission', 'E-Shop & Bundle Builder', 'engine', 'system'),
    ('perm_can_purchase_eshop_item', 'can_purchase_eshop_item', 'NAVAS catalog permission', 'E-Shop & Bundle Builder', 'engine', 'system'),
    ('perm_can_view_bundle_recommendations', 'can_view_bundle_recommendations', 'NAVAS catalog permission', 'E-Shop & Bundle Builder', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Fuel Triple-Audit Hub (15 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_assign_fuel_card', 'can_assign_fuel_card', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_authorize_fuel_dispensing', 'can_authorize_fuel_dispensing', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_configure_fuel_limits', 'can_configure_fuel_limits', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_configure_fuel_station_approvals', 'can_configure_fuel_station_approvals', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_configure_fueling_corridors', 'can_configure_fueling_corridors', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_export_fuel_data', 'can_export_fuel_data', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_freeze_fuel_card', 'can_freeze_fuel_card', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_issue_fuel_voucher', 'can_issue_fuel_voucher', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_manage_bulk_fuel_tanks', 'can_manage_bulk_fuel_tanks', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_manage_fuel_cards', 'can_manage_fuel_cards', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_view_fuel_audit_report', 'can_view_fuel_audit_report', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_view_fuel_efficiency_report', 'can_view_fuel_efficiency_report', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_view_fuel_levels', 'can_view_fuel_levels', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_view_fuel_reconciliation', 'can_view_fuel_reconciliation', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system'),
    ('perm_can_view_fuel_transactions', 'can_view_fuel_transactions', 'NAVAS catalog permission', 'Fuel Triple-Audit Hub', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Geo-Zones & POIs (15 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_apply_geofence_template', 'can_apply_geofence_template', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_approve_geofence_edit', 'can_approve_geofence_edit', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_bulk_manage_geofences', 'can_bulk_manage_geofences', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_configure_geofence_dwell_rules', 'can_configure_geofence_dwell_rules', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_create_geofence', 'can_create_geofence', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_create_poi', 'can_create_poi', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_delete_geofence', 'can_delete_geofence', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_delete_poi', 'can_delete_poi', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_edit_geofence', 'can_edit_geofence', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_edit_poi', 'can_edit_poi', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_export_geofences', 'can_export_geofences', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_import_geofences', 'can_import_geofences', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_share_geofence_externally', 'can_share_geofence_externally', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_view_geofence', 'can_view_geofence', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system'),
    ('perm_can_view_geofence_audit_trail', 'can_view_geofence_audit_trail', 'NAVAS catalog permission', 'Geo-Zones & POIs', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Goods & IoT (9 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_cargo_lock_geofence', 'can_configure_cargo_lock_geofence', 'NAVAS catalog permission', 'Goods & IoT', 'engine', 'system'),
    ('perm_can_create_cargo_manifest', 'can_create_cargo_manifest', 'NAVAS catalog permission', 'Goods & IoT', 'engine', 'system'),
    ('perm_can_edit_cargo_manifest', 'can_edit_cargo_manifest', 'NAVAS catalog permission', 'Goods & IoT', 'engine', 'system'),
    ('perm_can_manage_cargo_handover', 'can_manage_cargo_handover', 'NAVAS catalog permission', 'Goods & IoT', 'engine', 'system'),
    ('perm_can_monitor_cold_chain', 'can_monitor_cold_chain', 'NAVAS catalog permission', 'Goods & IoT', 'engine', 'system'),
    ('perm_can_track_cargo_custody', 'can_track_cargo_custody', 'NAVAS catalog permission', 'Goods & IoT', 'engine', 'system'),
    ('perm_can_view_cargo_dwell_time', 'can_view_cargo_dwell_time', 'NAVAS catalog permission', 'Goods & IoT', 'engine', 'system'),
    ('perm_can_view_cargo_seal_status', 'can_view_cargo_seal_status', 'NAVAS catalog permission', 'Goods & IoT', 'engine', 'system'),
    ('perm_can_view_cargo_sensor_data', 'can_view_cargo_sensor_data', 'NAVAS catalog permission', 'Goods & IoT', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Helpdesk & Customer Success (8 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_close_ticket', 'can_close_ticket', 'NAVAS catalog permission', 'Helpdesk & Customer Success', 'engine', 'system'),
    ('perm_can_configure_helpdesk_integration', 'can_configure_helpdesk_integration', 'NAVAS catalog permission', 'Helpdesk & Customer Success', 'engine', 'system'),
    ('perm_can_create_support_ticket', 'can_create_support_ticket', 'NAVAS catalog permission', 'Helpdesk & Customer Success', 'engine', 'system'),
    ('perm_can_escalate_ticket', 'can_escalate_ticket', 'NAVAS catalog permission', 'Helpdesk & Customer Success', 'engine', 'system'),
    ('perm_can_manage_support_ticket', 'can_manage_support_ticket', 'NAVAS catalog permission', 'Helpdesk & Customer Success', 'engine', 'system'),
    ('perm_can_view_customer_success_metrics', 'can_view_customer_success_metrics', 'NAVAS catalog permission', 'Helpdesk & Customer Success', 'engine', 'system'),
    ('perm_can_view_support_sla_dashboard', 'can_view_support_sla_dashboard', 'NAVAS catalog permission', 'Helpdesk & Customer Success', 'engine', 'system'),
    ('perm_can_view_support_ticket', 'can_view_support_ticket', 'NAVAS catalog permission', 'Helpdesk & Customer Success', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Identity & Login (10 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_2fa', 'can_configure_2fa', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system'),
    ('perm_can_configure_distress_pin', 'can_configure_distress_pin', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system'),
    ('perm_can_configure_session_timeout', 'can_configure_session_timeout', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system'),
    ('perm_can_configure_time_restricted_login', 'can_configure_time_restricted_login', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system'),
    ('perm_can_configure_trust_score', 'can_configure_trust_score', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system'),
    ('perm_can_manage_guest_login', 'can_manage_guest_login', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system'),
    ('perm_can_manage_trusted_devices', 'can_manage_trusted_devices', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system'),
    ('perm_can_set_failed_attempt_threshold', 'can_set_failed_attempt_threshold', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system'),
    ('perm_can_set_login_policy', 'can_set_login_policy', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system'),
    ('perm_can_view_login_audit_log', 'can_view_login_audit_log', 'NAVAS catalog permission', 'Identity & Login', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Inspecta (15 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_conduct_inspection', 'can_conduct_inspection', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_configure_inspection_reminders', 'can_configure_inspection_reminders', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_create_inspection_template', 'can_create_inspection_template', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_delete_inspection_template', 'can_delete_inspection_template', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_edit_inspection_template', 'can_edit_inspection_template', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_export_inspection_report', 'can_export_inspection_report', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_grant_guest_inspection_access', 'can_grant_guest_inspection_access', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_override_inspection_item', 'can_override_inspection_item', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_reopen_inspection', 'can_reopen_inspection', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_schedule_inspection', 'can_schedule_inspection', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_share_inspection_evidence', 'can_share_inspection_evidence', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_signoff_inspection', 'can_signoff_inspection', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_view_inspection_audit_trail', 'can_view_inspection_audit_trail', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_view_inspection_record', 'can_view_inspection_record', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system'),
    ('perm_can_view_inspection_score', 'can_view_inspection_score', 'NAVAS catalog permission', 'Inspecta', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Live Dispatch & GIS (5 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_view_cost_per_delivery_metric', 'can_view_cost_per_delivery_metric', 'NAVAS catalog permission', 'Live Dispatch & GIS', 'engine', 'system'),
    ('perm_can_view_delivery_metrics', 'can_view_delivery_metrics', 'NAVAS catalog permission', 'Live Dispatch & GIS', 'engine', 'system'),
    ('perm_can_view_legislative_compliance_report', 'can_view_legislative_compliance_report', 'NAVAS catalog permission', 'Live Dispatch & GIS', 'engine', 'system'),
    ('perm_can_view_live_gis_map', 'can_view_live_gis_map', 'NAVAS catalog permission', 'Live Dispatch & GIS', 'engine', 'system'),
    ('perm_can_view_live_traffic_overlay', 'can_view_live_traffic_overlay', 'NAVAS catalog permission', 'Live Dispatch & GIS', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Messaging & Notification Hub (8 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_ai_generated_message', 'can_approve_ai_generated_message', 'NAVAS catalog permission', 'Messaging & Notification Hub', 'engine', 'system'),
    ('perm_can_configure_notification_channels', 'can_configure_notification_channels', 'NAVAS catalog permission', 'Messaging & Notification Hub', 'engine', 'system'),
    ('perm_can_configure_notification_templates', 'can_configure_notification_templates', 'NAVAS catalog permission', 'Messaging & Notification Hub', 'engine', 'system'),
    ('perm_can_configure_opt_out_rules', 'can_configure_opt_out_rules', 'NAVAS catalog permission', 'Messaging & Notification Hub', 'engine', 'system'),
    ('perm_can_monitor_notification_delivery_health', 'can_monitor_notification_delivery_health', 'NAVAS catalog permission', 'Messaging & Notification Hub', 'engine', 'system'),
    ('perm_can_suppress_notifications', 'can_suppress_notifications', 'NAVAS catalog permission', 'Messaging & Notification Hub', 'engine', 'system'),
    ('perm_can_view_notification_analytics', 'can_view_notification_analytics', 'NAVAS catalog permission', 'Messaging & Notification Hub', 'engine', 'system'),
    ('perm_can_view_notification_cost', 'can_view_notification_cost', 'NAVAS catalog permission', 'Messaging & Notification Hub', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Order & HGV Control (9 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_order_action', 'can_approve_order_action', 'NAVAS catalog permission', 'Order & HGV Control', 'engine', 'system'),
    ('perm_can_assign_job_to_cost_center', 'can_assign_job_to_cost_center', 'NAVAS catalog permission', 'Order & HGV Control', 'engine', 'system'),
    ('perm_can_bulk_manage_orders', 'can_bulk_manage_orders', 'NAVAS catalog permission', 'Order & HGV Control', 'engine', 'system'),
    ('perm_can_cancel_order', 'can_cancel_order', 'NAVAS catalog permission', 'Order & HGV Control', 'engine', 'system'),
    ('perm_can_configure_approval_workflow_for_jobs', 'can_configure_approval_workflow_for_jobs', 'NAVAS catalog permission', 'Order & HGV Control', 'engine', 'system'),
    ('perm_can_create_order', 'can_create_order', 'NAVAS catalog permission', 'Order & HGV Control', 'engine', 'system'),
    ('perm_can_edit_order', 'can_edit_order', 'NAVAS catalog permission', 'Order & HGV Control', 'engine', 'system'),
    ('perm_can_manage_fuel_vouchers', 'can_manage_fuel_vouchers', 'NAVAS catalog permission', 'Order & HGV Control', 'engine', 'system'),
    ('perm_can_view_order', 'can_view_order', 'NAVAS catalog permission', 'Order & HGV Control', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Owner & Broker Console (8 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_auto_logout', 'can_configure_auto_logout', 'NAVAS catalog permission', 'Owner & Broker Console', 'engine', 'system'),
    ('perm_can_configure_rental_rates', 'can_configure_rental_rates', 'NAVAS catalog permission', 'Owner & Broker Console', 'engine', 'system'),
    ('perm_can_set_fueling_limits', 'can_set_fueling_limits', 'NAVAS catalog permission', 'Owner & Broker Console', 'engine', 'system'),
    ('perm_can_view_asset_longevity', 'can_view_asset_longevity', 'NAVAS catalog permission', 'Owner & Broker Console', 'engine', 'system'),
    ('perm_can_view_fleet_downtime', 'can_view_fleet_downtime', 'NAVAS catalog permission', 'Owner & Broker Console', 'engine', 'system'),
    ('perm_can_view_fleet_tco', 'can_view_fleet_tco', 'NAVAS catalog permission', 'Owner & Broker Console', 'engine', 'system'),
    ('perm_can_view_risk_heatmap', 'can_view_risk_heatmap', 'NAVAS catalog permission', 'Owner & Broker Console', 'engine', 'system'),
    ('perm_can_view_satellite_map', 'can_view_satellite_map', 'NAVAS catalog permission', 'Owner & Broker Console', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: PackageOps PASO (11 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_create_delivery_manifest', 'can_create_delivery_manifest', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_edit_delivery_manifest', 'can_edit_delivery_manifest', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_flag_damaged_parcel', 'can_flag_damaged_parcel', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_generate_pod', 'can_generate_pod', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_manage_cold_chain_parcel', 'can_manage_cold_chain_parcel', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_manage_delivery_returns', 'can_manage_delivery_returns', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_scan_parcel', 'can_scan_parcel', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_share_parcel_tracking_link', 'can_share_parcel_tracking_link', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_view_delivery_cost_analytics', 'can_view_delivery_cost_analytics', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_view_delivery_tracking', 'can_view_delivery_tracking', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system'),
    ('perm_can_view_parcel_audit_log', 'can_view_parcel_audit_log', 'NAVAS catalog permission', 'PackageOps PASO', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Passengers (11 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_blacklist_passenger', 'can_blacklist_passenger', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_configure_passenger_notifications', 'can_configure_passenger_notifications', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_configure_passenger_zones', 'can_configure_passenger_zones', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_manage_passenger_boarding', 'can_manage_passenger_boarding', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_manage_passenger_list', 'can_manage_passenger_list', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_manage_passenger_roster', 'can_manage_passenger_roster', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_report_passenger_safety_incident', 'can_report_passenger_safety_incident', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_share_passenger_tracking', 'can_share_passenger_tracking', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_view_passenger_manifest', 'can_view_passenger_manifest', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_view_passenger_occupancy', 'can_view_passenger_occupancy', 'NAVAS catalog permission', 'Passengers', 'engine', 'system'),
    ('perm_can_view_passenger_safety_data', 'can_view_passenger_safety_data', 'NAVAS catalog permission', 'Passengers', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Payments & Mobile Money (7 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_payment_methods', 'can_configure_payment_methods', 'NAVAS catalog permission', 'Payments & Mobile Money', 'engine', 'system'),
    ('perm_can_export_payment_records', 'can_export_payment_records', 'NAVAS catalog permission', 'Payments & Mobile Money', 'engine', 'system'),
    ('perm_can_manage_partial_payment', 'can_manage_partial_payment', 'NAVAS catalog permission', 'Payments & Mobile Money', 'engine', 'system'),
    ('perm_can_process_mobile_money_payment', 'can_process_mobile_money_payment', 'NAVAS catalog permission', 'Payments & Mobile Money', 'engine', 'system'),
    ('perm_can_view_mobile_money_settlement', 'can_view_mobile_money_settlement', 'NAVAS catalog permission', 'Payments & Mobile Money', 'engine', 'system'),
    ('perm_can_view_payment_gateway_health', 'can_view_payment_gateway_health', 'NAVAS catalog permission', 'Payments & Mobile Money', 'engine', 'system'),
    ('perm_can_view_payment_status', 'can_view_payment_status', 'NAVAS catalog permission', 'Payments & Mobile Money', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Payments & Statements (13 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_payment', 'can_approve_payment', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_configure_auto_renew', 'can_configure_auto_renew', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_configure_consolidated_billing', 'can_configure_consolidated_billing', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_download_statement', 'can_download_statement', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_manage_credit_notes', 'can_manage_credit_notes', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_manage_dunning', 'can_manage_dunning', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_manage_escrow_payment', 'can_manage_escrow_payment', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_manage_refunds', 'can_manage_refunds', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_reconcile_payments', 'can_reconcile_payments', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_view_aging_buckets', 'can_view_aging_buckets', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_view_collections', 'can_view_collections', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_view_fx_rate_on_statement', 'can_view_fx_rate_on_statement', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system'),
    ('perm_can_view_statement', 'can_view_statement', 'NAVAS catalog permission', 'Payments & Statements', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Procurement & Stock Control (16 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_purchase_order', 'can_approve_purchase_order', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_approve_rfq', 'can_approve_rfq', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_configure_reorder_rules', 'can_configure_reorder_rules', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_create_purchase_order', 'can_create_purchase_order', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_create_rfq', 'can_create_rfq', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_edit_rfq', 'can_edit_rfq', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_manage_compatibility_registry', 'can_manage_compatibility_registry', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_manage_inventory', 'can_manage_inventory', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_manage_rma', 'can_manage_rma', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_manage_warranty_claims', 'can_manage_warranty_claims', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_reserve_stock', 'can_reserve_stock', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_track_serial_inventory', 'can_track_serial_inventory', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_view_landed_cost', 'can_view_landed_cost', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_view_procurement_catalog', 'can_view_procurement_catalog', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_view_stock_levels', 'can_view_stock_levels', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system'),
    ('perm_can_view_supplier_comparison', 'can_view_supplier_comparison', 'NAVAS catalog permission', 'Procurement & Stock Control', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Reports & Alerts Studio (6 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_create_report', 'can_create_report', 'NAVAS catalog permission', 'Reports & Alerts Studio', 'engine', 'system'),
    ('perm_can_edit_report', 'can_edit_report', 'NAVAS catalog permission', 'Reports & Alerts Studio', 'engine', 'system'),
    ('perm_can_manage_report_recipients', 'can_manage_report_recipients', 'NAVAS catalog permission', 'Reports & Alerts Studio', 'engine', 'system'),
    ('perm_can_share_report_externally', 'can_share_report_externally', 'NAVAS catalog permission', 'Reports & Alerts Studio', 'engine', 'system'),
    ('perm_can_update_cost_library', 'can_update_cost_library', 'NAVAS catalog permission', 'Reports & Alerts Studio', 'engine', 'system'),
    ('perm_can_view_report', 'can_view_report', 'NAVAS catalog permission', 'Reports & Alerts Studio', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Resources & Template Library (8 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_clone_resource_template', 'can_clone_resource_template', 'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_create_resource_template', 'can_create_resource_template', 'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_edit_resource_template', 'can_edit_resource_template', 'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_export_resources', 'can_export_resources', 'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_import_resources', 'can_import_resources', 'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_inherit_resource_template', 'can_inherit_resource_template', 'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_share_resource_template', 'can_share_resource_template', 'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system'),
    ('perm_can_view_resource_template', 'can_view_resource_template', 'NAVAS catalog permission', 'Resources & Template Library', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Routes & Journey Control (14 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_apply_route_template', 'can_apply_route_template', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_assign_route', 'can_assign_route', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_configure_curfew_corridors', 'can_configure_curfew_corridors', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_configure_route_dwell_rules', 'can_configure_route_dwell_rules', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_configure_route_restrictions', 'can_configure_route_restrictions', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_create_route', 'can_create_route', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_delete_route', 'can_delete_route', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_edit_route', 'can_edit_route', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_export_route', 'can_export_route', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_import_route', 'can_import_route', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_manage_route_checkpoints', 'can_manage_route_checkpoints', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_simulate_route', 'can_simulate_route', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_view_route', 'can_view_route', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system'),
    ('perm_can_view_route_profitability', 'can_view_route_profitability', 'NAVAS catalog permission', 'Routes & Journey Control', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: SIM & Connectivity Guard (13 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_mass_sim_change', 'can_approve_mass_sim_change', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_configure_apn', 'can_configure_apn', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_configure_roaming_rules', 'can_configure_roaming_rules', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_create_sim_group', 'can_create_sim_group', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_manage_sim_profile', 'can_manage_sim_profile', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_manage_sim_tariff', 'can_manage_sim_tariff', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_reactivate_sim', 'can_reactivate_sim', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_suspend_sim', 'can_suspend_sim', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_view_connectivity_dashboard', 'can_view_connectivity_dashboard', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_view_connectivity_health', 'can_view_connectivity_health', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_view_roaming_report', 'can_view_roaming_report', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_view_sim_data_spend', 'can_view_sim_data_spend', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system'),
    ('perm_can_view_sim_inventory', 'can_view_sim_inventory', 'NAVAS catalog permission', 'SIM & Connectivity Guard', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Security & HIC Controls (16 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_break_glass_access', 'can_approve_break_glass_access', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_configure_acl', 'can_configure_acl', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_configure_biometric_auth', 'can_configure_biometric_auth', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_configure_curfew_rules', 'can_configure_curfew_rules', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_configure_impossible_travel_alerts', 'can_configure_impossible_travel_alerts', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_configure_rbac', 'can_configure_rbac', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_configure_restricted_zones', 'can_configure_restricted_zones', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_enforce_2fa', 'can_enforce_2fa', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_generate_incident_narrative', 'can_generate_incident_narrative', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_manage_evidence_integrity', 'can_manage_evidence_integrity', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_manage_immobilizer', 'can_manage_immobilizer', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_manage_panic_controls', 'can_manage_panic_controls', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_revoke_all_user_sessions', 'can_revoke_all_user_sessions', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_view_audit_log', 'can_view_audit_log', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_view_security_incident', 'can_view_security_incident', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system'),
    ('perm_can_view_suspicious_login_alerts', 'can_view_suspicious_login_alerts', 'NAVAS catalog permission', 'Security & HIC Controls', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Sensors & Parameter Library (12 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_acknowledge_sensor_alert', 'can_acknowledge_sensor_alert', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_calibrate_sensor', 'can_calibrate_sensor', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_configure_sensor_group_threshold', 'can_configure_sensor_group_threshold', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_configure_sensor_threshold', 'can_configure_sensor_threshold', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_create_sensor_template', 'can_create_sensor_template', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_delete_sensor_template', 'can_delete_sensor_template', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_edit_sensor_template', 'can_edit_sensor_template', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_manage_virtual_sensor', 'can_manage_virtual_sensor', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_map_sensor_to_asset', 'can_map_sensor_to_asset', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_view_sensor_data_quality', 'can_view_sensor_data_quality', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_view_sensor_health', 'can_view_sensor_health', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system'),
    ('perm_can_view_sensor_library', 'can_view_sensor_library', 'NAVAS catalog permission', 'Sensors & Parameter Library', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Settings & Localization (14 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_bulk_manage_settings', 'can_bulk_manage_settings', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_configure_ai_behavior', 'can_configure_ai_behavior', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_configure_approval_workflow', 'can_configure_approval_workflow', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_configure_currency', 'can_configure_currency', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_configure_localization', 'can_configure_localization', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_configure_measurement_units', 'can_configure_measurement_units', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_configure_notification_settings', 'can_configure_notification_settings', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_configure_org_defaults', 'can_configure_org_defaults', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_configure_timezone', 'can_configure_timezone', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_disable_app', 'can_disable_app', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_enable_app', 'can_enable_app', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_manage_api_tokens', 'can_manage_api_tokens', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_manage_regional_settings', 'can_manage_regional_settings', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system'),
    ('perm_can_view_app_renewal_settings', 'can_view_app_renewal_settings', 'NAVAS catalog permission', 'Settings & Localization', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Staff Patrol (11 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_patrol_checkpoint', 'can_configure_patrol_checkpoint', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_configure_welfare_timer', 'can_configure_welfare_timer', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_create_patrol_route', 'can_create_patrol_route', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_edit_patrol_route', 'can_edit_patrol_route', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_export_patrol_data', 'can_export_patrol_data', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_manage_distress_workflow', 'can_manage_distress_workflow', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_manage_patrol_schedule', 'can_manage_patrol_schedule', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_view_patrol_audit_trail', 'can_view_patrol_audit_trail', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_view_patrol_compliance', 'can_view_patrol_compliance', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_view_patrol_coverage', 'can_view_patrol_coverage', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system'),
    ('perm_can_view_patrol_dashboard', 'can_view_patrol_dashboard', 'NAVAS catalog permission', 'Staff Patrol', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Tasks & Maintenance (19 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_parts_requisition', 'can_approve_parts_requisition', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_assign_task', 'can_assign_task', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_bulk_manage_tasks', 'can_bulk_manage_tasks', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_cancel_task', 'can_cancel_task', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_close_task', 'can_close_task', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_configure_maintenance_triggers', 'can_configure_maintenance_triggers', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_configure_task_templates', 'can_configure_task_templates', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_create_maintenance_interval', 'can_create_maintenance_interval', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_create_task', 'can_create_task', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_edit_maintenance_interval', 'can_edit_maintenance_interval', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_edit_task', 'can_edit_task', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_export_service_history', 'can_export_service_history', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_manage_job_card', 'can_manage_job_card', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_manage_service_intervals', 'can_manage_service_intervals', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_schedule_maintenance', 'can_schedule_maintenance', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_view_maintenance_dashboard', 'can_view_maintenance_dashboard', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_view_predictive_maintenance', 'can_view_predictive_maintenance', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_view_task', 'can_view_task', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system'),
    ('perm_can_view_workshop_kanban', 'can_view_workshop_kanban', 'NAVAS catalog permission', 'Tasks & Maintenance', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Token Wallet & Billing (18 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_allocate_tokens', 'can_allocate_tokens', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_approve_manual_token_allocation', 'can_approve_manual_token_allocation', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_approve_token_override', 'can_approve_token_override', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_configure_token_caps', 'can_configure_token_caps', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_configure_token_fifo', 'can_configure_token_fifo', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_create_token_bundle', 'can_create_token_bundle', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_edit_token_bundle', 'can_edit_token_bundle', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_manage_emergency_topup', 'can_manage_emergency_topup', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_manage_split_billing', 'can_manage_split_billing', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_pause_token_consumption', 'can_pause_token_consumption', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_resume_token_consumption', 'can_resume_token_consumption', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_simulate_token_usage', 'can_simulate_token_usage', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_topup_tokens', 'can_topup_tokens', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_transfer_tokens', 'can_transfer_tokens', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_view_billing_ledger', 'can_view_billing_ledger', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_view_token_balance', 'can_view_token_balance', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_view_token_burn_rate', 'can_view_token_burn_rate', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system'),
    ('perm_can_view_token_forecast', 'can_view_token_forecast', 'NAVAS catalog permission', 'Token Wallet & Billing', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Trailer Pairing (4 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_trailer_pairing_rules', 'can_configure_trailer_pairing_rules', 'NAVAS catalog permission', 'Trailer Pairing', 'engine', 'system'),
    ('perm_can_pair_trailer', 'can_pair_trailer', 'NAVAS catalog permission', 'Trailer Pairing', 'engine', 'system'),
    ('perm_can_unpair_trailer', 'can_unpair_trailer', 'NAVAS catalog permission', 'Trailer Pairing', 'engine', 'system'),
    ('perm_can_view_trailer_pairing_history', 'can_view_trailer_pairing_history', 'NAVAS catalog permission', 'Trailer Pairing', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Trailers (12 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_assign_trailer_to_job', 'can_assign_trailer_to_job', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_assign_trailer_to_route', 'can_assign_trailer_to_route', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_bulk_manage_trailers', 'can_bulk_manage_trailers', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_configure_trailer_sensor', 'can_configure_trailer_sensor', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_create_trailer', 'can_create_trailer', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_delete_trailer', 'can_delete_trailer', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_edit_trailer', 'can_edit_trailer', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_manage_subcontracted_trailer', 'can_manage_subcontracted_trailer', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_manage_trailer_documents', 'can_manage_trailer_documents', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_view_trailer', 'can_view_trailer', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_view_trailer_health', 'can_view_trailer_health', 'NAVAS catalog permission', 'Trailers', 'engine', 'system'),
    ('perm_can_view_trailer_utilization', 'can_view_trailer_utilization', 'NAVAS catalog permission', 'Trailers', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Training & Knowledge Center (12 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_assign_training', 'can_assign_training', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_configure_coaching_reminders', 'can_configure_coaching_reminders', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_configure_remedial_training_triggers', 'can_configure_remedial_training_triggers', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_create_training_plan', 'can_create_training_plan', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_edit_training_plan', 'can_edit_training_plan', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_export_training_data', 'can_export_training_data', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_manage_policy_acknowledgements', 'can_manage_policy_acknowledgements', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_schedule_training_event', 'can_schedule_training_event', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_track_certification', 'can_track_certification', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_upload_training_document', 'can_upload_training_document', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_view_training_compliance', 'can_view_training_compliance', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system'),
    ('perm_can_view_training_record', 'can_view_training_record', 'NAVAS catalog permission', 'Training & Knowledge Center', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Trip Replay & Audit (9 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_cinematic_playback', 'can_configure_cinematic_playback', 'NAVAS catalog permission', 'Trip Replay & Audit', 'engine', 'system'),
    ('perm_can_export_trip_data', 'can_export_trip_data', 'NAVAS catalog permission', 'Trip Replay & Audit', 'engine', 'system'),
    ('perm_can_impersonate_user_for_support', 'can_impersonate_user_for_support', 'NAVAS catalog permission', 'Trip Replay & Audit', 'engine', 'system'),
    ('perm_can_view_ai_audit_log', 'can_view_ai_audit_log', 'NAVAS catalog permission', 'Trip Replay & Audit', 'engine', 'system'),
    ('perm_can_view_fuel_reconciliation_audit', 'can_view_fuel_reconciliation_audit', 'NAVAS catalog permission', 'Trip Replay & Audit', 'engine', 'system'),
    ('perm_can_view_score_override_audit_log', 'can_view_score_override_audit_log', 'NAVAS catalog permission', 'Trip Replay & Audit', 'engine', 'system'),
    ('perm_can_view_token_audit_log', 'can_view_token_audit_log', 'NAVAS catalog permission', 'Trip Replay & Audit', 'engine', 'system'),
    ('perm_can_view_trip_event_markers', 'can_view_trip_event_markers', 'NAVAS catalog permission', 'Trip Replay & Audit', 'engine', 'system'),
    ('perm_can_view_trip_replay', 'can_view_trip_replay', 'NAVAS catalog permission', 'Trip Replay & Audit', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Users & Permissions (17 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_assign_role', 'can_assign_role', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_bulk_export_users', 'can_bulk_export_users', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_bulk_import_users', 'can_bulk_import_users', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_create_user', 'can_create_user', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_deactivate_user', 'can_deactivate_user', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_delete_user', 'can_delete_user', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_edit_user', 'can_edit_user', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_invite_user', 'can_invite_user', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_manage_branch_user', 'can_manage_branch_user', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_manage_delegated_admin', 'can_manage_delegated_admin', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_manage_user_permissions', 'can_manage_user_permissions', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_provision_user_from_directory', 'can_provision_user_from_directory', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_recertify_access', 'can_recertify_access', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_reset_user_password', 'can_reset_user_password', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_review_access', 'can_review_access', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_view_dormant_user_report', 'can_view_dormant_user_report', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system'),
    ('perm_can_view_user', 'can_view_user', 'NAVAS catalog permission', 'Users & Permissions', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: VEBA Booking & Escrow (8 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_booking', 'can_approve_booking', 'NAVAS catalog permission', 'VEBA Booking & Escrow', 'engine', 'system'),
    ('perm_can_cancel_booking', 'can_cancel_booking', 'NAVAS catalog permission', 'VEBA Booking & Escrow', 'engine', 'system'),
    ('perm_can_configure_booking_rules', 'can_configure_booking_rules', 'NAVAS catalog permission', 'VEBA Booking & Escrow', 'engine', 'system'),
    ('perm_can_create_booking', 'can_create_booking', 'NAVAS catalog permission', 'VEBA Booking & Escrow', 'engine', 'system'),
    ('perm_can_reject_booking', 'can_reject_booking', 'NAVAS catalog permission', 'VEBA Booking & Escrow', 'engine', 'system'),
    ('perm_can_release_escrow_funds', 'can_release_escrow_funds', 'NAVAS catalog permission', 'VEBA Booking & Escrow', 'engine', 'system'),
    ('perm_can_view_booking', 'can_view_booking', 'NAVAS catalog permission', 'VEBA Booking & Escrow', 'engine', 'system'),
    ('perm_can_view_booking_audit_trail', 'can_view_booking_audit_trail', 'NAVAS catalog permission', 'VEBA Booking & Escrow', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Veba Booking (16 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_booking_request', 'can_approve_booking_request', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_book_asset', 'can_book_asset', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_browse_asset_listings', 'can_browse_asset_listings', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_configure_hire_rates', 'can_configure_hire_rates', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_configure_insurance_verification', 'can_configure_insurance_verification', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_configure_kyc_verification', 'can_configure_kyc_verification', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_create_asset_listing', 'can_create_asset_listing', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_edit_asset_listing', 'can_edit_asset_listing', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_manage_booking_session', 'can_manage_booking_session', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_manage_operator_assignment', 'can_manage_operator_assignment', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_reject_booking_request', 'can_reject_booking_request', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_start_booking', 'can_start_booking', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_stop_booking', 'can_stop_booking', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_view_booking_revenue_forecast', 'can_view_booking_revenue_forecast', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_view_booking_schedule', 'can_view_booking_schedule', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system'),
    ('perm_can_view_marketplace_dashboard', 'can_view_marketplace_dashboard', 'NAVAS catalog permission', 'Veba Booking', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Waswa AI & System Health (12 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_access_waswa_ai', 'can_access_waswa_ai', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_approve_ai_action', 'can_approve_ai_action', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_configure_ai_approval_gates', 'can_configure_ai_approval_gates', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_configure_ai_automation', 'can_configure_ai_automation', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_configure_ai_cascade_rules', 'can_configure_ai_cascade_rules', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_manage_ai_token_caps', 'can_manage_ai_token_caps', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_query_ai_natural_language', 'can_query_ai_natural_language', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_view_ai_cost', 'can_view_ai_cost', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_view_ai_inference_health', 'can_view_ai_inference_health', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_view_billing_reconciliation', 'can_view_billing_reconciliation', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_view_system_health', 'can_view_system_health', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system'),
    ('perm_can_view_system_health_by_country', 'can_view_system_health_by_country', 'NAVAS catalog permission', 'Waswa AI & System Health', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: Workshop Garage (14 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_approve_cost_estimate', 'can_approve_cost_estimate', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_close_job_card', 'can_close_job_card', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_configure_workshop_kanban', 'can_configure_workshop_kanban', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_create_job_card', 'can_create_job_card', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_edit_job_card', 'can_edit_job_card', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_manage_bay_scheduling', 'can_manage_bay_scheduling', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_manage_outsourced_job', 'can_manage_outsourced_job', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_manage_quality_control_checklist', 'can_manage_quality_control_checklist', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_manage_repair_manual', 'can_manage_repair_manual', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_track_mechanic_productivity', 'can_track_mechanic_productivity', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_view_job_card', 'can_view_job_card', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_view_mechanic_labor_time', 'can_view_mechanic_labor_time', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_view_repeat_fault_analysis', 'can_view_repeat_fault_analysis', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system'),
    ('perm_can_view_workshop_dashboard', 'can_view_workshop_dashboard', 'NAVAS catalog permission', 'Workshop Garage', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Module: eShop & Solution Builder (3 permissions)
INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by)
VALUES
    ('perm_can_configure_eshop_integration', 'can_configure_eshop_integration', 'NAVAS catalog permission', 'eShop & Solution Builder', 'engine', 'system'),
    ('perm_can_create_solution_bundle', 'can_create_solution_bundle', 'NAVAS catalog permission', 'eShop & Solution Builder', 'engine', 'system'),
    ('perm_can_view_eshop_recommendations', 'can_view_eshop_recommendations', 'NAVAS catalog permission', 'eShop & Solution Builder', 'engine', 'system')
ON CONFLICT (permission_uid) DO NOTHING;

-- Verify:
-- SELECT COUNT(*) FROM dll_permissions WHERE account_root = 'engine' AND permission_name LIKE 'can\_%' ESCAPE '\';
-- Expected: 531
