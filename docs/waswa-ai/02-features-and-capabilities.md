# 2. Features and Capabilities

[← Index](README.md) · Status labels: ✅ Verified · 🟢 Built · 🟡 Partial · ⛔ Not built · 📋 Plan only

## 2.1 What customers can ask about

Waswa answers by calling read-only "tools" (`navas-core-apis/endpoints/assistant.py:110-111`). Each tool is listed below with what it gives the customer.

| Capability | What the user gets | Data used | Status |
|---|---|---|---|
| **Token balance and tracking time left** | Wallet tokens, packs awaiting use, time left (1 token = 1 hour), worded the same as the dashboard | Token accounts (account context) | ✅ `tests/test_tracking_time_left.py`, `test_wallet_owner.py` |
| **Find a vehicle** | Match by plate, name, VIN, make or IMEI; asks "which one?" if ambiguous | Device registry (`unit_find`) | ✅ `tests/test_waswa_fleet.py` |
| **Vehicle status / "why is it offline?"** | Last heartbeat, last position, billing status, pause rules, trip in progress | `unit_status` | ✅ `test_waswa_fleet.py` |
| **Fleet-wide liveness** | Which vehicles are reporting or silent, and which could not be read (a failed read is never counted as "offline") | `fleet_liveness`, up to 120 units | ✅ `tests/test_fleet_liveness.py` |
| **Trips** | Trips for a vehicle over up to 31 days; the same source as the Trips report | `unit_trips` | ✅ `test_waswa_fleet.py` |
| **Fleet activity** | Trips and kilometres per vehicle over recent days | `fleet_activity` | 🟢 (the model is told it covers 7 days by default; it actually covers 2, see Known Issues) |
| **Places along a route** | Places passed, optionally only where speeding | `unit_route_probe` + Google Places | 🟢 Needs `GOOGLE_MAPS_API_KEY`; capped at 25 look-ups |
| **Alerts** | Recent alerts with severity and read state | `alerts_recent` | ✅ `tests/test_alerts_tool.py` |
| **Geofences** | Zones, their shape, and which vehicles are inside now | `geofences_list` | ✅ `tests/test_waswa_geofences.py` (wording only) |
| **Payments standing** | Counts and totals of recorded payments by status; explicitly "not a credit assessment" | Account context | ✅ `tests/test_payment_standing.py` |
| **Empty-account guidance** | When there are no tokens or products, points to recorded payments without guessing what "pending" means | Account context | ✅ `tests/test_zero_state.py` |
| **How the OLIWA app works** | Step-by-step guidance from 31 app-guide articles | `app_guide_search` | ✅ eval questions; 🟡 guide is partly out of date (see Known Issues) |
| **How things work / policy / billing** | Answers from approved documents | `knowledge_search` | ✅ eval questions; customers only see documents marked for "everyone" |
| **Products and compatibility** | Find, compare and check products against existing hardware. **No prices.** | Product catalogue tables | ✅ `tests/test_product_search_words.py`, `test_waswa_ivms_lookup.py` |
| **Product recommendations** | Up to two suggested products when a customer describes a need; cheaper options (pause, auto-renew off, VEBA) when cost is raised | Prompt instruction | 🟡 Conflicts with the system prompt, which says not to raise sales (see Handover) |
| **Pricing and discounts** | Always a polite hand-off to sales; never reaches the AI model. Questions about the customer's *own* charges are still answered | Rule-based filter (also catches Swahili "bei gani", "gharama") | ✅ `tests/test_pricing_gate.py` |
| **Report requests (mobile)** | The user describes a report in words; Waswa fills in the Reports form (type, dates, vehicles) and generates it | Chat endpoint + app-side parsing | 🟡 Labelled **BETA** in the app; no automated test of the parsing |
| **Token-buying help (mobile)** | A separate "Ask AI" chat on Token Billing that turns package names in a reply into **Buy** cards | Chat endpoint | 🟡 Not tested; ignores the user's Waswa ON/OFF switch |

## 2.2 Conversation features

