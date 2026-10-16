-- 051_file_alerts_by_client.sql
--
-- Alerts and geofences are read by client (account_root): the fleet summary,
-- the OLIWA console and the OLIWA app all ask for the client. They were
-- written under whichever id the writer had — an alert under the owner of the
-- rule that raised it (rules are created under the user's account_uid), a
-- zone under the login that drew it — so those rows were filed where nobody
-- reads. The writers now file by client (endpoints/owner_root.py); this moves
-- the rows written before.
--
-- Only rows owned by a login whose account_root differs are touched. Safe to
-- run again: a moved row's owner is a root, which no login's account_uid
-- matches with a different root, so the second run changes nothing.
-- Event rules (dll_device_events.owner_org_uid) stay with their creator.

UPDATE dll_event_notifications n
   SET owner_uid = r.account_root
  FROM dll_access_relay r
 WHERE r.account_uid = n.owner_uid
   AND COALESCE(r.account_root, '') <> ''
   AND r.account_root <> n.owner_uid;

UPDATE dll_geozones z
   SET geozone_owner = r.account_root
  FROM dll_access_relay r
 WHERE r.account_uid = z.geozone_owner
   AND COALESCE(r.account_root, '') <> ''
   AND r.account_root <> z.geozone_owner;