| Feature | Status | Notes |
|---|---|---|
| Follow-up questions in the same thread | ✅ | The server keeps history and replays the last 10 messages; mobile tests cover the threading |
| Conversation resumes within 60 minutes | 🟢 | Same surface, last activity within 60 minutes (`waswa_data_api.py:209-242`) |
| "New conversation" | ✅ | Header ⋮ menu in the app |
| Conversation history list in the app | ⛔ | History lives in memory only; it is lost on sign-out or app restart |
| Archive / restore conversation | 🟡 | Backend console only (staff). No mobile UI. Conversations are never deleted |
| Screen awareness ("Context: Live Tracking") | 🟢 | 23 app screens tell Waswa which screen the user is on |
| Suggested questions | 🟢 | 4 quick chips + 6 suggestions sheet |
| Answer feedback (Helpful / Not helpful) | ✅ | "Not helpful" creates an item in the staff review queue |
| "Verified answer" badge | ✅ | Shown when a staff-approved correction was used |
| ON/OFF switch | ✅ | The user can switch Waswa off; it is remembered on the device |
| Rich formatting (tables, links, lists) | 🟡 | Only **bold** and *italic* are styled; links are not tappable |
| Streaming (words appear as typed) | ⛔ | The whole answer arrives at once; up to 90 s wait |
| Voice, images, attachments | ⛔ | — |
| Languages other than English | ⛔ | No language handling. The pricing filter recognises two Swahili phrases only |

## 2.3 Staff and back-office features

| Feature | Status | Notes |
|---|---|---|
| Staff-only knowledge and source references | ✅ | Staff see internal documents and a "Source:" line |
| Look up any client's fleet (staff) | 🟢 | Staff can name a client in chat; customers are always pinned to their own account |
| Review queue (flags, pending corrections, re-checks, new documents) | 🟢 | `GET /assistant/console/queue` |
| Write a correction ("verified answer") | 🟢 | Draft → submit → approve. Currency amounts are refused |
| Two-person approval | ✅ | Nobody can approve their own correction (enforced in code **and** database). "Policy" topics need two approvers |
| Corrections expire for re-check | 🟢 | After 180 days, or when their source document changes |
| Document library: upload PDF, Word, Excel, Markdown, text | 🟢 | Max 25 MB; prices are automatically blanked out; no OCR for scanned PDFs |
| Document versioning and approval | 🟢 | A new version goes live only after approval; the old version keeps answering until then |
| Remove / restore a document | 🟡 | Works, but there is no way to roll back to a previous version (see Known Issues) |
| OLIWA app guide sync | 🟢 | Manual sync works; the automatic CI sync is **not active** |
| Read all customer conversations | 🟢 | Reviewers can see every tenant's conversations (see Security) |
| Preview what a question would match | 🟢 | `GET /assistant/console/match` |
| Audit trail | 🟢 | Every console change goes to a transparency log and a tamper-evident audit log |

## 2.4 What Waswa cannot do

These limits are deliberate, by current design:

- **No actions.** Waswa cannot pause tracking, buy tokens, change settings, contact anyone, or immobilise a vehicle. All 15 tools are read-only.
- **No prices or discounts.** There is no price book connection (Odoo is not wired in).
- **No live push.** Waswa answers only when asked; it does not monitor events or send alerts.

## 2.5 Designed in the database but not built

| Item | Where it exists | Status |
|---|---|---|
| **Gated actions**: about 30 sales/ops actions with approval levels (e.g. schedule demo, send reminder, approve discount) | `database/migrations/033_waswa_gated_actions.sql`, `endpoints/waswa_gating.py` | ⛔ No code calls it. Waswa cannot perform any of these, even "automatic" level-0 ones. 11 sensitive actions have no approver assigned |
| Offers / opportunity tracking | `dll_waswa_offers` table (migration 030) | ⛔ Never written |
| Customer class (Diamond…Bronze) | Migration 031 | 🟡 Column exists; never filled automatically |
| Local / cheaper model tier | `router_tier = 2` | ⛔ |
| Semantic (meaning-based) search | `embedding` columns (migration 035) | ⛔ Reserved; search is keyword-based |
| Token burn rate | Account context | ⛔ Always "not measured yet" |
| RBAC permissions "Can chat with Waswa", "Can access Waswa AI", "Can view AI cost", etc. | Migrations 013 and 018 | ⛔ Appear in the permissions catalogue but are **not enforced**: switching them off has no effect |
