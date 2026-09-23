# SECTION 1 — FRONT MATTER + OPERATING FOUNDATION (LANDSCAPE)

# TABLE OF CONTENTS

## PART A — CMS ADMIN FUNDAMENTALS
1. Introduction & Operating Principles
2. NAVAS CMS vs Monitoring Portals (OLIWA/PIKI/VEBA) — What Admins Own
3. UI Navigation Model (Nav Rail, Sidebar, Workspace, Blades/Drawers)
4. Account Hierarchy & Multi‐Tenancy (Top Account → Dealer → Client)
5. RBAC & Access Governance (Least Privilege + HIC Controls)
6. Audit, Logs, and "Trash / Restore" Governance
## PART B — PRODUCT + APP PROVISIONING
1. 3D Product Portfolio Alignment (UG/KE) — Admin Provisioning Rules
2. Apps Library & Provisioning (Add‐On Apps, Feature Flags, Dependencies)
3. Configuration Standards by Product Domain (OLIWA, UKO, PIKI, PATROL, PASO, VEBA)
## PART C — TOKENOMICS, BILLING, PAYMENTS
1. Token Engine Fundamentals (FIFO, Usage Events, Ledger)
2. Token Catalog (What is Billable + Rule DSL Concepts)
3. Billing Plans / Token Bundles (Country‐sensitive pricing: UG vs KE)
4. Wallets, Top‐Ups, and Mobile Money Rails (M‐Pesa / MTN / Airtel)
5. Quoting, Simulation, and Dispute Resolution (Finance‐safe controls)
## PART D — DEVICES, DATA, AND TELEMATICS OPERATIONS
1. Device & Asset Onboarding (Units, SIMs, Install Standards)
2. Sensors & Inputs (Fuel, Temperature, CANBUS, MDVR, Personnel Tags)
3. Events, Alerts, Alarms & Notifications (Multi‐Channel)
4. Reporting, BI Dashboards, Exports, and Compliance Packs
5. Integrations & APIs (OEM, ERP, GIS, JMS, Partner Systems)
## PART E — AI + HIC (HUMAN IN CONTROL)
1. Waswa AI Console — Safe Automation Rules (HITL/HIC)
2. AI for Customer Experience (Proactive Ops, Leakage Prevention, CSAT)
3. AI for Risk (Fraud, Misuse, Safety, Incident Detection)
## PART F — PLATFORM OPERATIONS
1. System Health, SLAs, MTTR, and Incident Operations
2. Preventative Maintenance (Platform + Devices) ✅
3. Corrective Maintenance (Troubleshooting, Recovery, Post‐Mortems) ⚠
4. Backups, DR, and Business Continuity
## PART G — APPENDICES
1. Checklists (Daily/Weekly/Monthly Admin Routines)
2. Templates (Provisioning, RBAC, Billing Dispute, Incident Notes)
3. TABLE OF ACRONYMS & ABBREVIATIONS *(Mandatory — end of document)*

--- PAGE BREAK ---
# DOCUMENT CONTROL

## Document Metadata
Table formatting instruction: Remove borders  and shade the header row only (#F5F5F5).
| Field | Value |
| Document Title | NAVAS – CMS System Administration User Manual (3D Services Limited) |
| Audience | System Administrators, Dealer Admins, Platform Admins |
| Markets | Uganda o and Kenya a |
| System | NAVAS IoT System — CMS Module |
| Version | v1.0 (Serial Release Manual) |
| Effective Date | 01.MAR. 2026 |
| Owner | 3D Services Limited |
| Confidentiality | Internal Use / Controlled Distribution |

## Change Log
| Version | Date | Author/Role | Summary of Changes |
| v1.0 | 01.MAR. 2026 | System Administration Trainer (EA) | Initial full manual structure + operating foundation |

--- PAGE BREAK ---
# INTRODUCTION & OPERATING PRINCIPLES

## 1.1 Purpose of This Manual
Purpose: This manual defines the mandatory procedures and controls for administering the NAVAS CMS (Customer/Service Management System) for 3D Services Limited across Uganda and Kenya. ✅
You are a seasoned telematics administrator. Therefore:
1. We will not explain telematics basics.
2. We will define the NAVAS‐specific governance, module workflows, and HIC/AI operational discipline required to prevent revenue leakage, service instability, and security breaches.
## 1.2 What "CMS" Means in NAVAS (and Why It Matters)
NAVAS operates as a monetizable IoT infrastructure platform, not "just tracking." The administrator's role is to run CMS as a revenue governance layer over live telematics operations.
In practical terms, CMS MUST enable you to:
 - enforce multi‐tenancy and RBAC,
 - provision products/apps consistently,
 - operate token billing fairly and audibly,
 - control payments + top‐ups,
 - maintain system health and disciplined support response times (MTTR). ✅
## 1.3 NAVAS Technical Stack Context (Why Admins Must Care)
Context: Your admin actions are applied across a high‐velocity data pipeline. NAVAS uses:
 - Python sockets for ingestion,
 - Kafka streaming,
 - Node.js producer/consumer orchestration,
 - Cassandra (high‐write telemetry),
 - PostgreSQL (audit trails, accounts, RBAC),
 - Redis caching for low‐latency UI,
 - React/React Native front‐end experience. ✅
✅ Operational implication:
1. RBAC/audit actions are not cosmetic—they bind to PostgreSQL audit trails and must survive disputes.
2. Live system health is latency-sensitive—bad provisioning (e.g., uncontrolled video) can cause cost + performance spikes.
## 1.4 Governance Non‐Negotiables (Read This Twice) ⚠
The following rules are mandatory for all CMS admins:
1. Least Privilege by default
 - Roles MUST be scoped to job function and tenant scope.
2. HIC (Human‐In‐Control) for revenue-impacting changes
 - Token rules, billing plans, wallet edits, and payment rails MUST be gated with approvals and audit trails.
3. A single source of truth for "who changed what"
 - Every admin action MUST be traceable (user, time, tenant, object).
4. No "silent changes"
 - Any change that affects a customer's billing, alerts, or visibility MUST be documented and, where applicable, communicated.
✅ Key Takeaway: NAVAS isn't only a platform. It is a contract with the customer. CMS is where you enforce that contract.

--- PAGE BREAK ---
# NAVAS CMS VS. MONITORING PORTALS (OLIWA/PIKI/VEBA)

## 2.1 What CMS Owns (Admin Territory)
NAVAS defines the COCKPIT as the admin "command & control." It explicitly includes:
 - Waswa AI (proactive load prediction + revenue leakage identification),
 - SIM Card Intelligence (cost and data interval governance),
 - strict operational KPIs (MTTR),
 - RBAC + Multi‐Tenancy hierarchical model. ✅
CMS is the control plane for:
1. Tenant creation & hierarchy (top → dealer → customer)
2. RBAC (roles, permissions, scoping)
3. Product/app provisioning (enable/disable features per tenant)
4. Token billing governance (catalog, rules, FIFO logic, ledger integrity)
5. Payment rails & wallet governance (UG/KE)
6. System-wide audit and recovery (trash/restore concept)
7. Support operations (MTTR enforcement, SLA-driven workflows)
## 2.2 What Monitoring Portals Own (Operations Territory)
Monitoring portals (e.g., OLIWA/PIKI/PATROL style UIs) are for:
 - live tracking,
 - dispatch,
 - geofences,
 - reports execution,
 - operational alerts consumption.
This separation aligns with Wialon's split between the management system (CMS Manager) and the monitoring system, where CMS is for top users and dealer users to manage service structure and macro-objects. ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/introduction?utm_source=chatgpt.com))
✅ Operational implication:
 - A fleet operator should not need CMS access to run day‐to‐day monitoring.
 - A dealer admin MUST use CMS to create and govern tenants, plans, and rights.

--- PAGE BREAK ---
# PRODUCT PORTFOLIO ALIGNMENT (3D SERVICES) — ADMIN VIEW

## 3.1 NAVAS Product Domains (Where Products Live)
The NAVAS product stack is deployed across product domains such as:
 - piki.live (PIKI – Motorcycles)
 - oliwa.live (OLIWA – Vehicles)
 - uko.live (UKO – Vehicles)
 - staffpatrol.live (PATROL – Field Staff)
 - paso.live (PASO – Parcels/Goods)
 - veba.live (VEBA – Bookings/Marketplace) ✅【351:5†Navas_IoT_Products - Summary.pdf†L4-L19】
✅ Admin directive: CMS provisioning Mder one governance umbrella, not as separate "mini systems."
## 3.2 3D Product Portfolio (Service Types → Products)
Table formatting instruction: Remove borders  and shade the header row only (#F5F5F5).
| Service Type | Products (Must be provisionable via CMS) |
| AI & Video Telematics | DASH AI, DASHCAM, MDVR, MDVR AI |
| Fuel Telematics | MAFUTA CANBUS, MAFUTA FLOW METER, MAFUTA FLS, MAFUTA FUEL CARD, MAFUTA STATION, GENSET |
| Goods-in-Transit & IoT | KAGO, PASO, PAWA, THERMO |
| Personnel Tracing | CAPO, PATROL, PIKI, TOTO, WIATAG |
| Add‐On Apps | BI DASHBOARDS, DSC, ECO, FLEETRUN, INSPECTA, JMS, LOGISTICS, NIMBUS, VEBA |
| Value Added Services | HELP DESK & TRAINING, GIS & JMS, SATO, LOCAL OWNED SERVER, OEM SYSTEM INTEGRATIONS |
| Vehicle Telematics | GUVNA, iVMS, iVMS‐PLUS, OLIWA, OLIWA‐PLUS |

✅ Provisioning principle: Each product MUST map to:
1. a tenant scope (UG/KE),
2. a billing/tokens scope (what is billable),
3. an alerts scope (what events are enabled),
4. a support scope (SLA class, escalation rules),
5. an integration scope (APIs, webhooks, 3rd party systems).

--- PAGE BREAK ---
# UI NAVIGATION MODEL (NAVAS CMS)

## 4.1 The CMS Layout Pattern (Non‐Negotiable UX)
NAVAS CMS uses an Azure‐WhatsApp hybrid layout consisting of:
1. Nav rail (icon rail, persistent)
2. Accordion sidebar (module groups)
3. Main workspace (tables, cards, filters)
4. Right blade/drawer (detail view + wizards) ✅【333:3†CMS Mockup Redesign Request.txt†L1-L10】
This is not cosmetic—it enforces predictabtandard Strip (The Admin "Status & Context Bar")
The Standard Strip MUST show:
 - Tenant selector (top account / dealer / customer scope)
 - RBAC badge (current role)
 - Token details (wallet/burn state)
 - System Health (green/yellow/red) ✅【333:3†CMS Mockup Redesign Request.txt†L4-L9】
✅ Admin tactic (speed): Always confirm in disasters" are simply edits done in the wrong tenant. ⚠
## 4.3 CRUD as a Discipline (Create, Read, Update, Delete)
Every module in CMS MUST implement consistent CRUD patterns:
1. Create
 - Create buttons must be explicit (e.g., + New App, + New Account, + New Token).
2. Read
 - Tables are the default "read" surface.
 - Blades/drawers provide detail read views.
3. Update
 - Updates should be done in a blade/drawer with explicit Save and Cancel.
 - High-impact updates must require HIC confirmation.
4. Delete
 - Deletion MUST be soft-deletion whenever possible, using a Trash concept and restore capability.
 - This aligns with "restore deleted objects from trash" being a core CMS function in comparable systems. ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/introduction?utm_source=chatgpt.com))

--- PAGE BREAK ---
# ACCOUNT HIERARCHY & MULTI‐TENANCY FOUNDATION

## 5.1 NAVAS Account Types (Aligned to Wialon‐Style CMS)
NAVAS explicitly structures accounts as:
 - Top account
 - Account with dealer rights
 - Account without dealer rights ✅【333:1†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L71-L89】
This mirrors the recommended hierarchy discipline used in Wialon Hosting, where a service structure of at least ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/configuring-service-structure?utm_source=chatgpt.com))
## 5.2 Top Account (Service Owner) — What It Can and Cannot Do
Special capabilities: The top account is the system owner plane. It includes special features such as:
 - creating billing plans,
 - adding and configuring apps,
 - restoring deleted objects from trash. ✅【333:1†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L111-L118】
Hard restriction: You cannot create units in the top account. ✅【333:1†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L117-L119】
✅ Admin directive:
 - Top account access MUST be restricted to a minimal set of platform adminsrnance account.
This is consistent with Wialon guidance that CMS Managing broad access to top-level control accounts. ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/configuring-service-structure?utm_source=chatgpt.com))
## 5.3 Dealer Rights Account — What It Is For
An account with dealer rights can:
 - create and manage subordinate accounts,
 - block them, change rights, control payments, etc. ✅【333:1†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L123-L129】
Wialon guidance also warns it is not recommended to create units in dealer-rights accounts. ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/configuring-service-structure?utm_source=chatgpt.com))
✅ Admin tactic:
Use dealer accounts as commercial + governance layers (tenants, billing, support oversight) — not as places where units/vehicles live.
## 5.4 Accounts Without Dealer Rights — Where Customers Live
Acco- can create users and assign rights within their account,
 - operate units/resources based on assigned permissions. ✅【333:1†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L143-L152】
This matches Wialon's principle that operational users (end users) sit under accounts without dealer rights in the monitoring ecosystem. ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/introduction?utm_source=chatgpt.com))
✅ Admin directive: Create a separate account per client (unless a client explicitly requires sub‐branches). This is also a best‐practice recommended in Wialon service structure design. ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/configuring-service-structure?utm_source=chatgpt.com))
## 5.5 Hierarchy Rules (Absolute Enforcement)
You MUST enforce:
1. A subordinate account cannot([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/configuring-service-structure?utm_source=chatgpt.com))
2. Minimize hierarchy depth unless necessary, to avoid operational slowdown. ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/configuring-service-structure?utm_source=chatgpt.com))
3. Rights must be inherited deliberately—no accidental super-admin sprawl.

--- PAGE BREAK ---
# HIC (HUMAN IN CONTROL) + WASWA AI — GOVERNANCE MODEL

## 6.1 Waswa AI in CMS (What It Is Used For)
Waswa AI is positioned as a proactive co‐pilot to:
 - predict system load,
 - identify revenue leakage in real time. ✅【333:0† NAVAS IOT SYSTEM POLICY_ .pdf†L109-L120】
✅ Admin directive: Waswa AI MAY recommend; it MUST NOT execute revenue-impacting actions without HIC approval (see below).
## 6.2 HIC Control Levels (Mandatory)
CMS actions MUST be classified into one of these control levels:
1. Level 0 — Safe Automation (No Approval Required)
 - Viewing dashboards
 - Running read-only reports
 - Searching logs
 - Previewing token quotes (no purchase, no enforcement)
2. Level 1 — Single‐Admin Confirm (HIC Prompt Required)
 - Enabling/disabling an app for a tenant
 - Adjusting alert routing (e.g., email/WhatsApp templates)
 - Updating integration endpoints (non‐payment)
 - Editing a role permission set in one tenant
3. Level 2 — Two‐Step Approval (Dual Control) ⚠
 - Creating/editing billing plans / token plans
 - Enabling payment rails (M‐Pesa/MTN/Airtel)
 - Editing wallet balances or applying credits
 - Changing token enforcement thresholds or capsss
 - Database retention policy changes
 - System-wide pricing rule changes
 - Mass tenant migrations
 - Video/AI large-scale rollouts
✅ Key Takeaway: The token engine is the economic heart of NAVAS. HIC is the immune system that prevents catastrophic mistakes.
## 6.3 Token Billing — The CMS Admin's Economic Responsibilities
NAVAS token billing is designed as a universal, composable billing engine with:
 - product-agnostic design,
 - signal-level monetization,
 - FIFO consumption,
 - auditable ledger requirements. ✅【351:2†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L75-L117】
The platform token model explicitly requires:
 - FIFO consumption,
 - predictability and fairness controls,
 - auditable ledger. ✅【351:2†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L109-L117】
✅ Admin directive: Token governance MUST be "audit-ready by default." The system MUST withstand disputes, auditors, and scale. ✅【351:6†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L40-L66】
## 6.4 High-Value Signals (Where Revenue Leakage Often Hides)
Some parameters are inherently high value (and high cost), especially:
 - bandwidth usage for streaming video,
 - ADAS/headway monitoring,
 - video snapshots,
 - video events and storage diagnostics. ✅【351:9†Navas - TOKEN_BY_REVENUE.pdf†L10-L44】
✅ Admin tactic (margin protection): Treat AI/video enablement as a controlled rollout with:
1. tenant eligibility rules,
2. token caps/alerts (80% warnings),
3. strict usage reporting,
4. explicit customer consent.
## LY FOUNDATIONS
## 7.1 Why Alerts Matter to System Admins (Not Only Operations)
NAVAS supports an extensive alert ecosystem—y alerts, environmental triggers, and automated incident detection. ✅【351:0†List of Event that Triggers notifications, alerts, alarms.
 - which events are enabled per product,
 - which channels (SMS/WhatsApp/email/in-app) are used,
 - what "default alert policy" applies to a new tenant.
## 7.2 Preventative vs Corrective Maintenance (Admin's Role)
Preventative maintenance: You MUST ensure product and customer type (time-based, mileage-based). ✅【351:0†List of Event that Triggers notifications, alerts, alarms.pdf†L73-L80】
Corrective maintenance: When incidents occur (e.g., crash detection, fuel drop anomalies, device health warnings), admins MUST confirm:
1. the tenant's configuration is correct,
2. the token/wallet state did not suppress features,
3. the notification routing is valid,
4. escalations follow MTTR discipline.
✅ Key Takeaway: Customer experience is usually not lost by "bad tracking." It's lost by bad configuratreply with: "Proceed to Section 2" and I will continue with:
# SECTION 2 — CMS LOGIN, SESSION SAFETY, NAVIGATION DRILLS + ADMIN WORKFLOWS (TOP → DEALER → CLIENT)
# 7. TOKENOMICS & REVENUE

 Trainer's framing (read this once, then execute): NAVAS CMS Tokenomics is not "billing admin". It is revenue governance. Your mandate as System Administrator is to ensure that every measurable value (signal, storage, inference, alerting, reporting, bandwidth) is metered, priced, governed, and auditable — without destroying the customer experience. ✅
This aligns with NAVAS' PAYG token burn model and the principle that billing should be product‐agnostic and composable across NAVAS, Wialon, 3DTracking, and future backends.

## 7.1 Purpose (Non‐Negotiable)
The Tokenomics & Revenue module exists to do five things — and you SHALL run them as discipline, not preference:
1. Define what is billable (at the resolution of a single signal, event, inference, or query).
2. Price it transparently using consistent multipliers (RPS + time + compute + market + scarcity).
3. Enforce entitlements at multiple enforcement points (write/read/compute).
4. Protect margin (AI/video are premium; historical access is priced separately; safeguards prevent surprise bills).
5. Keep customer experience predictable using alerts, caps, hard‐stops, and optional auto‐pause.
✅ Key directive: If NAVAS can observe/calculate/infer/store/transmit/visualize/alert/report on it, it SHALL be billable — default answer is YES.

## 7.2 Where To Find It In CMS (Navigation Map)
In CMS, Tokenomics sits as a top‐level module grouping (consistent with your admin UI patterns):
 - Tokenomics & Revenue
 - Token Engine
 - Billing & Invoicing
 - Payments & Mobile Money
 (Aligned to the CMS navigation grouping used in the provisioning mockups.)
 UI Pattern Reminder: Expect the standard admin layout:
 - Left nav rail / accordion sidebar
 - Main workspace (tables + analytics)
 - Right blade/drawer for detail + approvals
 - Standard Strip: Tenant selector + RBAC badge + token balance/burn + system health ✅

## 7.3 Canonical Concepts (You Must Know These Cold)
*Token Definition:* A reusable commercial rule describing what can be consumed, how it is measured, and how it is priced.
*Subscription Instance:* A runtime purchase bound to a customer + asset/unit + product scope + validity window + consumption state.
*Usage Event:* A factual record that something billable occurred (time elapsed, event triggered, data transmitted, AI inference executed).
*Token Queue (FIFO):* Ordered list of active subscriptions for the same unit consumed sequentially (prevents debt and protects prepaid revenue).
*Revenue Potential Score (RPS):* Pricing multiplier for high‐value signals (e.g., AI, video, compliance). Every billable parameter SHALL have an RPS value.

## 7.4 Token Classes (Final Canonical Set)
NAVAS token classes MUST stay standardized across products, markets, and backends:
| Token Class | What It Bills | Examples (3D Portfolio Alignment) |
| Time Tokens | Access over time | OLIWA/PIKI tracking uptime; PATROL shift tracking |
| Data Tokens | Parameter visibility | Fuel level, temperature, CANBUS decoded fields |
| Event Tokens | Discrete incidents | Ignition, geofence, harsh braking, door open |
| Volume Tokens | Bandwidth/storage | DASHCAM uploads, MDVR streams, media storage |
| AI Tokens | Inference & learning | DASH AI, MDVR AI, fatigue probability inference |
| Insight Tokens | Scores/analytics | Driver risk index, eco score, anomaly signals |
| Action Tokens | Alerts/automation | WhatsApp/SMS alerts, escalation actions |
| Compliance Tokens | Reports/exports | Regulatory reports, audit exports, SLA reporting |
| Marketplace Tokens | Listings/transactions | VEBA listing time, revenue share flows |
| Enterprise Tokens | SLA & guarantees | Premium support SLA tokens, enterprise multipliers |

(Aligned to the token billing policy draft and canonical class list.)
✅ Admin rule: Do not invent "new classes" casually. If something is new, it is either:
 - a new Token Definition,
 - a new rule dimension, or
 - a new SKU bundle — not a new class.

## 7.5 The Token Pricing Engine (What Finance Will Audit You On)
NAVAS pricing follows a multiplicative engine:
TOKEN_PRICE = BASE_UNIT_COST × RPS × TIME_FACTOR × COMPUTE_FACTOR × MARKET_FACTOR × SCARCITY_FACTOR
### 7.5.1 Inputs You Must Maintain
*Technical drivers:* CPU cycles, GPU seconds, storage tier, bandwidth (MB), latency class.
*Commercial drivers:* market (UG/KE/Enterprise), industry, regulatory weight, SLA level.
### 7.5.2 Safeguards You MUST Enforce
 - Monthly caps
 - Hard stop thresholds
 - Soft alerts at 80%
 - Auto‐pause (optional)
⚠ Failure mode: No caps + no hard stops = disputes, churn, reputational damage.
✅ Directive: Every tenant SHALL have an explicit safeguard profile — even if caps are set to "high".
### 7.5.3 Margin Protection Rules (Do Not Break These)
 - GPU‐heavy tokens flagged premium
 - AI tokens non‐discountable by default
 - Video bandwidth priced dynamically
 - Historical access priced separately

## 7.6 Time Discount ≠ Cheap (Uganda vs Kenya Discipline)
Duration tables already discount longer periods; this is good — but never discount AI or video aggressively.
### 7.6.1 Example Time Token Values (Operational Reference)
From the published time‐based token table (PIKI/OLIWA in UGX; PIKI/UKO in KES):
 - 1 Day: PIKI (UG) UGX [amount withheld: pricing], OLIWA (UG) UGX [amount withheld: pricing], PIKI (KE) Ksh [amount withheld: pricing], UKO (KE) Ksh [amount withheld: pricing]
 - 2 Days (discount factor 0.98): PIKI (UG) UGX [amount withheld: pricing], OLIWA (UG) UGX [amount withheld: pricing], PIKI (KE) Ksh [amount withheld: pricing], UKO (KE) Ksh [amount withheld: pricing]
✅ Admin best practice:
 - Maintain separate UG price book and KE price book.
 - Apply enterprise multipliers via MARKET_FACTOR, not via "random discounts".

## 7.7 Token Rule DSL (How NAVAS Answers "YES" Without Code Rewrites)
NAVAS Token Billing uses atomic rule components — meaning a token can bill by WHAT, WHEN, BY, OVER, FOR, APPLY (pricing logic).
### 7.7.1 Rule Pattern (Admin Mental Model)
1. WHAT is billable (parameter, event, inference, stream)
2. WHEN it is billable (contextual conditions)
3. BY which billing unit (hour/event/km/MB/inference)
4. OVER what window (realtime/trip/shift/30 days)
5. FOR which scope (asset type, industry, country, product)
6. APPLY how pricing is calculated (multipliers, caps, discounts)
 Why this matters: you can monetize *new value* (e.g., "ADAS headway monitoring") without rebuilding billing — you register signal, assign RPS, define unit, expose to DSL.

## 7.8 Enforcement Points (Prevent Revenue Leakage)
NAVAS policy requires token enforcement at three points:
 - Write‐time: ingestion/storage authorization
 - Read‐time: UI/API query authorization
 - Compute‐time: AI inference/report generation authorization
✅ Directive: Do not rely on "UI hiding" as enforcement. UI hiding is cosmetic. Enforcement must be systemic.

## 7.9 The NAVAS PAYG Token Burn Logic (How The System Actually Behaves)
NAVAS replaced "monthly subscription" with PAYG token burn aligned to usage.
### 7.9.1 High‐Value vs Standard Signals
 - High‐Value parameters (e.g., video snapshots, ADAS headway monitoring) carry the highest RPS (10+).
 - Standard events (e.g., ignition cycles, geofence triggers) carry lower, high‐volume cost.
### 7.9.2 FIFO Consumption
Tokens are consumed FIFO to prevent debt and protect prepaid revenue.
### 7.9.3 Mobile Money Integration
Direct API hooks exist for instant token top‐ups via M‐Pesa (KE), MTN (UG), Airtel.

## 7.10 Core Admin Pages & CRUD Operations (What You Will Actually Do Daily)
Below is the operational structure. Each subsection includes the cards/blades you will see and the CRUD you must execute.

## 7.10.1 Token Engine (Catalog & Definitions)
### Primary Objects
1. Token Definition
2. Token Class
3. Billing Unit
4. Rule Template (DSL)
5. SKU Bundle (commercial wrapper)
### Standard Cards (Dashboard KPIs)
 - Token revenue (UG vs KE)
 - Burn rate per product
 - Top RPS bands consumed
 - Leakage alerts (unbilled events)
 - "Higher Token Needed" incidents (upsell triggers)
### CRUD — Token Definition
*Create:*
1. Navigate: Tokenomics & Revenue → Token Engine → + New Token Definition
2. Populate:
 - Name + short label
 - Token class (time/event/data/AI/video/...)
 - Scope: product (OLIWA/PIKI/UKO/VEBA/...)
 - Billing unit (hour/event/km/MB/inference)
 - Base unit cost
 - RPS band/multiplier policy
3. Add rule template (DSL)
4. Save as Draft vX.Y (versioned)
5. Submit for approvals (maker–checker)
*Read:*
 - Use filtered tables to inspect usage events, linked SKUs, and affected tenants.
*Update:*
 - Never overwrite a live policy. Create a new version.
 - Apply effective date/time.
*Delete / Archive:*
 - Archive only. Never hard delete revenue objects.
 - Archived items must remain auditable.
✅ Governance directive: Token definitions are controlled by Product + Finance; pricing changes require versioning and audit.

## 7.10.2 Billing & Invoicing (Ledger‐First Discipline)
### Immutable Ledger Requirement
Billing must survive auditors and disputes. Ledger entries must be immutable; adjustments are separate entries.
### Admin Actions
1. Invoice generation controls
 - billing cycles (weekly/monthly) per tenant
 - invoice templates per market (UG/KE)
2. Reconciliation
 - Ledger totals = invoice totals
 - Investigate mismatches immediately
3. Adjustments
 - manual credits, reversals: require reason + approval trail ✅
*HIC enforcement:*
 - You SHALL implement maker–checker for:
 - refund/credit above threshold
 - editing pricing multipliers
 - retroactive billing

## 7.10.3 Payments & Mobile Money (Callbacks and Failure Handling)
NAVAS supports mobile money rails (territory dependent) and maintains callback/webhook monitoring for top‐ups.
### Operational Workflow
1. Enable payment method by tenant (M‐Pesa / MTN / Airtel)
2. Validate callback endpoint status (health = green)
3. Perform test top‐up (small value) and confirm:
 - wallet increment
 - ledger entry created
 - entitlement applied (tokens available FIFO queue updated)
⚠ Corrective maintenance: If callbacks fail:
 - Freeze auto‐pause toggles (to avoid unintended outages)
 - Switch tenant to manual top‐up mode
 - Log incident in Helpdesk with "Billing Callback Failure" category
 - Run replay/reconciliation once rails restore

## 7.11 Human‐In‐Control (HIC) Tactics for Tokenomics ✅
Wialon CMS patterns that matter here (and NAVAS mirrors the intent):
 - Top/dealer admins manage accounts, billing plans, payments, limits, and cost controls centrally. ([Wialon Help Center](https://help.wialon.com/en/wialon-hosting/user-guide/management-system))
 - "Act on behalf"/impersonation is a controlled permission (used for troubleshooting). ([Wialon Help Center](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/users))
### 7.11.1 Maker–Checker (Mandatory)
You SHALL enforce maker–checker on:
 - Token definition publish
 - Market factor updates
 - RPS multiplier changes
 - High‐value refunds/credits
 - Enterprise custom pricing overrides
### 7.11.2 Explainability Requirements
Every change must have:
 - Change reason
 - Ticket reference (Helpdesk ID)
 - "Impact radius" (which tenants/products affected)
 - Rollback plan
✅ Trainer note: This turns your billing into a *QMS‐grade system* — not a "spreadsheet culture".

## 7.12 AI (Waswa AI) Tactics for Tokenomics
NAVAS COCKPIT includes an AI co‐pilot designed to identify revenue leakage and predict system load. 【389:1† NAVAS IOT SYSTEM POLICY_ .pdf†L105-L110】
### 7.12.1 What AI Should Do (Allowed)
 - Detect anomalies: "usage events with no matchinents (draft only)
 - Flag high‐cost patterns (e.g., video streaming spikes)
 - Predict low‐balance churn risk (based on burn rate + top‐up patterns)
### 7.12.2 What AI Must NOT Do (Forbidden Without HIC)
 - Publish pricing changes
 - Issue credits/refunds
 - Disable customer services
 - Retroactively bill
 - Alter ledger entries
✅ HIC rule: AI advises; humans decide; system audits.

## 7.13 Customer Experience Playbook (Token Systems That Don't Anger Customers)
The token strategy explicitly requires predictable and contextual upsell, not surprise blocking. 【385:5†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L15-L22】
### 7.13.1 Low Balance Strategy
You SHALL configure:
 - Soft alerts at 80ATEGY ver26.01.26a (2).pdf†L34-L39】
 - Multi‐step low‐balance alerts (e.g., 30% / 15% / 5%)
 - Grace rules for ment)
### 7.13.2 Contextual Upsell ("Higher Token Needed")
Treat "Higher Token Needed" as:
 - a value signal
 - a guided upgrade path
 - a transparent cost breakdown
 —not as a punishment. 【385:5†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L15-L22】

## 7.14 Preventative & Corrective Maintenance (Billing Health)
###rts
2. Confirm callback success rate (per payment rail)
3. Check top‐10 tenants by burn rate variance
4. Validate that FIFO queues are not stuck (expired subscriptions not clearing)
5. Confirm AI/video premium tokens are not mistakenly discountable 【385:1†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L42-L47】
### Corrective (When Incidents Occur) ⚠
1. Freeze pricing policy publis Run ledger reconciliation
2. Issue adjustments as separate entries (never overwrite) 【385:3†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L46-L65】

## 7.15 Module KPI Targets (What You Will Be Measured On)
You SHALfit by token class
 - Leakage rate (usage without billing)
 - Dispute rate (billing complaints)
 - Time‐to‐detect billing faults (internal MTTR)
(Token audit/reporting expectations are explicitly required.) 【385:1†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L50-L56】

✅ SECTION 7 SUMMARY (Mandatory Takeaways)
 - Tokens are not plans;LLING STRATEGY ver26.01.26a (2).pdf†L54-L70】
 - Pricing is formula‐driven and MUST be governed. 【385:1†NAVAS TOKEN BILLINlity are the revenue backbone. 【385:0†NAVAS TOKEN BILIC approves; audit is sacred. 【389:1† NAVAS IOT SYSTEM PO
# 8. INFRASTRUCTURE & CONNECTIVITY

enters NAVAS and how much it costs — across GPS trackers, IoT sensors, dashcams/MDVRs, and integrations. It includes device onboarding, protocol profiles, SIM intelligence, connectivity policies, and integration endpoints. 【389:1† NAVAS IOT SYSTEM POLICY_ .pdf†L53-L90】
 Trainer directive: In East Africa, the fastest way to lose margin is connectivity leakstorms, wrong bundles). NAVAS explicitly positions SIM intelligence as a system admin console for cost governance. 【389:1† NAVAS IOT SYSTEM POLICY_ .pdf†L111-L113】

## 8.2 NAVAS Data Pipeline (Admin‐Relevant View)
NAVAS runs as a high‐velocity dat(raw packet parsing)
 - Streaming: Apache Kafka (topic navas)
 - Orchestration: Node.js bridging Cassandra writes → Redis cache
 - Fast storage: Cassandra (location + IO parameters)
 - Static storage: PostgreSQL (audit trails, accounts, RBAC)
 - Cache/SSE: Redis for sub‐3s latency to UI
 - Frontend: React/React Native for OLIWA, PIKI, VEBA 【389:1† NAVAS IOT SYSTEM POLICY_ .pdf†L61-L90】
✅ Admin implication:
If live UI is slow, you check Redis/SSE health before blaming devicwrite path and parser mapping before blaming the customer.

## 8.3 Core Pages (Typical) + Why They Matter
1. Device Registry
 - device types, firmware versions, IMEI/unique IDs, provisioning status
2. Protocol & Integration Hub
 - parser configuration, retransmission routes, API keys
3. SIM Card Intelligence
 - roaming cost analysis, data intervals, "nearest bundle" matching for video vs tracking use cases 【389:1† NAVAS IOT SYSTEM POLICY_ .pdf†L111-L113】
4. Connectivity Policies
 - heartbeat expectations, offline thresholds, retry rul(3D Portfolio Mapping)
You SHALL classify provisioning by product family (because cost profile differs):
| Portfolio Group | Products | Typical Data Pattern | Admin Risk |
| Vehicle Telematics | OLIWA / iVMS / iVMS‐PLUS / GUVNA / OLIWA‐PLUS | frequent location + IO | wrong intervals → data cost + customer complaints |
| Personnel Tracing | PIKI / PATROL / CAPO / TOTO / WIATAG | high volume small wallets | top‐up failures → churn |
| Fuel Telematics | MAFUTA (CANBUS/FLS/Flow Meter/Fuel Card/Station) + GENSET | IO + sensor calibration | false fuel theft alarms if calibration wrong |
| AI & Video | DASHCAM / DASH AI / MDVR / MDVR AI | heavy bandwidth + storage + inference | margin collapse if bundles mis‐sized |
| Goods‐in‐Transit & IoT | KAGO / PASO / PAWA / THERMO | sensor bursts + alerts | alert storms and battery drain if misconfigured |

## 8.5 Provisioning A New Device (Safe Default Workflow)
### 8.5.1 Pre‐Provision Checklist
*Prerequisites:*
 - Tenant/account selected (correct ownership)
 - Product scope confirmed (OLIWA vs PIKI vs DASH AI etc.)
 - SIM profile ready (carrier, APN, bundle type)
 - Expected reporting interval defined (by use case)
### 8.5.2 Standard Provisioning Steps (Do This Every Time)
1. Select tenant/account that will own the unit
2. Add device identity in Device Registry (IMEI/unique ID)
3. Assign protocol profile (parser + expected parameters)
4. Attach SIM profile (carrier, APN, roaming rules)
5. Set reporting interval + offline threshold
6. Confirm first data (timestamp + location sanity)
7. Lock configuration after commissioning (reduce drift)
✅ HIC tactic: For video/AI devices, you SHALL require approval before enabling continuous upload (cost impact). This mirrors the governance approach used in structured CMS systems where high‐impact actions are permission‐controlled. ([Wialon Help Center](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/billing-plans))

## 8.6 SIM Card Intelligence (Where Money Leaks Silently)  ̧
NAVAS positions SIM intelligence to analyze roaming costs, data intervals, and bundle matching for specific use cases. 【389:1† NAVAS IOT SYSTEM POLICY_ .pdf†L111-L113】
### 8.6.1 What You Must Monitor
1. Roaming flags
 - cross‐border units (UG↔KE)
2. Interval compliance
 - expected vs actual reporting frequency
3. s → data spikes
4. Bundle mismatch
 - video device on tracking bundle = guaranteed overage
### 8.6.2 Preventative Controls ✅
 - Enforce "bundle template per product" (tracking vs fuel vs video)
 - Set maximum daily data thresholds for non‐video devices
 - Auto‐flag units that exceed baseline by >X%

## 8.7 AI (Waswa AI) for Connectivity Operations
Waswa AI is designed to predict load and identify revenue leakage. 【389:1† NAVAS IOT SYSTEM POLICY_ .pdf†L105-L110】
You SHALL configure AI to:
 - detect abnormal data interval behavior
 - recommend optimal bundles ("nearest bundle") per device use case
 - forecast network congestion an recommend; only humans can apply SIM policy changes to enterprise tenants.

## 8.8 Preventative & Corrective Maintenance Notes (Connectivity)
### Preventative ✅
 - Weekly audit of: reporting intervals, offline thresholds, roaming incidents
 - Firmware/OTA policy review for fleets with repeated dropouts
 - Protocol profile sanity checks after device model additions
### Corrective ⚠
When you see:
 - "No data" but device powered → check APN/bundle/coverage
 - "Wrong location jumps" → confirm parser mapping, time sync
 - "Customer says expensive data" → pull SIM analytics and compare to expected interval; fix root cause

✅ SECTION 8 SUMMARY (Mandatory Takeaways)
 - Infrastructure is a profit center when governed; a cost sink when ignored. 【389:1† NAVAS IOT SYSTEM POLICY_ .pdf†L111-L113】
 - SIM intelligence is not optional in EA markets — it is margin protection. 【389:1† NAVAS IOT SYSTEM POLICY_ .pdf†L111-L113】

 PAGE BREAK — NEXT SECTION
-S SOURCE TRACEABILITY)
According to a document from 20 February 2026, NAVAS v26.0 positions the CMS ("NAVAS Cockpit") as the operational command layer for multi-tenancy, RBAC, monetization via tokens, SIM intelligence, and AI-assisted governance across East Africa (Uganda o and Kenya a).

==================== PAGE BREAK ====================
## SECTION 09 — TOKENOMICS & REVENUE (CMS MODULE GROUP)
 Key takeaway (Non‐Negotiable): NAVAS does not "sell subscriptions." NAVAS sells metered, auditable intelligence. Anything the system observes, computes, infers, stores, transmits, queries, visualizes, or acts upon MUST be billable (directly or via bundled logic).
## 09.1 Token Engine
*Purpose:* The Token Engine is the monetization backbone of NAVAS. It governs token definitions, pricing rules, subscription instances, token consumption (burn), pause/resume, expiry, wallet balances, and service enforcement per product (e.g., OLIWA, PIKI, UKO, VEBA) across territories.
### Blade Navigation (What You See in CMS)
In CMS, the Token Engine is presented as a Blade with standardized Cards. You shall treat each card as an operational control surface with auditable CRUD.
Token Engine — Primary Cards (UI "Cards")
 - Token SKU Catalog ✅
 Create/manage token types, durations, and scopes (product + territory).
 - Billing Rules DSL (Billing Language)
 Define "how value is metered" across any telematics signal.
 - Pricing Profiles & Multipliers
 Apply UG/KE tables, enterprise multipliers, and controlled discounts.
 - Wallets & Ledger 3
 Wallet balance, token lots, FIFO burn, refunds, and adjustments.
 - Subscription Instances 3⁄4
 Bind purchased tokens to asset/product/time window.
 - Enforcement Simulator a
 Test a rule before production (HIC gate).
 - Token Burn Analytics
 Diagnose consumption spikes, leakage, fraud, or misconfiguration.
 - Alerts & Guardrails ⚠
 Thresholds: low balance, abnormal burn, failed payments, lockouts.
✅ System Administrator directive: You shall never implement a billing change directly in production without (1) simulator proof, (2) HIC approval, and (3) rollback plan.

### Token Concepts You Must Master (Authoritative Definitions)
1. Token Definition (SKU)
 A reusable blueprint: *what is sold*.
 Examples:
 - PIKI (UG) 1‐Month Dynamic Token
 - OLIWA (UG) Parameter‐Hybrid Token
 - VEBA Listing Time Token
2. Subscription Instance
 A purchase-created "live contract" that binds tokens to:
 - user
 - asset/unit
 - product (OLIWA/PIKI/UKO/VEBA/etc.)
 - token definition
 - time window (start/end)
3. Dynamic Tokens vs Parameter Tokens vs Hybrid Tokens
 - Dynamic Token: gates *service access by time window* (e.g., live map, trip playback).
 - Parameter Token: gates *specific parameters/events* (e.g., DTC fault codes, fuel flow, ADAS alerts).
 - Hybrid Token: time window + parameter gating (recommended for premium products).
4. Billing Units
 You shall explicitly recognize that billing units ≠ tokens. Billing units are the measurable consumption primitives:
 - per hour / per day
 - per event
 - per km
 - per image / per clip
 - per MB streamed
 - per AI inference
 Tokens are the commercial wrapper over billing units.
5. FIFO Burn
 Tokens are consumed first‐in, first‐out to prevent debt accumulation and ensure clean expiry behavior.

### Core Policy: Value-Based Pricing (What Gets Expensive and Why)
NAVAS token economics is built on a deliberate cross‐subsidy model:
 - Cheap GPS time (high volume, low value)
 - Expensive intelligence (AI, video, compliance, risk scoring)
 - Premium compliance (audits, certified exports, regulated reports)
⚠ Mandatory rule: Long-duration discounts are acceptable, but you shall never discount AI or video aggressively, because those are margin-risk modules.
Practical implication for Admins
 - Keep base tracking affordable (customer retention).
 - Price video/AI/ADAS as premium (profit protection).
 - Use parameter-level gating to upsell without losing historical data ("store but mask").

## 09.1.1 Token Duration Tables (UG & KE) — How to Apply
*Run‐in guidance:* NAVAS uses time-based pricing curves and discount factors across PIKI/OLIWA (UG) and PIKI/UKO (KE).
### Operational steps (CMS)
1. Go to: Token Engine → Pricing Profiles & Multipliers
2. Select Territory:
 - Uganda (UGX) o
 - Kenya (KES) a
3. Select Product Pricing Curve:
 - PIKI curve (high-volume low ARPU)
 - OLIWA/UKO curve (higher value)
4. Confirm Duration Table:
 Validate at least these anchors:
 - 1 Hour
 - 24 Hours / 1 Day
 - 1 Month
 - 12 Months
5. Publish only after simulator confirmation + HIC approval.
### Admin Tactic: "Pricing Anchors" (Do This Every Time)
When you change token pricing, you shall validate anchor math:
 - Compare 1 Day vs 1 Month: ensure month discount is logical.
 - Compare 1 Month vs 3 Months: ensure discount curve is not too steep.
 - Compare PIKI UG vs UKO KE: ensure territory intent remains consistent.

## 09.1.2 Parameter Monetization (Revenue Potential Score)
*Run‐in concept:* NAVAS recognizes that not all telemetry has equal value. High-value parameters (e.g., video snapshots, ADAS headway monitoring) command higher Revenue Potential Scores (RPS).
### How to operationalize RPS inside CMS
You shall treat each parameter category as an opportunity map:
 - High‐Value (RPS 8–10+) ✅
 - Video snapshots
 - ADAS/DSM events (headway monitoring, lane departure, fatigue indicators)
 - DTC fault codes and predictive maintenance
 - Fuel theft indicators and flow meter anomalies
 - Standard (High volume, lower value)
 - ignition cycles
 - geofence entry/exit
 - basic speed events
 Upsell tactic: "Store but mask." If a customer is not entitled to a high-value parameter, keep it stored (for later upgrade) but restrict visibility until token upgrade. This enables retroactive intelligence and reduces churn from "lost data".
### CMS Workflow: Create a Parameter Token SKU
1. Token Engine → Token SKU Catalog → Create New SKU
2. Define:
 - Token Type: Parameter or Hybrid
 - Scope: Product (e.g., MAFUTA / DASHCAM / MDVR AI)
 - Territory: UG or KE
 - Duration options: pick standard ladder (hour/day/month/year)
3. Add Parameter Set:
 - Use the "All Parameter Catalog" reference set (internal list) and choose parameters by value tier.
4. Set "Mask Mode" Policy:
 - If not entitled → hide on UI but retain in data store.
5. Save as Draft (do not publish).
6. Simulator Test (see below).
7. HIC Approval → Publish.

## 09.1.3 Billing Rules DSL (The "Billing Language")
*Run‐in directive:* NAVAS requires a billing language capable of expressing any commercial intent over any signal, at any resolution, and by any value lens.
### Billing Rule Dimensions (Minimum Required Fields)
Every billing rule you create shall specify at least:
1. WHAT (billing target)
 - parameter, event, report export, AI inference, video clip, API call
2. WHO (entity scope)
 - tenant / account / user / asset / group / product
3. WHEN (time window)
 - active token window / business hours / night driving window
4. HOW MUCH (unit rate)
 - tokens per unit (per event, per km, per MB, etc.)
5. APPLY (pricing modifiers)
 - territory (UG/KE), enterprise multiplier, discounts, minimum charges
6. ENFORCE (system behavior)
 - allow, throttle, mask, or block + "Higher Token Needed" upsell.
### CMS Simulator: Mandatory Pre‐Deployment Test a
Before publishing a rule, you shall simulate:
 - Normal driving day (baseline burn)
 - High violation day (overspeed, harsh braking)
 - Video heavy day (streaming + uploads)
 - Cold chain day (THERMO temperature deviation frequency)
 - Fuel theft scenario (rapid fuel drop bursts)
⚠ If simulation results show "uncontrolled burn", the rule is defective and must not pass HIC.

## 09.1.4 Token Enforcement Lifecycle (How Backend Behavior Maps to Admin Actions)
*Run‐in:* Understand enforcement points so you can diagnose disputes accurately. Token checks occur at two primary points:
 - Write-time (store or skip parameter)
 - Read-time (display or block parameter)
### Lifecycle Overview (Admin Mental Model)
1. Admin creates token definition (SKU) in CMS
2. Customer purchase creates a subscription instance bound to user/asset/product/window
3. Device sends data → system parses and stores
4. Token enforcement occurs:
 - Dynamic: service access gating
 - Parameter: allow/store/mask logic
5. UI produces the right behavior:
 - normal view, masked view, upsell prompts, or blocked service.
✅ Admin Standard for dispute handling:
When a customer claims "system stopped", you shall first classify the failure:
 - token expiry
 - token paused
 - low wallet balance
 - payment callback failure
 - device offline / connectivity
 - mis-scoped token (wrong product or territory)

## 09.1.5 HIC Governance for Token Changes (Mandatory Controls)
*Run‐in:* Billing is sensitive; it directly impacts trust. Therefore, token governance uses Human‐In‐Control (HIC) gates.
### HIC Gate Checklist (You shall enforce this) ✅
Before any billing change becomes active, ensure:
1. Draft created with description ("why", "what", "impact")
2. Simulator evidence attached (screenshots/export)
3. Rollback plan recorded
4. Dual approval captured:
 - Approver 1: Finance/Revenue owner
 - Approver 2: Systems owner (Senior Admin)
5. Change window defined:
 - avoid peak hours (customer impact containment)
6. Audit log confirms author, time, approvals, publish event
 CX tactic: Every published token policy change must have a customer-facing notice drafted (simple language), including "what changed" and "how to avoid service interruption." This reduces disputes and raises confidence.

## 09.1.6 AI Support in Tokenomics (Waswa AI)
*Run‐in:* NAVAS v26.0 uses Waswa AI to detect leakage and optimize costs, operating on a tiered approach to control inference spend.
### What Waswa AI is allowed to do (and what it is NOT allowed to do)
Allowed (Suggest-only unless explicitly configured):
 - Identify abnormal burn patterns
 - Recommend product upsells based on usage
 - Recommend SIM bundles for video vs GPS-only use cases
 - Detect revenue leakage (unbilled high-value features)
Not allowed without HIC approval:
 - Publishing token rules
 - Adjusting pricing multipliers
 - Issuing refunds or credits
 - Suspending a tenant
### AI + HIC Tactic: "Suggestion → Approval → Execution"
1. AI generates a recommendation
2. System Admin reviews evidence (usage charts, event logs)
3. Admin approves and triggers execution
4. Audit trail records: recommendation + approver + action

## 09.1.7 Preventative & Corrective Maintenance (Token Engine)
### Preventative Controls (Weekly) ✅
 - Review Top 10 burn spikes by tenant
 - Review Top 10 masked parameter requests (upsell opportunities)
 - Verify payment callbacks health (success rate, latency)
 - Confirm FIFO ledger consistency and expiry logic
### Corrective Actions (When Something Breaks) ⚠
When a tenant experiences unexpected service blocking:
1. Confirm wallet balance + expiry
2. Validate token scope (product and territory)
3. Check for paused state
4. Confirm payment callback logs
5. If needed, apply a temporary grace window with strict expiry (HIC approval required)
 Revenue tactic: Use corrective incidents as sales moments: "We can restore service immediately with a top‐up link + upgrade to include diagnostics/video compliance." Done politely, this improves CX and reduces churn.

## 09.2 Billing & Invoicing
*Purpose:* This blade ensures NAVAS tokenized consumption is auditable, invoice-ready, and reconcilable with finance systems (e.g., Odoo subscriptions and invoicing where applicable).
### Primary Cards
 - Invoice Templates & Tax Profiles 3⁄4
 - Tenant Billing Profiles (UG/KE currency, billing contacts)
 - Ledger → Invoice Mapping (token lots → invoice lines)
 - Dunning & Credit Control ⚠
 - Reconciliation Reports (tokens sold vs tokens burned vs services delivered)
### Non‐Negotiable Billing Standards
1. Every invoice line must tie back to an auditable ledger entry.
2. Every ledger entry must map to a definable billing rule.
3. Every billing rule must be versioned and attributable to an approver.
 Key takeaway: Disputes are not solved by arguing; they are solved by evidence (ledger, rule, and activity).

### Billing Workflow: Token Sale to Invoice
1. Customer purchases tokens (wallet top‐up)
2. System creates/updates subscription instance
3. Token lots are recorded in wallet ledger
4. Consumption produces burn logs
5. Invoice aggregates:
 - opening balance
 - tokens purchased
 - tokens consumed
 - closing balance
6. Invoice is issued per agreed schedule (monthly/quarterly/contract).

### HIC Controls for Invoicing (Finance + Admin)
Mandatory for enterprise tenants:
 - Draft invoice reviewed by finance
 - Consumption anomalies flagged before invoice finalization
 - Any manual adjustment requires:
 - reason code
 - approver
 - customer acknowledgement (email/WhatsApp confirmation)

## 09.3 Payments & Mobile Money
*Purpose:* NAVAS supports token top-ups via direct mobile money integration (Kenya and Uganda) for near real-time service continuity.
### Supported Payment Context (EA Market)
 - Kenya: M‐Pesa integration
 - Uganda: MTN MoMo + Airtel Money integration
 These are designed to feed wallet balances instantly on successful callbacks.
### Primary Cards
 - Payment Channels & API Keys
 - Callback Health Monitor ✅
 - Top‐Up Links Generator
 - Refund & Reversal Console ⚠ (HIC restricted)
 - Fraud & Abuse Watchlist

### Admin Procedure: Configure a Mobile Money Channel (Mandatory Checklist)
1. Register the channel with the provider (per territory).
2. In CMS → Payments:
 - store API keys securely
 - define callback URL endpoints
 - enable signature validation / token verification
3. Configure:
 - minimum top-up amounts
 - maximum daily top-ups (anti-fraud)
 - webhook retry policy
4. Run a controlled test:
 - success case
 - failure case
 - delayed callback case
5. Enable production only with:
 - finance approval
 - system approval
 - monitoring dashboards active
⚠ Risk mitigation: Payment callback failures must trigger fallback flows (SMS/WhatsApp notice + manual reconciliation queue) to prevent customer anger and churn.

### CX & Revenue Tactics (Payments)
 - Always provide a pay link in renewal reminders (reduces friction).
 - Use low balance notices as proactive support, not punitive threats.
 - Offer pre-paid longer durations for customers with poor payment discipline (reduces interruptions).
 - For video/AI customers, recommend:
 - "Base tokens + premium add-on tokens" (protects margins).

==================== PAGE BREAK ====================
## SECTION 10 — INFRASTRUCTURE & CONNECTIVITY (CMS MODULE GROUP)
✅ Key takeaway: Infrastructure governance is not "IT housekeeping." It is service continuity, customer experience, and revenue protection in one discipline.
## 10.1 Devices
*Purpose:* This blade controls hardware identity, provisioning, health, firmware, and binding to customer assets across all 3D product families (Vehicle Telematics, Fuel Telematics, AI/Video, Goods-in-Transit, Personnel Tracing).
### Primary Objects You Must Govern (CRUD Scope)
1. Device Model (Create/Update)
 - protocol, supported IO, expected intervals, firmware families
2. Physical Device Record (Create/Update/Deactivate)
 - IMEI/UID, serial number, SIM ICCID
3. Device-to-Unit Binding (Create/Update/Remove)
 - which customer asset is mapped to which tracker/camera
4. Device Health State (Read/Update triggers)
 - last seen, uptime, voltage, GNSS health, tamper
5. Device Groups (Create/Update/Delete)
 - templates and bulk operations
6. Provisioning Templates (Create/Clone/Update)
 - recommended configs per product

### Device Governance by Product Family (Implementation Reality)
Use the product list to decide templates and enforcement:
 - AI & Video Telematics: DASHCAM, DASH AI, MDVR, MDVR AI
 - Requires: bandwidth planning, storage retention policy, event video triggers, firmware discipline.
 - Fuel Telematics: MAFUTA FLS / FLOW METER / CANBUS / FUEL CARD / STATION / GENSET
 - Requires: calibration workflows, anti-theft alert integrity, sensor health monitoring.
 - Goods‐in‐Transit & IoT: KAGO / PASO / PAWA / THERMO
 - Requires: geofence logic, sensor thresholds (temp/humidity), tamper events.
 - Personnel Tracing: CAPO / PATROL / PIKI / TOTO / WIATAG
 - Requires: battery discipline, privacy controls, panic event routing.
 - Vehicle Telematics: GUVNA / iVMS / iVMS‐PLUS / OLIWA / OLIWA‐PLUS
 - Requires: reliable GPS, ignition, immobilization governance, service schedules.

### Standard Device Provisioning Workflow (CMS)
1. Create Device Record
 - capture IMEI/UID + model + territory
2. Assign SIM (if applicable)
 - ICCID, operator, APN profile
3. Bind Device to Asset/Unit
 - verify customer account + product
4. Push Provisioning Template
 - intervals, IO mapping, alert triggers
5. Verify live data
 - last seen < expected threshold
6. Enable product features
 - e.g., video triggers for DASHCAM, fuel events for MAFUTA, temp thresholds for THERMO
 Trainer's note: Provisioning errors create "ghost problems" that look like software bugs. Your discipline here saves days of support time.

## 10.1.1 Preventative & Corrective Maintenance (Hardware Ops)
*Preventative discipline is mandatory.* Use target repair/install timelines as your operational baseline.
### Preventative Maintenance (Field + Remote) ✅
 - Daily
 - check offline unit spikes (top 20)
 - check abnormal voltage/tamper alerts
 - Weekly
 - validate templates (random sample: 10 devices per category)
 - validate video retention compliance (where enabled)
 - Monthly
 - firmware review board (what to upgrade, what to freeze)
 - calibration schedule checks (MAFUTA FLS / GENSET recalibration where required)
### Corrective Maintenance (When You Must Dispatch) ⚠
 - Always classify:
 - device hardware failure
 - SIM/data failure
 - install wiring issue
 - sensor calibration issue
 - customer misuse / tampering
 - Use target times (examples):
 - DASHCAM install 4 hrs, repair 3 hrs
 - MDVR install 8 hrs, repair 3 hrs
 - OLIWA install 3 hrs, repair 2 hrs
 - MAFUTA FLS install 8 hrs, repair 3 hrs + recalibration 8 hrs

## 10.2 Integrations
*Purpose:* Integrations operationalize NAVAS as a platform (payments, messaging, BI, OEM systems) rather than a closed tracker.
### Integration Categories (You shall manage as separate risk domains)
1. Messaging: WhatsApp API, SMS gateway, email SMTP
2. Finance: Odoo Invoicing/Subscriptions, reconciliation bots
3. Maps: Google Maps / Mapbox / GIS feeds (for routing, geofences)
4. BI: Power BI dashboards & exports
5. Device ecosystems: Hardware vendors, protocol brokers, upstream platforms
✅ Admin directive: Every integration must have (1) an owner, (2) a health check, (3) an incident playbook, and (4) a rollback/fallback.

## 10.3 Firmware & OTA
*Purpose:* Control risk when updating trackers, cameras, and IoT sensors. Firmware governance must be conservative, test-driven, and auditable.
### Golden rules (Non‐Negotiable)
1. No mass updates without staged rollout
2. Always validate on a pilot pool
3. Freeze firmware during peak operational periods
4. Document rollback paths
⚠ Firmware failures cause customer panic. Treat OTA like surgery: minimal, precise, logged.

## 10.4 SIM Console (SIM Card Intelligence)
*Purpose:* The SIM Console optimizes cost and reliability by analyzing roaming costs, data intervals, and recommending "nearest bundle" for a specific use case (GPS-only vs video-heavy).
### What SIM Intelligence must deliver
 - Identify units with:
 - high data usage anomalies
 - roaming cost spikes
 - low balance / bundle depletion risks
 - Recommend:
 - interval tuning (1 min vs 30 sec)
 - video upload policy changes
 - bundle upgrades for DASHCAM/MDVR use cases
 Profit tactic: SIM cost control is margin control. Your best revenue is the revenue you don't lose to unmanaged bandwidth.

==================== PAGE BREAK ====================
## NEXT SECTION QUEUE (AUTO‐CONTINUATION): SECTION 11 — ASSET & RESOURCE GOVERNANCE (CLIENTS, RBAC, AUDIT LOGS)
In the next continuation, I will proceed directly into:
 - Clients & Accounts (multi-tenancy structure aligned to dealer/manager hierarchy)
 - RBAC & "Act on behalf" (HIC) for safe delegation (Wialon-style admin action patterns) ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/interface/top-panel?utm_source=chatgpt.com))
 - Audit Logs & Compliance (non-repudiation, change tracking)
 - Support readiness controls (SLA alignment and escalation workflows)
--- PAGE BREAK ---
## SECTION 04 — SERVICE STRUCTURE, TENANTS & ACCOUNT HIERARCHY (UG o / KE a)
4.1 Purpose Of This Section
Objective:* You will design and enforce the NAVAS service hierarchy in CMS so that billing, permissions, apps, and support behave predictably at scale (Dealer → Sub‐dealer → Customer → Sites → Units). ✅
*Why this matters:* In NAVAS, the account hierarchy is not "admin paperwork." It is the root control plane that determines:
1. Who can create subordinate accounts and manage payments
2. Which billing plans, apps, and token rules apply
3. What is auditable, reversible, and recoverable (trash/restore)
4. How support & HIC (Human‐In‐Control) actions are executed safely
This structure is aligned to a Wialon‐style management system (hierarchy + billing plans + apps + trash restore), but adapted to NAVAS tokenomics and East Africa operations. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system?utm_source=chatgpt.com))

4.2 Canonical Account Types (NAVAS CMS)
NAVAS uses three non‐negotiable account types:
| Account Type | Primary Role | Key Powers | Key Restrictions |
| Top Account | Service owner / platform owner | Create billing plans, configure apps, restore deleted objects | Cannot create units (by policy) |
| Dealer Rights Account | Distributor / dealer / sub‐dealer manager | Create and manage subordinate accounts; block/unblock; manage rights; control payments | Not recommended to create units here |
| Non‐Dealer Account | End‐customer tenant | Create users; create units; daily operational use | Cannot create subordinate accounts |

These definitions are explicitly documented in the NAVAS vision/scope reference (adapted from Wialon service hierarchy patterns).【383:11†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L71-L154】
✅*Dealer Rights is your "reseller management layer." Non‐Dealer is where tracking happens.

4.3 The Golden Rule: Never Mix Commercial Roles With Operational Units ⚠
You will enforce this rule in every implementation:
1. No units in Top Account (platform governance).【383:11†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L111-L121】 ership clean).【383:11†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L123-L131】 explicitly approved for demo/sandbox.
*Reasoning:
*When units are placed in commercial accounts, you corrupt reporting, billing liability, and support permissions. You also create "invisible ownership" problems during churn, migration, and legal disputes.

4.4 Recommended East Africa Hierarchy Blueprint (3D Services Ltd)
You will implement this hierarchy for Uganda/Kenya operations:
1. Top Account (3D Services Platform Owner)
 - Platform configuration: token engine, billing plans, app catalog, global templates, global compliance settings.
2. Dealer Rights Accounts
 - Examples:
 - 3DS-UG-DEALER-001 (UG)
 - 3DS-KE-DEALER-001 (KE)
 - Optional: Sub‐dealers per region (Western UG / Coastal KE) or vertical (Logistics dealer / Fuel dealer).
3. Customer Tenants (Non‐Dealer Accounts)
 - Structure:
 - CUSTOMERNAME-COUNTRY-SECTOR
 - Example: ACME-UG-LOGISTICS
4. Sites / Branches (Logical Entities inside Tenant)
 - Example: ACME-UG-KAMPALA-DEPOT, ACME-UG-GULU-DEPOT
5. Units / Assets
 - Vehicles, bikes, gensets, cold chain, people trackers, cameras.
This blueprint supports the NAVAS "monetizable IoT infrastructure" concept and multi‐tenant governance described in the system policy and cockpit design. 【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L14-L121】

4.5 Account
Follow this *exact* operational protocol to create a new customer tenant.
Step 1 — Confirm commercial readiness (pre‐flight checks)
You will confirm:
1. Approved quote / LPO / initial payment (per sales process).
2. Product(s) purchased: e.g., OLIWA vs OLIWA‐PLUS vs DASH AI etc.
3. Country + currency rules: UGX vs KES (pricing and token packs differ).
4. Support tier: Standard vs Premium.
5. Channels: WhatsApp recipients, email recipients, escalation contacts.
Step 2 — Create tenant (Non‐Dealer account)
Within CMS:
1. Navigate: Tenants / Accounts → Create New
2. Enter:
 - Tenant name (canonical)
 - Country = UG or KE
 - Dealer owner = correct dealer rights account
 - Industry vertical tag (Fleet / Fuel / GIT / Video / Personnel)
3. Save.
Step 3 — Attach billing plan and token policy profile
1. Assign Billing Plan (token pricing + enforcement mode)
2. Enable Token Wallet (default currency + payment rails)
3. Configure credit policy (e.g., hard stop vs grace window)
Step 4 — Apply tenant template pack (mandatory)
Apply baseline templates:
 - Roles & permission templates
 - Notification templates (WhatsApp/SMS/email)
 - Naming conventions
 - Default alert bundles (anti‐fatigue)
 - Standard reports pack (daily/weekly compliance reports)
Step 5 — Maker‐Checker (HIC) approval gate ⚠
Before activation:
 - A second admin must approve:
 1. Billing plan selection
 2. Token policy profile
 3. Enabled apps list
 4. Payment rails activated (Mobile Money hooks)
This maker‐checker discipline is consistent with NAVAS engineering and governance practices. 【383:5†NAVAS System Developement Playbook Ver5.0.pdf†L25-L31】
✅ Keilling + wallet + apps + templates + HIC approval are done.

4.6 Tenant Naming Conventions (Non‐Negotiable Standard) ✅
You will enforce a strict naming schema to prevent operational chaos.
Tenant Code Format:
 - CUSTOMERNAME-COUNTRY-SECTOR
 - Example: KAMPALA-CEMENT-UG-FLEET
Unit Naming Format (recommended):
 - REG-PLATE | ASSET-ID | SITE
 - Example: UBG123A | TRK-014 | KAMPALA-DEPOT
Driver Naming Format:
 - SURNAME FIRSTNAME | PHONE | ID
 - Example: KATO JOHN | +2567xxxxxxx | NIN-XXXX
Device Naming Format:
 - HWTYPE-SERIAL-LAST4SIM
 - Example: FMB920-123456-8899
⚠ *Why strict naming?
*Because AI/HIC workflows, triage, audit trails, and customer‐facing reports all become unreliable when naming is inconsistent.

4.7 Multi‐Tenancy & RBAC Model (How NAVAS Secures Separation)
NAVAS uses:
 - PostgreSQL for user accounts, audit trails, RBAC records【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L75-L90】
 - Hierarchical de:0† NAVAS IOT SYSTEM POLICY_ .pdf†L115-L120】
As System Admin, y one tenant context (unless explicitly multi‐tenant support role).
2. Cross‐tenant operations are executed only via support session impersonation (HIC) with audit logging.
3. Dealer accounts never receive global platform powers.

4.8 Operational Guardrails (East Africa Reality Checks)
These guardrails are mandatory for Uganda/Kenya operations:
1. Mobile Money integration readiness
 - NAVAS strategy explicitly includes M‐Pesa / MTN / Airtel payment integration.【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L23-L29】
2. Low‐bandwidth toxist (SMS when WhatsApp fails, and email when SMS fails).
3. Regional support SLAs
 - Design your tenant templates to respect business hours + after‐hours escalation rules (see incident section later).【387:3†3DS Process for Incident Management Escalation V.3.pdf†L50-L56PORT IMPERSONATION (HIC)

5.1 Purpose Of This Section
Objective:* You will implement least‐privilege access, enforce clean operational roles, and safely support customers through HIC-controlled impersonation (Wialon‐style "act on behalf," but stricter). ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system?utm_source=chatgpt.com))

5.2 NAVAS Role Architecture: Required Roles For 3D Services Ltd ✅
You will maintain the following standard role set. Anything outside this must be approved and documented.
### 5.2.1 Platform Roles (Top Account / 3D HQ)
 - Platform Owner (Restricted)
 - Platform System Admin
 - Platform Billing Admin
 - Platform Security Admin
 - Platform App Catalog Admin
 - Platform Observability Admin (Cockpit)
### 5.2.2 Dealer Roles (Dealer Rights Accounts)
 - Dealer Admin
 - Dealer Billing Officer
 - Dealer Support Lead
 - Dealer Onboarding Officer
### 5.2.3 Customer Tenant Roles (Non‐Dealer Accounts)
 - Customer Super Admin
 - Fleet Manager
 - Dispatcher / Controller
 - Safety Manager
 - Fuel Controller (MAFUTA)
 - Video Reviewer (MDVR / DASH AI)
 - Warehouse / GIT Ops (KAGO / PASO / PAWA / THERMO)
 - Read‐Only Auditor

5.3 Permission Design Pattern: CRUD + Approve + Export ✅
For each module, permissions must be separated into four layers:
1. View (read)
2. CRUD (create, edit, delete/archive)
3. Approve (HIC gate)
4. Export/Share (data exfiltration control)
✅ Key Takeaway:
Most breaches happen through "Export" rights, not through edit rights. Treat export as sensitive.

5.4 RBAC Practical Implementation Checklist
You will configure RBAC using the following controls:
1. Role Templates
 - Create baseline roles as templates (Top account level)
2. Object Scope
 - Define scope per object type:
 - Tenant
 - Site
 - Unit group
 - Report pack
 - Alert pack
3. Time Scope
 - Optional: time-limited roles for contractors (Field Tech accounts)
4. Session Controls
 - Enforce session expiry, MFA, and device trust policy (where available)

5.5 Support Impersonation (HIC-Controlled "Log In As") ⚠
This is one of the highest-risk capabilities in any telematics CMS. You will implement it as HIC-controlled.
5.5.1 When impersonation is allowed ✅
Impersonation is allowed only for:
1. Onboarding configuration support (first 30 days)
2. Critical incident troubleshooting (P1/P2)
3. Billing disputes requiring evidence review
4. Permission repair when customer locked out
5.5.2 When impersonation is forbidden
Impersonation is forbidden for:
 - Changing billing plans without approval
 - Suspending service without Finance approval
 - Modifying audit logs (never possible)
 - Downloading exports without recorded justification
5.5.3 HIC Protocol (mandatory)
You will enforce:
1. Ticket required (Odoo / help desk reference)
2. Reason captured (dropdown + free text)
3. Time limit (default 15 minutes; extend only with approval)
4. Actions logged (who, what, when, where, why)
5. Customer notification (optional policy: notify customer admin that a support session occurred)
This aligns with the "audit & QMS" focus for automated actions and approvals in the AI/agent governance strategy. 【387:5†3D-AI-AGENT-STRATEGY V5.pdf†L16-L20】

5.6 Standard Users For Every Tenant (Minimum Set) ✅
Upon tenant creation, you will ensure theseustomer)
2. 3DS-SUPPORT-L1 (support)
3. 3DS-SUPPORT-L2 (systems analyst)
4. 3DS-FINANCE-VIEW (read-only billing visibility)
5. Optional: 3DS-FIELD-TECH (time-limited)

5.7 Preventative Maintenance: Access Hygiene
You will schedule:
1. Quarterly access reviews (role correctness, dormant users)
2. Immediate revocation when staff exit or customer requests removal
3. Secrets/keys policy enforcement (never share API keys in WhatsApp)
This is consistent with security governance practices (RBAC, access reviews, audit logging) referenced in the AI agent strategy. 【387:5†3D-AI-AGENT-STRATEGY V5.pdf†L9-L20】

--- PAGE BREAK ---
## SECTION 06 — ADD‐ON APPS LIBRARY & PROVISIONING (BLADES, CARDS, CRUD)
*e:* You will manage the NAVAS Apps ecosystem (core + add‐ons) using the CMS "Apps Library / Provisioning" workspace, including feature flags, dependencies, token checks, and HIC gates.
NAVAS explicitly positions the CMS provisioning screen as a System Admin persona UI with:
 - Tenant selector
 - RBAC badge
 - Token details
 - System health
 - CRUD controls (+New App, Edit, Archive→Trash, Restore)
 - Provisioning drawer (enable per tenant, dependency checks, token meter, payment/top‐up)
 - Waswa AI co‐pilot widget with governance + HITL/HIC reminders【383:4†CMS Mockup Redesign Request.txt†L1-L10】

6.2 UI Layout Standard (NAVAS "Azure‐WhatsApp Hybrid")
The provisioning workspace follows module icons
2. Accordion Sidebar — module blades / sub‐menus
3. Workspace — tables, cards, dashboards
4. Right Blade / Drawer — provisioning actions, configuration forms, token meter
This layout is intentional: it supports fast admin operations while keeping HIC approvals and AI hints visible. 【383:4†CMS Mockup Redesign Request.txt†L1-L10】

6.3 App Portfolio Alignment (3D Products + Add‐Ons + VAS) ✅
As System Admin, you will treat ility bundles (apps + devices + token rules + templates).
### 6.3.1 Core Service Types And Products
 - AI & Video Telematics: DASH AI, DASHCAM, MDVR, MDVR AI
 - Fuel Telematics: MAFUTA CANBUS, MAFUTA FLOW METER, MAFUTA FLS, MAFUTA FUEL CARD, MAFUTA STATION, GENSET
 - Goods‐in‐Transit & IoT: KAGO, PASO, PAWA, THERMO
 - Personnel Tracing: CAPO, PATROL, PIKI, TOTO, WIATAG
 - Vehicle Telematics: GUVNA, iVMS, iVMS‐PLUS, OLIWA, OLIWA‐PLUS
 - Add‐On Apps: BI DASHBOARDS, DSC, ECO, FLEETRUN, INSPECTA, JMS, LOGISTICS, NIMBUS, VEBA
 - Value Added Services: Help Desk & Training, GIS & JMS, SATO, Local Owned Server, OEM System Integrations
✅ Key Takeaway:
Provisioning is not "turning on a switch." It is enabling a product operating model.

6.4 Apps Library: Required Columns (Operations View)
Your Apps Library table must support fast operational decisions. Recommended columns:
| Column | Description | Why It Matters |
| App Name | e.g., VEBA, INSPECTA | Recognition |
| Category | Add‐On / Core / VAS | Governance |
| Status | Draft / Active / Archived | Lifecycle |
| Tenant Enabled | Yes/No | Revenue control |
| Dependencies | e.g., Wallet, Units | Prevent breakage |
| Token Meter | Burn rate / forecast | Margin protection |
| Health | OK / Degraded | MTTR |
| Actions | Edit / Archive / Restore | Lifecycle control |

6.5 CRUD Operations (Apps Catalog) ✅
You will use these CRUD controls exactly as defined:
1. + New App
 - Create the app record (metadata, category, dependencies, billing class)
2. Edit
 - Update metadata, dependency rules, entitlement policy, templates
3. Archive → Trash
 - Removes from provisioning UI; does not delete billing history
4. Restore
 - Restores from trash (top account power)
This aligns with the documented CMS screen spec. 【383:4†CMS Mockup Redesign Request.txt†L6-L9】

6.6 Provisioning Drawer (Right Blade): Mandatory Controls ⚠
Every app must have a provisioninant (toggle)
2. Dependency Checks (auto‐validate prerequisites)
3. Token Meter (cost indicator + recommended pack)
4. Payment / Top‐Up Shortcut (wallet hook)
5. Governance Toggles (HIC) (policy-driven enablement)
6. Save & Apply (HIC approval if required)
This is explicitly part of the provisioning screen design spec. 【383:4†CMS Mockup Redesign Request.txt†L6-L9】

6.7 Governance Toggles (VEBA Example — Non‐Negotiable) ⚠
For high‐risk apps (marketplace + mance toggles such as:
 - Require KYC for Owners
 - Enable Leakage Shield (AI)
 - Require Telematics Unit Linked
 - Allow Cash Trips (Trusted only)
These are listed as mandatory controls in the provisioning drawer specification. 【351:5†CMS Mockup Redesign Request.txt†L356-L386】
✅ Key Takeaway:
VEBA is not "an app." It is a risk surface. Governance toggles are not optnt "Enabled But Broken")
You will implement dependencies as hard validation rules.
### 6.8.1 Common Dependencies
 - Token Wallet required for any paid add‐on
 - At least 1 Unit required for:
 - OLIWA/iVMS/MAFUTA features
 - Camera device profile required for:
 - DASHCAM/MDVR/MDVR AI/DASH AI
 - Geofences/POIs required for advanced logistics alerts
 - User roles present for:
 - INSPECTA (inspector)
 - FleetRun (dispatcher)
 - VEBA (owner/operator roles)
### 6.8.2 Dependency Failure Behavior
When dependency checks fail, you will enforce:
1. App remains disabled
2. CMS displays remediation steps
3. Waswa AI suggests the fastest fix (but requires HIC approval if it changes configuration)

6.9 Waswa AI Co‐Pilot Widget (Admin Use)
NAVAS COCKPIT defines Waswa AI as:
 - Predicting system load
 - Identifying revenue leakage in real time【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L105-L113】
In Apps Library, Waswa AI must:
1. Detect tenants enabling apps without funding (leakage risk)
 2.on
2. Flag "silent churn" risk (low usage + expiring wallet)
3. Recommend upsell packs contextually (not salesy)

6.10 Tactical Playbook: How To Provision Each Product Family
Use this as a repeatable deployment playbook.
### 6.10.1 Vehicle Telematics (OLIWA / iVMS / GUVNA)
1. Enable base app: OLIWA or iVMS
2. Ensure:
 - Units created
 - Device types assigned
 - Default alerts enabled (overspeed, ignition, geofence)
3. Enable optional add‐ons:
 - ECO (driver behavior)
 - BI Dashboards
 - JMS/GIS (job scheduling, routing)
### 6.10.2 Personnel Tracing (PIKI / PATROL / TOTO / WIATAG)
1. Enable base: PIKI/PATROL
2. Confirm:
 - Device profile (wearable/phone tracking)
 - Privacy policy & consent flags
3. Add optional:
 - FleetRun (dispatch workflows)
 - INSPECTA (field inspections, evidence capture)
### 6.10.3 Fuel Telematics (MAFUTA FLS / FLOW / CANBUS)
1. Enable base: MAFUTA
2. Configure:
 - Sensor calibration workflow
 - Theft rules (sudden drops)
3. Add:
 - BI Dashboards
 - ECO (fuel efficiency)
4. Enforce: CANBUS must complement FLS/ATG when reliability is a concern (avoid single-source truth failures).【387:7†Product_Market_Mix_notes.pdf†L123-L129】
### 6.10.4 AI & Video Telematics (DASH AI / MDVR AI)
1. Enable base: MDVR / DASHCAM
2. Add AI lIM Card Intelligence plan (nearest bundle, bandwidth)【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L109-L113】
 - Storage policy (retention, evidence clips)
3. Set alert fatigue controls:
 - Bundle alerts houatterns).【387:5†3D-AI-AGENT-STRATEGY V5.pdf†L62-L69】

--- PAGE BREAK ---
SECTION 07 — TOKEN BILLING, WALLET, AND COMMERCIAL GOVERNANCE (UGX/KES)
---ive:* You will configure and operate NAVAS Token Billing Engine as the primary monetization layer, replacing flat subscriptions with PAYG token burn and strict enforcement. 【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L123-L127】

7.2 NAVAS Token Engine Principle ("The YES Engine")
NAVAS token strategy is designed astime. Any Way."【383:8†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L1-L33】
As System Admin, you will treat tokens as:
1. A technical cost control mechanismage prevention mechanism

7.3 Token Enforcement Modes (How NAVAS Prevents Free-Riding) ⚠
NAVAS token policy includes:
 - Write-time checks: when data arrives and is stored
 - Read-time checks: when users request playback/reports/maps
 - Parameter-level enforcement: certain parameters cost more
 - Dynamic/hybrid enforcement: adapt to customer usage and product type
The token billing requirements explicitly mention write-time and read-time enforcement and "higher token needed" behavior for upsell without data loss.【351:4†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L49-L73】【351:12†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L143-L161】
✅ Key Takeawayare responsible for:
1. Wallet provisioning per tenant
2. Currency assignment (UGX or KES)
3. Payment rails enablement (Mobile Money hooks)
4. Auto top‐up policy (optional)
5. Hard stop / grace windows per customer contract
Mobile money integration is a strategic requirement (MTN, Airtel, Safaricom / M‐Pesa).【387:4†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L71-L72】【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L23-L29】

7.5 Wallet Funding Policy (Non‐rprise customers with signed credit terms
3. No silent overdrafts (unless explicitly approved)

7.6 Token Classes (Operational Categorization)
You will maintain token classes consistent with NAVAS canonical strategy:
1. Telemetry tokens (location, IO, CAN)
2. Alert tokens (SMS/WhatsApp/email dispatch cost drivers)
3. Map tokens (Google/Mapbox usage drivers)
4. AI tokens (inference cost drivers)
5. Video tokens (bandwidth/storage heavy)
6. API tokens (enterprise integrations)
This is consistent with the costing and ROI considerations in NAVAS policy (WhatsApp, map calls, server overhead).【383:6† NAVAS IOT SYSTEM POLICY_ .pdf†L15-L23】

7.7 Token Packaging By Product (Practical Bundling Guide)
As a seasoned telematics admin,not around "features."
### 7.7.1 OLIWA / iVMS (Vehicle Tracking)
 - Core: location + trip history + geofences
 - Add-ons: ECO, BI dashboards
 - Risk: alert fatigue → bundle alerts into digests
### 7.7.2 MAFUTA (Fuel)
 - Core: fuel level samples + theft events
 - Add-ons: BI dashboards, ECO
 - Risk: miscalibration → high false positives → wasted tokens (see maintenance section later)
### 7.7.3 DASH AI / MDVR AI (Video + AI)
 - Core: live video triggers + evidence upload
 - AI: driver behavior inference
 - Risk: roaming/data bundles → SIM intelligence required【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L109-L113】
✅ Key Takeaway:
Your primary enemy is not "low pricing." It is uncontrolled consumption.
s) ✅
Whenever you view Token Meter in the provisioning drawer:
1. Do not treat burn rate as "cost only." Treat it as behavior signal.
2. If burn is high:
 - Check excessive alert rules
 - Check high‐frequency telemetry settings
 - Check unauthorized AI triggers
3. If burn is low:
 - Check whether customer is inactive (churn risk)
 - Check device offline issues (support risk)

7.9 HIC Controls For Billing Actions ⚠
Certain billing actions must be maker‐checker:
 - Change billing plan
 - Change token pricing profile
 - Apply discounts beyond threshold
 - Approve suspension for overdue customers (Finance gate)
The AI agent strategy explicitly requires approval gates for suspension actions and audit logging. 【387:11†3D-AI-AGENT-STRATEGY V5.pdf†L76-L83】

7.10 Preventative Maintenance: Billing Leakage Controls
You will run these controls weekly:2. Top 20 AI inference consumers (video/AI)
3. Token burn anomalies (spikes)
4. Wallet negative events (blocked reads/writes)
5. App enabled without revenue (leakage risk) — Waswa AI should flag this【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L109-L113】

--- PAGE BREAK ---
SECTION 08 — NOTIFICATIONS, ALERTS, SLAs, AND INCIDENT ESCALATION (MTTR)*tive:* You will configure alert delivery (multi‐channel), reduce MTTR, prevent alert fatigue, and operate within 3D Services escalation policies.
NAVAS operational KPIs include strict MTTR targets (e.g., <15 min reply, <24 hr resolution).【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L115-L117】

8.2 Channel Strategy (East Africa Practical Policy) ✅
You will configure multi‐channel alsApp (fastest)
3. SMS (fallback, low bandwidth)
4. Email (formal reporting trail)
NAVAS capabilities include multi-channel event alerts (screen popups, email, SMS, WhatsApp).【387:4†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L165-L169】

8.3 Point‐Of‐Contact Response Time Targets ⚠
You will align alert routi 5 minutes
 - Phone (support hours): 15 minutes
 - Phone (after hours): 60 minutes
 - Email (support hours): 2 hours【387:2†3DS Process for Incident Management Escalation V.3.pdf†L1-L9】
✅ Key Takeaway:
If you configure WhatsApp alerts but do not enforce 5‐min Hardware Install & Repair Targets By Product (Operations SLA)
You will enforce these operational targets in scheduling and customer expectations:
| Service Type | Product | Time To Install | Time To Repair |
| AI & Video | Dash AI | 4.5 hrs | 3 hrs |
| AI & Video | Dashcam | 4 hrs | 3 hrs |
| AI & Video | MDVR | 8 hrs | 3 hrs |
| AI & Video | MDVR AI | 8 hrs | 3 hrs |
| Vehicle | iVMS | 3 hrs | 2 hrs |
| Vehicle | iVMS‐Plus | 4 hrs | 3 hrs |
| Vehicle | Oliwa | 3 hrs | 2 hrs |
| Vehicle | Oliwa‐Plus | 4 hrs | 3 hrs |
| Fuel | Mafuta‐FLS | 8 hrs | 3 hrs (+ recalibration 8 hrs) |
| Fuel | Mafuta‐CanBus | 4 hrs | 3 hrs |
| Fuel | Mafuta‐Flow Meter | 3 hrs | 2 hrs |
| Personnel | Capo | 1 hr | 30 mins |
| Personnel | Piki | 3 hrs | 2 hrs |
| Personnel | Toto | 1 hr | 30 mins |
| Personnel | Wiatag | 1 hr | 30 mins |
| Personnel | Patrol | 4 hrs | 2 hrs |
| Goods & IoT | Genset | 8 hrs | 3 hrs (+ recalibration 8 hrs) |
| Goods & IoT | Kago | 4 hrs | 3 hrs |
| Goods & IoT | Thermo | 2 hrs | 1 hr |
| Goods & IoT | Paso | 1 hr | 1 hr |
| Goods & IoT | Pawa | 4 hrs | 3 hrs |

These targets are defined in the 3D Services escalation/MTTR document. 【387:2†3DS Process for Incident Management Escalation V.3.pdf†L19-L92】

8.5 Alert Fatigue Prevention (Bundling & Quiet Hours)
You will impraking, fuel noise), send digest alerts hourly.
2. Quiet hours
 - Enforce customer-defined quiet hours for non-critical alerts.
<!-- end list -->
1. Severity tiers
 - P1: immediate
 - P2: bundled
 - P3: daily report
This is consistent with agent strategy patterns (bundling within 60 minutes to reduce fatigue). 【387:5†3D-AI-AGENT-STRATEGY V5.pdf†L62-L69】

8.6 AI Assistance In Support Operations (Resolution Co‐Pilot)
NAVAS AI customer service storize ticket, pull telemetry context, guide SOP steps, auto notes, SLA timers (Odoo/Wialon/n8n)【383:3†AI_Agent_Customer_Service_User_Stories_All.pdf†L142-L170】
As System Admin, you will configure:
1. Ticket intake mappings (unit ID, tenant, devproval gates for high-risk actions (suspend, delete, billing changes)

8.7 Corrective Maintenance (When Things Go Wrong) ⚠
You will apply a standardized corrective routine:
1. Confirm unit online status
2. Confirm last GPS fix and GSM uplink
3. Confirm power stability and wiring integrity
4. Confirm SIM data plan is active (SIM Intelligence console)【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L109-L113】
5. Confirm server-side ingestion (Kafka/Cassandra pipeline health)【383:0† NAVAS IOT SYSTEM POLtroubleshoot blind. Use the Cockpit + AI hints to drive evidence-first di — NAVAS COCKPIT OPERATIONS, AI + HIC GOVERNANCE (WASWA AI)

9.1 Purpose Of This Section
Objective:* You will operate NAVAS COCKPIT as the System Admin "Command & Control" layer and deploy AI/HIC features safely.
NAVAS COCKPIT explicitly includes:
 - AI Co‐Pilot (Waswa AI)
 - SIM Card Intelligence console
 - Operational KPIs (MTTR)
 - RBAC & multi‐tenancy hierarchy【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L105-L120】

9.2 Cockpit: Daily Admin Workflow (Non‐Negotiable Routine) ✅
You will run this routine atatform)
 - Ingestion status
 - Queue lag (streaming)
 - DB health
<!-- end list -->
1. MTTR Dashboard
 - Tickets pending beyond SLA
 - P1 open incidents
2. Revenue Leakage Watch
 - Apps enabled without wallet funding
 - Unusual token burn spikes
3. SIM Card Intelligence
 - Roaming costs flags
 - Data interval anomalies
 - "Nearest bundle" recommendations for camera deployments【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L109-L113】
4. HIC Queue
 - Approvals pending (billing changes, provisioning, suspensions)

9.3 Waswt) ⚠
Waswa AI is a proactive agent that predicts load and identifies revenue leakage. 【383:0† NAVAS IOT SYSTEM POLICY_ .pdf†L109-L113】
### Allowed (suggestions + drafts) ✅
 - Suggest root causes for offline units
 - Recommend bundlt remediation steps
 - Propose billing upsell packs (contextual, not spammy)
 - Draft incident summaries and customer updates
### Not Allowed (without approval)
 - Enable/disable apps for a tenant
 - Change billing plan
 - Suspend a tenant
 - Delete/restore objects
 - Send customer-facing messages without HIC approval (unless template is pre-approved)
This is consistent with the AI governance posture (audit logs, approvals, fail-open to manual during outages).【387:5†3D-AI-AGENT-STRATEGY V5.pdf†L16-L21】

9.4 HIC (Human‐In‐Control): Mandatory Approval Gates ✅
You will configure approval gates for:
R AI, DASH AI, API Monetization
2. Billing
 - Plan changes, discounts, credits, suspension proposals
<!-- end list -->
1. Security
 - Role elevation, impersonation sessions > 15 minutes
2. Data
 - Bulk exports, integrations, webhook creation

9.5 Audit & Evidence Pack Discipline (QMS Alignment)
Every automated message, approval, and financial action must produce an immutable log entry, and the system supports exporting evidence packs for QMS/ISO needs. 【387:5†3D-AI-AGENT-STRATEGY V5.pdf†L16-L20】
As System Admin, you will:
1. Ensure logs are enabled and retained per policy
2. Export quarterly evide
3. Maintain incident postmortems for Sev‐1/Sev‐2

9.6 AI Agent Operations Map (Practical Use In CMS)
NAVAS AI customer service automations include:
 - Resolution Co‐Pilot (L1 support acceleration)
 - Progress Notifier + Scheduler (customer comms + scheduling)
 - Health Sentinel (anomaly detection + evidence ticket creation)
 - Access Governance Bot (access reviews + change logs)【383:3†AI_Agent_Customer_Service_User_Stories_All.pdf†L142-L264】
As System Admin, you will configure where these agents operate:
1. Cockpit dashboard + SOP steps)
2. Provisioning drawer (governance reminders + token meter explanations)
3. Finance console (renewal reminders + pay links)
The strategy targets measurable outcomes like P1 <2 minutes end-to-end and helpdesk response <15 minutes. 【387:11†3D-AI-AGENT-STRATEGY V5.pdf†L1-L7】

9.7 Preventative Maintenance: AI Drift & Template Hygiene
You will enforce:
1. Weekly promptonthly knowledge base refresh
2. Quarterly provider evaluation / cost governance
3. Canary releases + rollback plan if CSAT drops【387:5†3D-AI-AGENT-STRATEGY V5.pdf†L22-L34】
✅ Key Takeaway:
AI is not "set and forget." It is a managed operational asset.

REFERENCE PAC*
3⁄4 FORMATTING NOTE (FOR GOOGLE DOC) ✅
 - Orientation: Landscape
 - Page break rule: Insert a page break before every H1 section below.
 - Footer (set once for the whole doc):
 - Left: *NAVAS IoT System - CMS Module - 01.MAR. 2026*
 - Center: *"You name it, we track it." ✅*
 - Page numbering: Bottom-right

— PAGE BREAK —
# 8. INFRASTRUCTURE & CONNECTIVITY

## Purpose
Your job in this module is simple, non‐negotiable, and measurable:
1. Guarantee data continuity (the platform must receive clean, timely telemetry).
2. Control connectivity cost (data usage MUST not become revenue leakage).
3. Maintain predictable customer outcomes (no "it went offline" surprises).
4. Enforce governance (changes must be auditable, reversible, and approved where required).
NAVAS is architected as a high‐velocity pipeline (ingestion → streaming → storage → cache → UI). Connectivity is the bloodstream. If you misconfigure onboarding, SIM, protocol, or interval policy, you directly damage:
 - Fleet visibility
 - Fuel integrity ⛽
 - Driver safety programs
 - Video evidence readiness
 - Billing accuracy
 - SLA performance  ̄
This module therefore operates as a commercial operations control point, not "just technical settings."

## Operating Principles (You SHALL Enforce) ✅
1. Every device MUST have an owner context (Tenant → Account → Asset/Unit).
2. Every device MUST have a protocol profile (parser + parameter mapping).
3. Every device MUST have a connectivity policy (expected interval + offline threshold + retry rules).
4. Every SIM MUST have cost governance (bundle strategy + roaming rules + alerts).
5. Every high-impact change MUST follow HIC (maker–checker where risk is high). ✈
6. No "silent failures": offline, stale data, or abnormal data spikes MUST trigger alerts.

## Module Map (Blades, Cards, CRUD)
Below is the standard CMS layout you MUST master. The naming may vary slightly by build, but the operating logic MUST remain consistent.
### Primary blades
 - Device Registry
 - Protocol & Integration Hub
 - SIM Card Intelligence
 - Connectivity Policies
 - Firmware & OTA  (where applicable)
 - Connectivity Logs / Telemetry Health o
### Card patterns you will see
 - Identity Card: IMEI/UID, serial, model, device family
 - Ownership Card: Tenant, Account, Asset/Unit linkage
 - Protocol Card: protocol type, codec, decoder version, parameter map
 - SIM Card: ICCID/MSISDN, carrier, APN, bundle profile, roaming state
 - Interval Policy: heartbeat, GPS interval, event interval, offline threshold
 - Cost Controls: bundle cap, video caps, retry storm protection
 - Audit Card: who changed what, when, why, approvals
### CRUD operations you MUST perform correctly
 - Create: add new device, add SIM profile, add protocol profile, add connectivity policy
 - Read: health checks, last seen, message logs, consumption reports
 - Update: change interval policy, swap SIM mapping, update firmware, update decoder
 - Disable/Suspend: block device from producing billable services (HIC-controlled)
 - Archive: retire device/SIM, preserve audit trails and usage history

## HIC Control Points (Mandatory) ✈⚠
Certain actions are high-risk and MUST not be executed casually. Implement maker–checker (or equivalent) for the following:
1. Protocol / Decoder Changes (can break telemetry system-wide).
2. APN and SIM Profile Changes (can cause mass offline events).
3. Global Interval Policy Templates (can increase data consumption instantly).
4. Video / Bandwidth Settings (high burn potential in token model).
5. Bulk Firmware Updates (bricking risk + downtime).
6. Roaming enablement (can create catastrophic cost spikes).
7. Connectivity storm overrides (retries can amplify costs and instability).
Trainer rule: If a change can affect ≥ 25 units, it MUST be treated as a controlled change with rollback, audit entry, and after-action review.

## SOP: Provisioning a New Device (Safe Default) ✅
Follow this exact sequence to avoid rework and billing disputes.
### Step 1 — Pre‐Provisioning Checklist.
Before you touch CMS, confirm:
 - Asset type: Vehicle / Motorcycle / Staff wearable / Generator / Cold chain / Camera
 - Operating country: UG / KE (this affects SIM choice, payment rails, compliance)
 - Required products: OLIWA / PIKI / PATROL / MAFUTA / MDVR / THERMO / etc.
 - Installation readiness: power source, ignition, antenna placement, sensor wiring
 - Customer expectation: tracking interval, alerts, reporting
### Step 2 — Create Device in Device Registry (CREATE).
Device Registry → Add Device
1. Enter IMEI/UID exactly (no spaces).
2. Assign Device Type (GPS tracker, MDVR, dashcam, wearable, sensor hub).
3. Attach ownership: Tenant + Account.
4. Assign asset label (plate / boda number / staff ID / generator ID).
5. Save.
✅ Key takeaway: The UID is your "primary key." Any UID error becomes a ghost unit, double billing, or invisible tracking.
### Step 3 — Assign Protocol Profile (UPDATE).
Protocol & Integration Hub → Profiles
1. Select correct protocol (Teltonika / Concox / Ruptela / Jimi / MDVR vendor, etc.).
2. Confirm parameter dictionary for the product you're enabling.
3. Enable required telemetry set (see "Product profiles" below).
4. Save.
### Step 4 — Attach SIM Profile (UPDATE).
SIM Card Intelligence → SIM Assignment
1. Map ICCID/MSISDN to this device.
2. Select correct carrier + APN.
3. Apply bundle profile (standard tracking vs high‐bandwidth video).
4. Set roaming policy (disabled unless business case).
5. Save.
### Step 5 — Apply Connectivity Policy Template (UPDATE).
Connectivity Policies → Apply Template
1. Choose baseline template for asset type (vehicle/motorcycle/video/cold chain).
2. Set expected reporting interval + offline threshold.
3. Enable retry limits (storm protection).
4. Save.
### Step 6 — Commissioning Validation (READ).
Confirm:
 - First message time is current (no timezone drift).
 - GPS coordinates are sane (not in ocean, not 0,0).
 - Ignition status matches test conditions.
 - Basic IO parameters appear (voltage, gsm, satellites).
 - Required sensors appear (fuel probe, temp probe, door, etc.).
### Step 7 — Lock Commissioned Baseline (HIC recommended).
Once stable:
 - Lock core identity + protocol assignment
 - Require approval for future profile changes
 - Log commissioning notes

## Product‐Aligned Device Profiles (Non‐Negotiable Configuration Standards)
NAVAS is a product umbrella. Your connectivity configuration MUST reflect the product's value promise.
### A) Vehicle Telematics (OLIWA / OLIWA‐PLUS / GUVNA / iVMS / iVMS‐PLUS / UKO)
Minimum telemetry set
 - GPS: lat/lon, speed, heading, timestamp
 - Connectivity: gsm, satellites, hdop/pdop
 - Power: external voltage, internal battery (if supported)
 - Ignition / ACC status
Recommended policies
 - Normal tracking: moderate interval while moving; slower while parked
 - Offline threshold: strict enough to catch faults early; not so strict it creates noise
Preventative maintenance
 - Weekly: check top 20 "most offline" units
 - Monthly: audit ignition wiring issues (common cause of wrong trip logic)
### B) Motorcycle Telematics (PIKI)
Your objective is ultra‐efficient tracking for high‐volume environments.
 - Prefer low-cost bundles
 - Enforce strong interval governance
 - Ensure location quality (GPS drift is common on low‐end installs)
Customer experience tactic
PIKI users judge you on:
1. "Can I see my boda now?"
2. "Did it stop moving unexpectedly?"
3. "Can I prove where it went?"
Your settings MUST prioritize reliability over fancy extras.
### C) Personnel Tracing (PATROL / CAPO / TOTO / WIATAG) 3⁄4♂
Critical parameters
 - Check-in/out events
 - SOS / panic events
 - Man-down / immobility (if device supports)
 - Battery level and charging status
Corrective maintenance
 - Battery complaints are operational failures:
 - confirm charging habits
 - adjust reporting interval
 - confirm device firmware
### D) Fuel Telematics (MAFUTA FLS / FLOW METER / CANBUS / FUEL CARD / STATION / GENSET) ⛽
Fuel data integrity is an audit function. You MUST protect:
 - Fuel level (probe)
 - Fuel used (CANBUS/OBD if available)
 - Fuel rate / consumption
 - Refuel and drain event logic
⚠ Rule: Never change fuel sensor calibration without:
 - Baseline validation (dipstick / tank chart)
 - Maker–checker approval
 - Recorded "before vs after" report
 - Customer sign-off where contract requires
### E) AI & Video Telematics (DASHCAM / DASH AI / MDVR / MDVR AI)
Video is the fastest path to token burn and cost overrun if unmanaged.
High-value video and AI parameters carry the highest revenue potential weighting (e.g., bandwidth usage, video snapshots, video events).
Bandwidth governance MUST include
1. Live streaming disabled by default unless contract demands it
2. Snapshot capture event-driven (not continuous)
3. Storage health monitoring (SD/HDD)
4. Offline video upload rules (avoid retry storms)
AI safety parameters you should expect
 - ADAS events (lane departure, forward collision, headway)
 - DMS events (yawning, distraction, seatbelt, smoking)
Preventative maintenance (video)
 - Weekly: check top bandwidth consumers
 - Monthly: verify storage status "OK" rate > 95%
 - Quarterly: firmware updates in controlled waves (pilot → expansion)

## SIM Card Intelligence (The Silent Margin Killer)
SIM cost problems look like "technical issues," but they are usually profit leakage.
### The 6 SIM cost leakage patterns you MUST monitor
1. Over-reporting (interval too aggressive)
2. Retry storms (poor coverage + retries)
3. Roaming surprises (cross-border / forced roaming near borders)
4. Video misuse (live view left running, uncontrolled streaming)
5. Wrong bundle type (tracking bundle used for video assets)
6. Dormant SIMs still consuming minimum fees
### SIM Governance SOP ✅
1. Classify SIMs into tiers:
 - Tier 1: Low data tracking (PIKI/OLIWA basic)
 - Tier 2: Standard tracking + events (fleet operations)
 - Tier 3: High bandwidth (MDVR / Dashcam AI)
2. Assign bundle profiles per tier
3. Set consumption alerts: 50%, 80%, 95% thresholds
4. Tag roaming zones (border operations, cross‐country routes)
5. Automate actions where allowed (rate limit, disable streaming, notify admin)
### AI + HIC tactic (Waswa AI + Admin approvals) ✈
Use AI to:
 - Detect anomalous data spikes (compare device vs fleet baseline)
 - Recommend bundle changes (tracking → video or downgrade)
 - Identify "unused enabled services" (enabled but no activity)
Then enforce HIC:
 - AI recommends ✅
 - Admin reviews
 - Admin approves + executes ✈
 - Audit log is stored
This is the only sustainable way to scale across UG/KE without drowning in support noise.

## Protocol & Integration Hub (Avoiding Data Corruption)
Protocols are where you win or lose:
 - Correct decoding of parameters
 - Correct interpretation of units (km vs miles, liters vs %)
 - Correct timestamp handling
 - Correct event classification
### Protocol change control (Mandatory) ⚠
When updating any parser/profile:
1. Create a draft version
2. Test on a pilot group (≤ 5 devices)
3. Validate:
 - location plot
 - ignition logic
 - sensor values (fuel/temp/door)
4. Enable for next wave (≤ 25 devices)
5. Roll out widely only after stability confirmation
6. Log rollback plan

## Connectivity Policy Templates (Standardization = Scale)
You MUST use templates because:
 - They reduce human error
 - They enable bulk governance
 - They reduce onboarding time
 - They keep billing predictable
### Connectivity policy template fields (You SHALL define)
 - Expected heartbeat interval (moving vs idle if supported)
 - Offline threshold (minutes/hours)
 - Retry rules (max retries, backoff)
 - Event priority (SOS > fuel theft > standard tracking)
 - Video rules (if applicable)
✅ Key takeaway: Without templates, every technician becomes a pricing engine by accident.

## Common Fault Scenarios & Corrective Actions
| Symptom | Likely Root Cause | Admin Action (CMS) | Field Action | HIC? |
| Unit "Offline" but customer says it's moving | wrong APN / no data / power issue | Check last message + GSM + voltage; validate SIM status | inspect power/ground/ignition, replace SIM if needed | No (unless bulk) |
| Unit shows wrong location | GPS antenna placement / spoof / cache | validate GPS quality params; check mapping | reposition antenna, check tracker placement | No |
| Fuel reading jumps | calibration wrong / sensor wiring | freeze changes; compare baseline | recalibrate with tank chart | ✅ Yes |
| Video streaming consumes massive data | live view left on / policy weak | enforce streaming caps + alerts | retrain users; update SOP | ✅ Yes |
| Many units go offline same day | APN change / carrier outage / parser change | check recent bulk changes; rollback if needed | engage carrier; dispatch triage | ✅ Yes |

## Section 8 Key Takeaways ✅
 - Connectivity is commercial governance in NAVAS, not "IT housekeeping."
 - Standardize with templates or you will lose margin.
 - Treat protocol, APN, and video policy changes as controlled changes (HIC).
 - Always commission with evidence (first data sanity checks + notes).
 - Use AI to detect anomalies, but keep humans accountable for actions. ✈

— PAGE BREAK —
# 9. ASSET & RESOURCE GOVERNANCE

## Purpose
This module is where you govern ownership, access, and accountability across NAVAS. If you are running Uganda + Kenya operations, your multi‐tenancy MUST be airtight.
You are responsible for:
1. Correct service structure (tenant hierarchies that match the business model)
2. RBAC enforcement (least privilege, auditable exceptions)
3. Clean object ownership (no orphan units, no cross-tenant contamination)
4. Controlled delegation (dealer/reseller governance without losing control)
5. Lifecycle discipline (onboard → operate → suspend → archive)

## Wialon‐Style Concept Alignment (Admin Mental Model)
If you are familiar with WialON CMS Manager, the mental model is similar:
 - A management system for top/dealer users that controls accounts, users, units, unit groups, and access. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system?utm_source=chatgpt.com))
 - Account/resource governance actions exist in the management interface and include bulk edits, logs, and restore-from-trash functions. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/accounts-and-resources/working-with-accounts-and-resources?utm_source=chatgpt.com))
 - Users are system objects with access rights, assigned by a system manager; "creator" matters for hierarchy. ([Wialon Help Centre](https://help.wialon.com/en/wialon-local/2104/user-guide/management-system/users?utm_source=chatgpt.com))
✅ NAVAS principle: We use this model, but we extend it with token governance, AI co-pilot oversight, and revenue-leakage controls.

## Governance Model (Hierarchy You MUST Maintain)
### Level 1 — Platform / Top Account
 - Full oversight across UG + KE
 - Defines global token policy versions
 - Defines standard templates (roles, device profiles, alert catalogs)
### Level 2 — Dealer / Reseller
 - Manages child tenants/accounts under delegas onboarding operations
 - Cannot override platform guardrails (unless explicitly permitted)
### Level 3 — Customer Admin
 - Manages their own users, assets, operational configs
 - Cannot manipulate platform billing logic beyond allowed entitlements
### Level 4 — End Users / Operators
 - Monitoring + workflows
 - Restricted from governance objects and billing controls

## Account Lifecycle (Mandatory SOP) ✅
### Stage 1 — Create Account (CREATE).
Asset & Resource Governance → Accounts → Create
You MUST define:
1. Account name + code (use naming conventions below)
2. Territory (UG / KE)
3. Currency + tax profile
4. Timezone + measurement system
5. Enabled products (OLIWA/PIKI/MAFUTA/MDVR/VEBA/etc.)
6. Baseline service entitlements + token SKU assignment
7. Data retention policy (history duration, logs, media retention)
8. Delegation model (if the account is a reseller)
### Stage 2 — Provision Access Baseline (UPDATE).
You MUST create:
 - Customer Admin user
 - Default operator roles
 - Read-only auditor role (recommended)
 - Standard groups (units, drivers, routes)
### Stage 3 — Link Assets (UPDATE).
 - Ensure every unit belongs to correct account and groups
 - Ensure metadata is complete (plate, asset ID, driver mapping where used)
### Stage 4 — Operational Handover (HIC).
Before the customer goes live:
 - Confirm all alerts are configured
 - Confirm notification channels
 - Confirm billing/tokens are active
 - Confirm support escalation route
### Stage 5 — Suspend / Reactivate (CONTROLLED).
Suspension is a governance action:
 - Must be logged (reason, ticket number, approval)
 - Must define what still works (e.g., safety tracking minimal updates)
### Stage 6 — Archive / Offboard (ARCHIVE).
 - Deactivate services
 - Export customer data if contract requires
 - Archive audit logs and billing ledger
 - Preserve evidentiary logs for required retention period

## Naming Conventions (You SHALL Enforce)
Consistency is operational power.
### Account codes
 - UG-<CLIENT>-<SEGMENT>
 - KE-<CLIENT>-<SEGMENT>
### Unit naming
 - Vehicles: KDA123A | Toyota Hilux | Kampala
 - Motorcycles: BODA-01492 | StageName | Town
 - Staff: STAFF-0021 | Name | Team
 - Genset: GEN-01 | SiteName | District
✅ Customer experience benefit: consistent names reduce support friction and speed up incident resolution.

## RBAC (Role‐Based Access Control) — The Standard Matrix ✅
You MUST implement least privilege. Below is a recommended baseline.
| Role | Can Create Objects | Can Change Billing/Token Policy | Can Impersonate | Can Bulk Edit | Recommended Use |
| System Admin (Platform) | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | HQ governance, critical changes |
| Dealer Admin | ✅ Limited | ❌ No (policy), ✅ limited (top-ups if allowed) | ⚠ Optional | ✅ Yes (within scope) | Reseller operations |
| Customer Admin | ✅ Within tenant | ❌ No | ⚠ Limited | ✅ Limited | Customer self-management |
| Ops Supervisor | ✅ Ops objects only | ❌ No | ❌ No | ✅ Limited | Dispatch, alerts, reports |
| Finance Officer | ❌ No | ✅ Top-ups/ledger actions | ❌ No | ✅ Limited | Billing, reconciliation |
| Support Agent | ❌ No | ❌ No | ⚠ View-as only | ❌ No | Troubleshooting |
| Auditor / Compliance | ❌ No | ❌ No | ❌ No | ❌ No | Read-only evidence access |

✈ HIC rule: If impersonation exists, it MUST create an audit record (who, when, why, and what was touched).

## Users & Identity (CREATE / UPDATE / SUSPEND)
### User creation SOP.
1. Create user in correct account context
2. Assign role(s)
3. Assign scope (unit groups, resources, apps)
4. Enforce MFA where available (especially admins)
5. Issue credentials via secure channel
6. Record onboarding completion
### User suspension SOP (Security & Offboarding).
You MUST suspend when:
 - staff exits the company
 - customer requests access removal
 - compromise is suspected
 - role changes require re-approval
Minimum actions
 - disable login
 - revoke API tokens
 - preserve audit logs
 - notify stakeholders if sensitive role

## Resources & Object Ownership (No Orphans Allowed)
A common failure in telematics operations is "objects floating without owners," e.g.:
 - units created under wrong account
 - report templates stored in wrong resource
 - notification templates not linked properly
 - drivers created by end users with no governance
✅ Your governance objective: every object must be traceable to:
 - creator
 - owner account
 - effective permissions
 - audit events
This mirrors classic management-system principles where objects are created/managed by privileged users and controlled via access rights. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system?utm_source=chatgpt.com)) ([Wialon Help Centre](https://help.wialon.com/en/wialon-local/2104/user-guide/management-system/users?utm_source=chatgpt.com))

## Maker–Checker (HIC) for Governance Changes ✈
Apply maker–checker to:
1. Role changes for privileged users
2. Bulk unit reassignment between accounts
3. Data retention policy changes
4. Enabling/disabling major products (MDVR/VEBA/MAFUTA)
5. Any billing/token entitlement changes
Minimum approval record
 - change request ID
 - reason + business impact
 - scope (# of units/users affected)
 - rollback plan
 - approver + timestamp

## AI Assist in Governance (Waswa AI Controls)
AI MUST be used to reduce admin fatigue, but MUST NOT replace accountability.
### Approved AI use cases (Admin-safe) ✅
 - Identify over-permissioned users ("admin drift")
 - Detect inactive users and recommend cleanup
 - Recommend role templates based on behavior (ops vs finance vs support)
 - Summarize audit logs for investigations
 - Flag unusual cross-account access patterns
### Not approved without HIC ⚠
 - AI auto-assigning admin roles
 - AI disabling accounts
 - AI changing token policy versions
 - AI changing protocol profiles or SIM policies

## Preventative & Correctivovernance)
### Preventative (monthly) ✅
1. Run "Dormant users" report → disable or confirm need
2. Review privileged roles → validate job alignment
3. Audit cross-tenant object ownership
4. Confirm reseller/dealer scopes still correct
5. Validate data retention is aligned to contract tier
### Corrective (when incidents occur)  ̄
 - If data leaks across customers: treat as a security incident
 - Immediately:
 1. freeze access changes
 2. revoke suspected roles
 3. export audit logs
 4. identify scope of exposure
 5. implement remediation and document

## Section 9 Key Takeaways ✅
 - Governance is not optional; it is the foundation of UG/KE scale.
 - RBAC MUST be standardized; exceptions MUST be audited.
 - Maker–checker prevents "silent misconfiguration" disasters.
 - AI helps you identify drift; humans must approve high-risk changes. ✈
 - Maintain object ownership discipline: no orphan units, no orphan resources.

If you want me to proceed immediately (no pauses) into:
— PAGE BREAK —
# 10. TELEMATICS & GIS OPS
...and keep going through VEBA, Utility & Support, HIC + Waswa AI, Incident Management, Security, Troubleshooting, and the Acronyms Table at the end, tell me "continue" and I'll push the next full section in the same format. ✅
According to a document from 20.FEB.2026, NAVAS CMS (Cockpit) is the command & control layer for multi-tenant telematics operations — combining RBAC, token enforcement, mobile money payment rails, operational KPIs, and Waswa AI co‐pilot for guided admin actions (with Human‐In‐Control governance).

## ⛳ COPY-TO-GOOGLE-DOC FORMAT NOTE (KEEP / DELETE AS YOU LIKE)
 - Landscape: Set Google Doc → *File → Page setup → Landscape*.
 - Mandatory Page Breaks: Insert a page break wherever you see: --- PAGE BREAK ---
 - Footer (set once):
 - Left: NAVAS IoT System - CMS Module - 01.MAR. 2026
 - Center: You name it, we track it. ✅
 - Page number: Bottom-right (Insert → Page numbers)
--- PAGE BREAK ---
# UTILITY & SUPPORT MODULE — ADD‐ON APPS LIBRARY & PROVISIONING

## 1. Module Purpose & Why It Matters (Non‐Negotiable) ✅
The Add‐On Apps Library is where you control expansion revenue and reduce operational chaos.
As a System Administrator, you must use this module to:
1. Standardize how add‐on apps are activated across tenants (UG/KE).
2. Govern activation using HIC/HITL gates (avoid leakage, fraud, and compliance breaches).
3. Bind monetization to tokens and payment rails (mobile money / ePayments).
4. Protect customer experience by provisioning only when dependencies and health checks pass.
✅ Key Takeaway: *Provisioning is a controlled operational change — not a "toggle". You must treat it as "mini‐deployment" with approvals, audit, and rollback.*
Source anchor (UI + governance model): Screen 27 defines the provisioning drawer as a right‐blade with dependency checks, token rules, payment rails, and an "HITL Required" badge.

## 2. Screen Anatomy (So You Train Others Correctly)
Your CMS screens follow a consistent structure. Train admins to recognize it fast:
1. Nav Rail: Primary module icons (fast switching).
2. Accordion Sidebar: Grouped pages under the selected module.
3. Workspace: Primary table/cards.
4. Standard Strip: Tenant selector + RBAC badge + token/burn indicators + system health.
5. Right Blade / Drawer: "Provision App" workflow and governance.
This pattern is explicitly reflected in the Screen 27 layout and mobile parity specification.
### Standard Strip.
This is your at-a-glance safety rail:
 - Tenant context (top account → dealer → org)
 - RBAC badge (example: SYSTEM_ADMIN)
 - Token Balance and Token Burn rate
 - Top-up shortcut
 - System Health status dot
These indicators are shown directly in the screen spec and must be treated as operational signals, not decoration.
### Waswa AI Widget.
A floating co‐pilot provides insights like:
 - leakage risk
 - unused apps > 30 days
 - trial→paid nudges via WhatsApp templates
 - recommended governance tightening
...and is shown with "HIC ON".
 Trainer tip: Teach admins to treat Waswa AI as "recommendation + evidence", not "autopilot". Anything that changes money, access, or compliance must stay HIC‐approved.

## 3. CRUD Model for Add‐On Apps (Must Be Enforced)
Add‐On Apps Library must support (and you must enforce) a complete lifecycle:
1. Create (New app record)
2. Read (Catalog listing + app detail)
3. Update (Edit metadata, dependencies, token bind, rails)
4. Disable / Deprovision (Tenant-level)
5. Archive → Trash (Soft delete)
6. Restore (From Trash)
The UI spec explicitly calls out CRUD controls: +New App, Edit, Archive → Trash, Restore.
### Policy Rule.
You must not allow "hard delete" for provisioned apps without:
 - 2‐person approval (HIC)
 - audit trail retention
 - data retention decision (retain, mask, purge)
 - customer notification plan
⚠ Risk: Hard delete without governance creates regulatory exposure (audit gaps) and customer disputes (missing evidence).

## 4. Provisioning Workflow (Mandatory "5‐Gate" Process)
When you click an app row, a right drawer opens: Provision App — {AppName} with HITL Required badge and tabs such as Enablement, Billing Tokens, Payments, Audit Trail.
You must provision with the following 5 gates:
### Gate 1 — Tenant Context Lock
1. Confirm selected tenant chain: TopAccount → Dealer → Org
2. Validate you are acting in the right country context: UGX vs KES pricing, UG vs KE tax rules, rails availability.
The drawer shows tenant context explicitly (example: Dealer‐KE / Org: BodaFleet / Org: CorporateHire).
✅ Required output: A provisioning record that includes tenant ID, dealer ID, country, currency, timestamp, actor, and justification.

### Gate 2 — Dependency Checks (Non‐Optional) ✅
Enablement toggles must run dependency checks before activation:
 - Enable app for tenant
 - Require KYC for Owners
 - Enable Leakage Shield (AI)
 - Require Telematics Unit Linked
 - Allow Cash Trips (Trusted only) *(default OFF unless approved)*
These toggles appear directly in the drawer spec and represent your governance baseline.
#### Trainer Directive.
Teach admins: If "Require Telematics Unit Linked" fails → stop.
Do not "turn on features" without data sources.
⚠ Risk: Enabling VEBA/Logistics/JMS without linked assets creates ghost usage, disputes, and revenue leakage.

### Gate 3 — Token Binding Rules (Monetize Correctly) 3
Before activation you must bind:
1. Which token type powers usage (time, event, AI inference, video bandwidth, listing time).
2. Where enforcement occurs (write‐time, read‐time, hybrid).
3. What happens on insufficient tokens (block, mask, grace, soft-store + upsell prompt).
NAVAS token strategy explicitly supports enforcement at write‐time and read‐time, enabling upsell without data loss (store but mask).
✅ Required output: Token policy attached to tenant + app + product scope.

### Gate 4 — Payments & Settlement Rails 2
Attach rails (UG/KE) for:
 - Wallet top‐ups
 - auto-renewal
 - escrow/settlement (where applicable)
The provisioning drawer bottom state explicitly includes Payments & Mobile Money Rails and lists rails such as M‐Pesa and MTN MoMo as toggles.
 EA market reality: If you ship without working rails, you don't have a product — you have a demo.

### Gate 5 — Audit Trail & HIC Sign‐Off 3⁄4
Every provisioning action must generate:
 - configuration snapshot
 - actor identity + RBAC role
 - reason code (new sale, upsell, compliance, pilot, remediation)
 - Waswa AI suggestions (if used) + your final decision
 - effective date/time
 - rollback plan + rollback owner
The Screen 27 drawer includes an Audit Trail tab specifically; treat it as mandatory evidence, not optional logging.

## 5. Add‐On Apps: Standard Provisioning Blueprints (3D Product Alignment)
Below are implementable blueprints. You must treat them as the default unless a project requires deviation.
### 5.1 BI DASHBOARDS
Purpose: executive visibility (SLA, utilization, collections, driver behavior, fuel anomalies, uptime).
Best-fit product domains:
 - Vehicle Telematics: OLIWA, OLIWA‐PLUS, iVMS, iVMS‐PLUS, GUVNA
 - Fuel: MAFUTA (CANBUS / Flow / FLS / Fuel Card / Station), GENSET
 - Video/AI: DASH AI, DASHCAM, MDVR, MDVR AI
 - GIT/IoT: KAGO, PASO, PAWA, THERMO
 - Personnel: PIKI, PATROL, CAPO, TOTO, WIATAG
Dependency checklist.
 - Data completeness thresholds (min 85% reporting over last 7 days).
 - Timezone alignment (EAT).
 - Country/currency mapping (UGX/KES).
 - Tenant contact matrix (who receives what).
Token recommendation.
 - Read‐time dashboard access tokens (protect heavy queries).
 - AI insight tokens for anomaly summarization.
✅ CX tactic: Provide a weekly digest to fleet owners — reduces "follow-ups" and improves perceived reliability, aligned with "Ops Insights + weekly digest" user stories.

### 5.2 ECO
Purpose: eco‐driving scoring, reduction of fuel burn and harsh events.
Dependency checklist.
 - Speed + ignition reliability (no drifting sensors).
 - Calibrated fuel source if used (CANBUS / FLS / flow meter).
 - Driver identifiers (where available).
Token recommendation.
 - Event tokens (overspeed, harsh brake/accel).
 - Report tokens for scoring exports.
✅ Opportunity: Eco is an upsell into insurance / compliance programs (especially fleets with corporate governance).

### 5.3 DSC
Purpose: safety compliance, driver discipline, incident handling.
Dependency checklist.
 - Standard alert templates per region.
 - Escalation contact groups mapped.
Token recommendation.
 - Event tokens (safety incidents).
 - Messaging tokens (WhatsApp/SMS).
✅ CX tactic: use WhatsApp "first actions" templates to reduce escalation load, aligned to "Self‐Service Coach + Alert Orchestrator".

### 5.4 FLEETRUN
Purpose: dispatch operations and utilization.
Dependency checklist.
 - Live tracking reliability.
 - Geofence library (depots, client locations).
 - Driver/vehicle assignments.
Token recommendation.
 - Time tokens for continuous dispatch visibility.
 - Routing tokens (distance/mapping usage when enabled).

### 5.5 INSPECTA
Purpose: inspections, preventative maintenance workflows.
Dependency checklist.
 - Asset registry correctness (VIN/chassis/plate).
 - Service intervals + reminders configured.
 - Evidence capture (photos/checklists).
Token recommendation.
 - Job card tokens (per inspection).
 - Storage tokens (attachments).
✅ Preventative maintenance tactic: INSPECTA should be provisioned with default checklists per product domain (e.g., camera wiring checks for DASHCAM/MDVR; fuel sensor calibration checks for MAFUTA).

### 5.6 JMS
Purpose: Job management system for field works (installs, maintenance, troubleshooting).
Dependency checklist.
 - Technician roster + regions.
 - Spare parts inventory references.
 - Ticketing linkage (Odoo / helpdesk).
AI/HIC tactic.
Use "Field Ops Router + Scheduler" automation to propose technician assignment and ETA; staff must confirm for high priority jobs.

### 5.7 LOGISTICS
Purpose: trip planning, proof of delivery, ETA & milestones.
Dependency checklist.
 - Geofences for customer points.
 - Driver mobile workflows.
 - Thermo integration when cold chain.
Token recommendation.
 - Trip tokens (per trip plan / replay).
 - Event tokens (milestone pings).
✅ CX tactic: milestone pings + weekly digest reduces uncertainty for fleet managers.

### 5.8 NIMBUS ☁
Purpose: cloud utilities — storage, archival, distribution, data exports.
Dependency checklist.
 - Retention policies per tenant (compliance).
 - Export permissions (RBAC, audit).
Token recommendation.
 - Storage tokens
 - Export tokens
✅ Risk mitigation: restrict exports to privileged roles; enforce audit for every export event.

### 5.9 VEBA 3⁄4
Purpose: marketplace / mobility listing, booking flows, or asset monetization.
The provisioning drawer example explicitly uses VEBA and includes "HITL Required", KYC requirement, leakage shield AI, telematics link requirement, and cash-trips gating.
Non‐negotiable gating.
1. KYC must be ON for owners.
2. Telematics unit link must be ON.
3. Leakage shield AI must be ON.
4. Cash trips: only trusted accounts with explicit approval.
Token recommendation.
 - Commercial listing tokens (time-based listing visibility).
 - Trip/event tokens depending on transactional model.
 - Fraud/Leakage AI tokens (if billed).
✅ Opportunity: Waswa AI can identify tenants with high leakage risk and unused apps and recommend nudges; admins must approve and apply templates under HIC governance.

## 6. Waswa AI + HIC Tactics Inside Add‐On Provisioning  ✅
Your admin behavior must follow this pattern:
### 6.1 The "AI → Evidence → Approval" Loop
1. Ask AI for recommendation (dependency issues, best token policy, rails).
2. Require AI to show evidence (tenant usage, health, last 30 days).
3. Apply HIC review checklist (below).
4. Save & apply.
The UI spec literally places Ask AI and "Type a command..." inside the Waswa widget, reinforcing this loop.
### 6.2 HIC Review Checklist (Provisioning Decision)
Before you click Save & Apply, you must confirm:
1. Tenant correctness (right org, country, currency).
2. KYC gating correct for VEBA-like apps.
3. Token policy attached and enforcement mode defined.
4. Payment rails verified (M‐Pesa / MTN / Airtel availability).
5. Rollback plan written (who disables if issues arise).
6. Customer comms plan (what changes for end users).
7. Audit trail complete.
✅ Customer experience tactic: send "What changed" message within 15 minutes of enabling an app — prevent confusion and reduce tickets.

## 7. Preventative & Corrective Maintenance Notes (Add‐On Apps)
### 7.1 Preventative
You must schedule monthly checks:
 - Apps enabled but unused > 30 days → perform a value audit and decide: retrain / nudge / disable.
 - Crash rate, support tickets, and health indicator must be reviewed weekly (Screen 27 KPI cards).
### 7.2 Corrective
When an app is "enabled" but not delivering value:
1. Validate ingestion health and permissions.
2. Validate token enforcement is not masking required data incorrectly.
3. Validate user roles have necessary rights.
4. Validate comms (templates, alerts) are enabled.

### Section Sources (for audit / traceability only)
 - Add‐On Apps Library Screen 27 UI pattern, provisioning drawer, governance toggles, payments rails, and Waswa AI widget.
--- PAGE BREAK ---
# TOKENOMICS & REVENUE MODULE — UNIVERSAL TOKEN ENGINE ADMINISTRATION

## 1. Non‐Negotiable Principle: Tokens Are Your Operating System 3✅
In NAVAS, the token engine is not "billing only". It is:
 - access control to services (time-based and dynamic services)
 - visibility control to data (parameter gating, masking, upsell without loss)
 - cost control (bandwidth, storage, AI inference)
 - cashflow control (wallet balance, top‐ups, dunning)
NAVAS token strategy explicitly enforces tokens at both write-time and read-time, and supports masking to enable upsell while retaining raw data.
✅ Key Takeaway: *If you manage tokens well, you reduce churn, increase ARPU, and prevent disputes. If you manage tokens badly, you create service pauses, angry customers, and revenue leakage.*

## 2. Token Taxonomy (Standard Set — Must Be Used) 3⁄4
The recommended "final" token taxonomy includes:
1. Core Time Tokens — access & uptime
2. Data Parameter Tokens — data visibility
3. Event Tokens — incidents & alerts
4. AI Inference Tokens — intelligence calls
5. Video Bandwidth Tokens — streams & snapshots
6. Commercial Listing Tokens — VEBA / marketplace use
This taxonomy is explicitly described as best-in-class and must be your default structure.
### Trainer Directive.
Do not design "random tokens per feature". Use the taxonomy, then bundle around use cases.

## 3. Token Enforcement Types (How Services Are Controlled) ⚙
You will configure tokens into one of three enforcement types:
1. Dynamic Token (time / validity window)
2. Parameter Token (data visibility)
3. Hybrid (dynamic + parameter)
Admin defines token type and binds scope to products such as OLIWA, PIKI, UKO, VEBA and region pricing for UG/KE.
### 3.1 Dynamic Token Enforcement
For dynamic tokens, the system checks validity window:
 - active → allow service
 - paused → do not decrement
 - expired → block service
Examples include live map, trip replay, VEBA listing, AI inference calls.
### 3.2 Parameter Token Enforcement
For parameter-based tokens:
 - device sends all IOs
 - system compares each parameter against subscription
 - allowed → store + display
 - not allowed → store but mask/soft‐store
 - UI shows "Higher Token Needed"
This is the mechanism enabling upsell without losing data and enabling retroactive insights.
 CX tactic: Masking (not deleting) prevents "you stole my data" disputes. It also enables "upgrade to unlock last 90 days" promotions.

## 4. Backend Token Lifecycle (Admin Must Understand This)
The token lifecycle maps into the platform architecture:
### Step 1 — Token Creation (CMS Admin)
Admin defines:
 - token type (dynamic/parameter/hybrid)
 - scope (product)
 - durations
 - parameters
 - pause rules
 - region pricing (UG/KE)
 - discount curve (time-based)
These are explicit fields for token definition in the billing strategy.
### Step 2 — Token Purchase → Subscription Instance
When tokens are bought:
 - subscription instance is created
 - bound to user, asset, product, token definition, time window
 - same token type can exist multiple times under one user and be consumed independently
This is highlighted as a key design win for fleet-level flexibility.
### Step 3 — Data Ingestion & System Flow
The strategy maps ingestion flow:
 - device sends data
 - core server parses sockets
 - Cassandra stores raw
 - Kafka broadcasts
 - Redis buffers hot data
 - Node SSE streams to apps
Token checks happen at write-time and read-time.

## 5. The Pricing Engine (How You Must Think About Tokens)
Your pricing must connect to billing units (not arbitrary "token points"). The strategy flags a critical gap: billing units ≠ tokens, and tokens must map to real units such as:
 - per hour
 - per event
 - per image
 - per km
 - per AI inference
 - per MB streamed
These units exist in the parameter catalog and must be monetized explicitly.
### Cost vs Margin Awareness. ⚠
Your token pricing must be aware of cost drivers:
 - GPU inference
 - bandwidth
 - storage
 - Kafka/Redis throughput
Otherwise you risk being revenue positive but margin negative.
✅ Key Takeaway: *Every token SKU must have a "cost driver" note. Admins must not publish token SKUs without cost mapping.*

## 6. Token Bundling Strategy (Sell Use‐Cases, Not IOs)  ̄
The strategy requires bundling around outcomes ("Fleet Safety Pro"), combining:
 - time token (24/7)
 - overspeed + harsh events
 - driver scorecard
 - AI inferences/month
...and notes the commercial impact: locks customer in, raises ARPU, reduces churn.
### 6.1 Recommended Bundles by 3D Product Domain
Below are default bundles you should maintain in CMS as templates.
#### A) Vehicle Tracking Bundle (OLIWA / UKO / iVMS)
 - Core time token
 - Parameter token: location, ignition, mileage
 - Event token: geofence in/out
 - Optional: reporting/export token
#### B) Personnel Safety Bundle (PIKI / PATROL / CAPO / TOTO / WIATAG)
 - Core time token
 - Event tokens: SOS/panic, out-of-zone
 - Messaging token: WhatsApp alerts to supervisors
#### C) Fuel Control Bundle (MAFUTA variants + GENSET) ⛽
 - Core time token
 - Parameter token: fuel level/flow/CAN
 - Event token: drain/refuel anomaly
 - BI token: weekly fuel variance
#### D) Video + AI Safety Bundle (DASH AI / DASHCAM / MDVR / MDVR AI)
 - Core time token
 - Video bandwidth tokens
 - AI inference tokens (DMS/ADAS events)
 - Storage tokens (clip retention)
✅ Push high-margin tokens: Strategy explicitly flags AI video events, ADAS/DMS, VEBA listing time, and compliance reports as high-margin categories to push aggressively.

## 7. Token Rule DSL (Admin-Friendly Governance Layer) 3⁄4⚙
The strategy defines a token rule DSL pattern:
 - WHAT: unit of billing
 - WHEN: trigger point
 - BY: cost model
 - OVER: scope
 - FOR: product/event group
 - APPLY: deductions/limits/blocks/notifications
...and gives example rule structure. This is your governance tool to standardize monetization.
### Admin Directive.
For every new token SKU, you must:
1. Define the rule in DSL form (for audit).
2. Map it to enforcement points (write-time/read-time).
3. Attach "customer story" label (safety, savings, compliance, convenience) — strategy notes tokens must be story-wrapped, not just technical.

## 8. Wallet Policies (Prevent Service Interruptions) ✅
### 8.1 Low Balance Prevention
You must configure:
1. Threshold alerts (e.g., 20% remaining)
2. Auto top-up prompts (WhatsApp/SMS/email)
3. Grace policies (optional, controlled)
The AI user stories explicitly support automated renewal reminders with payment links to reduce late renewals and service interruptions.
### 8.2 Dunning and Suspension (HIC‐Controlled)
If you apply suspension/resume:
 - automation may propose
 - finance must approve
 - action must be audited
This HITL gate is explicitly mandated in the AI agent strategy: suspension/resume must be finance-approved.
⚠ Risk: Auto-suspension without finance approval causes reputational damage and legal disputes. Treat this as high-risk.

## 9. Token + Mobile Money Rails (UG/KE Operational Reality) 2
NAVAS policy explicitly describes token payment rails and mobile money hooks, including M‐Pesa, MTN, Airtel, and instant top‐ups; this is core to the PAYG design approach.
Additionally, the vision scope highlights token packages, simplified mobile money transactions, and even SMS fallback in low-connectivity areas — relevant for UG/KE deployment constraints.
### Admin Operating Rule.
In Uganda/Kenya, a token model fails if:
 - payment rails are unreliable
 - payment links aren't delivered correctly
 - settlement reconciliation isn't auditable
So you must implement:
1. Payment link templates (WhatsApp primary)
2. Fallback channels (SMS/email)
3. Reconciliation report (daily)
4. Dispute workflow (ticket → evidence → settlement)

## 10. HIC + Waswa AI: Token Governance Tactics  ✅
### 10.1 Use Waswa AI for Detection, Not Final Action
Examples of acceptable AI work:
 - anomaly detection in token burn rates
 - suggesting bundles
 - forecasting churn risk
 - recommending nudges (trial→paid)
The Screen 27 widget explicitly proposes insights and nudges; treat this as advisory output.
### 10.2 Mandatory HIC Gates
You must enforce human approvals for:
1. token price changes
2. bundle definition changes
3. enforcement behavior changes (block vs mask vs grace)
4. suspension/resume triggers
5. creation of "new billing units" (video/AI/high-cost units)
✅ Key Takeaway: *Any action that impacts money, access, or compliance must remain human-approved and auditable.*

## 11. Preventative & Corrective Maintenance Notes (Token Engine)
### 11.1 Preventative Controls
You must review weekly:
 - top 20 tenants by burn rate
 - token leakage risk signals
 - negative balances or near-zero events
 - high-cost AI/video usage spikes
### 11.2 Corrective Controls
If you see unexpected token burn:
1. Validate token enforcement points (write/read).
2. Validate subscription instances are correctly bound (user/asset/product).
3. Validate that "paused" tokens are not decrementing.
4. Validate that data masking rules aren't incorrectly blocking essential operations.

### Section Sources (for audit / traceability only)
 - Token taxonomy, bundling, high-margin token categories, and enforcement behaviors (write/read-time, masking).
 - Token lifecycle (creation → subscription instance → ingestion flow → enforcement).
 - Token rule DSL structure for standardized governance.
 - EA market mobile money + token PAYG and operational constraints (mobile money rails + simplified transactions + low connectivity support).
--- PAGE BREAK ---
# NEXT SECTION (AUTOMATIC CONTINUATION): OPERATIONS MODULE — INCIDENT, SLA, MTTR, & AI‐ASSISTED TRIAGE

✅ I will continue next with:
 - SLA/MTTR dashboards & enforcement
 - Incident classification (Sev‐1/2/3)
 - Escalation workflow + HIC gates
 - Preventative & corrective maintenance runbooks by product domain
 - Health Sentinel + Resolution Co‐Pilot integration (Odoo/Wialon/n8n workflows)

### Optional Downloadable Source Chips (ignore when copying into Google Doc)
 CONTINUATION NOTE (Google Docs):
 - Orientation: Landscape (File → Page setup → Landscape)
 - Font & spacing: 12pt sans‐serif (Arial/Roboto), 1.15 spacing, Justified
 - Footer: Left = NAVAS IoT System - CMS Module - 01.MAR. 2026 | Center = "You name it, we track it." ✅ | Page number Bottom‐Right
 - Wherever you see ⧉ PAGE BREAK, insert a page break (Insert → Break → Page break).
 - Headings are formatted to match your H1/H2/H3 rules (H1 = ALL CAPS + rule; H2 = bold Title Case; H3/H4 = run‐in *italic*).

⧉ PAGE BREAK
# SECTION 08: TOKENOMICS & REVENUE (TOKEN ENGINE, BILLING & PAYMENTS)

## 8.1 Purpose, Scope, And Admin Authority
Purpose. This section defines the mandatory operating procedures for system administrators managing Token Engine, Subscriptions, Billing, Invoicing, and Payments inside NAVAS CMS, including enforcement controls, audit requirements, and Human‐in‐Control (HIC) gates.
Scope. Applies to all products and add‐ons under 3D Services Limited in Uganda and Kenya, including but not limited to: OLIWA, OLIWA‐PLUS, iVMS, iVMS‐PLUS, PIKI, UKO, DASH AI, DASHCAM, MDVR, MDVR AI, MAFUTA variants, KAGO/PASO/PAWA/THERMO, VEBA, and all listed Add‐On Apps (ECO, DSC, FleetRun, Inspecta, JMS, Logistics, Nimbus, BI Dashboards).
Admin authority.
1. ✅ Only Top Account / Dealer‐level administrators may:
 - Create new token definitions (SKUs) and pricing rules
 - Change regional pricing (UG/KE)
 - Create/modify billing plans
 - Enable/disable payment rails
 - Apply credits/write‐offs beyond a defined threshold
2. ⚠ Any pricing rule change is a revenue‐risk operation and must follow HIC Maker‐Checker approval.
✅ Key takeaway: Token administration is not "settings work". It is financial operations. Treat every change as audit‐visible and reversible.

## 8.2 CMS Navigation Path And UI Expectation
Where to find Tokenomics modules.
 - Tokenomics & Revenue → Token Engine
 - Tokenomics & Revenue → Billing & Invoicing
 - Tokenomics & Revenue → Payments & Mobile Money
 - Utility & Support → Add‐On Apps Library (pricing + provisioning often sits here in the operator flow)
UI pattern you must expect.
 - A left navigation rail + sidebar structure (grouped modules)
 - Card‐based workspaces for lists and catalogs
 - A right‐side blade/drawer for configuration and provisioning actions
 - A visible "HITL Required" indicator for sensitive actions (pricing, enabling paid apps, KYC gating, payment rails)

## 8.3 Token Fundamentals You Must Enforce
8.3.1 Token Types (Mandatory Definitions)
NAVAS tokens must be defined as one of the following types:
1. Dynamic Tokens
 - Used to allow/deny time‐window access to a service (e.g., Live Map, Trip Replay, VEBA listing time, AI inference windows).
2. Parameter Tokens
 - Used to allow/deny access to specific data elements (parameters), while preserving raw data to support upsell later.
3. Hybrid Tokens
 - Combine time access + parameter access for premium bundles.
These classifications are explicitly required at creation time in CMS Token Engine .
8.3.2 Token Scope (Product Binding)
Every token definition must be bound to:
 - Product scope (e.g., OLIWA, PIKI, UKO, VEBA)
 - Duration options
 - Region pricing (UG / KE)
 - Discount curve (time‐based)
✅ Key takeaway: Tokens are not generic. They are Product‐scoped financial contracts.

## 8.4 Token Duration Discount Factor (Time‐Based Pricing Rules)
8.4.1 What The Discount Factor Means
The token discount factor is the rule that ensures longer commitments apply a discount curve. Your CMS must enforce the discount factor table as the pricing "source of truth" for durations (hour → year) .
8.4.2 Example: Time‐Based Token Pricing Table (Operational Use)
From NAVAS pricing tables, you have explicit duration pricing for PIKI/OLIWA (UG) and PIKI/UKO (KE), e.g.:
 - 1 Hour(s): Discount factor 1; PIKI(UG) and OLIWA(UG) values are defined; PIKI(KE) and UKO(KE) values are defined
 - 1 Day(s): Discount factor 1; daily values defined
 - 1 Month(s): discount factor 0.98; monthly values defined
 - 1 Year(s): discount factor 0.92; yearly values defined
 - 5 Year(s): discount factor 0.90; 5‐year values defined
8.4.3 Admin Directive: How You Apply The Table In CMS
1. Do not manually type discount logic per product.
2. Configure the discount factor curve once, then bind it to token SKUs by:
 - Product scope
 - Region (UGX / KES)
 - Duration family (Hours/Days/Months/Years)
3. Lock the curve behind HIC approval.
4. Any exception pricing must be implemented as a Promotion Layer, not by corrupting the base curve.
 Trainer tactic: If sales asks for "special pricing," instruct them:
 - "We can create a promo SKU with a start/end date + audit trail, but we will not alter the base curve." ✅

## 8.5 Subscription Instance Model (How Purchases Must Bind)
8.5.1 What Happens When A Customer Buys Tokens
When tokens are purchased, a Subscription Instance must be created and uniquely bound to:
 - User
 - Asset
 - Product
 - Token definition
 - Time window
8.5.2 Why This Is Non‐Negotiable (Operational Outcomes)
This binding enables asset‐level flexibility where:
 - Asset A can expire
 - Asset B continues
 - Same token type can exist multiple times under one user and be consumed independently
✅ Admin directive: Never create "fleet tokens" that cannot be traced to asset/product/time window. That design leaks revenue and destroys auditability.

## 8.6 Token Enforcement Points (Write‐Time vs Read‐Time Controls)
8.6.1 Enforcement is Multi‐Point
Token checks must occur at:
1. Write‐time (store/skip parameter or store/mask logic)
2. Read‐time (display/block parameter or block service UI)
8.6.2 Dynamic Token Enforcement
If token is dynamic:
 - If active → allow service
 - If paused → do not decrement
 - If expired → block service
8.6.3 Parameter Token Enforcement (Upsell‐Safe)
If token is parameter‐based:
 - System compares each parameter against subscription
 - If allowed → store + display
 - If not allowed → store but mask / soft‐store
 - UI must present an upsell prompt such as "Higher Token Needed"
✅ Key takeaway: This is the "upsell without data loss" architecture. You monetize by unlocking visibility, not by losing raw telemetry.

## 8.7 Billing Units Must Map To Tokens
8.7.1 Mandatory Mapping
Tokens must map to explicit billing units such as:
 - per hour
 - per event
 - per image
 - per km
 - per AI inference
 - per MB streamed
8.7.2 Admin Procedure (Token SKU Design Checklist)
For every token SKU you create, you must fill the following metadata:
1. SKU name (Product + tier + region)
2. Token type (Dynamic / Parameter / Hybrid)
3. Billing unit (choose one primary)
4. Metering source (what generates usage events)
5. Consumption rules (FIFO; pause rules; grace rules)
6. Enforcement surface
 - UI feature gating
 - Parameter masking
 - API rate limit gating
7. Audit requirements
 - Who can adjust?
 - Who approves?
 - Which log is written?
⚠ Policy rule: If Billing Unit is blank, the SKU must not be published to production.

## 8.8 Subscriptions (Traditional) vs Tokens (Time‐Based) — How CMS Must Support Both
8.8.1 Subscription Prices For 3D Products
Your price lists include subscription SKUs for products such as iVMS, iVMS‐PLUS, KAGO, LOGISTICS, MAFUTA variants, MDVR variants, OLIWA, OLIWA‐PLUS, PASO, PAWA, PIKI, SATO, THERMO, and add‐on apps such as Nimbus, Driver Score Card, Eco Driving, FleetRun, Inspecta, JMS, Logistics, VEBA Booking App .
The same price list references structured subscription horizons (monthly/quarterly/6‐month/annual) per product class .
8.8.2 Admin Directive (Dual Model)
1. Use Subscriptions for:
 - Stable, predictable services (e.g., baseline tracking, standard reporting)
2. Use Tokens for:
 - Burst usage (e.g., short‐term tracking windows, marketplace listing time, API usage)
 - High‐cost compute/streaming (AI inference, video bandwidth)
3. For each product, define the default commercial path:
 - "Subscription‐first with token add‐ons" OR
 - "Token‐first with minimum subscription access"
 Trainer tactic: In EA markets (UG/KE), token options increase adoption because they match cashflow realities (short horizons, mobile money payments) — but only if your auto‐alerts prevent surprise expiration.

## 8.9 Payments & Mobile Money Rails (UG & KE Operations)
8.9.1 Payment Rails You Must Support In CMS
Your provisioning drawer explicitly indicates multi‐rail support such as:
 - M‐Pesa
 - MTN MoMo
 - Airtel Money
 - Card rails (Visa/Master)
 - Bank rails
8.9.2 Admin Configuration Steps (Non‐Optional)
1. Merchant profiles
 - Create merchant profiles per region (UGX/KES)
 - Lock credentials in secure configuration storage
2. Webhook validation
 - Enable signed callbacks for payment status updates
3. Reconciliation mapping
 - Map transaction reference → tenant/account → invoice/token purchase
4. Posting rules
 - Funds received = ledger posting
 - Token issuance = subscription instance creation (bound to user/asset/product/time window)
5. Failure handling
 - If payment success but token issuance fails, raise P2 incident (financial impact).
6. Receipts
 - Must send receipt via configured messaging channel (Email/SMS/WhatsApp) with invoice reference.
✅ Customer experience directive: Always provide a "Pay Now" self‐service link and show token balance + burn rate in the admin dashboard view when possible (prevents escalations).

## 8.10 Refunds, Credits, Write‐Offs, And Revenue Protection
8.10.1 Refund Rules (Strict)
1. Refunds are allowed only when:
 - Duplicate payment confirmed
 - Service was blocked incorrectly by platform fault
 - Incorrect SKU applied due to admin error
2. Refunds must be executed as one of:
 - Credit note (preferred)
 - Wallet credit (token top‐up)
 - Payment reversal (only if rail supports it)
8.10.2 HIC Mandatory Approvals
 - Any credit/write‐off above your internal threshold must be:
 - Raised by Maker
 - Approved by Checker
 - Logged in Audit Trail
 Trainer tactic: Use AI to propose refunds, but never allow AI to approve refunds automatically. Keep humans accountable.

## 8.11 HIC + AI In Revenue Operations (How You Use Waswa AI Without Losing Control)
8.11.1 AI Role (Advisor, Not Cashier)
Waswa AI must be configured as:
 - A recommender for:
 - Upsell opportunities
 - Leak detection
 - Anomaly detection (token burn spikes)
 - SKU mismatch detection
 - Not an autonomous actor for:
 - Pricing changes
 - Refund approvals
 - Account blocking/unblocking
8.11.2 "Leakage Shield" Example (VEBA Provisioning)
Provisioning controls include an option to enable "Leakage Shield (AI)" as part of tenant enablement toggles .
✅ Admin directive: Enable Leakage Shield only when:
1. Tenant has validated payment rails
2. Tenant has an assigned billing plan/token plan
3. Tenant has KYC rules configured (where applicable)
8.11.3 HIC Gate Pattern (Mandatory)
For every financially sensitive automation, enforce:
1. AI Suggestion → 2. Human Review → 3. Execute → 4. Audit Log → 5. Post‐action monitoring

## 8.12 Practical Admin Workflows (Step‐By‐Step)
### 8.12.1 Workflow A — Create A New Token SKU (OLIWA‐UG Example)
1. Go to Tokenomics & Revenue → Token Engine → Create Token Definition
2. Fill:
 - Product scope: OLIWA
 - Region: UG
 - Token type: Dynamic / Parameter / Hybrid
 - Duration options: Hours/Days/Months/Years
 - Discount curve: Bind to the standard table (do not recreate)
3. Set pause rules and grace rules (if supported)
4. Set enforcement surfaces:
 - UI services
 - API services
 - Parameter masking list
5. Submit for HIC approval
6. Publish only after Checker approval
7. Validate with a test tenant before general rollout
✅ Validation checklist:
 - Token purchase creates subscription instance with correct binding
 - Service blocks correctly on expiry
 - Masking behaves correctly for non‐entitled parameters

### 8.12.2 Workflow B — Top Up Tokens For A Tenant (UG/KE Mobile Money)
1. Open Tenant Account → Wallet/Token Balance
2. Select: product scope + duration + quantity
3. Generate payment request (M‐Pesa/MTN/Airtel/Card)
4. Confirm payment event received via webhook
5. Verify subscription instance created
6. Verify UI service unlock
7. Send receipt via chosen channel
⚠ Risk control: If payment status is "Success" but wallet not updated in 3 minutes, escalate as financial incident.

⧉ PAGE BREAK
# SECTION 09: UTILITY & SUPPORT (ADD‐ON APPS LIBRARY & PROVISIONING)

## 9.1 Why This Module Exists (Strategic Intent)
Purpose. The Add‐On Apps Library enables 3D Services to:
 - Package features as modular products
 - Apply tenant‐specific enablement
 - Set token rules + payment rails per app
 - Deploy controlled upgrades (feature expansion) without destabilizing core tracking
This module is explicitly represented as "Add‐On Apps Library" with an app grid, search/filter, and a provisioning right‐blade/drawer .

## 9.2 UI Anatomy (Blades, Cards, And Drawers — What You Must Train Admins To See)
Core workspace.
 - A card grid of apps (each card includes app name, tagline, status, usage metric, revenue potential, and action buttons such as "Provision")
Provisioning drawer (Right blade).
 - Example: "Provision App — VEBA 3⁄4"
 - Includes an explicit "HITL Required" indicator
 - Contains tabs: Overview | Enablement | Billing Tokens | Payments | Audit Trail
✅ Admin directive: Treat the right drawer as the "control plane". If a drawer change cannot be audited, it must not exist in production.

## 9.3 Add‐On App Catalog Governance (CRUD Standards)
### 9.3.1 Create (Add New App Listing)
You may create an app listing only when:
1. App has an owner (Product Manager / Technical Owner)
2. App has defined:
 - Compatibility constraints (which products can enable it)
 - Dependency list (e.g., VEBA requires telematics unit linked)
 - Billing mode (subscription add‐on, token add‐on, hybrid)
 - Support tier (standard vs premium)
3. App has risk notes + CX notes
Create fields (minimum set):
 - App Name (e.g., ECO, DSC, NIMBUS, VEBA)
 - Category (Ops, Safety, Compliance, Marketplace, Analytics)
 - Region availability (UG/KE)
 - Default pricing plan(s)
 - Token rules (if tokenized)
 - Enablement checklist & dependency checks
 - Audit requirements
### 9.3.2 Read (Search, Filter, Inspect)
You must be able to:
 - Search by name
 - Filter by category, status, compatibility, revenue score
 - Open card → view "Overview"
### 9.3.3 Update (Versioning Discipline)
⚠ Never overwrite a live pricing definition without versioning.
Update rules:
1. Create a new version
2. Migrate tenants via controlled rollout
3. Preserve historical invoices and token consumption mapping
### 9.3.4 Disable / Deprecate (Do Not Hard Delete)
Disable means:
 - App no longer provisionable for new tenants
 - Existing tenants retain service until end of contract window (unless blocked for compliance reasons)
 - UI shows deprecated status
✅ Admin directive: Hard delete is permitted only for test environment artifacts.

## 9.4 Provisioning Workflow (Right Drawer) — VEBA Example
9.4.1 Enablement Controls
The enablement list in the drawer includes toggles such as:
 - Enable VEBA for tenant
 - Require KYC for Owners
 - Enable Leakage Shield (AI)
 - Require Telematics Unit Linked
 - Allow Cash Trips (Trusted only)
Mandatory provisioning procedure:
1. Select tenant(s)
2. Run dependency checks
3. Enable toggles as per policy
4. Bind billing tokens
5. Bind payment rails
6. Submit for HIC approval
7. Activate only after Checker approval
✅ Customer experience tactic: Always enable "Telematics Unit Linked" for VEBA by default. This prevents marketplace fraud and ensures trip auditing via telemetry.

## 9.5 Billing Tokens Tab (How Add‐Ons Hook Into Revenue)
Token strategy alignment. VEBA explicitly requires listing time tokens and trip/commission tokens in the token roadmap .
Admin must configure:
1. Listing time tokens (dynamic token)
2. Trip commission tokens (event‐based token)
3. Marketplace‐level guardrails
 - low balance auto‐notify
 - suspension logic
 - fraud/anomaly flags routed to Alarm Center
⚠ Risk control: If VEBA is enabled without token rules, you have built a marketplace with no monetisation guardrails.

## 9.6 Payments Tab (Mobile Money + Trust Controls)
The drawer explicitly supports "Payments & Mobile Money Rails" with rails enabled/disabled per tenant .
Admin directives:
1. In UG: prioritize MTN MoMo + Airtel Money rails operationally
2. In KE: prioritize M‐Pesa operationally
3. If "Allow Cash Trips" is enabled, apply strict rule:
 - Only for trusted tenants
 - Must have KYC enabled
 - Must have a deposit / pre‐authorization policy
✅ Trainer tactic: Cash trips are a CX feature but also a fraud surface. Keep it controlled.

## 9.7 Audit Trail Tab (Non‐Negotiable Content)
Every app provisioning event must write:
 - Who (Maker)
 - Who (Checker)
 - What changed (before/after values)
 - When (timestamp, timezone)
 - Why (reason field)
 - Tenant(s) affected
 - Financial impact estimate (if possible)
 Pro move: If Waswa AI suggested the action, store the AI suggestion ID + confidence score so audits can trace "why we did it".

⧉ PAGE BREAK
# SECTION 10: COMMAND & CONTROL (OPS DASHBOARD, SYSTEM HEALTH, ALARM CENTER & AI CONSOLE)

## 10.1 The Control‐Room Mindset (Trainer Standard)
Non‐negotiable truth. A telematics business does not fail because of "no features." It fails because of:
 - silent device outages
 - slow incident response
 - unmanaged token expiry chaos
 - ungoverned AI actions
 - inconsistent customer communication
Therefore, your Command & Control modules must be used daily.

## 10.2 Ops Dashboard (Daily Flight Instruments)
Your dashboard must surface (minimum):
1. Ingestion health
 - active devices vs expected
 - new offline devices in last 15/60/240 minutes
2. Token health
 - tenants below threshold balance
 - unusual burn spikes
3. Alarm health
 - open alarms by severity
 - time‐to‐acknowledge (TTA)
4. Support health
 - incident count by product
 - MTTR vs targets
✅ Trainer directive: If the Ops Dashboard is not checked every morning and every afternoon, the business is operating blind.

## 10.3 System Health (Infrastructure Readiness)
What System Health must include:
 - Device connectivity performance
 - Integration uptime (payment rails, WhatsApp/SMS/email gateways)
 - Queue/stream health (message lag, retries)
 - Storage health (video, telemetry, logs)
 - Error budgets for key services
⚠ Risk control: A billing outage is a revenue outage. Treat it as severity P1/P2 based on impact.

## 10.4 Alarm Center (Operational Discipline)
Alarm Center must act as the single pane for:
 - critical security events (RBAC anomalies)
 - device offline clusters
 - geofence breach escalations
 - fuel theft anomalies
 - video event overloads
 - payment posting failures
Admin directives:
1. Alarms must have: severity, owner, SLA clock, and an action playbook.
2. Alarms must link to: tenant, asset(s), recent events, and suggested action.
3. Every alarm must end in one of:
 - Resolved (root cause + action)
 - Deferred (explicit reason + revisit date)
 - Escalated (who/when)

## 10.5 AI Console (Waswa AI) — How To Use It With HIC
Mandatory usage model. Waswa AI is used for:
 - diagnostics summarization
 - recommended mitigations
 - anomaly detection
 - triage suggestions
But the AI must be constrained by HIC approval gates, consistent with the strategy requirement of HITL gates and safe usage. (Your AI strategy explicitly defines HITL gates for sensitive workflows.)
✅ Admin directive: AI can *recommend* disabling a tenant, but only a human can *execute* tenant suspension.
 Trainer tactic: Configure AI with "confidence thresholds":
 - ≥ 0.85: show as "Recommended"
 - 0.60–0.84: show as "Suggestion"
 - < 0.60: show as "Observation only"

## 10.6 Shift Handover Protocol (Preventive Maintenance for People)
Run this at every shift change:
1. Review open P1/P2 incidents
2. Review top 10 tenants by alarms
3. Review token expiry list (next 72 hours)
4. Review payment posting failures
5. Confirm outbound customer communications sent
6. Confirm tomorrow's planned maintenance windows
✅ Key takeaway: People continuity is the cheapest form of uptime.

⧉ PAGE BREAK
# SECTION 11: INCIDENT MANAGEMENT, ESCALATION & MAINTENANCE (PREVENTIVE + CORRECTIVE)

## 11.1 Support Response Standards (Channel‐Based Targets)
Your escalation procedure defines target response timelines based on channel, including:
 - WhatsApp: rapid response expectation
 - Standard support email response windows
 - After hours phone escalation windows
✅ Admin directive: Align CMS Helpdesk routing and SLA timers to the documented response expectations. If CMS timers contradict your SOP, your team will fail audits.

## 11.2 Hardware Install & Repair MTTR Targets (Per Product)
Your escalation SOP explicitly provides target time‐to‐install and time‐to‐repair per product family, including:
 - DASH AI: install ~4.5 hrs, repair ~3 hrs
 - DASHCAM: install ~4 hrs, repair ~3 hrs
 - MDVR / MDVR AI: install ~8 hrs, repair ~3 hrs
 - iVMS: install ~3 hrs, repair ~2 hrs
 - OLIWA: install ~3 hrs, repair ~2 hrs
 - MAFUTA FLS: install ~8 hrs, repair ~3 hrs + recalibration guidance
 - PIKI: install ~3 hrs, repair ~2 hrs
 - THERMO: install ~2 hrs, repair ~1 hr
 ...and others
✅ Admin directive: Use these targets inside CMS as:
 - SLA defaults in Helpdesk
 - Performance benchmarks in Ops Dashboard
 - Customer expectation templates in messaging

## 11.3 Incident Severity Model (Operational Rules)
P1 — Platform Outage / Revenue Outage
Examples:
 - Token Engine cannot issue subscriptions after successful payments
 - Alarm Center down during mass outage
 - GPS ingestion halted for > X% of fleet
P2 — Major Degradation
Examples:
 - delayed updates for a high‐value enterprise tenant
 - payment rail down in one region
 - video upload failures exceeding threshold
P3 — Localized Fault / Standard Ticket
Examples:
 - single unit offline
 - sensor calibration request
 - user access reset
⚠ Rule: Severity is determined by impact, not by who is shouting the loudest.

## 11.4 Preventive Maintenance (Technical + Customer Experience)
### 11.4.1 Preventive Maintenance You Must Run Weekly
1. Offline device sweeps
 - identify devices offline > 24 hrs
 - classify by: power issue, network issue, SIM issue, hardware failure
2. Sensor sanity checks
 - fuel level drift detection
 - temperature sensor spike detection
3. Billing integrity checks
 - payment success but no token issuance
 - invoice generated but no receipt delivered
4. Account hygiene
 - remove stale users
 - enforce least privilege
5. Template hygiene
 - notification templates updated
 - escalation contacts verified
### 11.4.2 Preventive Maintenance Tied To Product Truths (Fuel Example)
Your product notes explicitly warn that CANBus alone is not reliable for fuel monitoring and should complement FLS/ATG where liquid levels are known .
✅ Admin directive:
 - When provisioning MAFUTA CANBUS, ensure:
 1. A primary liquid level sensor (FLS/ATG) is configured
 2. CANBus is configured as a secondary corroboration stream
 3. Reports and alerts are calibrated to avoid false theft accusations
 Customer experience tactic: Fuel false‐positives are reputational damage. Calibrate once; apologize never.

## 11.5 Corrective Maintenance (Root Cause Discipline)
Corrective maintenance must always end with:
1. Root cause classification (installation, device, network, sensor, user training, configuration)
2. Action taken
3. Preventive control added (alert, training note, template update)
✅ Trainer directive: "Fix and forget" is forbidden. Every incident must reduce the probability of recurrence.

⧉ PAGE BREAK
# SECTION 12: PRODUCT-SPECIFIC ADMIN PLAYBOOKS (PART 1 — PROVISIONING STANDARDS)

## 12.1 The Universal Provisioning Checklist (Applies To Every Product)
Step 1 — Confirm the commercial contract
 - Subscription SKU OR Token SKU defined
 - Region currency correct (UGX/KES)
 - Discount horizon correct (if long duration)
Step 2 — Confirm the tenant structure
 - Tenant/account exists
 - Tenant admin user exists
 - Roles assigned (RBAC)
 - Support group assigned
Step 3 — Confirm the asset model
 - Unit/device created and linked
 - Asset identifiers validated (plate, chassis, driver ID, etc.)
 - Correct product tag applied (OLIWA vs iVMS vs PIKI vs MAFUTA, etc.)
Step 4 — Confirm operational templates
 - Alerts template applied
 - Report templates assigned
 - Contact list validated (email/phone/WhatsApp)
Step 5 — Confirm HIC gates
 - Any paid add‐on enablement approved
 - Any payment rail enablement approved
 - Any KYC toggles configured (VEBA, marketplace contexts)

## 12.2 Vehicle Telematics (OLIWA, OLIWA‐PLUS, iVMS, iVMS‐PLUS)
Target outcome. Stable tracking + compliance + report readiness.
### 12.2.1 Baseline Configuration
1. Create/verify unit
2. Ensure correct tracker model mapping (per standard device catalog)
3. Apply baseline alerts:
 - overspeed
 - ignition on/off
 - geofence in/out
 - towing (if supported)
4. Apply baseline reports:
 - daily trips
 - stops
 - mileage
 - driver behavior summary (if ECO/DSC enabled)
### 12.2.2 OLIWA‐PLUS Upgrade Controls
OLIWA‐PLUS implies additional features (e.g., immobilizer workflows or expanded sensor set).
✅ Admin directive: Treat upgrade as add‐on provisioning:
 - Enable additional feature flags
 - Confirm hardware readiness (relay/immobilizer wiring)
 - Confirm operational SOP for immobilization approval (HIC recommended)

## 12.3 Personnel Tracing (PIKI, CAPO, TOTO, WIATAG, PATROL)
Target outcome. Human asset accountability, safety, and proof‐of‐presence.
### 12.3.1 PIKI (Motorcycle Tracking) — Token Model Compatibility
Time‐based token pricing exists for PIKI in UG and KE tables .
✅ Admin directive:
 - Offer token durations aligned to customer journey:
 - short durations (hours/days) for casual customers
 - monthly/annual for fleets
 - Ensure low‐balance alerts are enabled to prevent riders "going dark" unexpectedly.
### 12.3.2 PATROL / Guard Workflows
 - Configure geofences for patrol zones
 - Configure schedule compliance reports
 - Enable proof‐of‐visit logic (where applicable)

## 12.4 Fuel Telematics (MAFUTA FLS, FLOW METER, CANBUS, FUEL CARD, STATION, GENSET)
Target outcome. Fuel truth + theft detection + reconciled refuelling accountability.
### 12.4.1 Calibration is Not Optional
From the MTTR table: MAFUTA FLS and GENSET include recalibration considerations .
✅ Admin directive:
 - Calibration tickets must be tagged as "Calibration" not "Repair"
 - Fuel alerts must not be enabled until calibration is confirmed
### 12.4.2 CANBUS Discipline (CX Protection)
As stated in product notes, CANBus must complement liquid level sensing; it is not reliable alone .
⚠ Admin directive: Any Mafuta CANBus deployment without FLS/ATG must be blocked at provisioning via dependency checks.

## 12.5 AI & Video Telematics (DASHCAM, DASH AI, MDVR, MDVR AI)
Target outcome. Evidence‐grade video + AI events + responsible bandwidth management.
### 12.5.1 Provisioning Controls
1. Confirm device class (DASHCAM vs MDVR)
2. Confirm channel count (2–7 channels) where applicable
3. Assign video storage policy
4. Assign AI event policies (ADAS/DMS/DSM, etc.)
### 12.5.2 Bandwidth As A Billable Asset
Your cost/pricing notes explicitly include camera bandwidth considerations in subscription cost planning .
✅ Admin directive:
 - Video bandwidth must be priced and monitored; do not treat it as "free data".
 - If a tenant activates high‐frequency upload, ensure token/subscription alignment to avoid margin loss.

## 12.6 Goods‐In‐Transit & IoT (KAGO, PASO, PAWA, THERMO)
Target outcome. Condition monitoring + custody events + route accountability.
### 12.6.1 THERMO (Cold Chain Monitoring)
 - Configure temperature thresholds
 - Configure door open alerts (if sensors present)
 - Configure escalation actions (SMS/WhatsApp) for immediate intervention
### 12.6.2 KAGO (Cargo/Container Tracking)
 - Configure lock/door events (if supported)
 - Configure route deviation alerts
 - Configure tamper detection events

## 12.7 Add‐On Apps (ECO, DSC, FleetRun, Inspecta, JMS, Logistics, Nimbus, VEBA)
Target outcome. Monetizable feature expansion with controlled rollout.
✅ Admin directive: All add‐ons must be provisioned via Add‐On Apps Library and not via "manual feature toggling," to preserve:
 - pricing consistency
 - token enforcement integrity
 - audit logs
 - customer communication standardization

## REFERENCE LIBRARY (FOR INTERNAL TRACEABILITY)
*(You may keep or remove this section when copying into Google Docs.)*
 - NAVAS token lifecycle and enforcement model:
 - Token duration discount factor tables (PIKI/OLIWA/UKO):
 - Add‐On Apps Library UI + provisioning drawer (HITL Required, tabs, payment rails):
 - 3D product subscription and SKU list (PriceList):
 - Incident escalation + install/repair targets per product:
 - Wialon CMS Manager reference concepts (service structure, dealer hierarchy, billing plans): ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system?utm_source=chatgpt.com))

If you want me to continue immediately, I will proceed with:
SECTION 13: INFRASTRUCTURE & CONNECTIVITY (DEVICES, FIRMWARE/OTA, SIM CONSOLE, INTEGRATIONS) → then SECTION 14: ASSET & RESOURCE GOVERNANCE (ACCOUNTS, RESOURCES, RBAC, AUDIT LOGS) → then SECTION 15: TELEMATICS & GIS OPS (LIVE DISPATCH, TRIP PLAYBACK, GEOFENCES, REPORTING).
According to a document from 20 February 2026 (NAVAS IoT System Policy v26.0), NAVAS CMS is designed to operate as a multi-tenant, RBAC-governed, AI-assisted command center that supports mobile money integration and token-based monetization as first-class controls for East Africa. ✅
Below is the next continuation section of the NAVAS – CMS System Administration User Manual (3D Services Limited, Uganda o & Kenya a).

# 17. ACCOUNT LIFECYCLE MANAGEMENT AND SERVICE STRUCTURE

## 17.1 Purpose and Administrator Mandate ✅
CMS System Administrators SHALL manage the full customer lifecycle, from onboarding to suspension and offboarding, without breaking service continuity, auditability, or revenue governance.
Your mandate is to ensure:
1. Every customer account is correctly structured in the hierarchy (Top → Dealer → Sub-dealer → Customer → Branch).
2. Every enabled feature is intentional (enabled-by-policy, not enabled-by-accident).
3. Every cost driver is controlled via token policies, caps, and alerting.
4. Every delegation action is traceable via HIC and audit logs.
5. Every onboarding event is repeatable using standard templates and checklists.
✅ Key Takeaway: The CMS is not "settings." It is your governance cockpit—where structure, access, cost, and accountability are enforced.

## 17.2 The NAVAS Service Structure Model
*Core principle.* NAVAS service structure MUST be hierarchical and delegable, similar to dealer-style service management systems: top account with downstream accounts, where each level controls what the level below can do.
This aligns with industry-standard CMS models where top users and dealer-rights users control accounts, resources, users, units, and billing constructs. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system?utm_source=chatgpt.com))
### 17.2.1 Account types you MUST support
1. Top Account
 - Owns platform-wide governance, tokenomics defaults, and global security policies.
2. Dealer Account
 - May create/manage subordinate customer accounts and assign allowed service bundles.
3. Sub-dealer Account
 - Operates under dealer controls for local scaling (regional resellers, franchise operators).
4. Customer Account
 - End-customer operational boundary (fleet company, school, logistics operator).
5. Customer Branch Account
 - Optional: for enterprises with multiple depots, regions, or business units.
 Admin tip: If a customer has multiple departments with different privacy needs, treat each department as a branch account to prevent cross-visibility and reduce audit exposure.
### 17.2.2 Macro-objects and what they represent
Use these constructs consistently:
 - Users → Human identities (admins, dispatchers, finance, safety, drivers if needed)
 - Roles → Permission bundles for the users
 - Resources → Shared operational objects (geofences, POIs, report templates, notification templates)
 - Units → Tracked entities (vehicles, motorcycles, staff devices, containers, fridges, generators) ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/units?utm_source=chatgpt.com))
 - Apps → Modular product experiences and add-ons (VEBA, BI dashboards, JMS, INSPECTA, etc.)

## 17.3 Naming and Governance Conventions
*Policy.* All accounts, users, and macro-objects SHALL follow standardized naming to ensure searchability, reduced duplication, and cleaner audits.
### 17.3.1 Recommended naming pattern
Use a consistent prefix system:
 - Country: UG / KE
 - Account tier: TOP / DLR / SDLR / CUST / BR
 - Customer short code: 3–10 chars
 - Optional suffix: region, product bundle, or SLA tier
Examples
 - UG-DLR-3DS-KLA
 - KE-CUST-TRANSLOG
 - UG-BR-KCCA-DEPOT2
### 17.3.2 Identity and permissions hygiene
*Directive.* You MUST prevent "permission drift":
1. Every user MUST have exactly one primary role (System Admin, Customer Admin, Dispatcher, Finance, Safety).
2. Temporary access MUST expire automatically or be reviewed weekly.
3. Shared logins MUST NOT exist (no "admin/admin", no "fleet@company.com shared by 6 people").

## 17.4 Account Onboarding Workflow
This workflow is designed to be fast, auditable, and consistent with 3D operational targets.
### 17.4.1 Operational timing discipline
3D service delivery discipline includes explicit operational responsibilities and timing targets across roles. For example, device approvals and job allocations have tight internal targets, and job completion communications MUST follow once the system admin confirms the unit reporting online. ✅【485:1†3DS Process for Incident Management Escalation V.3.pdf†L42-L64】
### 17.4.2 Onboarding steps you MUST execute
1. Create the Account
 - Set: Country, timezone, currency, SLA tier,
 - Dealer/Sub-dealer assignment MUST reflect commercial ownership.
2. Enable Product Bundles
 - Assign product family: Vehicle, Personnel, Fuel, Video, Goods/IoT, VEBA.
3. Create Admin Users
 - Customer Admin + optional read-only auditors.
4. Initialize Token Wallet
 - Apply caps, alert thresholds, and stop/soft-pause rules.
5. Provision Resources
 - Default geofences, POIs, notification templates, report templates.
6. Provision Units and Devices
 - Create unit, link device, set profile, confirm data stream.
7. Validate via HIC
 - Log in "as the customer admin" and confirm the experience is correct.
⚠ Non-negotiable: You MUST perform the HIC validation step before declaring onboarding complete.

## 17.5 HIC Administration: "Act on Behalf Of" Without Breaking Trust ⚖
HIC is your controlled delegation model: you can "become" a subordinate user for validation, support, or configuration—but only under explicit rights and logging.
Industry reference: Service management systems typically require a special access right to log in on behalf of another user, and it is restricted to subordinate contexts. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/interface/top-panel?utm_source=chatgpt.com))
### 17.5.1 Approved use cases ✅
You SHOULD use HIC for:
1. Confirming customer experience
 - "Do they see the correct menu?"
 - "Do they see the right units?"
2. Emergency remediation
 - Hotfix a broken role, a missing report template, or a misconfigured notification route.
3. Audit validation
 - Confirm the customer cannot access restricted assets or cross-branch resources.
### 17.5.2 Forbidden use cases
You MUST NOT use HIC to:
 - Perform finance-impact actions without maker-checker approval (suspensions, refunds, token rule overrides).
 - Access private customer data that is not required to solve the support issue.
 - Permanently operate as a customer (HIC is a tool, not a lifestyle).
### 17.5.3 HIC safe operation checklist ✅
Before acting:
1. Confirm ticket/reference exists.
2. Confirm your rights allow "Act on behalf of user."
3. Announce internally (Ops/Helpdesk) you are entering HIC.
4. Perform the smallest required action.
5. Exit HIC and document actions in the ticket + audit log.

## 17.6 Account Suspension, Pausing, and Reactivation 3
NAVAS token governance is designed to make service interruptions predictable, not chaotic, using caps, soft alerts, and optional auto-pause. ✅【476:1†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L34-L39】
### 17.6.1 Suspension policy model
1. Soft alert at 80% consumption ✅
2. Hard stop threshold if enabled ✅
3. Optional auto-pause depending on SLA and customer risk profile ✅【476:1†NAVAS TOKEN BILLING STRATEGY - Any suspension action SHALL be proposed by system logic or AI but MUST be approved by Finance where policy requires. This aligns to HITL practices in automation governance. ✅【485:6†3D-An can propose; humans must approve where money, trust, or compliance is on the line.

⟦PAGE BREAK⟧
# 18. ADD-ON APPS LIBRARY AND PROVISIONING

## 18.1 Purpose
The Add-On Apps Library is your controlles: BI Dashboards, DSC, ECO, FleetRun, INSPECTA, JMS, Logistics, Nimbus, VEBA
 - Value Added Services enablement hooks: Helpdesk & Training, SATO, OEM integrations, local server models
 - Governance modules: token billing rules, mobile money rails, app dependency checks
The UI and workflow are built around:
 - Table-first catalog
 - Right-side provisioning blade
 - HIC/HITL governance controls
 - Token wallet integration
Reference UI pack for Screen 27 deliverables:

## 18.2 Where It Sits in the CMS Navigation
In the standard CMS layout, the Add-On Apps Library is under:
 - Utility & Support → Add-On Apps Library
 - It includes a workspace table (apps catalog) and blade drawer (provisioning & governance)【476:4†CMest.txt†L1-L85】

## 18.3 Standard Screen Pattern You MUST Master
This pattern repeats across CMS modules (apps, users, devices, alerts):
1. Nav rail (icons)
2. Sidebar (module tree)
3. Topbar (search + shortcuts)
4. Standard strip (tenan
5. Workspace (cards + table)
6. Blade (right drawer for deep configuration)
 Trainer tip: Your speed as a CMS admin is determined by how quickly you move between table row → blade → audit log.

## 18.4 App Catalog: Table Operations ✅
### 18.4.1 What the catalog table MUST show
Minimum columns (non-negotiable):
 - App Name
 - Category
 - Enabled status
 - DAU/WAU or usage proxy
 - Revenue proxy
 - Dependencies
 - Health status
 - Actions menu
This structure is reflected in the current UI blueprint. ✅【476:4†CMS Mockup Redesign Request.txt†L61-L85】
### 18.4.2 CRUD operations
*Create.*
1. Click + New App
2. Enter:
 - App Name
 - Category
 - Dependency set (GPS, Payments, Camera, Maps, Sensors)
 - Default pricing/token class mapping
 - Default status: Disabled or Trial
*Reon App blade.
*Update.*
 - Use action menu ⋮ → Edit:
 - Update dependencies
 - Update token policy templates
 - Update supported countries (UG/KE)
 - Update app health rules
*Disable/Archive.*
 - Archive SHOULD move the app into a controlled "Trash/Archive" state.
 - Restoration MUST retain audit trail.
⚠ Admin warning: Do not "delete" revenue objects. Always archive so historical billing remains reconcilable.

## 18.5 Provisioning Blade: Enablement and Dependency Checks 3⁄4
When you open an app (e.g., VEBA), the blade MUST allow:
1. Tenant selection
2. Enablement toggles
3. Dependency checks
4. Token rules
5. Payment rails
6. Audit trail view
This blade structure is explicitly modeled in the Screen 27 spec. ✅【476:4†CMS Mockup Redesign Request.txt†L10-L31】
### 18.5.1 Enablement toggles you SHOULD include
 - Enable app for tenant
 - Require KYC (if marketplace/financial)
 - Enable leakage shield AI (if fraud risk)
 - Require linked telematics unit
 - Allow cash transactions only for trusted tenants
e not "features." They are risk controls.

## 18.6 Token Policy Attachment for Apps
NAVAS token pricing is designed to be composable: pricing can be derived from unit costs and scaled by market/commercial factors, with safeguards like caps and audit logs. ✅【476:1†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L1-L55】
### 18.6.1 Token controls you MUST configure per app
1. Token class (Video, AI, Maps, Messaging, Storage, Core Tracking)
2. Discount eligibility
 - AI tokens SHOULD be non-discountable by default
3. Monthly caps
 r visibility
 - Per-customer token ledger
 - Parameter-level usage log
 - AI inference log ✅【476:1†NAVAS TOKEN BILLING STRATEGY ver26.01.26a (2).pdf†L42-L55】
### 18.6.2 Admin tactics for Uganda vs Kenya
*Uganda o (common patterns).*
 - Higher sensitivity to PAYG volatility → enforce stronger caps + proactive top-up nudges.
*Kenya a (common patterns).*
 - Mobile money adoptiont.

## 18.7 Payment Rails and Mobile Money Hooks 2
NAVAS is explicitly positioned to integrate Mobile Money directly into the telematics business layer. ✅【476:2† NAVAS IOT SYSTEM POLICY_ .pdf†L23-L29】
Therefore, when provisioning apps that require payments:
1. Confirm rail availability:
 - M-Pesa
 - MTN MoMo
 - Airtel Money
 - Cards via gateway if applicable
2. Perform a controlled "Test Pay" in staging environment
3. Confirm callback  Non-negotiable: Payment rails MUST be enabled using HITL approval for enterprise or high-volume tenants.

## 18.8 Waswa AI in the Apps Library
The Waswa AI widget (co-pilot) SHOULD provide:
 - Leakage risk detection
 - App usage anomaly detection
 - Trial-to-paid recommendations
 - Suggested upsell message templates
 - Suggested policy tightening for risky tenants
NAVAS positions AI co-pilot as a proactive agent that predicts system load and identifies revenue leakage in real-time. ✅【476:2† NAVAS IOT SYSTEM POLICY_ .pdf†L105-L116】
### 18.8.1 Mandatory HIC rule
All AI recommendations MUST be treated as:
 - Decision support
 - Not automatic authority
Use the following acceptance gate:
1. Verify the underlying data signals are valid
2. Validate with at least one. Apply change with maker-checker if it affects:
 - Billing
 - Access
 - Compliance
 - Customer experience at scale

⟦PAGE BREAK⟧
# 19. ALERTS NOTIFICATIONS AND AUTOMATION ORCHESTRATION

## 19.1 Purpose
Alerts are where telematics becomes operational value—or customer frustration.
Your goal is to ensure:
1. Alerts are meaningful
2. Alerts are actionable
3. Alerts do not cause fatigue
4. Alerts integrate into incident and maintenance workflows

## 19.2 NAVAS Event Trigger Catalog ✅
NAVAS supports a broad event trigger list across driver behavior, fuel, maintenance, environment, security, and more. ✅【476:0†List of Event that Triggers notifications, alerts, alarms.pdf†L4-L92】
### 19.2.1 High-value categories you MUST prioritize
1. Safety and driver behavior
 - Harsh braking, harsh acceleration, distracted driving, fatigue
2. Fuel integrity
 - Fuel drop, rapid consumption, reengine hours reached ✅【476:0†List of Event that Triggers notifications, alerts, alarms.pdf†L73-L80】
3. Security
 - Panic button, unauthorized movement, door intrusion
4. Environmental compliance
 - Temperature deviation, humidity deviation, air quality for cargo ✅【476:0†List of Event that Triggers notifictions, alerts, alarms.pdf†L84-L86】
✅ Key Takeaway: If you cannot answer "what should the user do next?" the alert is not ready for production.

## 19.3 Alert Design 5 minutes)
1. Use context (geofence zones, shift hours, vehicle type)
2. Use bundling (digest instead of spam)
### 19.3.2 Quiet hours and bundling
Automation playbooks explicitly call for bundling hourly events and respecting quiet hours to reduce notification fatigue. ✅【485:6†3D-AI-AGENT-STRATEGY V5.pdf†L16-L18】【485:3†3D-AI-AGENT-STRATEGY V5.pdf†L87-L90】
Operational rule:
 - Real-time alerts ONLY for:
 - Safety-critical incidents
 - Theft/security events
 - Compliance-critical events
 - Digest for everything else:
 - Hourly digest (ops team)
 - Daily sonfiguration Procedure ✅
 *Run-in and mandatory.* *Prerequisites.* You MUST have:
 - A configured tenant
 - Units reporting
 - Notification channels verified (email/SMS/WhatsApp)
 - Recipient roles assigned
Steps
1. Navigate to Command & Control → Alarm Center
2. Click + New Alert Rule
3. Set:
 - Name
 - Trigger signal (event type)
 - Threshold logic
 - Cooldown window
4. Select channels:
 - Screen popup
 - Email
 - SMS
 - WhatsApp
 - API callback
5. Select recipients:
 - Driver
 - Dispatcher
 - Fleet manager
 - Safety manager
 - Owner/CFO
6. Configure escalation:
 - If not acknowledged in X minutes → escalate to next level
7. Enable with HIC test
 - Use a test unit or simulated signal
8. Activate rule and monitor false positives for 7 days
⚠ Mandatory: For any "mass alert" affecting >50 recipients, you MUST use HITL approval before activation.

## 19.5 Preventative Maintenance Alerts
Preventative maintenance triggers are explicitly part of NAVAS event triggers, including mileage-based and time-based schedules. ✅【476:0†List of Event that Triggers notifications, alerts, alarms.pdf†L73-L75】
### 19.5.1 Best-practice maintenance workflow
1. Define service interval per vehicle class:
 - Oil service
 - Major service
 - Tire rotation
 - Brake checks
2. Configure triggers:
 - Mileage
 - Engine Assign to workshop/service owner
3. Notify:
 - Fleet manager
 - Maintenance supervisor
4. Close loop:
 - Ticket closure updates the service counter
 CX tactic: Maintenance alerts MUST include a "next action" link (call workshop, schedule, confirm completion).

⟦PAGE BREAK⟧
# 20. AI CONSOLE AND HUMAN IN CONTROL OPERATIONS

## 20.1 Operating Philosophy
NAVAS AI is designed to accelerate decision-making while preserving human accountability.
The AI Agent strategy mandates HITL gates for:
 - First-month template approvals
 - P1 triage approvals
 - Quote approvals
 - Finance approvals for suspension/resume
 - KB publish review ✅【485:3†3D-AI-AGENT-STRATEGY V5.pdf†L1-L4】

## 20.2 AI Use Cases You SHOULD Operationalize
From the AI agent strategy, high-value operational agents include:
1. ITA – Ticket Assistant
 - Suggest category, priority, top-3 KB steps, with citations ✅【485:13†3D-AI-AGENT-STRATEGY V5.nt
 - Bundles events + drafts summaries for approval ✅【485:6†3D-AI-AGENT-STRATEGY V5.pdf†L16-L18】
2. SCA – Sales Copilot
 - Lead enrichment + quote drafting with approval ✅【485:3†3D-AI-AGENT-STRATEGY V5.pdf†L7-L25 - Automated reminders and policy-compliant suspensions with finance approval ✅【485:3†3CA – Knowledge Base Copilot
 - Curated SOP answers, not hallucinated responseL58】
3. VEA – Video Evidence Agent
 - Attach relevant 30–60s clips to incidents with masking ✅【485:3†3D-AI-AGENT-STR* AI in NAVAS is an "operations multiplier," not an uncontrolled chatbot.

## 20.3 Ad✅
1. Enable AI per tenant
 - Default: OFF for new tenants unless explicitly included in hat objects AI can see (tickets only vs tickets + telemetry vs telemetry + billing)
2. Set HITL gates
 - Which actions require approval (most actions SHOULD)
3. Define audit depth
 - Store prompt + outputs for governance where needed
4. Define safety filters
 - Redact secrets
 - Minimize PII exposure
5. Define monitoring KPIs
 - Latency, false positives, opt-out rates
The AI strategy defines KPIs like FRT/MTTR, alert false positive rate, and audit completeness as mandatory operational measures. ✅【485:13†3D-AI-AGENT-STRATEGY V5.pdf†L1-L12】

## 20.4 Prompt Hygiene and Data Protection
NAVAS governance policy and engineering playbooks explicitly warn against exposing secrets and require human verification. ✅【485:2†NAVAS System Developement Playbook Ver5.0.pdf†L23-L31】
Therefor, or customer PII into prompts.
 - You MUST validate AI output before applying changes.
 - You MUST use retrieval-based prompts (AI answers grounded in SOPs and logs).
⚠ Admin ction governance.

⟦PAGE BREAK⟧
# 21. INCIDENT SERVICE DELIVERY AND ESCALATION RUNBOOK

## 21.1 Why this section is mandatory
3D Services operates with strict escalation and MTTR discipline. The escalation process exists to improve MTTR across the product lifecycle including sales, service delivery, and support. ✅【485:5†3DS Process for Incident Management Escalation V.3.pdf†L30-L37】

## 21.2 Business Hours and After-Hours Rules
3D's documented operating model includes standard business hours and after-hours on-call support. ✅【485:5†3DS Process for Incident Management Escalation V.3.pdf†L50-L55ules
2. P1 incidents bypass quiet-hours (safety/security always breaks silence)
3. Escalations MUST route to on-call schedule when outside standard hours
--ument defines key MTTR parameters and targets, including:
 - ART: Point-of-contact response time target (not greater than 15 minutes)
 - FCR: First contact resolution (not greater than 30 minutes)
 - MRT: Mean resolution time (within 24 hours)
 - ER: Escalation rate (keep escalations under 10%)
 - RTRS: Response time to reach site depends on distance bands ✅【485:1†3DS Process for Incident Management Escalation V.3.pdf†L96-L174】
✅ Key Takeaway: Your CMS workflows MUST make it easy to hit 15-minute response and 24-hour resolution targets.

## 21.4 System Admin Incident Workflow ✅
1. Intake
 - Ticket created within 2 minulikely root cause (connectivity, permissions, billing, device health)
2. Validate telemetry
 - Is the unit online?
 - Is data fresh?
 - Are key IO parameters present?
3. Apply fast remediation
 - RBAC fix, re-provision a device, token top-up action, notification route fix
4. If field action required
 - Dispatch technician via routing rules
5. Communicate to client
 - ETA, action plan, expected outcome
6. Close with QA
 - Confirm "unit reporting online" before closure communication ✅【485:1†3DS Process for Incident Management Escalation V.3.pdf†L58-L64】
7. Post-incident review
 - If repeated incident type: raise preventive action (template, dashboard, training)

## 21.5 Escalation Layers in Practice ⚠
You MUST treat escalation as a time-based control:
 - If Lresolve within target window → escalate to L3
 - Final escalation to executive oversight where required (especially for enterprise outages)
 Admin tactic: Escalation is not blame. It is time protection for the customer.

⟦PAGE BREAK⟧
# 22. PRODUCT FAMILY ADMINISTRATION PLAYBOOKS PART 1

## 22.1 Purpose
This section aligns CMS administration with 3D's product portfolio across Uganda and Kenya, ensuring every product is:
 - Provisioned consistently
 - Governed financially
 - Supported operationally
 - Maintained preventively and correctively
A product summary indicates NAVAS product domains and core tracked categories (vehicles, motorcycles, staff, parcels, bookings) as part of the portfolio footprint. ✅【485:4†Navas_IoT_Products - Summary.pdf†L4-L19】

## 22.2 Portfolio Alignment Matrix ✅
*Table note:* Header row shade #F5F5F5, no borders
| Service Type | Product Family | Core CMS Controls | High-Risk Governance Areas |
| Vehicle Telematics | OLIWA, OLIWA-PLUS, UKO,, Alerts, Reports, Tokens | Token depletion, RBAC drift | |
| Personnel Tracing | PIKI, PATROL, CAPO, TOTO, WIATAG | Users, Mobile access, Geofences, Safety alerts | Privacy, role scoping |
| Fuel Telematics | MAFUTA (CANBUS/FLS/Flow Meter/Fuel Card/Station), GENSET | Sensors, calibration, fuel rules, reports | Theft disputes, sensor errors |
| AI & Video | DASHCAM, DASH AI, MDVR, MDVR AI | Video storage, bandwidth, AI inference | Cost spikes, privacy masking |
| Goods & IoT | KAGO, PASO, PAWA, THERMO | Temperature/humidity rules, chain-of-custody | Compliance failures |
| VEBA Mobility | VEBA | KYC, booking rules, payments, leakage shield | Fraud/leakage, payments |

## 22.3 Vehicle Telematics Family Administration
### 22.3.1 Minimum viable configuration
1. Account created and assigned to correct dealer
2. Admin user created
3. Units created with correct device profiles
4. Default alerts enabled:
 - Overspeed
 - Ignition on/off
 - Geofence entry/exit
 - Maintenance schedules
5. Standard reports enabled:
 - Trip summary
 - Idle report
 - Overspeed report
6. Token policies applied:
 - Soft alert at 80%
 - Cap per month
✅ Preventive maintenance note: Maintenance schedules MUST be created during onboarding—not after the first breakdown.
### 22.3.2 Corrective maintenance patterns
 - "Unit offline":
 - Check SIM health + coverage
 - Check device last message timestamp
 - Validate power input
 - Reboot procedure and log action
 - "Trips missing":
 - Confirm time zone
 - Confirm ignition wiring logic
 - Confirm filtering rules not too aggressive

## 22.4 Personnel Tracing Family Administration
### 22.4.1 Minimum viable configuration
1. User identity structure:
 - Supervisor user
 - Field staff users (mobile)
2. Geofence zones:
 - Depot, duty station, restricted areas
3. Safety event triggers:
 - Man-down detection
 - Panic button activation
 - Unauthorized movement during rest ✅【476:0†List of Event that Triggers notifications, alerts, alarms.pdf†L64-L69】【476:0†List of Event that Triggers notifications, alerts, alarms.pdf†L88-L90】
4. Notification routing:
 - Supervisor + operations desk + optional emergency contacts
### 22.4.2 Privacy governance
 - Personnel produ Personnel data is high-risk. Over-sharing destroys trust and creates legal exposure.

## 22.5 Next Product Families Coming Immediately
In the next continuation sections, the manual will cover:
 - Fuel telematics (MAFUTA + GENSET)
 - AI & video telematics (DASHCAM/MDVR + AI governance)
 - Goods & IoT (KAGO/PASO/PAWA/THERMO)
 - VEBA marketplace governance + leakage prevention deep dive (using UML flows)

### Screen 27 UI Reference Pack
Use this to align training screenshots, navigation patterns, and provisioning blade behavior:
--- PAGE BREAK ---
# 8. INFRASTRUCTURE & CONNECTIVITY

## Purpose
This section defines mandatory administrative controls for how telemetry enters NAVAS, how it is normalized, how it is cached, and how it is delivered to end‐user portals (OLIWA, PIKI, VEBA, PATROL, etc.). Your objective is zero ambiguity: every device, SIM, protocol, and integration endpoint must be known, governed, auditable, and cost‐optimized. ✅
 Key takeaway: If *Asset & Resource Governance* controls *who can do what*, then Infrastructure & Connectivity controls whether the platform works at all (and whether it stays profitable).

## Architecture For Administrators
NAVAS operates as a high‐velocity data pipeline. As System Admin, you must understand the "path of truth" for telemetry so you can troubleshoot without guesswork. ✅
### Data Flow Overview:
1. Ingestion: raw GPS/IoT packets received (device → server)
2. Streaming: messages published to real‐time topics
3. Orchestration: consumers validate, enrich, and route data
4. Storage: fast writes for telemetry; separate store for audit/RBAC
5. Cache + Live Delivery: live data served with low latency
6. UI: CMS (admin) and product portals (customer) consume APIs/SSE
### Admin‐Relevant Stack Map:
Format note (Google Doc): header row shade #F5F5F5, no borders.
| Layer | Component | What You MUST Administer | Primary Admin Risk |
| Ingestion | Python socket listeners | Listener ports, IP allowlists, protocol adapters | Packet loss, spoofing, port exposure |
| Streaming | Kafka topics | Topic naming/retention, consumer lag monitoring | Backlogs = "silent outage" |
| Orchestration | Node.js producer/consumer | Routing rules, retries, dead‐letter handling | Retry storms, duplicated records |
| Storage (Fast) | Cassandra | Partitioning strategy adherence, retention | Hot partitions, write saturation |
| Storage (Static) | PostgreSQL | RBAC, user accounts, audit trails | Privilege drift, audit gaps |
| Cache + SSE | Redis | Cache TTL policy, live stream health | Stale data, UI latency |
| Frontend | React / React Native | CMS availability, portal API uptime | Admin lockout, customer churn |

✅
⚠ Non‐negotiable rule: When telemetry is "missing," you MUST identify which layer failed before escalating. Do not escalate based on "it looks offline" alone.

## Connectivity Objects You Must Govern
### Object Definitions:
The CMS typically exposes these as tables (with right‐side blades/drawers for CRUD).
1. Device (Unit)
 - Identity: IMEI / serial / device ID
 - Type: GPS tracker, dashcam, MDVR, fuel sensor gateway, wearable, etc.
 - Ownership: tenant/account/resource mapping
2. Protocol Profile
 - Parser settings, parameter map, validation rules, decoding templates
3. SIM Profile
 - Carrier, ICCID, MSISDN, APN, roaming policy, bundle type
4. Connectivity Policy
 - Expected reporting interval, offline threshold, retry logic
5. Integration Endpoint
 - API keys, webhooks, callbacks, third‐party connectors (Odoo, n8n, WhatsApp, SMS, Maps, BI)
6. Firmware/OTA Policy
 - Update windows, canary rollout, rollback rules
✅ Admin standard: Every Device MUST have a Protocol Profile + SIM Profile + Connectivity Policy assigned, or it is not commissioned.

## Key Pages In This Module
### Device Registry:
Your single source for unit lifecycle control:
 - Create / import devices (bulk CSV or API)
 - Assign templates (protocol + parameters)
 - Commission / decommission
 - Lock changes post‐commissioning (HIC) ✅
### Protocol & Integration Hub:
 - Decoder selection & mapping
 - API keys / tokens
 - Retry rules
 - Dead‐letter queues and reconciliation
### SIM Card Intelligence Console:
This is where "money leaks silently" through:
 - Uncontrolled roaming
 - Wrong bundle type (video device on low‐tier bundle)
 - Retry storms in poor coverage
 - Excessive heartbeat/report intervals
 ✅

--- PAGE BREAK ---
## Device Provisioning Standard
### Objective:
Provision devices with safe defaults, then tighten to profit‐safe policies (token burn control + network cost control). ✅
### Provisioning Workflow (SAFE DEFAULT)
1. Select the Tenant / Account Context (HIC safe)
 - Confirm you are acting under the correct tenant context.
 - If using "Act on behalf," ensure your actions will be captured in audit logs. ✅
2. Create Device Identity (Device Registry → + New)
 - Required: Unique ID (IMEI/serial), device type, vendor/model
 - Optional: Asset label, plate/driver, installation team reference
3. Assign Protocol Profile
 - MUST match device firmware/protocol version
 - MUST map expected parameters (GPS, IO, CAN, video, sensors)
4. Attach SIM Profile
 - ICCID/MSISDN, APN, roaming rule, bundle type, expiry date
5. Set Connectivity Policy
 - Reporting interval (expected)
 - Offline threshold (operational)
 - Retry/backoff (cost control)
6. Commissioning Validation (First Data)
 - Confirm first timestamp is fresh
 - Confirm location is plausible
 - Confirm core parameters exist (GPS fix, speed, ignition, voltage)
7. Lock Configuration (post‐commission)
 - Prevent drift from "helpful but destructive" edits
 - Enforce Maker‐Checker for changes affecting billing, safety, or privacy
⚠ Corrective action rule: If first data is wrong (time offset, impossible coordinates), do not "wait it out." Fix the root cause (timezone, parser map, APN route, firmware mismatch).

## Provisioning Templates By 3D Product Line
Your provisioning must align with what the customer is buying. A DASHCAM‐class device is not governed like a PIKI tracker. ✅
Format note (Google Doc): header row shade #F5F5F5, no borders.
| Product Family | Product Examples | Typical Telemetry Load | Admin Focus | Typical Risk |
| Vehicle Telematics | OLIWA, OLIWA‐PLUS, iVMS, iVMS‐PLUS, GUVNA | Medium | Uptime, geofences, notifications | "Offline panic" from poor thresholds |
| Personnel Tracing | PATROL, CAPO, WIATAG, TOTO | Low–Medium | Safety events, check‐in/out | Identity/RBAC misuse |
| Fuel Telematics | MAFUTA FLS, FLOW METER, CANBUS, FUEL CARD, STATION, GENSET | Medium–High | Sensor calibration + anomaly detection | False theft alerts |
| Goods‐in‐Transit & IoT | KAGO, PASO, THERMO, PAWA | Medium | Sensor integrity + chain of custody | Missing events = liability |
| AI & Video Telematics | DASHCAM, DASH AI, MDVR, MDVR AI | Very High | Bandwidth, storage, privacy gates | Runaway cost + compliance breach |
| Add‐On Apps | BI DASHBOARDS, ECO, FLEETRUN, INSPECTA, JMS, LOGISTICS, NIMBUS, VEBA | Variable | Provisioning governance | Leakage, mis‐billing |
| VAS | Help Desk & Training, SATO, OEM Integrations, Local Server | Variable | SLA delivery | Service drift |

✅ (Product alignment reference)

## Token/Cost Implications: Why Connectivity Choices Matter
NAVAS monetizes usage via token burn tied to telemetry parameters. Some parameters (especially video and AI events) carry higher revenue potential and thus require stricter governance. ✅
### High‐Value Parameters You Must Monitor
Examples of cost‐heavy/high‐value telemetry that MUST be governed tightly:
 - Real‐time streaming bandwidth (video)
 - Video snapshots (image events)
 - ADAS/DMS events (headway, lane departure, fatigue indicators)
 ✅
### Admin Directive:
 - For AI & Video fleets, you MUST set:
 - data retention limits
 - streaming permissions (RBAC)
 - snapshot rules (event‐based only)
 - anomaly alarms for bandwidth spikes
 - For non‐video fleets, you MUST prevent:
 - accidental high‐frequency tracking intervals
 - retry storms caused by poor APN/coverage

--- PAGE BREAK ---
## SIM Card Intelligence: Where Money Leaks Silently  ̧
### Purpose
This console exists to protect margin by aligning SIM costs with the client's operational reality:
 - Uganda: MTN / Airtel patterns
 - Kenya: Safaricom / Airtel patterns
 - Cross‐border: roaming + routing control
✅ Admin mindset: SIM governance is not "telecom admin." It is commercial survival.
### SIM Inventory Governance (Mandatory)
You MUST maintain a clean SIM inventory table with:
1. ICCID
2. MSISDN
3. Carrier
4. APN policy
5. Bundle type (low, medium, video)
6. Assigned device ID
7. Activation date + expiry date
8. Roaming rule (allowed/blocked)
9. Status (In stock / Installed / Suspended / Retired)
### Daily SIM Checks (10 minutes)
1. Top 20 data consumers
 - Validate each is a video‐class or high‐telemetry class unit
2. Roaming events (past 24h)
 - Confirm legitimate cross‐border operations
3. Retry storms / reconnect loops
 - Usually indicates coverage blackspots or APN issues
4. SIM assigned but no telemetry
 - Likely wrong APN, wrong IMEI mapping, or device wiring fault
### Common SIM Anomalies & Correct Admin Actions
Format note (Google Doc): header row shade #F5F5F5, no borders.
| Anomaly | Likely Cause | Mandatory Action | Customer Impact If Ignored |
| High data usage spike | Streaming enabled, camera misconfigured, or excessive snapshots | Enforce RBAC + event‐based capture; audit rules | Bill shock, churn |
| Frequent reconnects | Poor coverage, wrong APN, power instability | Reduce retry aggressiveness; validate wiring | "Phantom offline" complaints |
| Roaming charges | Device crossed border or carrier mis‐routing | Apply roaming rule; whitelist only required devices | Margin erosion |
| No telemetry, SIM active | Wrong IMEI mapping, device dead, wrong protocol | Validate identity + protocol profile; field check | SLA breach |
| Multiple devices on same SIM | Operational error / fraud | Lock SIM to device; audit log review | Legal/security incident |

## HIC + AI Tactics For SIM Optimization ✈
### AI Can Recommend; Humans Must Approve
Waswa AI may highlight:
 - "This tenant is burning tokens too fast"
 - "This SIM bundle is mis‐matched to device class"
 - "This device is retrying abnormally"
 ✅
Your rule:
 - AI suggestions are advisory, not authoritative.
 - Changes that affect billing or privacy MUST be maker‐checker (HIC). ✅
### Practical Admin Prompts (Copy/Paste)
Prompt 1 (SIM cost governance): *"Identify the top 20 SIMs by data use in the last 7 days, classify each as video vs non‐video, and recommend bundle adjustments. Flag any anomalies requiring HIC approval."*
Prompt 2 (retry storm diagnosis): *"For these 10 devices with frequent reconnects, correlate power voltage, GSM signal, and last known locations. Propose a corrective action per device."*
Prompt 3 (roaming risk): *"Detect roaming events by tenant and device class. Recommend which roaming rules to apply with minimal operational disruption."*

--- PAGE BREAK ---
## Connectivity Policies: Heartbeats, Offline Thresholds, and Retry Control
### Baseline Controls
Every device MUST have:
1. Expected reporting interval (what "normal" looks like)
2. Offline threshold (when CMS alerts)
3. Retry/backoff policy (prevents data storms)
4. Alert routing (who gets notified, and how)
### Admin Rule: Offline Is Not A Single Condition
Define offline thresholds by class:
 - Vehicle tracking (OLIWA/UKO/iVMS): moderate thresholds
 - Personnel safety (PATROL/CAPO): tighter thresholds during shifts
 - Fuel theft risk (MAFUTA): tighter thresholds for high‐risk routes
 - Video devices (MDVR/DASHCAM): separate thresholds for telemetry vs video upload
⚠ Do not punish poor network areas with aggressive offline rules. You will generate alert spam, reduce trust, and increase support costs.
### Preventative Maintenance Note
 - Weekly: review top 10 routes/regions with weak GSM signal and adjust policies to reduce false alerts.
 - Monthly: review retry policies and ensure they are not "maximum aggressiveness."

## Protocol & Parser Governance
### Why It Matters
Protocol misconfiguration creates "garbage telemetry," which then creates:
 - false alarms
 - incorrect reports
 - incorrect billing/tokens
 - customer distrust
### Mandatory Admin Controls
1. Protocol profiles MUST be versioned
2. Changes MUST be logged (who, what, when, why)
3. High‐impact changes MUST be maker‐checker
4. Rollback path MUST exist (previous profile kept)
✅ Standard: Treat protocol changes like production code changes—because they are.

## Integration Endpoints: Odoo, n8n, Messaging, BI
NAVAS CMS operations in 3D typically rely on integrations for billing, onboarding, customer comms, and analytics workflows. ✅
### Core Integration Categories
1. Billing & Subscription Control
 - Renewal reminders (SMS/WhatsApp/email)
 - Suspend/unblock accounts based on DPD rules
2. Sales & Onboarding Automation
 - Lead capture → account creation → job cards → route planning
3. Customer Experience & Support
 - Sentiment analysis of customer messages
 - Ticket summaries + insights
4. Reporting & Compliance
 - Audit logs to secure storage
 - Cross‐reconciliation (billing vs tracked units)
✅
### Admin Directive: Integrations MUST Be Treated As Production Systems
You MUST implement:
 - API key rotation policy (quarterly minimum)
 - Webhook signature verification (where supported)
 - Rate limiting to prevent abuse
 - Dead‐letter logging for failed events
 - A single integration inventory register (owner, purpose, SLA, keys, expiry)

--- PAGE BREAK ---
## Operational Priorities: Where 3D Revenue Concentrates
3D's historical revenue mix shows subscriptions and hardware heavily concentrated in Vehicle Telematics and Fuel Telematics, with significant contribution from AI/Video. Your infrastructure reliability priorities MUST reflect this reality. ✅
### Admin Priority Order (Directive)
1. Vehicle Telematics uptime stability (largest recurring base)
2. Fuel telemetry accuracy (highest dispute risk if wrong)
3. AI/Video bandwidth governance (highest cost leakage risk)
4. Personnel safety uptime (shift‐based)
5. Goods‐in‐Transit event integrity

## Corrective Maintenance Runbook: "Units Went Offline"
### Step‐By‐Step Diagnostic Ladder (Do Not Skip Steps)
1. Confirm scope
 - One device? One client? One region? Entire system?
2. Check ingestion health
 - Are listeners accepting connections?
3. Check streaming backlogs
 - Consumer lag = delayed telemetry = "offline" illusion
4. Check cache/live delivery
 - If UI is stale but storage is fresh, it's a cache/SSE issue
5. Check SIM status
 - Suspended? expired bundle? roaming?
6. Check device electrical health
 - Voltage events, ignition, intermittent power
7. Check protocol drift
 - Wrong parser profile = dropped packets
⚠ Escalate only after classification. "Offline" without layer classification creates noise and wastes MTTR.

## Customer Experience Tactics (Admin‐Level) ✅
Even seasoned telematics customers evaluate you on clarity, control, and speed. Your infrastructure governance directly affects CX.
1. Reduce false alarms
 - Tune offline thresholds by region and product class
2. Make downtime visible and honest
 - Status banners in portals when systemic issues occur
3. Use proactive notifications
 - "We detected a network outage in Region X; your devices may appear offline."
4. Deploy AI as a triage assistant, not a decision maker
 - AI speeds classification; human confirms action

## Section Closure Checklist ✅
Before moving to the next module, you MUST confirm:
1. Every device has identity + protocol + SIM + connectivity policy assigned
2. SIM inventory is complete and current
3. Offline thresholds are segmented by product class
4. Retry/backoff rules are not cost‐explosive
5. Protocol profile changes are audited and rollback‐capable
6. Integration endpoints are inventoried, secured, and monitored

--- PAGE BREAK ---
NEXT SECTION: 9. ASSET & RESOURCE GOVERNANCE
# 8. INFRASTRUCTURE & CONNECTIVITY

SECTION INTENT (MANDATORY): This section prescribes the *non‐negotiable* operational standards for keeping NAVAS services online, accurate, cost‐efficient, and supportable across Uganda o and Kenya a. As a System Administrator, you are accountable for data continuity, data quality, connectivity cost control, and predictable service restoration (MTTR). ✅
Landscape Orientation Note : Set the Google Doc page orientation to Landscape before pasting this section.
Mandatory Page Break Rule: Insert a Page Break at the end of this section before the next section.

## 8.1 Purpose
The Infrastructure & Connectivity module exists to ensure the following outcomes are always true:
1. Units report reliably (GPS + GSM/GPRS + Power continuity) with defensible data quality.
2. Video and high‐value telemetry parameters (ADAS/DMS/MDVR, fuel, temperature, door sensors) are online with correct intervals and thresholds.
3. Connectivity cost is governed (SIM bundles, roaming, video bandwidth) without degrading customer experience.
4. Failures are detected early and resolved with controlled, auditable change.
5. HIC (Human‐In‐Control) gates are enforced for high‐impact actions (firmware updates, intervals, token policy, shutdowns, suspension actions, integrations). ✈
 Key takeaway: If you do Infrastructure right, you reduce (a) downtime tickets, (b) revenue leakage, (c) churn risk, and (d) field support cost.

## 8.2 Reference Architecture for Admins
NAVAS is implemented as a high‐velocity telemetry pipeline with the following core layers (you must understand this at admin level for fault isolation):
 - Ingestion: Python socket parsers (raw device packets)
 - Streaming: Kafka topics (real‐time message broadcasting)
 - Orchestration: Node.js producers/consumers (bridging Cassandra writes to Redis cache)
 - Storage: Cassandra (fast telemetry), PostgreSQL (audit/users/RBAC)
 - Cache: Redis (low‐latency UI and SSE)
 - UI: React / React Native (apps like OLIWA, PIKI, VEBA)
 These are foundational to "<3s latency to UI" expectations and must be monitored accordingly.
*Operational doctrine.* You do not "guess" causes of downtime; you isolate failures layer‐by‐layer (Device → Network → Ingestion → Stream → DB → Cache → UI). ✅

## 8.3 Module Surfaces in CMS (What You Will See)
In CMS, Infrastructure & Connectivity typically presents as:
 - Blades (right drawers) for provisioning, edits, batch actions, and governance approvals
 - Cards for health counters (offline units, low signal units, high data usage, sensor faults)
 - Tables for bulk filtering and CRUD actions
 - Audit panels for "who changed what, when, and why"
*Mandatory operating principle.* You must run Infrastructure from tables + filters + bulk actions, not from one‐unit‐at‐a‐time clicking. This is how you scale across 1,000+ assets.

## 8.4 The "Connectivity Triangle" Standard (GPS + GSM/GPRS + Power) ✅
Every stable unit depends on three independent pillars:
1. GPS Quality (satellites, HDOP, antenna health)
2. GSM/GPRS Connectivity (signal strength, SIM health, data bundles)
3. Power Integrity (vehicle power + backup battery + wiring workmanship)
When any pillar fails, tracking degrades or collapses. Your job is to classify failures fast, then route the correct fix.
### 8.4.1 Failure Pattern Library (Do Not Reinvent This)
Below is a mandatory failure classification baseline used in procurement and field diagnosis (Risk Level + typical causes).
Header row shaded #F5F5F5 (apply in Google Docs).  No borders.
| Risk Area | Risk Level | Common Failure Mode | Typical Root Cause (Most Frequent) |
| GPS | Medium | Loss of GPS fix | Antenna disconnected, faulty module, underground parking, device installed upside‐down |
| GSM/GPRS | High | No data / offline | GSM shadow/no carrier, SIM fault, telecom outage, SIM loose, no data bundle |
| Power (12/24V) | Medium | Device off | Battery removed, tampering, loose harness, faulty backup battery, 3rd‐party repairs |
| Tracking Device | High | Fragile HW failures | Vibration, heat, dust, surges, moisture, weak accessories |
| Vehicle Fit | Medium | Wrong device for need | Poor R\\&D, bad QA, wrong accessories/sensors |
| Workmanship | Low | Poor install | Short circuits, battery drain, damage to dashboards, loose joins |
| Software | Low | Poor reliability | Poor design, slow web/app, limited features, limited upgrades |
| Server | Low | Uptime issues | Poor hosting choice, no redundancy, weak security, poor connectivity |
| Customer Service | High | Slow MTTR | Weak SLA governance, slow response, no compensation model |
| User Training | Medium | User misuse | Poor training, users benefiting from abuse of assets/fuel |
| Supplier Quality | Medium | Poor aftersales | Incompetent supplier, low manpower, inexperienced |
| Asset Location | High | Access difficulty | Distance/security, SLA constraints, availability of asset |
| Fuel Monitoring | High | Complex measurement | Irregular tanks, calibration errors, leaking tanks, weak know‐how |
| HW Flexibility | High | Limited options | Manufacturer limitations, compatibility constraints |
| SW Flexibility | High | Limited reports/alerts | Manufacturer design limits, limited rights to adjust locally |

✅ Directive: Every support ticket must be assigned a *Connectivity Triangle classification* before you escalate to field teams. This prevents "random dispatch" and reduces unnecessary travel.

## 8.5 Device Provisioning Lifecycle (The Only Acceptable Workflow)
This is the system admin provisioning lifecycle you must enforce.
### 8.5.1 Stage 1 — Pre‐Provisioning Planning
Before any device is activated in production:
1. Confirm product class & use case (OLIWA vs PIKI vs VEBA vs MAFUTA vs DASHCAM/MDVR).
2. Confirm country & network constraints
 - Uganda: MTN/Airtel coverage variance, some heavy GSM shadow in rural corridors
 - Kenya: M‐Pesa rails, roaming behavior around borders is a known cost driver
3. Confirm sensor plan (fuel probes, temperature, door, TPMS, camera channels).
4. Confirm customer SLA tier (response times, escalation rules, reporting cadence).
5. Confirm billing governance (token wallet rules, low‐balance triggers, payment rails).
 *Trainer's tip.* If you plan wrongly, you will "repair forever." Plan right and repairs drop naturally.
### 8.5.2 Stage 2 — Create or Select a Provisioning Profile
Provisioning profiles must be standardized by product and use case.
*Provisioning Profile.* A controlled template containing:
 - Device type / protocol
 - Reporting interval and sleep mode rules
 - Speed & movement filters
 - IO mapping and sensor calibration templates
 - Alert policies (offline, tamper, overspeed, fuel drop, temperature deviation)
 - Token burn safety rules (especially for video/AI)
✅ Directive: You are forbidden to create "one‐off" device configs outside a governed profile unless you document a technical exception and attach it to the audit trail.

## 8.6 SIM Console Operations (Cost Control Without Service Collapse) 3
NAVAS includes SIM Card Intelligence as a dedicated console for:
 - Roaming cost detection
 - Data interval mismatch detection
 - "Nearest bundle" decisioning for camera + telematics use cases
### 8.6.1 Non‐Negotiable SIM Governance Rules
1. Every unit must have SIM metadata stored in CMS:
 - MSISDN / ICCID (or internal SIM ID)
 - Network operator (MTN/Airtel/Safaricom/etc.)
 - Bundle category (telemetry‐low, telemetry‐high, video‐standard, video‐premium)
 - Roaming allowed (Yes/No)
2. Data bundle exhaustion is NOT an acceptable outage reason
 You must configure *low‐bundle alerts* and *auto‐top‐up workflows* where allowed by policy.
3. Cross‐border roaming must be flagged
 Especially for clients with frequent travel near borders (UG‐KE corridors).
⚠ *Risk pattern:* Video devices are the #1 silent cost killer if interval + stream policies are misconfigured.

## 8.7 Product‐Specific Connectivity Standards (UG o / KE a)
You must operate each product category with its own connectivity assumptions.
### 8.7.1 Standard Connectivity Classes
Header row shaded #F5F5F5 (apply in Google Docs).  No borders.
| Service Type | Products | Connectivity Profile | Admin Priority |
| Vehicle Telematics | GUVNA, iVMS, iVMS‐PLUS, OLIWA, OLIWA‐PLUS | Low‐to‐Medium data. GPS reliability first. | Offline control + data quality |
| Personnel Tracing | CAPO, PATROL, PIKI, TOTO, WIATAG | Medium data; identity & safety events matter. | Alert hygiene + rapid triage |
| Fuel Telematics | MAFUTA (CANBUS, Flow, FLS, Card, Station), GENSET | Medium data; calibration and false positives are common. | Sensor integrity + governance |
| Goods‐in‐Transit & IoT | KAGO, PASO, PAWA, THERMO | Medium data; environment sensors & security events. | Threshold tuning + proof logs |
| AI & Video Telematics | DASH AI, DASHCAM, MDVR, MDVR AI | High data; bandwidth/storage/channel governance. | Cost control + evidence integrity |
| Add‐On Apps | BI Dashboards, DSC, ECO, FLEETRUN, INSPECTA, JMS, LOGISTICS, NIMBUS, VEBA | Variable; depends on integrations and reporting. | Entitlements + reliability |
| Value Added Services | Help Desk & Training, GIS & JMS, SATO, Local Owned Server, OEM Integrations | Variable; SLA enforcement critical. | MTTR + compliance |

✅ Directive: You must apply the correct class at provisioning. Do not treat MDVR like OLIWA. That is operational malpractice.

## 8.8 Target Installation & Repair Times (Operational SLA Baseline)  ̄
As System Admin, you must configure CMS workflows and dashboards to reflect installation and repair time targets per product. These targets define operational planning and escalation.
Header row shaded #F5F5F5 (apply in Google Docs).  No borders.
| Service Type | Product | Target Time to Install | Target Time to Repair |
| AI & Video | DASH AI | 4.5 hrs | 3 hrs |
| AI & Video | DASHCAM | 4 hrs | 3 hrs |
| AI & Video | MDVR | 8 hrs | 3 hrs |
| AI & Video | MDVR AI | 8 hrs | 3 hrs |
| Vehicle Telematics | iVMS | 3 hrs | 2 hrs |
| Vehicle Telematics | iVMS‐PLUS | 4 hrs | 3 hrs |
| Vehicle Telematics | OLIWA | 3 hrs | 2 hrs |
| Vehicle Telematics | OLIWA‐PLUS | 4 hrs | 3 hrs |
| Fuel Telematics | MAFUTA‐FLS | 8 hrs | 3 hrs (recalibration: 8 hrs) |
| Fuel Telematics | MAFUTA‐CANBUS | 4 hrs | 3 hrs |
| Fuel Telematics | MAFUTA‐FLOW METER | 3 hrs | 2 hrs |
| Personnel Tracing | CAPO | 1 hr | 30 mins |
| Personnel Tracing | PIKI | 3 hrs | 2 hrs |
| Personnel Tracing | TOTO | 1 hr | 30 mins |
| Personnel Tracing | WIATAG | 1 hr | 30 mins |
| Personnel Tracing | PATROL | 4 hrs | 2 hrs |
| Goods & IoT | GENSET | 8 hrs | 3 hrs (recalibration: 8 hrs) |
| Goods & IoT | KAGO | 4 hrs | 3 hrs |
| Goods & IoT | THERMO | 2 hrs | 1 hr |
| Goods & IoT | PASO | 1 hr | 1 hr |
| Goods & IoT | PAWA | 4 hrs | 3 hrs |

✅ Directive: Your CMS must measure these times (ticket created → resolved), and surface breaches automatically for escalation. This is not optional.

## 8.9 Telemetry Diagnostics: What You Must Monitor
Your monitoring must be parameter‐driven. NAVAS supports a large parameter catalogue (including high‐value AI/video parameters).
### 8.9.1 Minimum Diagnostic Signals (All Products)
*Baseline telemetry health.* You must maintain dashboards and alerting for:
 - GSM / signal (e.g., signal strength categories)
 - GPS quality (satellites, HDOP/PDOP)
 - Timestamp freshness (last message age)
 - Power & battery (external voltage + internal battery)
 - Ignition state consistency
 - Tamper events
 - Movement events (motion while ignition off for towing)
✅ Directive: A unit is not "healthy" because it is "online." It is healthy when freshness + quality + power integrity are in acceptable ranges.
### 8.9.2 Video/AI Diagnostics (DASHCAM/MDVR/MDVR AI/DASH AI)
*Video health governance.* You must actively monitor:
 - Bandwidth usage and stream session behavior
 - Storage status (SD/HDD OK/Fail)
 - Camera channels online
 - AI event production quality (fatigue, distraction, lane departure, forward collision, etc.)
⚠ Directive: Never let customers discover video failures first. Your system must detect and raise health alarms automatically.

## 8.10 Alerts & Notification Triggers: Standard Event Taxonomy
A mature telematics CMS *must* run on a standardized event taxonomy.
Below is a canonical sample coverage list you must configure as templates per product tier:
 - Driver fatigue, distracted driving, phone use, smoking, seatbelt unbuckled
 - Over‐speeding, harsh acceleration/braking/cornering, rollover/crash/impact detection
 - Fuel drop / refill / rapid consumption / low level
 - Door open/close unauthorized, cargo intrusion, asset detachment
 - Temperature/humidity deviation (THERMO/cold chain)
 - Maintenance reminders (mileage/time/engine hours)
 - Panic/SOS/man‐down (personnel safety)
 - Route compliance and geofence entry/exit
✅ Directive: Alerts must be:
1. Actionable (have a required action and owner),
2. Routed correctly (role + tenant + severity),
3. Rate‐limited (no alert storms),
4. Auditable (what was sent, to whom, when).

## 8.11 Firmware & OTA Changes (HIC‐Gated) ⚠
Firmware/OTA is a high‐risk activity. It must be executed under HIC governance.
### 8.11.1 Mandatory OTA Safety Protocol
1. Classify the change
 - *Security patch* (urgent)
 - *Feature update* (planned)
 - *Bug fix* (planned)
2. Select a canary group
 - 3–5 units (non‐critical) first
3. Define rollback
 - Clear rollback trigger thresholds (offline > X minutes, sensor failure, abnormal battery drain)
4. Execute in controlled windows
 - Avoid peak operational hours for corporate fleets
5. Audit & close
 - Log results; attach evidence and post‐change validation
*Run-in rule.* *Approval required.* OTA on production fleets requires a maker‐checker approval record.

## 8.12 Integrations & Automation: What a CMS Admin Must Own
3D Services operates a multi‐system environment. CMS must integrate with operational and commercial tools (examples include billing/CRM, messaging, dashboards, automation orchestrators).
### 8.12.1 Integration Control Rules (Non‐Negotiable)
1. All API keys must be stored in a secure secret manager (never inside browser‐only configs).
2. All webhooks must be versioned
3. All automations must write logs
 - Timestamp, actor, tenant, object, action, outcome
4. All finance‐impact actions must be HIC‐gated
 - Suspension/unblock, credit notes, token wallet changes, price rules
 *Practical admin tactic:* Build a "Heartbeat Dashboard" for integrations:
 - WhatsApp gateway success rate
 - SMS gateway success rate
 - Payment callback success rate
 - Odoo/ERP sync status
 - BI refresh status
 When any heartbeat fails, raise an incident automatically.

## 8.13 Preventative Maintenance (Admin‐Level) ✅
This is your prevention routine. If you skip it, outages and escalations increase—guaranteed.
### 8.13.1 Daily (15–20 minutes)
1. Review offline units by tenant
2. Review SIM bundle low warnings
3. Review top token burn anomalies (especially video tenants)
4. Confirm message gateway health
5. Confirm critical alarms are closing with accountable ownership
### 8.13.2 Weekly
1. Review the worst 10 units by:
 - Offline frequency
 - Low signal
 - Battery instability
2. Review sensor anomaly clusters
 - Fuel false positives, temperature spikes, door sensor chatter
3. Review firmware/version drift
4. Review integration error logs
### 8.13.3 Monthly
1. Review provisioning templates
2. Review roaming patterns and bundle policies
3. Run a "fleet health report" per top 20 customers
4. Run access review on any user with provisioning permissions

## 8.14 Corrective Maintenance (Admin‐Level)
Corrective work must follow controlled steps.
### 8.14.1 Remote‐First Triage (Before Dispatch)
1. Confirm last message time + GPS/GSM quality
2. Check power metrics and ignition state
3. Check if SIM has data and is attached to correct APN profile
4. Confirm the unit is not in "sleep mode"
5. Confirm no recent config change caused regression (audit log review)
✅ Directive: If you cannot explain *why* a unit is offline remotely, you are not ready to dispatch.
### 8.14.2 Dispatch Decision Standard
Dispatch only when:
 - Root cause is likely physical (power, antenna, wiring, tamper, hardware failure), OR
 - SLA tier mandates field action within time thresholds

## 8.15 HIC + Waswa AI in Infrastructure (How to Use It Correctly) ✈
AI is a *multiplier*, not a replacement. Use it to speed diagnosis and reduce blind spots, then validate.
### 8.15.1 Approved AI Uses
 - Trend detection: "Which tenant's units are deteriorating fastest?"
 - Correlation: "Is offline rate correlated with a specific SIM batch/operator?"
 - Cost leakage: "Which video tenants are misconfigured and burning tokens abnormally?"
 - Drafting: Draft incident updates, SOP checklists, maintenance reminders
### 8.15.2 Forbidden AI Uses
 - Executing production changes without approval
 - Auto‐dispatching technicians without human verification
 - Auto‐updating token or billing policy without maker‐checker
✅ Directive: AI outputs must be treated as *recommendations* unless evidence confirms. You remain accountable.

### SECTION 8 — STRATEGIC HIGHLIGHTS ✅
 - Infrastructure is governance. Your job is to engineer predictability.
 - Template everything (provisioning, alerts, SIM bundles, firmware rollout).
 - Run remote‐first triage to reduce unnecessary dispatch.
 - Use HIC gates for high‐impact actions (OTA, token policy, integrations).
 - Use Waswa AI for insight, not authority. Evidence still wins.

FOOTER STANDARD (Apply in Google Docs):
Left: NAVAS IoT System - CMS Module - 01.MAR. 2026 | Center: "You name it, we track it." ✅ | Page number: Bottom‐Right

## --- PAGE BREAK ---
# 9. ASSET & RESOURCE GOVERNANCE

SECTION INTENT (MANDATORY): This section defines the governance model for managing tenants, accounts, resources, users, roles, devices, and entitlements at scale—without privilege drift, without revenue leakage, and without audit gaps. ✅

## 9.1 Purpose
Asset & Resource Governance ensures:
1. Multi‐tenancy integrity (no cross‐tenant data bleed—ever)
2. RBAC correctness (least privilege enforced)
3. Operational scale (bulk workflows, templates, consistent naming)
4. Auditability (all actions recorded, explainable, and reviewable)
5. Commercial control (token wallets, entitlements, add‐on enablement, policy versions)
 *Key takeaway:* Governance is how you protect *both* customer trust and your margins.

## 9.2 Core Entities You Must Govern
You will encounter these objects across modules:
1. Tenant / Account
 The commercial boundary for billing + policy + data segregation.
2. Organization / Business Unit
 A customer's internal subdivisions (departments, branches).
3. Resource / Asset
 The "thing being managed" (vehicle, motorcycle, person, genset, parcel, equipment).
4. Unit / Device
 The telematics hardware identity mapped to the asset.
5. User
 A human identity (customer admin, operator, dispatcher, auditor, technician).
6. Role / Permission Set
 The allowed scope of actions.
7. Groups
 Logical grouping for fleet operations (regions, routes, business units).
8. Entitlements
 Which products/apps/features the tenant can use (VEBA, INSPECTA, BI, Video, Fuel).
9. Token Wallet / Billing Policy
 The consumption governance engine.
10. Audit Log Records
 The permanent truth of actions.
✅ Directive: You must be able to answer this question at any time:
"Who can do what to which assets, and why?"

## 9.3 Hierarchy & Delegation (Dealer‐Style Governance)
NAVAS supports hierarchical governance aligned to East African distribution models:
 - Top Account (3D / internal master tenant)
 Owns global policies, templates, and supervision.
 - Dealers / Regional Managers
 Delegate provisioning and support under controlled scope.
 - Customer Tenants
 Operate daily monitoring within limited permissions.
### 9.3.1 Non‐Negotiable Delegation Rules
1. Dealers cannot change global token policy (only propose; top approves).
2. Customers cannot change provisioning templates (only request).
3. Audit roles must remain read‐only and immune to "role stacking."
4. All impersonation ("act on behalf") must be logged as a privileged action.

## 9.4 RBAC: Roles, Permissions, and Least Privilege
RBAC is not paperwork. RBAC is operational survival.
### 9.4.1 Standard Roles You Must Provide
Header row shaded #F5F5F5 (apply in Google Docs).  No borders.
| Role | Purpose | Must Be Able To | Must NOT Be Able To |
| System Admin | Platform governance | Everything (within policy + approvals) | Bypass maker‐checker on restricted actions |
| Support Supervisor | Support governance | View all tenants, assign tickets, view logs | Change token price rules, edit billing policies |
| Field Technician | Install/repair | View assigned jobs, update device status | Change RBAC, edit tenant billing, impersonate |
| Customer Admin | Customer governance | Manage their users, groups, reports, alerts | See other tenants, change global templates |
| Dispatcher/Operator | Daily ops | Live tracking, trip replay, alerts triage | Provision devices, change firmware |
| Auditor | Compliance | Read data + export audit evidence | Create/edit/delete anything |
| Finance Officer | Commercial ops | Token top‐up visibility, invoice mapping | Change telemetry configs, disable units |

✅ Directive: You must enforce separation of duties between:
 - Provisioning (technical control),
 - Billing & tokens (commercial control),
 - Audit (oversight).

## 9.5 CRUD Operations: The CMS Discipline (Do It the Same Way Every Time) ✅
System Admin work is repetitive by design. Excellence comes from consistency.
### 9.5.1 Create (C)
*Run-in rule.* *Creation standard.* Every new object must follow:
1. Standard naming convention
2. Correct tenant mapping
3. Correct country + currency + timezone
4. Correct entitlement assignment
5. Correct audit tag (reason: onboarding, migration, change request)
### 9.5.2 Read (R)
You must support:
 - Table filters (tenant, group, status, product)
 - Drilldowns (open asset card, open device card, open user card)
 - Evidence exports (PDF/CSV audit exports)
### 9.5.3 Update (U)
All updates must be:
 - Atomic (one change per action when possible)
 - Reversible (rollback plan)
 - Audited (who/what/why)
### 9.5.4 Delete (D)
Deletion must follow:
1. Soft delete first (archive/trash)
2. Retention policy compliance
3. Approval required for destructive deletes (HIC gate)
✅ Directive: Permanent deletion is a *compliance event*. Treat it that way.

## 9.6 HIC Governance Controls (Maker–Checker) ✈
HIC is enforced to prevent:
 - Accidental outages
 - Revenue leakage
 - Unauthorized access
 - Irreversible change
### 9.6.1 Actions That MUST Be HIC‐Gated
1. Token policy updates / pricing changes
2. Payment rail configuration changes
3. Firmware/OTA rollouts
4. Bulk provisioning changes (intervals, sensor mappings)
5. Tenant suspension / unblock
6. Audit log retention changes
7. Data export of high‐sensitivity datasets (video, personnel tracking)
✅ Directive: If a change can impact more than 10 units or any billing, it is automatically a maker‐checker action.

## 9.7 Entitlements & Product Harmonization (3D Portfolio Alignment)
Your entitlements must align with the full 3D portfolio:
 - Vehicle Telematics: OLIWA / OLIWA‐PLUS / iVMS / iVMS‐PLUS / GUVNA
 - Personnel: PIKI / TOTO / CAPO / PATROL / WIATAG
 - Fuel: MAFUTA (CANBUS/FLS/FLOW/CARD/STATION) + GENSET
 - Goods & IoT: KAGO / PASO / PAWA / THERMO
 - AI & Video: DASHCAM / DASH AI / MDVR / MDVR AI
 - Add‐Ons: BI, DSC, ECO, FLEETRUN, INSPECTA, JMS, LOGISTICS, NIMBUS, VEBA
 - VAS: Help Desk & Training, GIS & JMS, SATO, Local Owned Server, OEM Integrations
### 9.7.1 Entitlement Rules You Must Enforce
1. No access without entitlement (UI menus must hide/lock consistently).
2. Trials must expire automatically or convert with explicit approval.
3. Add‐On Apps must be provisioned per tenant with dependencies validated.
4. Token wallet must match entitlement (video users must have video token rules).
 *Admin tactic.* Use an "Entitlement Readiness Checklist" before enabling any new product:
 - Device readiness ✅
 - Training readiness ✅
 - Alert templates ✅
 - Reporting templates ✅
 - Token rules ✅
 - Support routing ✅

## 9.8 Audit Logs: What Must Always Be Captured
Audit logs must be immutable and searchable by:
 - Tenant
 - Actor
 - Object (unit, user, policy)
 - Action type (create/update/delete/impersonate/export)
 - Timestamp
 - Reason (free‐text + category)
 - Outcome (success/failure)
✅ Directive: If it wasn't logged, it didn't happen (from compliance perspective).

## 9.9 Preventative Governance Maintenance ✅
### 9.9.1 Weekly
1. Review new privileged users
2. Review impersonation events
3. Review bulk changes and confirm change reasons exist
4. Review "orphan objects" (units without assets, users without roles)
### 9.9.2 Monthly
1. Access review (least privilege validation)
2. Entitlement review (unused apps > 30 days)
3. Token policy version review
4. Audit export test (prove you can produce evidence fast)

## 9.10 Corrective Governance (When Things Go Wrong) ⚠
### 9.10.1 If You Detect Privilege Abuse
1. Disable compromised user session
2. Revoke tokens/keys
3. Force password reset and MFA review (if enabled)
4. Audit: export all actions last 72 hours
5. Post‐incident: document root cause + preventive controls
### 9.10.2 If You Detect Cross‐Tenant Misconfiguration
1. Immediately isolate affected tenants
2. Stop automation workflows temporarily (if risk to finance/data)
3. Restore correct mappings from templates/backups
4. Notify leadership with evidence summary
✅ Directive: In governance incidents, speed matters—but *evidence matters more*. Move fast with control.

### SECTION 9 — STRATEGIC HIGHLIGHTS ✅
 - Governance is the foundation of scale: without it, every new customer increases chaos.
 - RBAC + HIC gates are the profit protection layer (stop revenue leakage, stop errors).
 - Entitlements must match product portfolio exactly—no shadow access, no informal enablement.
 - Audit evidence must be exportable within minutes, not days.

FOOTER STANDARD (Apply in Google Docs):
Left: NAVAS IoT System - CMS Module - 01.MAR. 2026 | Center: "You name it, we track it." ✅ | Page number: Bottom‐Right

### Internal Reference Pack (For Traceability)
 - NAVAS IoT System Policy v26.0
 - Expanded Automation Backlog (Billing/Credit Control/CX/AI)
 - Telematics Parameter Catalogue (Revenue Potential Scoring)
 - NAVAS Products Summary (domains/hardware context)

If continuing immediately: the next section is 10. TELEMATICS & GIS OPS  (Live Ops, Trips, Geofences, Driver Behaviour, Fuel, Video Evidence, Reports).
According to a document from 20 February 2026, NAVAS has been positioned as a Monetizable IoT Infrastructure Platform (not "just tracking"), with a system-admin command center (NAVAS Cockpit), token-based monetization, SIM intelligence, and Waswa AI embedded into core operations.

## — PAGE BREAK —
# 8. INFRASTRUCTURE & CONNECTIVITY

Purpose
This section prescribes the mandatory operating standards for keeping NAVAS connectivity stable, cost-controlled, and hardware-agnostic across Uganda & Kenya deployments. System Administrators MUST treat connectivity as a revenue surface (not just an IT layer): every offline unit, bad interval, or uncontrolled video stream is a direct margin leak. ✅
NAVAS is engineered as a high-velocity pipeline (Python sockets → Kafka → Cassandra/PostgreSQL → Redis → React UI). Your work in this module determines whether that pipeline stays clean, low-latency, and monetizable.

## 8.1 Infrastructure Architecture You Must Understand
Pipeline Reality (H3).* You cannot administer what you cannot model.
NAVAS operates as a layered pipeline. Administrators MUST understand what each layer does, what failures look like, and what actions are allowed.
Core Layers (Operational View)
 - Ingestion (Vanilla Python Sockets)
 Receives raw tracker packets, parses binary payloads, extracts GPS + IO parameters.
 - Streaming (Apache Kafka)
 Publishes real-time events to NAVAS topics for fan-out.
 - Orchestration (Node.js Producer/Consumer)
 Bridges data movement and supports live streaming to UI via Redis/SSE.
 - Storage
 - Cassandra = high-write "fast" store for location and IO parameters.
 - PostgreSQL = static store for audit trails, user accounts, RBAC.
 - Cache & Real-Time Delivery (Redis + SSE)
 Enables sub‐3s perceived latency to clients.
 - Frontend (React / React Native)
 Unified experience across OLIWA, PIKI, VEBA.
✅ Key Takeaway: Every admin action must be traceable to one of these layers (ingestion, streaming, orchestration, storage, cache, UI). If you cannot locate a problem in this chain, you are guessing—and guessing is not an operational strategy.

## 8.2 CMS Connectivity Objects: What You Manage (Non-Negotiable)
Canonical objects (H3). Your CMS configuration MUST treat these as first-class governed objects.
1. Device Record (Tracker / Sensor / Camera / Wearable)
 - Device identifiers (IMEI/serial/device ID)
 - Protocol adapter
 - Communication endpoints (host/port)
 - Feature flags (e.g., CANBUS enabled, video on/off)
2. SIM Record
 - ICCID / IMSI (where applicable)
 - Operator + APN
 - Bundle plan, renewal date, region (UG/KE)
 - Roaming rules & thresholds
3. Asset/Unit Binding
 - Device → Unit → Client account
 - Correct product domain: OLIWA/PIKI/VEBA/PATROL etc.
4. Interval Policy
 - Live mode intervals (e.g., 10s / 30s / 60s)
 - Sleep mode intervals (e.g., 5–30 minutes)
 - Escalation intervals (when alarm state occurs)
5. Firmware / OTA Package
 - Version control, staged rollouts, rollback plan
6. Integration Connector
 - Maps, messaging (SMS/WhatsApp), payment APIs
 - API keys, scopes, rate limits
7. Operational Health Rules
 - Offline detection thresholds
 - Data gaps rules
 - Burn-rate anomalies (tokens)

## 8.3 Product-Aware Connectivity: Admin Control Matrix (UG/KE)
Why this matters (H3). "Connectivity" differs by product. Your default policies MUST match each product's operating physics.
Table formatting note: Set to 100% width, header row shaded #F5F5F5, no borders
| Service Type | Product | Typical Connectivity Profile | Primary Risk | Mandatory Admin Control |
| AI & Video Telematics | DASH AI / DASHCAM / MDVR / MDVR AI | High bandwidth + event bursts | Data bundle blowout; video misuse | Enforce video rules + thresholding; SIM Intelligence review weekly |
| Vehicle Telematics | OLIWA / iVMS / iVMS‐PLUS / GUVNA | Moderate, continuous | Silent offline due to power cuts | Offline SLA monitoring + installation QA |
| Fuel Telematics | MAFUTA FLS / FLOW METER / CANBUS | Moderate + sensor integrity critical | Bad calibration → wrong fuel theft alerts | Calibration governance + maintenance schedule |
| Goods-in-Transit & IoT | THERMO / KAGO / PASO / PAWA / GENSET | Sensor-driven, sometimes rural | Low network; delayed packets | Low-bandwidth policy + store-and-forward expectations |
| Personnel Tracing | CAPO / PATROL / PIKI / TOTO / WIATAG | Mobile + battery constrained | Battery drain; phone permission issues | Low-power mode + disciplined alerting |

✅ Admin tactic: "One interval policy fits all" is prohibited. Video products require strict bandwidth governance. Low-power IoT requires tolerant offline thresholds. The CMS must enforce these differences.

## 8.4 Standard Workflow: Provisioning a New Device (Safe Default) ✅
Rule (H3). Provisioning MUST be executed as a controlled sequence. Improvisation creates later outages and billing disputes.
### Step 1 — Pre-Provision (Before installation)
1. Identify product domain
 - OLIWA vs PIKI vs VEBA vs PATROL (etc.)
2. Create/confirm the client account context
 - Ensure correct country settings (UG/KE), time zone, billing policy.
3. Create the device record
 - Add IMEI/serial, assign protocol, pre-select server endpoint.
4. Create the unit/asset record
 - Naming convention MUST be consistent:
 COUNTRY-CLIENT-ASSETTYPE-REGNO/ID (example: UG-KCCA-LORRY-UAR123A)
5. Bind device → unit
6. Assign SIM record
 - Capture ICCID, operator, APN, planned bundle.
7. Pre-load baseline configuration
 - Report profile, notifications baseline, token policy baseline.
 Trainer Tip: Pre-provisioning in CMS ensures field technicians do not "make up settings on site" (that is the #1 cause of inconsistent deployments).

### Step 2 — Installation & Field Validation
System Administrators MUST require evidence before marking an install as completed.
Mandatory acceptance checks
1. GPS lock achieved
2. Ignition state correctly detected
3. Movement produces distance
4. At least one IO parameter validates (where applicable)
5. Event triggers sanity test
 - Overspeed threshold test (controlled)
 - Geofence entry/exit test (if configured)
6. Connectivity durability check
 - Confirm at least 15–30 minutes stable reporting at expected interval

### Step 3 — Post-Provision Governance (After installation)
1. Attach installation documentation
 - Job-card ID, installer name, timestamp, photos (if used in your SOP)
2. Enable applicable apps/add-ons
3. Activate token subscription rules
 - Ensure the unit is not "visible without entitlement"
4. Enable monitoring alarms
 - Offline alarm + abnormal consumption alarm
5. Customer onboarding confirmation
 - Users created, roles assigned, notification channels set

## 8.5 SIM Card Intelligence: Stop Data Leakage at Source 3
The NAVAS policy explicitly treats SIM Intelligence as a dedicated admin console for analyzing roaming costs, data intervals, and bundle sizing.
Non-negotiable (H3). SIM governance is billing governance.
### Daily SIM Intelligence Checklist (10 minutes)
1. Top 20 data consumers (by unit + by account)
2. Roaming detection list (UG units roaming in KE; KE units roaming in UG)
3. Interval anomaly list
 - Units sending too frequently (misconfigured)
 - Units sending too rarely (offline risk)
4. Video burst flags (for dashcams/MDVR)
5. Bundle expiry timeline (next 7 days)
⚠ Policy: Any unit exceeding expected data profile MUST be actioned within 24 hours (throttle intervals, disable video streaming, or re-bundle with customer approval).

## 8.6 Firmware & OTA Management (Controlled Risk)
Rule (H3). Firmware changes are high-impact and MUST be executed with Human‐in‐Control (HIC).
### OTA Rollout Stages (Mandatory)
1. Stage 0 — Lab validation
2. Stage 1 — Canary deployment
 - 1–2 units per product type
3. Stage 2 — Pilot (5–10%)
4. Stage 3 — Controlled bulk rollout
5. Stage 4 — Post-change review
 - Confirm no spike in offline events, no IO drift, no battery drain issues
✅ HIC tactic: Waswa AI may propose "update all devices now", but execution MUST be approved by an authorized human role (maker–checker). This aligns with the broader NAVAS governance practices and HITL mitigation approach described in the AI strategy.

## 8.7 Preventative Maintenance: Connectivity Stability Program
You MUST run preventative maintenance. East Africa's connectivity realities demand it.
NAVAS explicitly acknowledges remote connectivity constraints and low-bandwidth approaches (SMS/low-data patterns are strategic).
### Daily (System Admin)
 - Review offline units (by product category)
 - Review Kafka/Redis health dashboards (if exposed)
 - Review token burn anomalies (fast burn = misconfigured events or misused features)
### Weekly
 - SIM data audit (top consumers, roaming, bundle optimization)
 - Device health audit (battery, voltage where available)
 - Event noise audit (reduce false alarms → improves customer trust)
### Monthly
 - Firmware baseline review
 - Integration key rotation review
 - Capacity planning review (especially video products)
 Customer experience tactic: Reduce "notification fatigue". Over-notification creates churn. Use bundling, quiet hours, and threshold discipline.

## 8.8 Corrective Maintenance: Offline Units Triage (Do This First)  ̄
Rule (H3). Offline triage MUST follow a structured root-cause drill-down.
### Step-by-step offline triage
1. Confirm scope
 - Single unit? One account? Entire region? Entire product?
2. Check last known heartbeat
 - Timestamp + last known location
3. Check SIM status
 - Bundle expiry, suspension, roaming, APN mismatch
4. Check power integrity
 - Especially after vehicle battery work, fuse replacement, or tampering
5. Check device health
 - Firmware crash loops, memory issues (vendor dependent)
6. Check pipeline health
 - Ingestion healthy? Kafka lag? Redis?
7. Escalate using SLA targets
 - If field action required, schedule per product install/repair targets
### Target install/repair times (Field Governance)
The escalation SOP defines expected install/repair timelines across product lines—for example, Oliwa install ~3 hrs, repair ~2 hrs; MDVR install ~8 hrs, repair ~3 hrs; Piki install ~3 hrs, repair ~2 hrs; Thermo install ~2 hrs, repair ~1 hr.
✅ Corrective principle: If the unit is offline and the root cause is unknown after 30 minutes of remote checks, stop guessing and trigger the appropriate escalation path.

## 8.9 AI + HIC in Connectivity (How to Use It Without Losing Control) ✈
NAVAS policy defines Waswa AI as proactive (load prediction + leakage detection) and explicitly ties it to command/control operations.
Approved AI use (H3). Waswa AI is a diagnostic assistant; you remain accountable.
### Approved admin prompts (copy/paste)
1. "Show me top 30 units by data consumption this week and likely cause categories (interval, video, roaming, firmware loop)."
2. "Identify accounts with rising offline events in the last 72 hours—correlate by operator and region."
3. "Recommend interval policy adjustments for PIKI in rural zones without breaking trip integrity."
### HIC gating (Mandatory)
Waswa AI MAY propose actions, but the admin MUST approve before:
 - Mass interval policy changes
 - Bulk firmware rollouts
 - SIM suspension/reactivation
 - Enabling/disabling video streaming
 - Any action that affects billing/tokens

## — PAGE BREAK —
# 9. ASSET & RESOURCE GOVERNANCE

Purpose
This section defines the operational governance for multi-tenancy, dealer delegation, RBAC, and auditability. In NAVAS, governance is not bureaucracy—it is how you scale across Uganda & Kenya without revenue leakage, security breaches, or account chaos. ✅
NAVAS explicitly adopts a hierarchical structure aligned to Wialon-like service organization: top account, account with dealer rights, and account without dealer rights.

## 9.1 Account Types and What They Are Allowed to Do
Account types (H3). System administrators MUST apply the correct account type for the correct business role.
### Top Account
 - Exists at activation and is reserved for the service owner.
 - Has special features such as:
 - creating billing plans
 - adding/configuring apps
 - restoring deleted objects from trash
 - Cannot create units.
✅ Directive: Access to the top account MUST be restricted. Do not operationalize daily customer work from the top account.
### Account with Dealer Rights
 - Can create and manage subordinate accounts.
 - Can control payments and rights (delegation layer).
 - It is not recommended to create units here.
✅ Directive: Use dealer accounts as governance + distribution layers, not as operational tracking containers.
### Account Without Dealer Rights
 - Cannot create subordinate accounts.
 - Can create users and assign object access.
 - Can create units (and this is where most client assets should live).
✅ Directive: Every client SHOULD have a separate account (standard enterprise multi-tenancy practice).

## 9.2 Hierarchy Configuration Rules (DO NOT VIOLATE)
Hierarchy principles (H3). These are design rules, not suggestions.
NAVAS/Wialon-style hierarchy configuration includes critical constraints:
1. A subordinate account cannot have more rights/features than its parent.
2. Objects created in a subordinate account inherit access to users defined as creators in the vertical hierarchy.
3. Keep hierarchy depth minimal unless necessary—excess depth slows down the system.
✅ Minimum recommended hierarchy
 - Level 1: Top Account
 - Level 2: Dealer Rights Account
 - Level 3: Client Accounts (No Dealer Rights)

## 9.3 Account Lifecycle: Create, Configure, Operate ✅
Rule (H3). New accounts MUST follow a consistent provisioning lifecycle to prevent future support debt.
### Step 1 — Create Account
1. Account name convention:
 - COUNTRY - CLIENTNAME - SEGMENT
 Example: UG - ACME LOGISTICS - ENTERPRISE
2. Set:
 - Country / currency
 - Timezone (EAT)
 - Contact channels (email + WhatsApp recommended)
### Step 2 — Assign Commercial Policy
 - Assign billing plan/token policy appropriate to product scope.
 - Confirm token enforcement boundaries (what is included vs premium).
 - Ensure mobile money rails exist where required (UG: MTN/Airtel; KE: M‐Pesa). NAVAS explicitly integrates mobile money into monetization strategy.
### Step 3 — Create Resources
Minimum resources per client:
 - Geofence library (depots, customer sites, borders)
 - POI library
 - Notification templates
 - Report templates
 - Driver directory (where applicable)
 - Maintenance templates (fuel, service intervals, camera health)
### Step 4 — Create Users & Role Assignments
 - Create users by job function.
 - Enforce least privilege.
 - Activate 2FA where supported.

## 9.4 RBAC Design: Role Matrix You MUST Implement
Principle (H3). RBAC is your strongest tool against security incidents and revenue leakage.
Table formatting note: 100% width, header shaded #F5F5F5, no borders
| Role | Intended User | Allowed Scope | Prohibited Actions (Examples) |
| SYSTEM\\_ADMIN | 3D platform admin | All tenants | Cannot bypass audit; cannot share top account |
| DEALER\\_ADMIN | Dealer ops lead | Dealer + sub-accounts | Cannot change platform-level billing templates |
| ORG\\_ADMIN | Client admin | Single client account | Cannot create subordinate accounts |
| OPS\\_DISPATCH | Fleet dispatcher | Units + routes | Cannot edit billing/tokens |
| FINANCE\\_ADMIN | Client finance | Invoices + payments | Cannot delete units or change device configs |
| SUPPORT\\_AGENT | Helpdesk | View + limited edits | Cannot mass-change settings without HIC |
| READ\\_ONLY\\_AUDIT | Internal audit | Read-only | No editing, no export without approval |

 AI governance tactic: Automate periodic access reviews. The AI backlog includes governance automation (access reviews + change logs) to reduce permission drift.

## 9.5 Human-in-Control Operations (Wialon-Style "Act on Behalf") ✈
Rule (H3). Impersonation/act-on-behalf MUST be auditable and justified.
### When to use "Act on behalf of"
 - Customer cannot access menus due to permissions misconfiguration
 - You must reproduce a UI/permission issue exactly
 - You are performing guided troubleshooting during a live support session
### Mandatory control steps
1. Select user to impersonate
2. Record:
 - Ticket ID / reason / expected change
3. Time-box the session (auto logout recommended)
4. Execute minimal required change
5. Exit impersonation and document resolution
✅ Policy: Any impersonation session MUST leave an audit trace in PostgreSQL audit trails (NAVAS architecture explicitly stores audit and RBAC in PostgreSQL).

## 9.6 Audit Logs and Change Tracking (Your Legal Shield)
Non-negotiable (H3). Every high-impact change MUST be attributable.
### You MUST audit
 - Role changes
 - Billing/token policy changes
 - Integrations enabled/disabled
 - Unit transfers between accounts
 - Restore from trash
 - Export of sensitive datasets
 - AI action approvals (HIC approvals)
### Audit review cadence
 - Weekly: high-impact changes review (top 20)
 - Monthly: full governance review (sampling)
 - Quarterly: compliance pack (if ISO/QMS)

## 9.7 Trash & Restore: The Safety Net ✅
Top account has the special ability to restore deleted objects from trash.
Rule (H3). Deletion MUST be reversible unless legally required otherwise.
### Operational directive
 - Use Archive → Trash patterns for client objects (units, resources) rather than destructive deletion.
 - Restoration MUST be executed by authorized admins only (typically top account privileges).

## 9.8 Preventative Maintenance: Governance Hygiene (Stops Chaos Early)
### Weekly
 - Identify dormant users (no logins) → disable
 - Remove permissions no longer needed
 - Verify finance roles still correct
### Monthly
 - Confirm dealer hierarchy integrity
 - Verify no "units in dealer account" anti-patterns
 - Run a permission drift scan (AI-assisted if available)
✅ Outcome: Fewer "customer can't see unit", fewer accidental deletions, fewer billing disputes.

## — PAGE BREAK —
# 10. TELEMATICS & GIS OPS

Purpose
This section defines how administrators govern the operational telematics layer: units, sensors, geofences, events, notifications, and safety triggers across all products (OLIWA/PIKI/MAFUTA/DASHCAM/THERMO/etc.).
NAVAS supports broad event-trigger coverage, including safety (fatigue, seatbelt), security (panic, intrusion), fuel events (drop/refill), maintenance triggers (engine hours), and environmental triggers (temperature/humidity deviation).
Admin stance (H3). Events are not "features". Events are operational contracts with the customer. Misconfigured events create churn.
*(Continuation of Section 10 will proceed next: units & groups governance → geofence libraries → notification routing (SMS/WhatsApp/email) → preventive/corrective maintenance triggers → product-specific event packs.)*

### Reference Files Used (for your internal documentation pack)
# INCIDENT MANAGEMENT, ESCALATION & SLA GOVERNANCE

Purpose. This section defines the mandatory operational protocol for handling incidents, service requests, and escalations within NAVAS CMS for 3D Services Limited (Uganda & Kenya). The objective is non‐negotiable: reduce MTTR, enforce consistent customer communication, and protect revenue + reputation through disciplined execution. ✅
Strategic Takeaway
Every "small fault" in telematics (GPS, GSM, power, fitment quality, user training) becomes customer churn if you allow slow response and unclear ownership. Your CMS discipline is the difference between "tracking vendor" and "revenue governance partner."

## Module Map (Where This Lives In CMS)
Where you operate. In NAVAS CMS, incident work is executed across the following blades/cards (names may vary by tenant branding, but the structure is mandatory):
1. Helpdesk & Ticketing Blade
 - Cards: *New Ticket*, *Queue*, *Assigned to Me*, *Escalations*, *SLA Breaches*, *Closed – QA Pending*
2. System Health / Alarm Center Blade
 - Cards: *No Data*, *GNSS Drift*, *Device Power Loss*, *SIM/Data Issues*, *Camera Offline*, *Fuel Sensor Anomalies*
3. Device & Connectivity Blade (SIM Console)
 - Cards: *ICCID Lookup*, *Data Usage*, *Roaming Risk*, *Coverage*, *APN Config*, *Last Session*
4. Audit & Governance Blade
 - Cards: *Change Log*, *HIC Approvals*, *Access Reviews*, *Billing Holds/Suspensions*
5. Waswa AI Console (when enabled)
 - Cards: *Triage Suggestions*, *Root Cause Guess*, *Auto‐draft Customer Update*, *Evidence Pack Builder*

## Operating Hours, Channels & Response Targets
Support hours. The official standard business hours are 08:30–17:30 EAT, Monday to Saturday, excluding Ugandan public holidays; on‐call support exists for Sundays and public holidays. Routine matters SHALL be raised by email; urgent matters SHOULD be raised by phone and MUST be backed by an email containing the full evidence pack. ✅
### Channel Response Time Targets
You SHALL enforce the following response targets.
| Channel | Target Response Time | Mandatory Rule |
| Phone (Standard Hours) | 15 minutes | Must acknowledge + open ticket |
| Phone (After Hours) | 60 minutes | Must acknowledge + confirm severity |
| Email (Standard Hours) | 2 hours | Must acknowledge + ticket \\# |
| Email (After Hours) | Next business day | Must acknowledge + next steps |
| WhatsApp | 5 minutes | Must send scripted first actions |
| Walk‐in | Immediately | Must open ticket + assign owner |
| On‐site | 3–8 hours (product‐dependent) | Must dispatch with RACI owner |
| | | |

Tactic
WhatsApp is your fastest de‐escalation tool in UG/KE. Use it for acknowledgement + first actions, not for long diagnostics. Keep the detailed trail inside the ticket.

## Mandatory Intake Standard (Evidence Pack)
Non‐negotiable. No ticket is "valid" until it has the evidence required to prevent back‐and‐forth. Your intake must capture:
1. Account/Tenant identifiers
 - Top account / dealer / client account name (and country)
2. Asset identifiers
 - Unit name, registration, IMEI/serial, tracker model, camera/MDVR model (if applicable)
3. Connectivity
 - SIM ICCID, telco (MTN/Airtel/Safaricom), APN profile, last data timestamp
4. Last known telemetry
 - Last position time, last ignition state, last voltage, satellite count (if available)
5. User context
 - "What changed?" (battery removed, vehicle went upcountry, device swapped, service due, accident)
6. Steps already done
 - Power cycle, visual wiring check, fuse check, device health check, SIM reseat, antenna check
7. Impact statement
 - Number of affected units, safety risk, revenue impact, customer criticality (VIP / enterprise / public sector)
HIC policy. If the ticket requires any "irreversible" or high‐impact action (e.g., immobilization, service suspension, token policy override, firmware push), the ticket MUST be flagged HIC REQUIRED before execution. ✅

## Severity & Prioritization (P1–P4) — Required Classification
You SHALL classify every ticket. Use this severity system for consistent operations:
1. P1 – Critical (Safety / Security / Major Outage) ⚠
 - Examples: crash event + emergency response; camera evidence required; immobilization failure; region‐wide outage
 - Response: immediate acknowledgement; escalation rules apply; frequent customer updates
2. P2 – High (Business Impact / Multi‐asset degradation)
 - Examples: multiple units "no data"; fuel theft suspected; MDVR offline for high‐risk fleet
3. P3 – Medium (Single asset issue / degraded feature)
 - Examples: GPS drift; intermittent GSM; missing trips; sensor calibration drift
4. P4 – Low (How‐to / access / training / minor config)
 - Examples: report customization; user permissions; dashboard tweaks
Trainer note. Seasoned telematics admins already know: severity is not "emotion"—it's a strict function of impact × urgency × risk.

## MTTR Governance (Targets You MUST Track)
The escalation standard defines MTTR as a core reliability metric and introduces specific operational parameters and targets. ✅
### MTTR Parameters & Targets
| Metric | Definition | Target | How CMS Enforces It |
| RTRS | Response time to reach site | 50km: 1hr / \\<100km: 2hr / \\>110km: 24hrs | Dispatch SLA timers + geo distance |
| FCR | First Contact Resolution | ≤30 mins | L1 scripts + remote diagnostics checklist |
| MRT | Mean Resolution Time | ≤24 hours | Escalation timers + owner enforcement |
| TVTB | Ticket Volume vs Backlog | Reduce backlog 10% weekly | Queue dashboard + WIP limits |
| ER | Escalation Rate | Keep \\<10% | Improve remote capability + training |
| ART | Average Response Time | ≤15 mins | Auto-ack + WhatsApp macros |
| | | | |

Tactic
If your ER (Escalation Rate) is above 10%, don't hire more field techs first—fix L1 capability: better macros, better remote diagnostics, better SIM/data correlation, and stronger SOP enforcement.

## Departmental Task Matrix (RACI) — Execution Discipline
RACI is mandatory. The escalation work instruction defines time‐bound ownership across the lifecycle (Sales → Service Delivery → Support). Your CMS workflow MUST map tasks to accountable and responsible roles, not "who is available." ✅
### Key Time‐Bound Responsibilities
1. Job Confirmation & Invoicing
 - Trigger: immediately after LPO/payment confirmation
2. Device Type Assignments (Helpdesk → Install)
 - Trigger: immediately after LPO/payment confirmation
3. Device Approval
 - Target: within 10 minutes of receiving request email
4. Job Allocation & Ticketing
 - Target: within 15 minutes of request receipt
5. Hardware Allocation
 - Target: within 10 minutes upon request
6. Device Sign‐out & Testing
 - Target: within 30 minutes after receiving ticket
7. Job Execution Communication
 - Target: within 10 minutes after ticket creation
8. Job Closure Review
 - Target: within 12 hours after job completion
9. Job Completion Communication
 - Trigger: as soon as System Admin confirms unit online

## Hardware Install & Repair Targets (By Product Line)
These targets are enforceable. Use them to plan dispatch and to judge SLA compliance. ✅
Rule ✅
Any job that exceeds target time MUST produce a closure note explaining: (a) root cause category, (b) blocking factor, (c) prevention action.
### Target Time To Install vs Time To Repair
| Service Type | Product | Install Target | Repair Target |
| AI & Video Telematics | Dash AI | 4.5 hrs | 3 hrs |
| AI & Video Telematics | Dashcam | 4 hrs | 3 hrs |
| AI & Video Telematics | MDVR | 8 hrs | 3 hrs |
| AI & Video Telematics | MDVR AI | 8 hrs | 3 hrs |
| Vehicle Telematics | iVMS | 3 hrs | 2 hrs |
| Vehicle Telematics | iVMS‐Plus | 4 hrs | 3 hrs |
| Vehicle Telematics | Oliwa | 3 hrs | 2 hrs |
| Vehicle Telematics | Oliwa‐Plus | 4 hrs | 3 hrs |
| Fuel Telematics | Mafuta FLS | 8 hrs | 3 hrs (recalibration: 8 hrs) |
| Fuel Telematics | Mafuta CANBus | 4 hrs | 3 hrs |
| Fuel Telematics | Mafuta Flow Meter | 3 hrs | 2 hrs |
| Personnel Tracing | Capo | 1 hr | 30 mins |
| Personnel Tracing | Piki | 3 hrs | 2 hrs |
| Personnel Tracing | Toto | 1 hr | 30 mins |
| Personnel Tracing | Wiatag | 1 hr | 30 mins |
| Personnel Tracing | Patrol | 4 hrs | 2 hrs |
| Goods‐in‐Transit & IoT | Genset | 8 hrs | 3 hrs (recalibration: 8 hrs) |
| Goods‐in‐Transit & IoT | Kago | 4 hrs | 3 hrs |
| Goods‐in‐Transit & IoT | Thermo | 2 hrs | 1 hr |
| Goods‐in‐Transit & IoT | Paso | 1 hr | 1 hr |
| Goods‐in‐Transit & IoT | Pawa | 4 hrs | 3 hrs |
| | | | |

## Standard Lead Times (Delivery & Activation)
Expectation management is a customer‐experience weapon. Standard service delivery lead times are defined by service type and MUST be communicated during onboarding and whenever new hardware is ordered. ✅
| Service Type | Standard Lead Time |
| AI & Video Telematics | 21 business days |
| Personnel Tracing | 21 business days |
| Vehicle Telematics | 21 business days |
| Fuel Telematics | 21 business days |
| Goods & IoT | 21 business days |
| Value Added Services | 21 business days |
| Add‐On Apps | 3 business days |
| | |

## Sales Quote Turnaround Targets (Critical for Trust)
Sales turnaround is part of system administration governance because delays trigger rushed provisioning, bad device matching, and poor SLA outcomes.
All major service types have a 60‐minute quote turnaround target. ✅

## Upstream Vendor Escalation (When You Must Go External)
Rule ✅ You escalate upstream only after you attach evidence and after you confirm the issue is not due to:
 - local SIM/data bundle gaps,
 - installation workmanship,
 - APN/profile misconfiguration,
 - power/battery disconnection,
 - device tampering,
 - or user error.
Upstream support touchpoints exist for key suppliers (software + hardware). ✅
Operational directive. In CMS, the upstream escalation MUST be recorded as:
1. Linked ticket ID
2. Vendor case ID
3. Vendor SLA timer
4. Customer update schedule
5. Temporary mitigation (workaround)

## Root Cause Taxonomy (Use This to Stop Repeat Incidents)
You SHALL classify closure root cause using this taxonomy. It is based on known causes of poor service in telematics operations. ✅
1. GPS / GNSS
 - Loss of GPS signal; antenna faults; vehicle in underground parking
2. GSM / GPRS / Data Bundle
 - No carrier signal; SIM faulty; telecom downtime; no bundle; loose SIM
3. Power (12/24V)
 - Battery removed; wiring harness loose; backup battery failure
4. Device Quality / Environment
 - Vibration, heat, dust, moisture, voltage surges
5. Fitment Workmanship
 - Poor wiring; short circuits; drain battery; broken dashboards
6. Software/Platform
 - Feature gaps; slow system; no upgrades
7. Server/Uptime/Security
 - Poor hosting choice; lack of backup power; IT security weakness
8. Customer Service / SLA
 - Slow repair cycle; unclear response time; poor escalation discipline
9. User Training
 - Incompetent users; misuse of assets; lack of awareness
Corrective Maintenance Note
"Fixing the device" without fixing the root cause (bundle policy, install workmanship, access governance) guarantees recurrence. Every closure MUST include prevention action.

## Waswa AI + HIC in Incident Management (How to Use It Properly)
AI is a force multiplier, not a decision maker. NAVAS is positioned as a command & control cockpit with AI co‐pilot capabilities that identify load and revenue leakage, while enforcing strict operational KPIs like MTTR. ✅
### What Waswa AI MAY Do
1. Suggest triage category and probable root cause (GPS/GSM/power/software)
2. Propose customer response drafts (clear expectations; next steps)
3. Compile an evidence pack (device last seen, SIM state, historical uptime trend)
4. Recommend macro steps for L1 resolution (reduce FCR time)
### What Waswa AI MUST NOT Do Without Human Approval (HIC)
1. Suspend service or block tenant access
2. Change token pricing or billing plan
3. Push firmware at scale
4. Enable/disable mission‐critical add‐on apps
5. Trigger immobilization workflows
HIC enforcement pattern. "Suggestions appear for approval with citations" and high‐impact actions (e.g., suspensions) require explicit approval and must be audit‐logged. ✅

## Customer Experience Tactics (UG/KE Reality)
You SHALL execute these tactics to reduce churn and follow‐ups.
1. Acknowledge fast, fix later ✅
 - Acknowledgement within channel target times is mandatory.
2. Communicate in timestamps
 - Provide next update time (e.g., "Next update at 14:00 EAT").
3. Use WhatsApp for first actions
 - Use templates for: *"No Data – quick checks"*, *"Power loss – fuse/battery check"*, *"Fuel sensor – recalibration steps"*.
4. Always close with prevention
 - Example: "Bundle policy updated; SIM seating SOP reinforced; installer retrained."
AI assist. A customer support copilot approach is specifically designed to: capture omnichannel requests, dedupe contacts, create tickets with SLA/priority, auto‐ack with ticket # and ETA, and improve MTTR/CSAT. ✅

⎯⎯⎯ PAGE BREAK ⎯⎯⎯
# ADD‐ON APPS LIBRARY & PROVISIONING (TENANT ENABLEMENT)

Purpose. This section provides the operational method for provisioning Add‐On Apps and modules across tenants (UG/KE dealers, sub‐dealers, and client accounts). You will use this module to manage catalog, enablement, dependencies, billing tokens, payment rails, and audit evidence in one controlled workflow. ✅
Strategic Takeaway
Add‐On Apps are not "features." They are governed products. Provisioning without dependency checks + token rules + audit trail is the fastest path to revenue leakage and support overload.

## How the Screen is Structured (Blades, Cards, Drawer)
Workspace pattern. The Add‐On Apps Library is built as:
1. Catalog Workspace (Main)
 - Table columns: App, Category, Enabled, DAU/WAU, Revenue, Deps, Health, Actions
2. Standard Strip (Top)
 - Tenant selector + RBAC badge + token details + system health
3. Right Drawer (Provisioning Blade)
 - Tabs: Overview, Enablement, Billing Tokens, Payments, Audit Trail
 - "HITL Required" label for sensitive actions

## Concept Model: What is an Add‐On App in NAVAS?
Definition. An Add‐On App is a licensed capability package enabled per tenant or per client, aligned to 3D's product portfolio. In 3D terms, examples include:
 - BI Dashboards (analytics layer)
 - DSC / ECO (driver safety + eco scoring)
 - FleetRun / Logistics / JMS (operations)
 - Inspecta (inspection & job card workflows)
 - Nimbus (cloud services, automation)
 - VEBA (marketplace governance module)
Governance rule. Add‐Ons MUST only be enabled through the provisioning flow, not "by request in WhatsApp." Your CMS is the system of record. ✅

## Account Hierarchy & Who Can Provision What
Authority model. NAVAS follows an account hierarchy similar to enterprise telematics management systems:
1. Top Account
 - Can create billing plans, configure apps, restore deleted objects (trash).
2. Dealer Account
 - Can create/manage subordinate accounts and control payments (where permitted).
3. Standard Account
 - Manages users and assets within its own scope.
Non‐negotiable. Provisioning rights MUST be restricted by RBAC and recorded in the audit log.

## Provisioning Workflow (Step‐by‐Step)
This is the exact operational sequence you MUST follow. ✅
### Step 1 — Select the Tenant Scope
1. In the Standard Strip, choose:
 - Top account / Dealer / Sub‐dealer / Client account
2. Confirm RBAC badge shows you have the provisioning permission set.
3. Confirm token wallet balance is sufficient if the add‐on burns tokens at activation (policy dependent).

### Step 2 — Locate the App
1. Use catalog filters (product, status, country)
2. Search by:
 - App name
 - Dependency (e.g., "Camera", "Maps", "Payments")
 - Tenant adoption

### Step 3 — Open Actions → Provision
1. In the table row (App), use Actions (⋮)
2. Select Provision App
3. Right Drawer opens with:
 - App identity
 - "HITL Required" flag (if sensitive)
 - Provisioning tabs

### Step 4 — Enablement & Dependency Checks (Enablement Tab)
This is where you prevent chaos. ⚠
The provisioning drawer supports enablement toggles and dependency checks. Example controls include:
 - Enable app for tenant
 - Require KYC for owners
 - Enable Leakage Shield (AI)
 - Require Telematics Unit Linked
 - Allow Cash Trips (Trusted only)
Hard rule. Dependencies MUST be validated before activation:
 - Hardware present (tracker/camera/sensor)
 - Connectivity policy met (SIM bundle + APN)
 - Payments rail ready (where required)
 - User roles mapped (who can do what)

### Step 5 — Billing Tokens (Billing Tokens Tab)
Principle. NAVAS is built for PAYG governance and tokenized billing. When configuring Billing Tokens for an app, you SHALL define:
1. Metered events/parameters (what burns tokens)
2. Thresholds (avoid false burns)
3. Fair use and rate limits
4. Free trial rules (trial → paid conversion governance)
5. HIC approval requirement for pricing exceptions
Why this matters. Tokenization is a core platform design for aligning costs with usage (and preventing subscription leakage). ✅

### Step 6 — Payments (Payments Tab)
EA reality. Payments must support mobile money rails as a first‐class capability. ✅
In the drawer, Payments rails can be configured and tested; example rails include:
 - M‐Pesa
 - MTN MoMo
 - Airtel Money
 - Cards (Pesapal/DPO)
Operational directive. If Payments are required for the app:
 - Do not enable production access until:
 - settlement path is tested,
 - webhook/callback status is confirmed,
 - reconciliation is mapped to Finance workflow.

### Step 7 — Audit Trail (Audit Trail Tab)
Non‐negotiable. Every provisioning event MUST record:
1. Who enabled the app (user + role)
2. Tenant scope
3. Settings changed (before/after snapshot)
4. Effective date/time
5. HIC approver (if required)
6. Related ticket/change request ID

### Step 8 — Save & Apply
1. Click Save & Apply
2. Verify:
 - App status updated in table (Enabled/Trial/Disabled)
 - Health reflects expected state
 - Usage tracking starts within expected telemetry window

## HIC Controls in Provisioning (Where Humans MUST Stay in Control)
HITL/HIC flag is intentional. Provisioning screens explicitly label when "HITL Required." This MUST be enforced for:
1. VEBA governance (marketplace risk)
2. Payment rail activation
3. Token policy overrides
4. Fraud/leakage controls that may affect user experience
RACI reinforcement. Human roles remain in the loop for approvals, closure QA, finance suspensions, dispatch rules, and compliance gates. ✅

## Waswa AI in the Add‐On Apps Library (Practical Use)
Use AI for recommendations, not authority. The UI pattern includes a Waswa AI widget that can highlight:
 - Leakage risk in certain tenants
 - Enabled but unused apps (wasted cost / wasted complexity)
 - Trial → paid nudges via WhatsApp templates
### Your Mandatory AI Operating Pattern
1. Ask AI for insight (e.g., "Which tenants have VEBA leakage risk?")
2. AI produces a suggestion
3. Human validates against:
 - audit log
 - payment reconciliation
 - client operational reality
4. Human approves or rejects (HIC log recorded)

⎯⎯⎯ PAGE BREAK ⎯⎯⎯
# ALERTS, NOTIFICATIONS & AUTOMATION ORCHESTRATION

Purpose. Alerts are how NAVAS transitions from "passive tracking" to proactive governance. This section defines how you SHALL configure alerts/alarms, route them across channels (SMS/Email/WhatsApp/UI), prevent alert fatigue, and convert alerts into tickets + actions. ✅

## Event Trigger Catalog (What You Can Automate)
NAVAS supports a broad catalog of event triggers across safety, security, maintenance, driver behavior, fuel, environmental sensors, and cargo monitoring. Examples include:
 - Driver fatigue/distraction, phone use, seatbelt, lane departure, forward collision warning
 - Fuel drop/refill, rapid fuel consumption, low fuel
 - Engine DTC fault codes, service due (time/mileage), low fluid levels
 - Door open/unauthorized access, cargo intrusion, trailer detachment
 - Temperature deviation, humidity deviation, air quality alerts (cargo specific)
 - Panic button, impact/crash detection, rollover detection, man‐down detection
 - Geofence entry/exit/breach, border exit, route deviation
Key Takeaway
Your job is not to "turn on all alerts." Your job is to build an alert program: fewer alerts, higher signal, better response.

## Channel Strategy (UG/KE Best Practice)
Rule ✅ Use channels according to severity and customer maturity:
1. WhatsApp
 - Best for immediate acknowledgement and first actions (fastest in practice)
2. SMS
 - Use when data is unreliable or user is offline
3. Email
 - Use for formal logs, reports, compliance, escalations
4. In‐App / CMS Pop‐ups
 - Use for operations teams monitoring live assets
NAVAS explicitly supports multi‐channel event alerts including WhatsApp. ✅

## Alert Design Standard (How to Build Alerts That Don't Backfire)
Every alert MUST define:
1. Trigger (parameter + threshold + debounce)
2. Severity (P1–P4 alignment)
3. Recipients (who gets it first; who gets escalations)
4. Channels (WhatsApp/SMS/Email/UI)
5. Suppression rules (avoid duplicate spam)
6. Action hooks (create ticket, open job card, request confirmation, trigger AI analysis)

## Product‐Aligned Alert Packs (Mandatory Defaults)
You SHALL deploy product‐specific "starter packs" (then tune per client).
1. DASH AI / DASHCAM / MDVR / MDVR AI (Video + Safety)
 - FCW, LDW, harsh braking, distraction, seatbelt, fatigue
2. MAFUTA (Fuel Telematics)
 - fuel drop, refill, rapid consumption, low fuel, calibration drift
3. THERMO (Cold Chain)
 - temperature deviation, humidity deviation, door open at wrong time
4. KAGO / PASO (Goods in Transit)
 - cargo intrusion, trailer detachment, route deviation, geofence breach
5. PATROL / CAPO / WIATAG (Personnel)
 - man‐down, panic, geofence breach
6. OLIWA / iVMS (Vehicle Tracking)
 - overspeed, towing detection, power cut, unauthorized movement

## AI + HIC in Alerts (False Positives Are a Business Risk)
AI role. AI may recommend thresholds (e.g., overspeed limits by route type, fuel drop thresholds by tank capacity), but:
 - Immobilization triggers MUST always be HIC‐approved
 - Fraud/leakage flags MUST require evidence before enforcement
 - Customer‐facing "accusation alerts" MUST be phrased neutrally until verified
Why. High‐trust operations reduce escalations and improve MTTR/CSAT by guiding correct first actions through templated instructions. ✅

## Preventive Maintenance Notes (Tie Alerts to Maintenance)
Mandatory link. Maintenance alerts MUST create a maintenance record or job card to avoid "alert with no follow‐through."
 - Engine hours reached for service
 - Preventative maintenance (mileage/time based)
 - Tire pressure low/high
 - Brake system warning, fluid level low

## Minimum Automation Set (Recommended)
Implement these automations first for immediate operational wins:
1. Auto‐ticket creation from:
 - No‐data > X minutes (per client profile)
 - Camera offline > X minutes (MDVR/Dashcam)
 - Fuel drop above threshold (Mafuta)
2. Auto‐acknowledgement with ticket # and ETA
3. Auto‐routing to the correct queue (L1 / Analyst / Field)
4. Auto‐status updates at milestones
5. Weekly digest to key client stakeholders (ops + CFO)
These patterns are directly aligned to the AI customer service user stories for omnichannel intake, ticket creation, SLA routing, and proactive updates. ✅

## Referenced Project Artefacts (Internal)
(Use these as internal governance anchors while maintaining your CMS as the system of record.)
 - Incident escalation process + MTTR targets:
 - NAVAS policy v26 (cockpit, tokenization, AI co‐pilot):
 - Alerts & triggers library:
 - AI agent strategy + HITL/HIC roles:
 - Add‐On Apps Library UI + provisioning drawer patterns:

According to a document from 20 February 2026, NAVAS is operated as a monetizable, hardware‐agnostic IoT platform with token burn, mobile money rails, RBAC + multi‐tenancy, and a Waswa AI co‐pilot that must remain auditable and human‐governed.

# CONTINUATION — PART II (DEEP‐DIVE OPERATIONS PLAYBOOK)

Landscape & Page Break Rule (Mandatory): This continuation is structured with explicit PAGE BREAK markers. Keep them when pasting into Google Docs.

## Part II Mini Table of Contents
1. 17. Apps Library & Provisioning (Portals, Add‐Ons, Entitlements, Dependencies)
2. 18. Notification Factory (Event Triggers, Templates, Channels, Escalations)
3. 19. Reporting & BI Dashboards (Exports, KPI Governance, BI Packs)
4. 20. Video Telematics Governance (DASHCAM, DASH AI, MDVR, MDVR AI)
5. 21. Fuel Telematics Governance (MAFUTA + GENSET) ⛽
6. 22. Personnel Tracing Governance (PIKI, PATROL, CAPO, TOTO, WIATAG) 1⁄4
7. 23. Goods‐in‐Transit & IoT Governance (KAGO, PASO, PAWA, THERMO)
8. Appendix Z (Continuation) Acronyms & Abbreviations (Additions)

--- PAGE BREAK ---
# 17. APPS LIBRARY & PROVISIONING — APP CATALOG, ENTITLEMENTS & DEPENDENCIES

## 17.1 Purpose
The Apps Library & Provisioning module is the commercial + operational control plane for enabling NAVAS portals, add‐on apps, and value‐added capabilities per tenant, while enforcing:
1. Governance (RBAC + maker‐checker) ✅
2. Dependency integrity (no half‐enabled services) ⚠
3. Token & payment correctness (no revenue leakage)
4. Auditability (who did what, when, and why) 3⁄4
This module implements the "service owner / dealer / client" mental model aligned with management systems like Wialon CMS Manager (top user + dealer rights managing macro‐objects). ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system))
## 17.2 Operating Principle (Non‐Negotiable)
You SHALL treat App Provisioning as a controlled change.
If a change can alter customer visibility, billing, or risk posture, it MUST be performed via:
1. Proposal (Waswa AI / operator initiates)
2. Human validation (HIC / maker‐checker) ✈
3. Apply + log (system commits) 3⁄4
4. Post‐change verification (smoke checks + telemetry sanity) ✅
This aligns with the AI/HITL doctrine: irreversible actions must be human‐approved and auditable. 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L48-L50】
## 17.3 Where This Lives iS → Administration → Apps Library
 - CMS → Tenant → Apps & Entitlements
 - CMS → Billing → Tokens → App Token Policies
 - CMS → Payments → Rails & Callbacks
## 17.4 UX Pattern: Table + Row Actions + Right Blade (Drawer)
This module is designed to be table‐first and blade‐driven:
 - Table columns typically include: App, Category, Enabled, DAU/WAU, Revenue, Dependencies, Health, Actions. 【459:4†CMS Mockup Redesign Request.txt†L10-L21】
 - Row actions open a Rig such as:
 - Overview
 - Enablement
 - Billing Tokens
 - Payments
 - Audit Trail 【459:10†CMS Mockup Redesign Request.txt†L11-L18】
HIC enforcement is exp Required" for high‐risk operations. 【459:8†CMS Mockup Redesign Request.txt†L19-L27】
### Blade Standard.ent and use these tabs in this order:
1. Overview. Business intent, dependencies, risk rating, last changed by.
2. Enablement. Toggle entitlements, enforce pre‐checks (KYC, device link, etc.).
3. Billing Tokens. Token class, burn rules, caps, bundles, grace thresholds.
4. Payments. Mobile money rails, pay links, callback validation.
5. Audit Trail. Immutable change log + approvals + rollback references.
## 17.5 CMS Data Objects (Admin Mental Model)
In provisioning, treat the system as these objects:
1. App Catalog Item (global definition)
 - Name, category, dependencies, supported products, billing mode.
2. Tenant Entitlement
 - Enabled status (Yes/Trial/No), effective dates, environment constraints.
3. Dependency Graph
 - GPS unit required, camera required, payment required, KYC required.
4. Token Policy
 - Token class mapping, burn rules, caps, discounts (bundle logic).
5. Payment Rail
 - M‐Pesa / MTN / Airtel mapping, callback secrets, settlement rules.
6. Audit Event
 - Who changed what, approvals, and rollback pointers.
This matches NAVAS's monetization posture: token engine + mobile money rails integrated into the telemetry heart. 【491:2† NAVAS IOT SYSTEM POLICY_ .pdf†L23-L29】【491:10† NAVAS IOT SYSTEM New App Catalog Item) ➕
Use this only when product leadership has approved a new capability (e.g., "Fraud Shield", "Route Optimizer", "BI Export Pro").
Procedure (must be followed):
1. Define:
 - App Name (official nomenclature)
 - Category (Video / Fuel / Marketplace / Safety / Reports / Integration)
2. Declare dependencies (hard + soft)
3. Assign default token policy
4. Assign activation gates
 - HITL required? (Yes for billing‐impacting changes)
5. Save → Submit for approval (maker‐checker)
### B) Read (Find & Diagnose)
You SHALL use filters to locate issues quickly:
 - Enabled status: Yes / Trial / No
 - Health: OK / Warn / Alarm
 - Revenue band: UGX/KES thresholds
 - Usage: DAU/WAU (adoption signals)
### C) Update (Provision to Tenant)
This is the most common admin action.
Standard flow:
1. Select the Tenant / Dealer / Org context in the blade (multi‐tenant selector). 【459:10†CMS Mockup Redesign Request.txt†L24-L28】
2. In Enablement, tog (if applicable)
 - Require Telematics Unit Linked
 - Enable leakage/AI shields (where applicable) 【459:8†CMS Mockup Redesign Request.txt†L36-L44】
3. Configure Billing Tokes
4. Configure Payments:
 - Payment rail activation and callback tests
5. Save & Apply
6. Execute Post‐Provision Smoke Tests (see 17.9)
### D) Delete (Archive → Trash)
Deletion is never hard‐delete.
Rule:
 - You MUST use Archive → Trash, with a restoration path.
 This mirrors management-system patterns where deleted macro‐objects are recoverable from trash. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system))
## 17.7 Mapping: 3D Product Portfolio → CMS Provisioning
Table styling instruction: set header row shade to #F5F5F5 and remove borders .
| Service Type | Product / App | Provisioning "Hard Dependencies" | Primary Admin Concern |
| Vehicle Telematics | OLIWA / OLIWA‐PLUS / GUVNA / iVMS / iVMS‐PLUS | GPS unit linked, map tiles, reporting enabled | Data continuity + geofence + token stability |
| Personnel Tracing | PIKI / PATROL / CAPO / TOTO / WIATAG | GPS/mobile identity, geofences, alert channels | Safety alerts + duty rules + privacy |
| Goods‐in‐Transit & IoT | KAGO / PASO / PAWA / THERMO | Sensor binding (temp/door/power), alert channels | Cold chain + intrusion + SLA |
| Fuel Telematics | MAFUTA (FLS/Flow/CANBUS/Fuel Card/Station) + GENSET | Sensor calibration + vehicle profile + report templates | Theft detection + false positives |
| AI & Video | DASHCAM / DASH AI / MDVR / MDVR AI | Camera device + storage + bandwidth policy | Evidence chain + cost control |
| Add‐On Apps | BI DASHBOARDS / DSC / ECO / FLEETRUN / INSPECTA / JMS / LOGISTICS / NIMBUS / VEBA | Base tracking + role rights + payment where needed | Adoption + upsell + integration |
| Value Added | Help Desk & Training / GIS & JMS / SATO / Local Server / OEM Integrations | Contracts + tenant roles + integration keys | Compliance + service quality |

NAVAS explicitly positions OLIWA, PIKI, VEBA, and PATROL as specialized portals under the umbrella platform. 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L15-L29】
## 17.8 Waswa AI Assist (Allowed) vs HIC Decision (Mandatory)
### ✅ Waswa AI MAY do:
 - Suggelag "enabled but unused >30 days" for cost control and adoption actions. 【459:8†CMS Mockup Redesign Request.txt†L1-L4】
 - Recommend trial→paid nudges via WhatsApp templates. 【459:8†CMS Mockup Redesign Request.txt†L1-L4】
 - ed without payment rail).
### ⚠ *Waswa AI MUST NOT dooken policies
1. Enabling payment rails
2. Suspending a tenant / disabling a core portal
3. Changing security‐relevant roles or access rights
This is consistent with "agent proposes; named role approves; action and rationale logged." 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L48-L50】
## 17.9 Post‐Provision Smoke Tests (You MUST run these) ✅
For each tenant/app enablement, execute:nly to intended roles
2. Telemetry binding
 - Unit/device linked and appears under correct tenant
<!-- end list -->
1. Alert path
 - Trigger a test event (or simulated rule) → verify WhatsApp/SMS/email routing
2. Token burn sanity
 - Verify token counters increment as expected (not 10×)
3. Payment top‐up (if applicable)
 - Sandbox top‐up callback validated
4. Audit trail exists
 - Change request + approval + operator identity logged
## 17.10 Preventative Maintenance Notes (Monthly)
You SHALL run a monthly entitlement and leakage audit:
 - List tenants with:
 1. Apps enabled but no usage (DAU/WAU = 0)
 2. Apps used heavily but not billed correctly
 3. Payment rails failing callbacks
 - Validate token FIFO logic is functioning (no hidden debt build‐up). 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L5-L6】

--- PAGE BREAK ---
# 18. NOTIFICATION FACTORY — EVENT TRIGGERS, TEMPLATES, CHANNELS & ESCALAns are where telematics becomes operational action. Your job is to convert:
 - Noisy events → actionable alerts
 - Human attention scarcity → controlled triage
This aligns with the operating thesis: telematics is "event‐rich but attention‐poor," therefore we prioritize deterministic interfaces, auditability, and reversible automations. 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L1-L5】
## 18.2 Event Taxonomy (Admin Standard)
You SHALL classify every trigger into:
1. Safety & Compli
2. Security (geofence breach, intrusion, unauthorized movement)
3. Asset Health (DTCs, battery health, service intervals)
4. Fuel & Cost (fuel drop, rapid consumption)
5. Cold Chain / Cargo (temp/humidity deviations, door open)
6. People Safety (man‐down, panic button, heart rate anomalies if deployed)
NAVAS explicitly targets configurable thresholds and multi‐channel delivery (push, email, SMS, WhatsApp). 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L6-L15】
## 18.3 Canonical Trigger Library (Use This as Your Baseline)
The NAVAS triggers:
 - Overspeeding, harsh acceleration/braking/cornering, excessive idling
 - Fuel drop, fuel level low, fuel refill, rapid fuel consumption
 - Geofence entry/exit, route deviation, country border exit
 - Driver distraction, driver fatigue, seatbelt unbuckled, phone use
 - Engine fault codes (DTCs), engine hours reached for service
 - Temperature deviation, humidity deviation, cargo intrusion, door open/close unauthorized
 - Panic button, man‐down, fall detection, impact detection 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L4-L91】
## 18.4 The Notification Rule Builder (Mandatory Fields)
Each notiS, sensor, video AI, mobile app, external API
2. Condition
 - Threshold + comparison + time window (e.g., speed > 80 km/h for 30 seconds)
<!-- end list -->
1. Scope
 - Vehicle(s), group(s), tenant(s), routes, geofences
2. Severity
 - Info / Warning / Alarm / Critical
3. Recipients
 - Driver, Fleet Manager, Ops Desk, Security Desk, Maintenance Desk
4. Delivery channels
 - In‐app + Email + SMS + WhatsApp + Webhook
5. Suppression rules
 - Quiet hours, deduplication, throttling
6. Escalation
 - If unacknowledged → escalate after X minutes
7. Audit
 - Creator, approver, last edit, change reason
## 18.5 Channel Governance (EA Market Reality) 2
NAVAS supports multi‐channel alerts including WhatsApp/SMS/email and requires reliability mechanisms. 【459:3†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L89-L96】
### 18.5.1 WhatsApp (Primary High‐Context Channel)
Use WhatsApp when:
 - You ne want fast acknowledgment
### 18.5.2 Fallback Rules (Mandatory)
You MUST configure a fallback mechanism:
 - If WhatsApp fails, fall back to SMS or email. 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L68-L80】
### 18.5.3 Message Logs (Mandatory)
You MUST maintain logs of sent messages fo0 (4).pdf†L89-L91】
## 18.6 HIC Controls for High‐Risk Actions ⚠
The following outcomes MUST omer service suspension
3. Public‐facing escalation messages (legal risk)
4. Insurance / accident reports that imply liability
Policy rule: Waswa AI may propose; human approves; system executes; audit stores the rationale. 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L48-L50】
## 18.7 Waswa AI Tactics (How to Use It Correctly) ✅
### A) Alert summarization for Ops Desk
utes of events for a vehicle/group
 - Suggest probable root cause (e.g., "fuel theft vs sensor noise") using tiered reasoning 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L31-L44】
### B) Reduce alert fatigue
Waswa AI should propose:
1. Bundling (group related alerts intes within N minutes)
2. Reclassification (downgrade recurring non‐actionable alerts)
### C) Actionable "First‐Steps" templates
Align with self‐service coaching: send the driver/fleet manager first actions quickly to reduce escalations. 【459:1†AI_Agent_Customer_Service_User_Stories_All.pdf†L102-L139】
## 18.8 CX Improvements (Admin Playbook)
You SHALL build notifications that Why does it matter?
3. What should the recipient do now?
4. How do they acknowledge / close it?
Tip : For enterprise customers, pair critical alerts with a "case number" and link it to the incident/ticket thread.
## 18.9 Preventative Maintenance Notes (Weekly)
Run a weekly alert health review:
1. Top 20 alerts by volume
2. Top 20 alerts by severity
3. False‐positive suspects (high volume + low action rate)
4. Delivery failures (WhatsApp/SMS/email)
5. Template drift (placeholders broken)

--- PAGE BREAK ---
# 19. REPORTING & BI DASHBOARDS — KPI GOVERNANCE, EXPORTS & BI PACKS

## 19.1 Purpose
Reporting is how you convert telemetry into:
 - Customer value (visibility + compliance) ✅
 - Retention (renewal confidence)
 - Upsell (exposing operational gaps)
NAVAS explicitly targets customizable dashboards, KPI tracking (fuel, driver behavior, utilization), visual tools (charts, trend analysis, anomaly detection), and export formats (Excel/PDF/JSON). 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L18-L37】【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L129-L132】
## 19.2 ReportLibrary (standard + customer‐specific)
1. A Scheduling Policy (who receives what, when)
2. A Data Quality Routine (sensor validation, unit mapping integrity)
## 19.3 Report Template Lifecycle (CRUD)
### Create ➕
1. Choose template category (Vehicle / Fuel / Safety / Compliance / Cold chain / Marketplace)
2. Bind objects (units/groups/tenants)
3. Choose output format(s): PDF, Excel, CSV, JSON (as required) 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L129-L132】
4. Save as:
 - Global template (for all tenants)
 - Tenant template ( Update
<!-- end list -->
 - Add/remove columns
 - Adjust thresholds
 - Add chart panels
 - Update branding/logos for dealer‐level accounts
### Archive
 - Remove obsolete templates to prevent accidental sends.
## 19.4 Scheduled Reports (Operational Standard)
You SHOULD standardize schedules:
1. Daily: Exceptions (overspeed, geofence, idling, temperature breaches)
2. Weekly: Driver scorecards + fuel variance + utilization
3. Monthly: Management pack (KPIs + SLA/MTTR summary + renewal status)
Tactic : Combine the management pack with renewal reminders to reduce service lapses. 【459:1†AI_Agent_Customer_Service_User_Stories_All.pdf†L36-L66】
## 19.5 BI DASHBOARDS Add‐On (Admin Duties)
The BI add‐on is a value‐added laynant partitioning (no data bleed)
2. Refresh governance
 - Scheduled refresh windows aligned to off‐peak hours
<!-- end list -->
1. Performance governance
 - Avoid heavy queries during peak operational monitoring
NAVAS architecture includes fast telemetry storage (Cassandra), audit/user/RBAC storage (PostgreSQL), and cache (Redis) to keep UI latency low. 【491:2† NAVAS IOT SYSTEM POLICY_ .pdf†L53-L90】
## 19.6 Waswa AI in Reporting (Correct Use) ✅
### ✅ Allowed
 - Draft executive summaries ("whatuel drain outliers")
 - Recommend next actions ("review route compliance for vehicle group X")
### ⚠ Requires human review
 - Any report sent externally that includes conclusions about liability, fraud, or disciplinary action.
## 19.7 Opportunity Identification (Admin‐Led)
You SHOULD use reporting to surface upsell triggers:
 - High overspeed → propose DSC / driver coaching pack
 - Frequent fuel anomalies → propose MAFUTA FLS / Flow Meter / CANBUS
 - Cold chain breaches → propose THERMO + escalation templates
 - High incident rate → propose DASHCAM/MDVR AI evidence pack

--- PAGE BREAK ---
# 20. VIDEO TELEMATICS GOVERNANCE — DASHCAM, DASH AI, MDVR, MDVR AI

## 20.1 Purpose
Video telematics is your evidence + coaching layer. It must be provisioned with strict control of:
1. Bandwidth consumption (EA network reality)
2. Storage cost (S3/object store discipline) 1⁄2
3. Evidence chain‐of‐custody (audit and legal defensibility) 3⁄4
4. AI inference costs (tiered strategy)
NAVAS recognizes that video snapshots and ADAS headway monitoring are high "revenue potential" parameters, while standard events (ignition, geofence) are high volume and lower value. 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L1-L4】
## 20.2 Video Provisioning Checklist (You MUST Enforce) ✅
1. Device registration
 - Serial- Ensure the camera is linked to the correct vehicle/unit record
2. Storage assignment
 - Default retention + event‐based retention
3. Traffic/bandwidth policy
 - Event upload only vs continuous (enterprise)
4. Role rights
 - Who can view clips? Who can export? Who can delete?
5. Evidence tags
 - Incident type, driver ID, route ID (where available)
Wialon's management system includes a dedicated Video section with topics like traffic packages and storage configuration, which mirrors how you must treat video as a governed subsystem. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system))
## 20.3 Video‐Driven Alerts (Canonical Examples)
Use triggers such as:
 - Driver distracted, yawning, phone use, smoking
 - Lane departure warning, forward collision warning, headway monitoring warning
 - Seatbelt unbuckled
 - Impact/crash detection 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L22-L88】
## 20.4 Evidence Workflow (Ops Desk Standard) 3⁄4
You MUST follow this workflow:
1. Alert fires (ADAS/DMS event)
2. Waswa AI drafts 4. Attach evidence (clip/snapshot) to ticket/case
3. Notify stakeholders via agreed channels
4. Close with outcome (coaching, maintenance, escalation)
This aligns with the strategy that video platforms are integrated for incident evidence to improve ticket quality and driver coaching. 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L19-L25】
## 20.5 AI Cost Control (Mandatory Tiering)
To protect profitability, NAVAS runs a tiered AI model:
1. Tier 1 (Edge logic): basic monitors (speeding, fuel drops)
 2ning on owned servers
2. Tier 3 (External API): complex legal/financial reports used sparingly 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L31-L44】
Admin rule: You MUST configure video analytics so that high‐volume events are handled at Tier 1/2 wherever feasible, reserving Tier 3 for exceptional cases.
## 20.6 eo)
### Preventative (monthly per fleet)
 - Clean lenses + check camera alignment
 - Validate time sync (camera vs GPS)
 - Verify storage retention policies
 - Confirm upload performance in weak network zones
### Corrective (when issues occur)
 - If clips are missing: verify bandwidth policy + storage credentials
 - If AI events spike: verify sensitivity thresholds and calibration
 - If driver identity is wrong: verify driver assignment mapping and device pairing

--- PAGE BREAK ---
# 21. FUEL TELEMATICS GOVERNANCE — MAFUTA SUITE + GENSET ⛽

## 21.1 Purpose
Fuel is where customers measure you the hardest. The MAFUTA stack must deliver:
1. Accurate consumption
2. Credible theft detection
3. Low false positives
4. Actionable reporting for finance
## 21.2 What You Must Provision (Per MAFUTA Variant)
### MAFUTA FLS (Fuel Level Sensor)
 - Tank profile (shape)
 - Calibration table
 - Event rules: drop/refill/low fuel
### MAFUTA FLOW METER
 - Flow pulse mapping
 - Engine hours correlation
 - Refuel verification
### MAFUTA CANBUS
 - ECU parameter mapping (supported models)
 - DTC enablement
 - Consumption baseline modeling
### MAFUTA FUEL CARD / STATION
 - Card identity binding
 - Station mapping
 - Reconciliation rules (expected vs actual)
### GENSET
 - Runtime hours
 - Load profile
 - Service intervals
## 21.3 Canonical Fuel Triggers (Baseline Library)
You MUST implement fuel triggers such as:
 - Fuel drop, fuel refill, fuel level low
 - Rapid fuel consumption
 - Excessive idling (fuel cost driver) 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L34-L76】
## 21.4 Fuel Integrity Tactics (Reduce False Positives)
1. Use time windows
 - Fuel drop must persist for N minutes before alertingpicion
2. Geofence context
 - Drops at known stations may be legitimate
3. Driver/route context
 - Route risk profiles (where available) influence severity
## 21.5 Reporting Standard (Minimum Set)
You SHOULD maintain these standard customer reports:
1. Fuel drains (suspected siphoning)
2. Fuel fillings (verified)
3. Fuel consumption per route / per driver
4. Idle time cost impact
5. Maintenance‐linked consumption drift
NAVAS's roadmap includes fuel efficiency KPIs and analytics as core outcomes. 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L23-L37】
## 21.6 Waswa AI in Fuel (Correct Use) ✅
### ✅ Allowed
 - Classify anomalies ("likely theft vs maintenance drain") using contextual reasoning tiers. 【49IC
 - Declaring fraud in customer communications
 - Triggering punitive action (disable unit, disciplinary notes)
## 21.7 Preventative & Corrective Main install / quarterly)
 - Re‐check wiring integrity
 - Validate sensor readings against manual dip tests (where feasible)
 - Re‐calibrate after tank repairs or fleet modifications
 - Review alert thresholds (seasonal/route changes)
### Corrective (when customers complain)
 - If "theft alerts" spike: verify calibration + smoothing + route/station mapping
 - If consumption looks too low/high: verify CANBUS parameter mapping and unit configuration
 - If refills not detected: adjust refill detection logic and validate sensor sampling rate

--- PAGE BREAK ---
# 22. PERSONNEL TRACING GOVERNANCE — CAPO, PATROL, PIKI, TOTO, WIATAG 1⁄4

## 22.1 Purpose
Personnel tracing must be run with privacy discipline, safety urgency, and operational clarity. It typically supports:
 - Security teams
 - Field ops dispatch
 - Patrol and lone worker safety
 - Boda Boda monitoring (PIKI) at high volume micro‐transactions
NAVAS explicitly positions PIKI for boda‐boda high volume transactions and PATROL for personnel tracing. 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L19-L29】
## 22.2 Canonical Safety & People Triggers
Your baseline alert library should include:
 - Man‐down detection, fall detection, panic button activation
 - Geofence breach for restricted zones
 - Heart rate abnormalities (only when deployed) 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L44-L90】
## 22.3 HIC Rules (Privacy & Safety) ⚠
1. You MUST restrict location access to "need‐to‐know" roles.
2. You MUST log all access to sensi4. Any sharing of a person's location externally requires explicit authorization.
## 22.4 Operational Tactics (Field Ops)
Use automation carefully to hit MTTR targets, including dispatch optimization for field technicians, parts planning, and routing—while keeping approvals auditable. 【459:1†AI_Agent_Customer_Service_User_Stories_All.pdf†L77-L100】

--- PAGE BREAK ---
# 23. GOODS‐IN‐TRANSIT & IOT GOVERNANCE — KAGO, PASO, PAWA, THERMO

## 23.1 Purpose
These modules protect cargo in## 23.2 Canonical Cargo / Cold Chain Triggers
Baseline triggers include:
 - Door open/close unauthorized, cargo intrusion, asset detachment
 - Temperature deviation, humidity deviation
 - Long no‐movement while expected in transit
 - Route deviation (where configured) 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L12-L90】
## 23.3 Preventative Maintenance Notes (Cold Chain)
 - Validate sensor calibration and placement
 - Verify alert thresholds match commodillback logic)

--- PAGE BREAK ---
# APPENDIX Z. ACRONYMS & ABBREVIATIONS — ADDITIONS (CONTINUATION)

Instruction: Merge this table into the master "Table of Acronyms/Abbreviations" at the end of the full document.
| Acronym | Meaning |
| HIC / HITL | Human‐in‐Control / Human‐in‐the‐Loop |
| RBAC | Role‐Based Access Control |
| DAU/WAU | Daily Active Users / Weekly Active Users |
| MTTR | Mean Time To Reply/Resolve (ops context) |
| PAYG | Pay‐As‐You‐Go |
| FLS | Fuel Level Sensor |
| DTC | Diagnostic Trouble Code |
| CANBUS | Controller Area Network Bus |
| DMS | Driver Monitoring System |
| ADAS | Advanced Driver‐Assistance Systems |
| FCW / LDW / HMW | Forward Collision Warning / Lane Departure Warning / Headway Monitoring Warning |
| GIS | Geographic Information System |
| S3 | Simple Storage Service compatible object storage |
| KPI | Key Performance Indicator |

## Sources Used in This Continuation (Internal)
 -  NAVAS IOT SYSTEM POLICY v26.0
 - NAVAS Vision & Scope Doc v3.0
 - 3D AI Agent Strategy v5
 - AI Agent Customer Service User Stories
 - List of Event Triggers (
 - CMS Mockup Redebrary / Provisioning UI) --
If you want, I can continue immediatel, starting at Section 24: Integrations & Ole Money, Maps, Webhooks, API Monetization) and then Section 2(UG/KE multi‐currency, branding, tenant lifecycle, renewals)—still in the same landscape + page‐break structure
According to a document from 20 February 2026, NAVAS is operated as a monetizable, hardware‐agnostic IoT platform with token burn, mobile money rails, RBAC + multi‐tenancy, and a Waswa AI co‐pilot that must remain auditable and human‐governed.

# CONTINUATION — PART II (DEEP‐DIVE OPERATIONS PLAYBOOK)

Landscape & Page Break Rule (Mandatory): This continuation is structured with explicit PAGE BREAK markers. Keep them when pasting into Google Docs.

## Part II Mini Table of Contents
1. 17. Apps Library & Provisioning (Portals, Add‐Ons, Entitlements, Dependencies)
2. 18. Notification Factory (Event Triggers, Templates, Channels, Escalations)
3. 19. Reporting & BI Dashboards (Exports, KPI Governance, BI Packs)
4. 20. Video Telematics Governance (DASHCAM, DASH AI, MDVR, MDVR AI)
5. 21. Fuel Telematics Governance (MAFUTA + GENSET) ⛽
6. 22. Personnel Tracing Governance (PIKI, PATROL, CAPO, TOTO, WIATAG) 1⁄4
7. 23. Goods‐in‐Transit & IoT Governance (KAGO, PASO, PAWA, THERMO)
8. Appendix Z (Continuation) Acronyms & Abbreviations (Additions)

--- PAGE BREAK ---
# 17. APPS LIBRARY & PROVISIONING — APP CATALOG, ENTITLEMENTS & DEPENDENCIES

## 17.1 Purpose
The Apps Library & Provisioning module is the commercial + operational control plane for enabling NAVAS portals, add‐on apps, and value‐added capabilities per tenant, while enforcing:
1. Governance (RBAC + maker‐checker) ✅
2. Dependency integrity (no half‐enabled services) ⚠
3. Token & payment correctness (no revenue leakage)
4. Auditability (who did what, when, and why) 3⁄4
This module implements the "service owner / dealer / client" mental model aligned with management systems like Wialon CMS Manager (top user + dealer rights managing macro‐objects). ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system))
## 17.2 Operating Principle (Non‐Negotiable)
You SHALL treat App Provisioning as a controlled change.
If a change can alter customer visibility, billing, or risk posture, it MUST be performed via:
1. Proposal (Waswa AI / operator initiates)
2. Human validation (HIC / maker‐checker) ✈
3. Apply + log (system commits) 3⁄4
4. Post‐change verification (smoke checks + telemetry sanity) ✅
This aligns with the AI/HITL doctrine: irreversible actions must be human‐approved and auditable. 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L48-L50】
## 17.3 Where This Lives iS → Administration → Apps Library
 - CMS → Tenant → Apps & Entitlements
 - CMS → Billing → Tokens → App Token Policies
 - CMS → Payments → Rails & Callbacks
## 17.4 UX Pattern: Table + Row Actions + Right Blade (Drawer)
This module is designed to be table‐first and blade‐driven:
 - Table columns typically include: App, Category, Enabled, DAU/WAU, Revenue, Dependencies, Health, Actions. 【459:4†CMS Mockup Redesign Request.txt†L10-L21】
 - Row actions open a Rig such as:
 - Overview
 - Enablement
 - Billing Tokens
 - Payments
 - Audit Trail 【459:10†CMS Mockup Redesign Request.txt†L11-L18】
HIC enforcement is exp Required" for high‐risk operations. 【459:8†CMS Mockup Redesign Request.txt†L19-L27】
### Blade Standard.ent and use these tabs in this order:
1. Overview. Business intent, dependencies, risk rating, last changed by.
2. Enablement. Toggle entitlements, enforce pre‐checks (KYC, device link, etc.).
3. Billing Tokens. Token class, burn rules, caps, bundles, grace thresholds.
4. Payments. Mobile money rails, pay links, callback validation.
5. Audit Trail. Immutable change log + approvals + rollback references.
## 17.5 CMS Data Objects (Admin Mental Model)
In provisioning, treat the system as these objects:
1. App Catalog Item (global definition)
 - Name, category, dependencies, supported products, billing mode.
2. Tenant Entitlement
 - Enabled status (Yes/Trial/No), effective dates, environment constraints.
3. Dependency Graph
 - GPS unit required, camera required, payment required, KYC required.
4. Token Policy
 - Token class mapping, burn rules, caps, discounts (bundle logic).
5. Payment Rail
 - M‐Pesa / MTN / Airtel mapping, callback secrets, settlement rules.
6. Audit Event
 - Who changed what, approvals, and rollback pointers.
This matches NAVAS's monetization posture: token engine + mobile money rails integrated into the telemetry heart. 【491:2† NAVAS IOT SYSTEM POLICY_ .pdf†L23-L29】【491:10† NAVAS IOT SYSTEM New App Catalog Item) ➕
Use this only when product leadership has approved a new capability (e.g., "Fraud Shield", "Route Optimizer", "BI Export Pro").
Procedure (must be followed):
1. Define:
 - App Name (official nomenclature)
 - Category (Video / Fuel / Marketplace / Safety / Reports / Integration)
2. Declare dependencies (hard + soft)
3. Assign default token policy
4. Assign activation gates
 - HITL required? (Yes for billing‐impacting changes)
5. Save → Submit for approval (maker‐checker)
### B) Read (Find & Diagnose)
You SHALL use filters to locate issues quickly:
 - Enabled status: Yes / Trial / No
 - Health: OK / Warn / Alarm
 - Revenue band: UGX/KES thresholds
 - Usage: DAU/WAU (adoption signals)
### C) Update (Provision to Tenant)
This is the most common admin action.
Standard flow:
1. Select the Tenant / Dealer / Org context in the blade (multi‐tenant selector). 【459:10†CMS Mockup Redesign Request.txt†L24-L28】
2. In Enablement, tog (if applicable)
 - Require Telematics Unit Linked
 - Enable leakage/AI shields (where applicable) 【459:8†CMS Mockup Redesign Request.txt†L36-L44】
3. Configure Billing Tokes
4. Configure Payments:
 - Payment rail activation and callback tests
5. Save & Apply
6. Execute Post‐Provision Smoke Tests (see 17.9)
### D) Delete (Archive → Trash)
Deletion is never hard‐delete.
Rule:
 - You MUST use Archive → Trash, with a restoration path.
 This mirrors management-system patterns where deleted macro‐objects are recoverable from trash. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system))
## 17.7 Mapping: 3D Product Portfolio → CMS Provisioning
Table styling instruction: set header row shade to #F5F5F5 and remove borders .
| Service Type | Product / App | Provisioning "Hard Dependencies" | Primary Admin Concern |
| Vehicle Telematics | OLIWA / OLIWA‐PLUS / GUVNA / iVMS / iVMS‐PLUS | GPS unit linked, map tiles, reporting enabled | Data continuity + geofence + token stability |
| Personnel Tracing | PIKI / PATROL / CAPO / TOTO / WIATAG | GPS/mobile identity, geofences, alert channels | Safety alerts + duty rules + privacy |
| Goods‐in‐Transit & IoT | KAGO / PASO / PAWA / THERMO | Sensor binding (temp/door/power), alert channels | Cold chain + intrusion + SLA |
| Fuel Telematics | MAFUTA (FLS/Flow/CANBUS/Fuel Card/Station) + GENSET | Sensor calibration + vehicle profile + report templates | Theft detection + false positives |
| AI & Video | DASHCAM / DASH AI / MDVR / MDVR AI | Camera device + storage + bandwidth policy | Evidence chain + cost control |
| Add‐On Apps | BI DASHBOARDS / DSC / ECO / FLEETRUN / INSPECTA / JMS / LOGISTICS / NIMBUS / VEBA | Base tracking + role rights + payment where needed | Adoption + upsell + integration |
| Value Added | Help Desk & Training / GIS & JMS / SATO / Local Server / OEM Integrations | Contracts + tenant roles + integration keys | Compliance + service quality |

NAVAS explicitly positions OLIWA, PIKI, VEBA, and PATROL as specialized portals under the umbrella platform. 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L15-L29】
## 17.8 Waswa AI Assist (Allowed) vs HIC Decision (Mandatory)
### ✅ Waswa AI MAY do:
 - Suggelag "enabled but unused >30 days" for cost control and adoption actions. 【459:8†CMS Mockup Redesign Request.txt†L1-L4】
 - Recommend trial→paid nudges via WhatsApp templates. 【459:8†CMS Mockup Redesign Request.txt†L1-L4】
 - ed without payment rail).
### ⚠ *Waswa AI MUST NOT dooken policies
1. Enabling payment rails
2. Suspending a tenant / disabling a core portal
3. Changing security‐relevant roles or access rights
This is consistent with "agent proposes; named role approves; action and rationale logged." 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L48-L50】
## 17.9 Post‐Provision Smoke Tests (You MUST run these) ✅
For each tenant/app enablement, execute:nly to intended roles
2. Telemetry binding
 - Unit/device linked and appears under correct tenant
<!-- end list -->
1. Alert path
 - Trigger a test event (or simulated rule) → verify WhatsApp/SMS/email routing
2. Token burn sanity
 - Verify token counters increment as expected (not 10×)
3. Payment top‐up (if applicable)
 - Sandbox top‐up callback validated
4. Audit trail exists
 - Change request + approval + operator identity logged
## 17.10 Preventative Maintenance Notes (Monthly)
You SHALL run a monthly entitlement and leakage audit:
 - List tenants with:
 1. Apps enabled but no usage (DAU/WAU = 0)
 2. Apps used heavily but not billed correctly
 3. Payment rails failing callbacks
 - Validate token FIFO logic is functioning (no hidden debt build‐up). 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L5-L6】

--- PAGE BREAK ---
# 18. NOTIFICATION FACTORY — EVENT TRIGGERS, TEMPLATES, CHANNELS & ESCALAns are where telematics becomes operational action. Your job is to convert:
 - Noisy events → actionable alerts
 - Human attention scarcity → controlled triage
This aligns with the operating thesis: telematics is "event‐rich but attention‐poor," therefore we prioritize deterministic interfaces, auditability, and reversible automations. 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L1-L5】
## 18.2 Event Taxonomy (Admin Standard)
You SHALL classify every trigger into:
1. Safety & Compli
2. Security (geofence breach, intrusion, unauthorized movement)
3. Asset Health (DTCs, battery health, service intervals)
4. Fuel & Cost (fuel drop, rapid consumption)
5. Cold Chain / Cargo (temp/humidity deviations, door open)
6. People Safety (man‐down, panic button, heart rate anomalies if deployed)
NAVAS explicitly targets configurable thresholds and multi‐channel delivery (push, email, SMS, WhatsApp). 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L6-L15】
## 18.3 Canonical Trigger Library (Use This as Your Baseline)
The NAVAS triggers:
 - Overspeeding, harsh acceleration/braking/cornering, excessive idling
 - Fuel drop, fuel level low, fuel refill, rapid fuel consumption
 - Geofence entry/exit, route deviation, country border exit
 - Driver distraction, driver fatigue, seatbelt unbuckled, phone use
 - Engine fault codes (DTCs), engine hours reached for service
 - Temperature deviation, humidity deviation, cargo intrusion, door open/close unauthorized
 - Panic button, man‐down, fall detection, impact detection 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L4-L91】
## 18.4 The Notification Rule Builder (Mandatory Fields)
Each notiS, sensor, video AI, mobile app, external API
2. Condition
 - Threshold + comparison + time window (e.g., speed > 80 km/h for 30 seconds)
<!-- end list -->
1. Scope
 - Vehicle(s), group(s), tenant(s), routes, geofences
2. Severity
 - Info / Warning / Alarm / Critical
3. Recipients
 - Driver, Fleet Manager, Ops Desk, Security Desk, Maintenance Desk
4. Delivery channels
 - In‐app + Email + SMS + WhatsApp + Webhook
5. Suppression rules
 - Quiet hours, deduplication, throttling
6. Escalation
 - If unacknowledged → escalate after X minutes
7. Audit
 - Creator, approver, last edit, change reason
## 18.5 Channel Governance (EA Market Reality) 2
NAVAS supports multi‐channel alerts including WhatsApp/SMS/email and requires reliability mechanisms. 【459:3†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L89-L96】
### 18.5.1 WhatsApp (Primary High‐Context Channel)
Use WhatsApp when:
 - You ne want fast acknowledgment
### 18.5.2 Fallback Rules (Mandatory)
You MUST configure a fallback mechanism:
 - If WhatsApp fails, fall back to SMS or email. 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L68-L80】
### 18.5.3 Message Logs (Mandatory)
You MUST maintain logs of sent messages fo0 (4).pdf†L89-L91】
## 18.6 HIC Controls for High‐Risk Actions ⚠
The following outcomes MUST omer service suspension
3. Public‐facing escalation messages (legal risk)
4. Insurance / accident reports that imply liability
Policy rule: Waswa AI may propose; human approves; system executes; audit stores the rationale. 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L48-L50】
## 18.7 Waswa AI Tactics (How to Use It Correctly) ✅
### A) Alert summarization for Ops Desk
utes of events for a vehicle/group
 - Suggest probable root cause (e.g., "fuel theft vs sensor noise") using tiered reasoning 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L31-L44】
### B) Reduce alert fatigue
Waswa AI should propose:
1. Bundling (group related alerts intes within N minutes)
2. Reclassification (downgrade recurring non‐actionable alerts)
### C) Actionable "First‐Steps" templates
Align with self‐service coaching: send the driver/fleet manager first actions quickly to reduce escalations. 【459:1†AI_Agent_Customer_Service_User_Stories_All.pdf†L102-L139】
## 18.8 CX Improvements (Admin Playbook)
You SHALL build notifications that Why does it matter?
3. What should the recipient do now?
4. How do they acknowledge / close it?
Tip : For enterprise customers, pair critical alerts with a "case number" and link it to the incident/ticket thread.
## 18.9 Preventative Maintenance Notes (Weekly)
Run a weekly alert health review:
1. Top 20 alerts by volume
2. Top 20 alerts by severity
3. False‐positive suspects (high volume + low action rate)
4. Delivery failures (WhatsApp/SMS/email)
5. Template drift (placeholders broken)

--- PAGE BREAK ---
# 19. REPORTING & BI DASHBOARDS — KPI GOVERNANCE, EXPORTS & BI PACKS

## 19.1 Purpose
Reporting is how you convert telemetry into:
 - Customer value (visibility + compliance) ✅
 - Retention (renewal confidence)
 - Upsell (exposing operational gaps)
NAVAS explicitly targets customizable dashboards, KPI tracking (fuel, driver behavior, utilization), visual tools (charts, trend analysis, anomaly detection), and export formats (Excel/PDF/JSON). 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L18-L37】【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L129-L132】
## 19.2 ReportLibrary (standard + customer‐specific)
1. A Scheduling Policy (who receives what, when)
2. A Data Quality Routine (sensor validation, unit mapping integrity)
## 19.3 Report Template Lifecycle (CRUD)
### Create ➕
1. Choose template category (Vehicle / Fuel / Safety / Compliance / Cold chain / Marketplace)
2. Bind objects (units/groups/tenants)
3. Choose output format(s): PDF, Excel, CSV, JSON (as required) 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L129-L132】
4. Save as:
 - Global template (for all tenants)
 - Tenant template ( Update
<!-- end list -->
 - Add/remove columns
 - Adjust thresholds
 - Add chart panels
 - Update branding/logos for dealer‐level accounts
### Archive
 - Remove obsolete templates to prevent accidental sends.
## 19.4 Scheduled Reports (Operational Standard)
You SHOULD standardize schedules:
1. Daily: Exceptions (overspeed, geofence, idling, temperature breaches)
2. Weekly: Driver scorecards + fuel variance + utilization
3. Monthly: Management pack (KPIs + SLA/MTTR summary + renewal status)
Tactic : Combine the management pack with renewal reminders to reduce service lapses. 【459:1†AI_Agent_Customer_Service_User_Stories_All.pdf†L36-L66】
## 19.5 BI DASHBOARDS Add‐On (Admin Duties)
The BI add‐on is a value‐added laynant partitioning (no data bleed)
2. Refresh governance
 - Scheduled refresh windows aligned to off‐peak hours
<!-- end list -->
1. Performance governance
 - Avoid heavy queries during peak operational monitoring
NAVAS architecture includes fast telemetry storage (Cassandra), audit/user/RBAC storage (PostgreSQL), and cache (Redis) to keep UI latency low. 【491:2† NAVAS IOT SYSTEM POLICY_ .pdf†L53-L90】
## 19.6 Waswa AI in Reporting (Correct Use) ✅
### ✅ Allowed
 - Draft executive summaries ("whatuel drain outliers")
 - Recommend next actions ("review route compliance for vehicle group X")
### ⚠ Requires human review
 - Any report sent externally that includes conclusions about liability, fraud, or disciplinary action.
## 19.7 Opportunity Identification (Admin‐Led)
You SHOULD use reporting to surface upsell triggers:
 - High overspeed → propose DSC / driver coaching pack
 - Frequent fuel anomalies → propose MAFUTA FLS / Flow Meter / CANBUS
 - Cold chain breaches → propose THERMO + escalation templates
 - High incident rate → propose DASHCAM/MDVR AI evidence pack

--- PAGE BREAK ---
# 20. VIDEO TELEMATICS GOVERNANCE — DASHCAM, DASH AI, MDVR, MDVR AI

## 20.1 Purpose
Video telematics is your evidence + coaching layer. It must be provisioned with strict control of:
1. Bandwidth consumption (EA network reality)
2. Storage cost (S3/object store discipline) 1⁄2
3. Evidence chain‐of‐custody (audit and legal defensibility) 3⁄4
4. AI inference costs (tiered strategy)
NAVAS recognizes that video snapshots and ADAS headway monitoring are high "revenue potential" parameters, while standard events (ignition, geofence) are high volume and lower value. 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L1-L4】
## 20.2 Video Provisioning Checklist (You MUST Enforce) ✅
1. Device registration
 - Serial- Ensure the camera is linked to the correct vehicle/unit record
2. Storage assignment
 - Default retention + event‐based retention
3. Traffic/bandwidth policy
 - Event upload only vs continuous (enterprise)
4. Role rights
 - Who can view clips? Who can export? Who can delete?
5. Evidence tags
 - Incident type, driver ID, route ID (where available)
Wialon's management system includes a dedicated Video section with topics like traffic packages and storage configuration, which mirrors how you must treat video as a governed subsystem. ([Wialon Help Centre](https://help.wialon.com/en/wialon-hosting/user-guide/management-system))
## 20.3 Video‐Driven Alerts (Canonical Examples)
Use triggers such as:
 - Driver distracted, yawning, phone use, smoking
 - Lane departure warning, forward collision warning, headway monitoring warning
 - Seatbelt unbuckled
 - Impact/crash detection 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L22-L88】
## 20.4 Evidence Workflow (Ops Desk Standard) 3⁄4
You MUST follow this workflow:
1. Alert fires (ADAS/DMS event)
2. Waswa AI drafts 4. Attach evidence (clip/snapshot) to ticket/case
3. Notify stakeholders via agreed channels
4. Close with outcome (coaching, maintenance, escalation)
This aligns with the strategy that video platforms are integrated for incident evidence to improve ticket quality and driver coaching. 【459:13†3D-AI-AGENT-STRATEGY V5.pdf†L19-L25】
## 20.5 AI Cost Control (Mandatory Tiering)
To protect profitability, NAVAS runs a tiered AI model:
1. Tier 1 (Edge logic): basic monitors (speeding, fuel drops)
 2ning on owned servers
2. Tier 3 (External API): complex legal/financial reports used sparingly 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L31-L44】
Admin rule: You MUST configure video analytics so that high‐volume events are handled at Tier 1/2 wherever feasible, reserving Tier 3 for exceptional cases.
## 20.6 eo)
### Preventative (monthly per fleet)
 - Clean lenses + check camera alignment
 - Validate time sync (camera vs GPS)
 - Verify storage retention policies
 - Confirm upload performance in weak network zones
### Corrective (when issues occur)
 - If clips are missing: verify bandwidth policy + storage credentials
 - If AI events spike: verify sensitivity thresholds and calibration
 - If driver identity is wrong: verify driver assignment mapping and device pairing

--- PAGE BREAK ---
# 21. FUEL TELEMATICS GOVERNANCE — MAFUTA SUITE + GENSET ⛽

## 21.1 Purpose
Fuel is where customers measure you the hardest. The MAFUTA stack must deliver:
1. Accurate consumption
2. Credible theft detection
3. Low false positives
4. Actionable reporting for finance
## 21.2 What You Must Provision (Per MAFUTA Variant)
### MAFUTA FLS (Fuel Level Sensor)
 - Tank profile (shape)
 - Calibration table
 - Event rules: drop/refill/low fuel
### MAFUTA FLOW METER
 - Flow pulse mapping
 - Engine hours correlation
 - Refuel verification
### MAFUTA CANBUS
 - ECU parameter mapping (supported models)
 - DTC enablement
 - Consumption baseline modeling
### MAFUTA FUEL CARD / STATION
 - Card identity binding
 - Station mapping
 - Reconciliation rules (expected vs actual)
### GENSET
 - Runtime hours
 - Load profile
 - Service intervals
## 21.3 Canonical Fuel Triggers (Baseline Library)
You MUST implement fuel triggers such as:
 - Fuel drop, fuel refill, fuel level low
 - Rapid fuel consumption
 - Excessive idling (fuel cost driver) 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L34-L76】
## 21.4 Fuel Integrity Tactics (Reduce False Positives)
1. Use time windows
 - Fuel drop must persist for N minutes before alertingpicion
2. Geofence context
 - Drops at known stations may be legitimate
3. Driver/route context
 - Route risk profiles (where available) influence severity
## 21.5 Reporting Standard (Minimum Set)
You SHOULD maintain these standard customer reports:
1. Fuel drains (suspected siphoning)
2. Fuel fillings (verified)
3. Fuel consumption per route / per driver
4. Idle time cost impact
5. Maintenance‐linked consumption drift
NAVAS's roadmap includes fuel efficiency KPIs and analytics as core outcomes. 【459:2†NAVAS_VISION_SCOPE_DOC_ver250425 ver 3.0 (4).pdf†L23-L37】
## 21.6 Waswa AI in Fuel (Correct Use) ✅
### ✅ Allowed
 - Classify anomalies ("likely theft vs maintenance drain") using contextual reasoning tiers. 【49IC
 - Declaring fraud in customer communications
 - Triggering punitive action (disable unit, disciplinary notes)
## 21.7 Preventative & Corrective Main install / quarterly)
 - Re‐check wiring integrity
 - Validate sensor readings against manual dip tests (where feasible)
 - Re‐calibrate after tank repairs or fleet modifications
 - Review alert thresholds (seasonal/route changes)
### Corrective (when customers complain)
 - If "theft alerts" spike: verify calibration + smoothing + route/station mapping
 - If consumption looks too low/high: verify CANBUS parameter mapping and unit configuration
 - If refills not detected: adjust refill detection logic and validate sensor sampling rate

--- PAGE BREAK ---
# 22. PERSONNEL TRACING GOVERNANCE — CAPO, PATROL, PIKI, TOTO, WIATAG 1⁄4

## 22.1 Purpose
Personnel tracing must be run with privacy discipline, safety urgency, and operational clarity. It typically supports:
 - Security teams
 - Field ops dispatch
 - Patrol and lone worker safety
 - Boda Boda monitoring (PIKI) at high volume micro‐transactions
NAVAS explicitly positions PIKI for boda‐boda high volume transactions and PATROL for personnel tracing. 【491:10† NAVAS IOT SYSTEM POLICY_ .pdf†L19-L29】
## 22.2 Canonical Safety & People Triggers
Your baseline alert library should include:
 - Man‐down detection, fall detection, panic button activation
 - Geofence breach for restricted zones
 - Heart rate abnormalities (only when deployed) 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L44-L90】
## 22.3 HIC Rules (Privacy & Safety) ⚠
1. You MUST restrict location access to "need‐to‐know" roles.
2. You MUST log all access to sensi4. Any sharing of a person's location externally requires explicit authorization.
## 22.4 Operational Tactics (Field Ops)
Use automation carefully to hit MTTR targets, including dispatch optimization for field technicians, parts planning, and routing—while keeping approvals auditable. 【459:1†AI_Agent_Customer_Service_User_Stories_All.pdf†L77-L100】

--- PAGE BREAK ---
# 23. GOODS‐IN‐TRANSIT & IOT GOVERNANCE — KAGO, PASO, PAWA, THERMO

## 23.1 Purpose
These modules protect cargo in## 23.2 Canonical Cargo / Cold Chain Triggers
Baseline triggers include:
 - Door open/close unauthorized, cargo intrusion, asset detachment
 - Temperature deviation, humidity deviation
 - Long no‐movement while expected in transit
 - Route deviation (where configured) 【459:0†List of Event that Triggers notifications, alerts, alarms.pdf†L12-L90】
## 23.3 Preventative Maintenance Notes (Cold Chain)
 - Validate sensor calibration and placement
 - Verify alert thresholds match commodillback logic)

--- PAGE BREAK ---
# APPENDIX Z. ACRONYMS & ABBREVIATIONS — ADDITIONS (CONTINUATION)

Instruction: Merge this table into the master "Table of Acronyms/Abbreviations" at the end of the full document.
| Acronym | Meaning |
| HIC / HITL | Human‐in‐Control / Human‐in‐the‐Loop |
| RBAC | Role‐Based Access Control |
| DAU/WAU | Daily Active Users / Weekly Active Users |
| MTTR | Mean Time To Reply/Resolve (ops context) |
| PAYG | Pay‐As‐You‐Go |
| FLS | Fuel Level Sensor |
| DTC | Diagnostic Trouble Code |
| CANBUS | Controller Area Network Bus |
| DMS | Driver Monitoring System |
| ADAS | Advanced Driver‐Assistance Systems |
| FCW / LDW / HMW | Forward Collision Warning / Lane Departure Warning / Headway Monitoring Warning |
| GIS | Geographic Information System |
| S3 | Simple Storage Service compatible object storage |
| KPI | Key Performance Indicator |

## Sources Used in This Continuation (Internal)
 -  NAVAS IOT SYSTEM POLICY v26.0
 - NAVAS Vision & Scope Doc v3.0
 - 3D AI Agent Strategy v5
 - AI Agent Customer Service User Stories
 - List of Event Triggers (
 - CMS Mockup Redebrary / Provisioning UI) --
If you want, I can continue immediatel, starting at Section 24: Integrations & Ole Money, Maps, Webhooks, API Monetization) and then Section 2(UG/KE multi‐currency, branding, tenant lifecycle, renewals)—still in the same landscape + page‐break structure
# 14. INCIDENT MANAGEMENT & ESCALATION  ̄

*Alignment note (QMS).* This section is aligned to the 3D Services escalation and incident governance approach (3DS‐QSP‐18, Rev 1, dated 01.NOV.2024) and is mandatory for all CMS System Administrators operating the NAVAS platform in Uganda & Kenya. ✅

## 14.1 Purpose & Scope
*Purpose.* You SHALL operate the CMS Incident Management capability as the single operational control point for:
1. Detection of failures before the customer calls (proactive monitoring).
2. Intake and triage of issues (correct classification + correct owner + correct SLA timer).
3. Escalation (internal + upstream suppliers) with auditability.
4. Field dispatch (when physical action is required).
5. Customer communications (timely, factual, and expectation-managed).
6. Problem management (prevent repeat incidents through corrective actions).
*Scope.* Applies to all 3D products and service types, including:
 - Vehicle Telematics: OLIWA / OLIWA‐PLUS, iVMS / iVMS‐PLUS, GUVNA
 - AI & Video Telematics: DASHCAM, DASH AI, MDVR, MDVR AI
 - Fuel Telematics: MAFUTA FLS, MAFUTA CANBUS, MAFUTA FLOW METER, MAFUTA FUEL CARD, MAFUTA STATION, GENSET
 - Goods-in-Transit & IoT: KAGO, PASO, PAWA, THERMO
 - Personnel Tracing: CAPO, PATROL, PIKI, TOTO, WIATAG
 - Add‐On Apps: BI Dashboards, DSC, ECO, FleetRun, INSPECTA, JMS, LOGISTICS, NIMBUS, VEBA
 - Value Added Services: Help Desk & Training, GIS & JMS, SATO, Local Owned Server, OEM Integrations

## 14.2 Operating Principles (Non‐Negotiable)
1. Single Source of Truth (SSOT).
 All incidents SHALL have one authoritative record (ticket/incident) in CMS (or the integrated ticket system surfaced in CMS). No "shadow resolution" in WhatsApp groups or personal calls without a ticket. ⚠
2. Evidence Before Action.
 You MUST capture *minimum evidence* before changing configuration, dispatching, or escalating upstream. Evidence includes:
 - Unit/asset identifier(s)
 - Time window of failure
 - Customer impact statement
 - Last known connectivity state and key parameters (power, GPS, GSM, sensors)
 - Screenshots/log snippets/telemetry extracts
3. HIC/HITL Control Always Applies.
 AI may recommend classification and actions, but a human MUST confirm all high-impact decisions (P1 triage approvals, quote approvals, suspension/resume approvals, KB publish review). ✅
4. Customer Communication = SLA Protection.
 If you cannot fix immediately, you SHALL still communicate: *ticket number + status + ETA + next update time*. Lack of updates is treated as service failure even when the technical fix is in progress.

## 14.3 CMS Module Map (What You Operate)
In CMS, the administrator operates the following blades (modules) and their associated "cards" (detail panels):
### 14.3.1 Incident & Ops Center Module (Core)
*Objects and CRUD responsibilities.*
1. Incident Ticket (Create / Read / Update / Close)
2. Alarm Event (Read / Link to incident / Acknowledge)
3. Work Order / Job Card (Create / Assign / Close)
4. Dispatch Task (Create / Route / Update / Close)
5. Post‐Incident Review (Create / Approve / Publish)
6. Knowledge Base Article (Draft / Review / Publish / Retire)
### 14.3.2 Detail Blade Structure (Standard)
*Incident Detail Blade.* You SHALL expect these cards and populate them consistently:
 - Summary Card: title, severity, status, owner, customer, affected assets
 - SLA Card: timers (FRT, MTTR), breach risk indicator
 - Impact Card: operational + financial + safety impact
 - Asset Telemetry Card: last packets, voltage, GPS, GSM, sensor values
 - Timeline Card: all actions (human + AI) with timestamps
 - Communications Card: outbound messages, inbound updates, acknowledgements
 - Attachments Card: photos, wiring diagrams, logs, customer evidence
 - Actions Card: escalate, dispatch, request access, request spares, close

## 14.4 Incident Lifecycle (Mandatory Workflow)
You SHALL manage every incident using the following lifecycle states:
1. Detected (system or user)
2. Logged (ticket created, minimum fields complete)
3. Triaged (severity + category + assignment set; SLA timer started)
4. Diagnosing (remote checks, evidence gathering, hypothesis)
5. Mitigated (service restored partially or workaround applied)
6. Resolved (root cause fixed)
7. Validated (QA verification + customer confirmation where applicable)
8. Closed (documented + tagged + preventive action assigned if needed)
9. Problem Review (repeat incidents → corrective plan)
*Run‐in rule.* *If it's not logged, it did not happen.* This protects you operationally and legally.

## 14.5 Business Hours, Support Coverage & Response Targets
### 14.5.1 Support Coverage
You MUST operate with the defined service window:
 - Standard business hours: 08:30–17:30 EAT, Monday–Saturday, excluding national public holidays
 - On‐call coverage exists for Sundays and public holidays (after‐hours support)
### 14.5.2 Minimum Required Info for Escalations
When raising an escalation request, you SHALL provide:
 - Reason for escalation
 - Severity level
 - Customer impact
 - Any evidence already collected
### 14.5.3 Point of Contact Response Time Targets
You SHALL enforce the following operational targets:
| Point of Contact | Target Response Time |
| Standard Support Hours (Phone) | 15 minutes |
| After Hours (Phone) | 60 minutes |
| Standard Support Hours (Email) | 2 hours |
| After Hours (Email) | Next business day |
| WhatsApp | 5 minutes |
| Walk‐in | Immediately |
| On‐site | 3–8 hours (subject to product/field constraints) |

✅ These targets are explicitly defined and MUST be tracked in CMS dashboards.

## 14.6 Severity Classification (P1–P4)
You SHALL use a severity model that aligns to customer impact:
1. P1 (Critical)
 - Safety risk, security breach, widespread outage, or major customer operational halt
 - Immediate management visibility required
 - HIC gate: *P1 triage approvals required* ✅
2. P2 (High) ⚠
 - Degraded service affecting key operations or multiple assets
 - Workaround may exist, but risk of escalation is high
3. P3 (Medium)
 - Localized issue affecting limited scope; workaround exists; no immediate safety risk
4. P4 (Low)
 - Minor issue, informational requests, cosmetic UI items, "how‐to" queries
*Run‐in policy.* *Severity is about impact, not emotion.* You SHALL downgrade/upgrade only with documented evidence (Impact Card + SLA Card).

## 14.7 Alarm Center & Event Triggers (Your Detection Engine)  ̈
### 14.7.1 Configure Alarm Triggers by Product Domain
NAVAS supports a broad alarm trigger catalog that you SHALL map into product‐specific alarm profiles, e.g.:
 - Fuel: fuel drop, rapid fuel consumption, fuel refill, fuel level low
 - Safety/Driving: overspeeding, harsh braking, harsh acceleration, harsh cornering
 - Geofence & Security: geofence breach, unauthorized movement, door open/close, cargo compartment intrusion
 - Video AI: driver on phone, fatigue alert, seatbelt unbuckled, lane departure, forward collision warning
 - IoT/Cold Chain: temperature deviation, humidity deviation
 - Maintenance: engine hours reached for service, preventative maintenance triggers
### 14.7.2 Alarm Profile Governance
You SHALL implement alarm profiles as controlled configuration objects:
1. Create a profile per product family (Vehicle, Fuel, Video, GIT/IoT, Personnel).
2. Attach profile to: account → group → unit(s).
3. Configure thresholds (speed limits, geofence rules, sensor bounds).
4. Define channels (screen, email, WhatsApp, SMS, API webhooks).
5. Apply quiet hours and deduplication rules to reduce alert fatigue.

## 14.8 Target Installation & Repair Time by Product (Field SLA Control)
You SHALL use the published targets to plan dispatch, schedule customers, and manage expectations:
| Service Type | Product | Target Install Time | Target Repair Time |
| AI & Video Telematics | Dash AI | 4.5 hrs | 3 hrs |
| | Dashcam | 4 hrs | 3 hrs |
| | MDVR | 8 hrs | 3 hrs |
| | MDVR AI | 8 hrs | 3 hrs |
| Vehicle Telematics | iVMS | 3 hrs | 2 hrs |
| | iVMS‐Plus | 4 hrs | 3 hrs |
| | OLIWA | 3 hrs | 2 hrs |
| | OLIWA‐Plus | 4 hrs | 3 hrs |
| | Speed Governor | 2 hrs | 1 hr |
| Fuel Telematics | Mafuta FLS | 8 hrs | 3 hrs *(recalibration: 8 hrs)* |
| | Mafuta Station | TBD | TBD |
| | Mafuta Fuel Card | TBD | TBD |
| | Mafuta CANBUS | 4 hrs | 3 hrs |
| | Mafuta Flow Meter | 3 hrs | 2 hrs |
| Personnel Tracing | CAPO | 1 hr | 30 mins |
| | PIKI | 3 hrs | 2 hrs |
| | TOTO | 1 hr | 30 mins |
| | WIATAG | 1 hr | 30 mins |
| | PATROL | 4 hrs | 2 hrs |
| Goods & IoT | GENSET | 8 hrs | 3 hrs *(recalibration: 8 hrs)* |
| | KAGO | 4 hrs | 3 hrs |
| | THERMO | 2 hrs | 1 hr |
| | PASO | 1 hr | 1 hr |
| | PAWA | 4 hrs | 3 hrs |

These targets SHALL be reflected in:
 - scheduling,
 - customer ETA communication,
 - SLA dashboards,
 - workforce utilization reports. ✅

## 14.9 Dispatch & On‐Site Response Management (EA Context)
### 14.9.1 On‐Site Response Timing by Distance
Where field attendance is required, you SHALL plan travel expectations by distance (regional reality check):
 - ≤ 50 km: target reach 1 hour
 - ≤ 100 km: target reach 2 hours
 - ≥ 110 km: target reach 24 hours (requires scheduling and customer confirmation)
### 14.9.2 Dispatch Readiness Checklist (Must Complete Before Sending a Technician)
*Run‐in and italicized per policy.
Access & Coordination.* You SHALL confirm before dispatch:
1. Site pin/location (WhatsApp live location or Google Maps pin)
2. Security clearance (who will open the gate, who is the contact)
3. Asset availability (vehicle/bike present? driver available?)
4. Spare parts availability (SIM, harness, sensor, camera, power monitor)
5. Tools & PPE (as required)
6. Job card + SOP attached to the ticket
This aligns with the "Field Ops Router + Scheduler" logic (skills + parts + routing).

## 14.10 HIC + AI Playbook Inside Incident Operations
### 14.10.1 AI Roles You SHALL Enable
You SHALL enable (at minimum) the following AI agent behaviours for incident operations:
1. Health Sentinel (Proactive Detection)
 - Detect anomalies (no data, GNSS drift, power loss)
 - Correlate with network/SIM issues
 - Auto‐open a ticket with evidence
 - Notify stakeholders early
2. Resolution Co‐Pilot (L1 Guidance)
 - Summarize ticket
 - Pull telemetry context
 - Suggest SOP steps
 - Auto‐draft internal notes
 - Start SLA timers
3. Self‐Service Coach + Alert Orchestrator (Driver/End‐User First Actions)
 - Deliver WhatsApp "first actions" instructions
 - Reduce avoidable escalations
4. Progress Notifier (Customer Communications)
 - Milestone pings and "next update time" messages
 - Reduce uncertainty and follow‐ups
### 14.10.2 HITL Gates You MUST Enforce
AI can recommend. Humans decide. You SHALL enforce human sign‐off for:
 - P1 triage approvals
 - Quote approvals
 - Finance approvals for suspension/resume
 - Knowledge base publish review
### 14.10.3 KPI Targets (AI + Human Combined)
The AI strategy explicitly targets operational KPIs including:
 - Latency for P1: *< 2 minutes*
 - FRT (First Response Time)
 - MTTR (Mean Time To Resolve)
 - CSAT and audit completeness
*Trainer's directive :* Your job is not to "use AI". Your job is to raise reliability and reduce repeat incidents while maintaining auditability.

## 14.11 Escalation Protocol (Internal + Upstream)
### 14.11.1 Internal Escalation (L1 → L2 → Field → Management)
You SHALL escalate when any of the following are true:
1. SLA breach risk is > 50% (SLA Card indicates red/amber).
2. Safety/security implication exists (panic, intrusion, tamper, crash).
3. Issue affects multiple customers or multiple units (suspected platform outage).
4. Root cause is unknown after the standard diagnosis checklist.
5. Customer is a strategic/high‐risk account and expects premium handling.
### 14.11.2 Upstream Escalation (Suppliers & Platforms)
You SHALL escalate upstream only after capturing:
 - ticket number
 - impacted device model + firmware + configuration snapshot
 - error logs or server-side evidence
 - exact timestamps (EAT)
 - steps already attempted
*Data hygiene.* You SHALL not expose customer PII or sensitive security details in supplier tickets unless contractually required and approved.

## 14.12 Preventative & Corrective Maintenance (Operational Discipline)
### 14.12.1 Known Causes of Poor Service (Risk Register You MUST Act On) ⚠
NAVAS telematics performance failures typically cluster into known failure points:
 - GPS issues (antenna disconnected, faulty module, underground parking, device orientation)
 - GSM/GPRS connectivity (no signal/shadow, SIM failure, telecom down, no data bundle)
 - Power issues (battery removed, tampering, harness loose, backup battery faults)
 - Tracking device quality (vibration, heat, dust, moisture, voltage surges)
 - Vehicle mismatch (wrong device/accessory selection, poor R&D, poor QA)
 - Install workmanship (short circuits, battery drain, electrical fires, dashboard damage)
 - Software quality (slow web/app, limited features, poor design)
 - Server reliability (poor host choice, no backup power, poor connectivity, weak security)
 - Customer service weakness (unclear SLA, slow MTTR, no compensation plan)
 - User training gaps (incompetent users; misuse/abuse incentives)
 - Supplier weakness (disorganized, under-resourced, poor support)
 - Asset location/accessibility (distance, security, asset availability)
 - Fuel monitoring complexity (irregular tanks, calibration difficulty, CANBus absence)
 - Hardware & software flexibility constraints (manufacturer limitations)
These causes MUST be mapped into:
 - problem categories,
 - SOP checklists,
 - training refreshers,
 - installation QA,
 - vendor procurement evaluation. ✅
### 14.12.2 Preventative Actions You SHALL Schedule
1. Weekly
 - Review top 10 alarms by volume (identify false positives)
 - Review top 10 incidents by repeat count (problem candidates)
 - Review device offline leaderboard (recurring offenders)
2. Monthly
 - Device firmware compatibility review (per product)
 - SIM bundle health + expiry review
 - Alarm profile review per customer segment (Enterprise vs SMB)
3. Quarterly
 - Installation QA audit (random sampling)
 - Knowledge base cleanup (retire outdated SOPs)
 - Supplier performance review

## 14.13 Customer Communication Templates (Use, Don't Improvise)
### 14.13.1 Acknowledgement (Within FRT Window)
*Template.*
✅ Ticket received: {Ticket#}
Affected asset(s): {Unit/Asset}
Status: Triaging
Next update: {Time, EAT}
ETA (if known): {ETA}
### 14.13.2 Field Dispatch Confirmation
 Technician scheduled: {Name/Team}
Arrival window: {ETA window}
Please confirm: {Location pin + contact person}
Requirements: {Access/PPE/parking}
### 14.13.3 Closure & Prevention
✅ Resolved: {Ticket#}
Root cause: {Cause}
Fix applied: {Fix}
Prevention: {Preventive action}
Kindly rate the support: {CSAT link}
*Trainer's note :* Use Progress Notifier automation to reduce "status chasing" and to protect the relationship during outages.

## 14.14 What "Good" Looks Like (Dashboards You Must Watch)
You SHALL maintain and review these KPIs weekly:
1. TTD (Time to Detect) – proactive monitoring effectiveness
2. FRT (First Response Time) – speed of acknowledgement
3. MTTR (Mean Time to Resolve) – actual repair speed
4. FCR (First Contact Resolution) – ability to resolve without multiple interactions
5. Escalation Rate – keep escalations controlled
6. Reopen Rate – quality of closure
7. CSAT – customer perception
8. Audit Completeness – evidence + timeline completeness
The AI strategy explicitly ties delivery performance and audit completeness to operational excellence and governance. ✅

## 14.15 Admin Checklist: Daily Incident Operations (Mandatory Routine) ✅
1. Start of day (08:30 EAT)
 - Review overnight alarms and open incidents
 - Identify any P1/P2 candidates
 - Confirm on-call handover notes are captured
2. Throughout the day
 - Ensure every new ticket has: classification, owner, SLA timer running
 - Confirm AI triage recommendations are reviewed (HIC)
 - Trigger dispatch immediately when remote diagnosis indicates physical work
3. End of day
 - Close or re-plan stale tickets; set next update time
 - Ensure evidence is attached for anything escalated
 - Flag recurring incidents for problem management review

[PAGE BREAK]
# 15. SECURITY, PRIVACY & COMPLIANCE

## 15.1 Security Posture (Admin Non‐Negotiables)
1. No secrets in code or tickets.
 You SHALL never paste API keys, credentials, or sensitive tokens into tickets, screenshots, or chat threads. Use secret managers and environment variables. ✅
2. 2FA is mandatory.
 You SHALL enforce 2FA for all privileged accounts (CMS owners, dealer admins, platform admins). ✅
3. Maker–Checker Controls for Risky Actions.
 High-impact changes SHALL require at least one peer or managerial review before execution (delete, suspend, billing changes, permission changes). The development playbook mandates maker–checker reviews and human verification. ✅

## 15.2 Access Governance (HIC + Automation)
You SHALL implement automated access reviews using an Access Governance Bot approach:
 - policy checks
 - access reviews
 - change logs (Directory + Odoo)
 - reduction of permission delays and breaches
*Run‐in rule.* *Access is granted fast, but reviewed faster.*
### 15.2.1 Required Access Review Cadence
1. Monthly: privileged users review (platform admins, dealer admins, finance admins)
2. Quarterly: customer account admin review (role drift, leavers, contractors)
3. Event-driven: immediate review after a security incident or suspected compromise

## 15.3 Data Privacy (Video + Location + People Tracking)
You SHALL treat the following as sensitive by default:
 - Live location and history (vehicle and personnel)
 - Driver identity data (RFID/iButton, DMS profile)
 - Video events and clips (DASHCAM/MDVR)
 - Cargo and temperature logs (cold chain/medical logistics)
*Best practice.* Minimize who can view, export, or share this data; apply least privilege; log all exports.

## 15.4 Auditability Requirements (What Must Be Logged)
The system admin SHALL ensure CMS logs capture:
1. user logins and session changes
2. permission changes
3. configuration changes (alarms, thresholds, integrations)
4. billing and token operations
5. incident escalations and closures
6. data exports

[PAGE BREAK]
# 16. TROUBLESHOOTING & RAPID RESTORATION PLAYBOOK

## 16.1 The Rule of Fast Triage
You SHALL triage issues in this order (fastest elimination first):
1. Is it global or local?
 - multiple accounts affected → platform issue
 - single unit affected → device/network/install issue
2. Is it connectivity, power, or configuration?
 These are the most common root cause clusters (GPS/GSM/Power/Device/Install). ✅
3. Can it be fixed remotely?
 - if remote fix possible → do it, document it
 - if field required → dispatch early, don't delay

## 16.2 Symptom → Likely Cause → First Actions (L1 Checklist)
### 16.2.1 "Unit Offline / No Data"
*Likely causes (top).*
 - GSM shadow / no carrier signal / SIM fault / no data bundle
 - power disconnection / tampering / harness loose
*First actions (remote).*
1. Confirm last message time and last coordinates
2. Check SIM status / bundle health
3. Check voltage/power telemetry (if available)
4. Check for a pattern: same customer/site/network?
5. Send self-service first actions to driver/site contact (HIC template)
*Escalate to field when:*
 - no data > 2 hours during operational time, or
 - power is lost repeatedly, or
 - customer is in a critical movement window (high-value cargo, VIP, school run)

### 16.2.2 "GPS Jumps / Wrong Location / No GPS Fix"
*Likely causes.*
 - GPS antenna disconnected/faulty; underground parking; device upside-down
*First actions.*
1. Confirm whether GSM data is still flowing (if yes, likely GPS antenna/fix issue)
2. Check reported satellites/HDOP (if available)
3. Ask customer: indoor parking? tunnels? basement?
4. If persistent outdoors → schedule inspection for antenna placement and grounding

### 16.2.3 "Fuel Drop Alerts Too Frequent / False Fuel Theft"
*Reality check.* Measuring liquid is difficult; calibration and tank irregularities are common failure sources.
*First actions.*
1. Check tank profile (irregular tanks require more calibration points)
2. Validate sensor wiring and grounding (noise causes spikes)
3. Compare with ignition state and movement (sloshing vs theft)
4. Adjust alert thresholds and apply debounce rules
5. If needed: book recalibration (see target times)

### 16.2.4 "Dashcam/MDVR Not Uploading Clips / Video Events Missing"
*Likely causes.*
 - bandwidth constraints; storage retention rules; device overheating; SIM bundle issues
 - camera connection fault or SD/storage fault
*First actions.*
1. Confirm device is online and reporting events
2. Confirm storage health (SD/HDD status if available)
3. Confirm network coverage and data bundle
4. For urgent incidents: request on-site retrieval when upload is impossible
5. Keep customer updated with a clear ETA for evidence delivery (Progress Notifier)

## 16.3 Corrective vs Preventative Actions (Admin Must Decide)
1. Corrective action fixes the immediate incident (replace SIM, rewire harness, recalibrate sensor).
2. Preventative action eliminates recurrence (update install SOP, vendor QA, training refresher, alarm tuning). ✅
*Run‐in directive.* *If the same incident happens twice, it becomes a problem ticket.* That is where you stop firefighting and start fixing systems.

## 16.4 When to Trigger a Problem Management Review
You SHALL trigger problem management when:
 - the same issue repeats on the same asset/customer ≥ 2 times in 30 days
 - multiple customers show the same symptom pattern (possible platform/vendor issue)
 - the incident exposed a security/privacy risk
 - the incident caused SLA breach or reputational damage
Use Health Sentinel + Ops Insights to detect patterns early and reduce time-to-detect to minutes.

## 16.5 Admin "Do Not Do" List (Avoid Self‐Inflicted Outages) ⚠
1. Do not change alarm rules globally without a rollback plan.
2. Do not grant broad permissions "temporarily" without an expiry date.
3. Do not close tickets without evidence and customer update.
4. Do not dispatch field staff without access confirmation and spares confirmation.
5. Do not paste secrets/PII into AI tools or tickets. ✅

[PAGE BREAK]
✅ If you want me to keep going immediately: the next sections I will generate are (17) Appendix: Incident Forms & Templates, (18) Appendix: Product-Specific SOPs (Dash AI, OLIWA, Mafuta, Kago, Piki, etc.), and (19) Appendix: CMS Admin Checklists & Audit Sheets—continuing in the same format.
# 14. INCIDENT MANAGEMENT & ESCALATION  ̄

*Alignment note (QMS).* This section is aligned to the 3D Services escalation and incident governance approach (3DS‐QSP‐18, Rev 1, dated 01.NOV.2024) and is mandatory for all CMS System Administrators operating the NAVAS platform in Uganda & Kenya. ✅

## 14.1 Purpose & Scope
*Purpose.* You SHALL operate the CMS Incident Management capability as the single operational control point for:
1. Detection of failures before the customer calls (proactive monitoring).
2. Intake and triage of issues (correct classification + correct owner + correct SLA timer).
3. Escalation (internal + upstream suppliers) with auditability.
4. Field dispatch (when physical action is required).
5. Customer communications (timely, factual, and expectation-managed).
6. Problem management (prevent repeat incidents through corrective actions).
*Scope.* Applies to all 3D products and service types, including:
 - Vehicle Telematics: OLIWA / OLIWA‐PLUS, iVMS / iVMS‐PLUS, GUVNA
 - AI & Video Telematics: DASHCAM, DASH AI, MDVR, MDVR AI
 - Fuel Telematics: MAFUTA FLS, MAFUTA CANBUS, MAFUTA FLOW METER, MAFUTA FUEL CARD, MAFUTA STATION, GENSET
 - Goods-in-Transit & IoT: KAGO, PASO, PAWA, THERMO
 - Personnel Tracing: CAPO, PATROL, PIKI, TOTO, WIATAG
 - Add‐On Apps: BI Dashboards, DSC, ECO, FleetRun, INSPECTA, JMS, LOGISTICS, NIMBUS, VEBA
 - Value Added Services: Help Desk & Training, GIS & JMS, SATO, Local Owned Server, OEM Integrations

## 14.2 Operating Principles (Non‐Negotiable)
1. Single Source of Truth (SSOT).
 All incidents SHALL have one authoritative record (ticket/incident) in CMS (or the integrated ticket system surfaced in CMS). No "shadow resolution" in WhatsApp groups or personal calls without a ticket. ⚠
2. Evidence Before Action.
 You MUST capture *minimum evidence* before changing configuration, dispatching, or escalating upstream. Evidence includes:
 - Unit/asset identifier(s)
 - Time window of failure
 - Customer impact statement
 - Last known connectivity state and key parameters (power, GPS, GSM, sensors)
 - Screenshots/log snippets/telemetry extracts
3. HIC/HITL Control Always Applies.
 AI may recommend classification and actions, but a human MUST confirm all high-impact decisions (P1 triage approvals, quote approvals, suspension/resume approvals, KB publish review). ✅
4. Customer Communication = SLA Protection.
 If you cannot fix immediately, you SHALL still communicate: *ticket number + status + ETA + next update time*. Lack of updates is treated as service failure even when the technical fix is in progress.

## 14.3 CMS Module Map (What You Operate)
In CMS, the administrator operates the following blades (modules) and their associated "cards" (detail panels):
### 14.3.1 Incident & Ops Center Module (Core)
*Objects and CRUD responsibilities.*
1. Incident Ticket (Create / Read / Update / Close)
2. Alarm Event (Read / Link to incident / Acknowledge)
3. Work Order / Job Card (Create / Assign / Close)
4. Dispatch Task (Create / Route / Update / Close)
5. Post‐Incident Review (Create / Approve / Publish)
6. Knowledge Base Article (Draft / Review / Publish / Retire)
### 14.3.2 Detail Blade Structure (Standard)
*Incident Detail Blade.* You SHALL expect these cards and populate them consistently:
 - Summary Card: title, severity, status, owner, customer, affected assets
 - SLA Card: timers (FRT, MTTR), breach risk indicator
 - Impact Card: operational + financial + safety impact
 - Asset Telemetry Card: last packets, voltage, GPS, GSM, sensor values
 - Timeline Card: all actions (human + AI) with timestamps
 - Communications Card: outbound messages, inbound updates, acknowledgements
 - Attachments Card: photos, wiring diagrams, logs, customer evidence
 - Actions Card: escalate, dispatch, request access, request spares, close

## 14.4 Incident Lifecycle (Mandatory Workflow)
You SHALL manage every incident using the following lifecycle states:
1. Detected (system or user)
2. Logged (ticket created, minimum fields complete)
3. Triaged (severity + category + assignment set; SLA timer started)
4. Diagnosing (remote checks, evidence gathering, hypothesis)
5. Mitigated (service restored partially or workaround applied)
6. Resolved (root cause fixed)
7. Validated (QA verification + customer confirmation where applicable)
8. Closed (documented + tagged + preventive action assigned if needed)
9. Problem Review (repeat incidents → corrective plan)
*Run‐in rule.* *If it's not logged, it did not happen.* This protects you operationally and legally.

## 14.5 Business Hours, Support Coverage & Response Targets
### 14.5.1 Support Coverage
You MUST operate with the defined service window:
 - Standard business hours: 08:30–17:30 EAT, Monday–Saturday, excluding national public holidays
 - On‐call coverage exists for Sundays and public holidays (after‐hours support)
### 14.5.2 Minimum Required Info for Escalations
When raising an escalation request, you SHALL provide:
 - Reason for escalation
 - Severity level
 - Customer impact
 - Any evidence already collected
### 14.5.3 Point of Contact Response Time Targets
You SHALL enforce the following operational targets:
| Point of Contact | Target Response Time |
| Standard Support Hours (Phone) | 15 minutes |
| After Hours (Phone) | 60 minutes |
| Standard Support Hours (Email) | 2 hours |
| After Hours (Email) | Next business day |
| WhatsApp | 5 minutes |
| Walk‐in | Immediately |
| On‐site | 3–8 hours (subject to product/field constraints) |

✅ These targets are explicitly defined and MUST be tracked in CMS dashboards.

## 14.6 Severity Classification (P1–P4)
You SHALL use a severity model that aligns to customer impact:
1. P1 (Critical)
 - Safety risk, security breach, widespread outage, or major customer operational halt
 - Immediate management visibility required
 - HIC gate: *P1 triage approvals required* ✅
2. P2 (High) ⚠
 - Degraded service affecting key operations or multiple assets
 - Workaround may exist, but risk of escalation is high
3. P3 (Medium)
 - Localized issue affecting limited scope; workaround exists; no immediate safety risk
4. P4 (Low)
 - Minor issue, informational requests, cosmetic UI items, "how‐to" queries
*Run‐in policy.* *Severity is about impact, not emotion.* You SHALL downgrade/upgrade only with documented evidence (Impact Card + SLA Card).

## 14.7 Alarm Center & Event Triggers (Your Detection Engine)  ̈
### 14.7.1 Configure Alarm Triggers by Product Domain
NAVAS supports a broad alarm trigger catalog that you SHALL map into product‐specific alarm profiles, e.g.:
 - Fuel: fuel drop, rapid fuel consumption, fuel refill, fuel level low
 - Safety/Driving: overspeeding, harsh braking, harsh acceleration, harsh cornering
 - Geofence & Security: geofence breach, unauthorized movement, door open/close, cargo compartment intrusion
 - Video AI: driver on phone, fatigue alert, seatbelt unbuckled, lane departure, forward collision warning
 - IoT/Cold Chain: temperature deviation, humidity deviation
 - Maintenance: engine hours reached for service, preventative maintenance triggers
### 14.7.2 Alarm Profile Governance
You SHALL implement alarm profiles as controlled configuration objects:
1. Create a profile per product family (Vehicle, Fuel, Video, GIT/IoT, Personnel).
2. Attach profile to: account → group → unit(s).
3. Configure thresholds (speed limits, geofence rules, sensor bounds).
4. Define channels (screen, email, WhatsApp, SMS, API webhooks).
5. Apply quiet hours and deduplication rules to reduce alert fatigue.

## 14.8 Target Installation & Repair Time by Product (Field SLA Control)
You SHALL use the published targets to plan dispatch, schedule customers, and manage expectations:
| Service Type | Product | Target Install Time | Target Repair Time |
| AI & Video Telematics | Dash AI | 4.5 hrs | 3 hrs |
| | Dashcam | 4 hrs | 3 hrs |
| | MDVR | 8 hrs | 3 hrs |
| | MDVR AI | 8 hrs | 3 hrs |
| Vehicle Telematics | iVMS | 3 hrs | 2 hrs |
| | iVMS‐Plus | 4 hrs | 3 hrs |
| | OLIWA | 3 hrs | 2 hrs |
| | OLIWA‐Plus | 4 hrs | 3 hrs |
| | Speed Governor | 2 hrs | 1 hr |
| Fuel Telematics | Mafuta FLS | 8 hrs | 3 hrs *(recalibration: 8 hrs)* |
| | Mafuta Station | TBD | TBD |
| | Mafuta Fuel Card | TBD | TBD |
| | Mafuta CANBUS | 4 hrs | 3 hrs |
| | Mafuta Flow Meter | 3 hrs | 2 hrs |
| Personnel Tracing | CAPO | 1 hr | 30 mins |
| | PIKI | 3 hrs | 2 hrs |
| | TOTO | 1 hr | 30 mins |
| | WIATAG | 1 hr | 30 mins |
| | PATROL | 4 hrs | 2 hrs |
| Goods & IoT | GENSET | 8 hrs | 3 hrs *(recalibration: 8 hrs)* |
| | KAGO | 4 hrs | 3 hrs |
| | THERMO | 2 hrs | 1 hr |
| | PASO | 1 hr | 1 hr |
| | PAWA | 4 hrs | 3 hrs |

These targets SHALL be reflected in:
 - scheduling,
 - customer ETA communication,
 - SLA dashboards,
 - workforce utilization reports. ✅

## 14.9 Dispatch & On‐Site Response Management (EA Context)
### 14.9.1 On‐Site Response Timing by Distance
Where field attendance is required, you SHALL plan travel expectations by distance (regional reality check):
 - ≤ 50 km: target reach 1 hour
 - ≤ 100 km: target reach 2 hours
 - ≥ 110 km: target reach 24 hours (requires scheduling and customer confirmation)
### 14.9.2 Dispatch Readiness Checklist (Must Complete Before Sending a Technician)
*Run‐in and italicized per policy.
Access & Coordination.* You SHALL confirm before dispatch:
1. Site pin/location (WhatsApp live location or Google Maps pin)
2. Security clearance (who will open the gate, who is the contact)
3. Asset availability (vehicle/bike present? driver available?)
4. Spare parts availability (SIM, harness, sensor, camera, power monitor)
5. Tools & PPE (as required)
6. Job card + SOP attached to the ticket
This aligns with the "Field Ops Router + Scheduler" logic (skills + parts + routing).

## 14.10 HIC + AI Playbook Inside Incident Operations
### 14.10.1 AI Roles You SHALL Enable
You SHALL enable (at minimum) the following AI agent behaviours for incident operations:
1. Health Sentinel (Proactive Detection)
 - Detect anomalies (no data, GNSS drift, power loss)
 - Correlate with network/SIM issues
 - Auto‐open a ticket with evidence
 - Notify stakeholders early
2. Resolution Co‐Pilot (L1 Guidance)
 - Summarize ticket
 - Pull telemetry context
 - Suggest SOP steps
 - Auto‐draft internal notes
 - Start SLA timers
3. Self‐Service Coach + Alert Orchestrator (Driver/End‐User First Actions)
 - Deliver WhatsApp "first actions" instructions
 - Reduce avoidable escalations
4. Progress Notifier (Customer Communications)
 - Milestone pings and "next update time" messages
 - Reduce uncertainty and follow‐ups
### 14.10.2 HITL Gates You MUST Enforce
AI can recommend. Humans decide. You SHALL enforce human sign‐off for:
 - P1 triage approvals
 - Quote approvals
 - Finance approvals for suspension/resume
 - Knowledge base publish review
### 14.10.3 KPI Targets (AI + Human Combined)
The AI strategy explicitly targets operational KPIs including:
 - Latency for P1: *< 2 minutes*
 - FRT (First Response Time)
 - MTTR (Mean Time To Resolve)
 - CSAT and audit completeness
*Trainer's directive :* Your job is not to "use AI". Your job is to raise reliability and reduce repeat incidents while maintaining auditability.

## 14.11 Escalation Protocol (Internal + Upstream)
### 14.11.1 Internal Escalation (L1 → L2 → Field → Management)
You SHALL escalate when any of the following are true:
1. SLA breach risk is > 50% (SLA Card indicates red/amber).
2. Safety/security implication exists (panic, intrusion, tamper, crash).
3. Issue affects multiple customers or multiple units (suspected platform outage).
4. Root cause is unknown after the standard diagnosis checklist.
5. Customer is a strategic/high‐risk account and expects premium handling.
### 14.11.2 Upstream Escalation (Suppliers & Platforms)
You SHALL escalate upstream only after capturing:
 - ticket number
 - impacted device model + firmware + configuration snapshot
 - error logs or server-side evidence
 - exact timestamps (EAT)
 - steps already attempted
*Data hygiene.* You SHALL not expose customer PII or sensitive security details in supplier tickets unless contractually required and approved.

## 14.12 Preventative & Corrective Maintenance (Operational Discipline)
### 14.12.1 Known Causes of Poor Service (Risk Register You MUST Act On) ⚠
NAVAS telematics performance failures typically cluster into known failure points:
 - GPS issues (antenna disconnected, faulty module, underground parking, device orientation)
 - GSM/GPRS connectivity (no signal/shadow, SIM failure, telecom down, no data bundle)
 - Power issues (battery removed, tampering, harness loose, backup battery faults)
 - Tracking device quality (vibration, heat, dust, moisture, voltage surges)
 - Vehicle mismatch (wrong device/accessory selection, poor R&D, poor QA)
 - Install workmanship (short circuits, battery drain, electrical fires, dashboard damage)
 - Software quality (slow web/app, limited features, poor design)
 - Server reliability (poor host choice, no backup power, poor connectivity, weak security)
 - Customer service weakness (unclear SLA, slow MTTR, no compensation plan)
 - User training gaps (incompetent users; misuse/abuse incentives)
 - Supplier weakness (disorganized, under-resourced, poor support)
 - Asset location/accessibility (distance, security, asset availability)
 - Fuel monitoring complexity (irregular tanks, calibration difficulty, CANBus absence)
 - Hardware & software flexibility constraints (manufacturer limitations)
These causes MUST be mapped into:
 - problem categories,
 - SOP checklists,
 - training refreshers,
 - installation QA,
 - vendor procurement evaluation. ✅
### 14.12.2 Preventative Actions You SHALL Schedule
1. Weekly
 - Review top 10 alarms by volume (identify false positives)
 - Review top 10 incidents by repeat count (problem candidates)
 - Review device offline leaderboard (recurring offenders)
2. Monthly
 - Device firmware compatibility review (per product)
 - SIM bundle health + expiry review
 - Alarm profile review per customer segment (Enterprise vs SMB)
3. Quarterly
 - Installation QA audit (random sampling)
 - Knowledge base cleanup (retire outdated SOPs)
 - Supplier performance review

## 14.13 Customer Communication Templates (Use, Don't Improvise)
### 14.13.1 Acknowledgement (Within FRT Window)
*Template.*
✅ Ticket received: {Ticket#}
Affected asset(s): {Unit/Asset}
Status: Triaging
Next update: {Time, EAT}
ETA (if known): {ETA}
### 14.13.2 Field Dispatch Confirmation
 Technician scheduled: {Name/Team}
Arrival window: {ETA window}
Please confirm: {Location pin + contact person}
Requirements: {Access/PPE/parking}
### 14.13.3 Closure & Prevention
✅ Resolved: {Ticket#}
Root cause: {Cause}
Fix applied: {Fix}
Prevention: {Preventive action}
Kindly rate the support: {CSAT link}
*Trainer's note :* Use Progress Notifier automation to reduce "status chasing" and to protect the relationship during outages.

## 14.14 What "Good" Looks Like (Dashboards You Must Watch)
You SHALL maintain and review these KPIs weekly:
1. TTD (Time to Detect) – proactive monitoring effectiveness
2. FRT (First Response Time) – speed of acknowledgement
3. MTTR (Mean Time to Resolve) – actual repair speed
4. FCR (First Contact Resolution) – ability to resolve without multiple interactions
5. Escalation Rate – keep escalations controlled
6. Reopen Rate – quality of closure
7. CSAT – customer perception
8. Audit Completeness – evidence + timeline completeness
The AI strategy explicitly ties delivery performance and audit completeness to operational excellence and governance. ✅

## 14.15 Admin Checklist: Daily Incident Operations (Mandatory Routine) ✅
1. Start of day (08:30 EAT)
 - Review overnight alarms and open incidents
 - Identify any P1/P2 candidates
 - Confirm on-call handover notes are captured
2. Throughout the day
 - Ensure every new ticket has: classification, owner, SLA timer running
 - Confirm AI triage recommendations are reviewed (HIC)
 - Trigger dispatch immediately when remote diagnosis indicates physical work
3. End of day
 - Close or re-plan stale tickets; set next update time
 - Ensure evidence is attached for anything escalated
 - Flag recurring incidents for problem management review

[PAGE BREAK]
# 15. SECURITY, PRIVACY & COMPLIANCE

## 15.1 Security Posture (Admin Non‐Negotiables)
1. No secrets in code or tickets.
 You SHALL never paste API keys, credentials, or sensitive tokens into tickets, screenshots, or chat threads. Use secret managers and environment variables. ✅
2. 2FA is mandatory.
 You SHALL enforce 2FA for all privileged accounts (CMS owners, dealer admins, platform admins). ✅
3. Maker–Checker Controls for Risky Actions.
 High-impact changes SHALL require at least one peer or managerial review before execution (delete, suspend, billing changes, permission changes). The development playbook mandates maker–checker reviews and human verification. ✅

## 15.2 Access Governance (HIC + Automation)
You SHALL implement automated access reviews using an Access Governance Bot approach:
 - policy checks
 - access reviews
 - change logs (Directory + Odoo)
 - reduction of permission delays and breaches
*Run‐in rule.* *Access is granted fast, but reviewed faster.*
### 15.2.1 Required Access Review Cadence
1. Monthly: privileged users review (platform admins, dealer admins, finance admins)
2. Quarterly: customer account admin review (role drift, leavers, contractors)
3. Event-driven: immediate review after a security incident or suspected compromise

## 15.3 Data Privacy (Video + Location + People Tracking)
You SHALL treat the following as sensitive by default:
 - Live location and history (vehicle and personnel)
 - Driver identity data (RFID/iButton, DMS profile)
 - Video events and clips (DASHCAM/MDVR)
 - Cargo and temperature logs (cold chain/medical logistics)
*Best practice.* Minimize who can view, export, or share this data; apply least privilege; log all exports.

## 15.4 Auditability Requirements (What Must Be Logged)
The system admin SHALL ensure CMS logs capture:
1. user logins and session changes
2. permission changes
3. configuration changes (alarms, thresholds, integrations)
4. billing and token operations
5. incident escalations and closures
6. data exports

[PAGE BREAK]
# 16. TROUBLESHOOTING & RAPID RESTORATION PLAYBOOK

## 16.1 The Rule of Fast Triage
You SHALL triage issues in this order (fastest elimination first):
1. Is it global or local?
 - multiple accounts affected → platform issue
 - single unit affected → device/network/install issue
2. Is it connectivity, power, or configuration?
 These are the most common root cause clusters (GPS/GSM/Power/Device/Install). ✅
3. Can it be fixed remotely?
 - if remote fix possible → do it, document it
 - if field required → dispatch early, don't delay

## 16.2 Symptom → Likely Cause → First Actions (L1 Checklist)
### 16.2.1 "Unit Offline / No Data"
*Likely causes (top).*
 - GSM shadow / no carrier signal / SIM fault / no data bundle
 - power disconnection / tampering / harness loose
*First actions (remote).*
1. Confirm last message time and last coordinates
2. Check SIM status / bundle health
3. Check voltage/power telemetry (if available)
4. Check for a pattern: same customer/site/network?
5. Send self-service first actions to driver/site contact (HIC template)
*Escalate to field when:*
 - no data > 2 hours during operational time, or
 - power is lost repeatedly, or
 - customer is in a critical movement window (high-value cargo, VIP, school run)

### 16.2.2 "GPS Jumps / Wrong Location / No GPS Fix"
*Likely causes.*
 - GPS antenna disconnected/faulty; underground parking; device upside-down
*First actions.*
1. Confirm whether GSM data is still flowing (if yes, likely GPS antenna/fix issue)
2. Check reported satellites/HDOP (if available)
3. Ask customer: indoor parking? tunnels? basement?
4. If persistent outdoors → schedule inspection for antenna placement and grounding

### 16.2.3 "Fuel Drop Alerts Too Frequent / False Fuel Theft"
*Reality check.* Measuring liquid is difficult; calibration and tank irregularities are common failure sources.
*First actions.*
1. Check tank profile (irregular tanks require more calibration points)
2. Validate sensor wiring and grounding (noise causes spikes)
3. Compare with ignition state and movement (sloshing vs theft)
4. Adjust alert thresholds and apply debounce rules
5. If needed: book recalibration (see target times)

### 16.2.4 "Dashcam/MDVR Not Uploading Clips / Video Events Missing"
*Likely causes.*
 - bandwidth constraints; storage retention rules; device overheating; SIM bundle issues
 - camera connection fault or SD/storage fault
*First actions.*
1. Confirm device is online and reporting events
2. Confirm storage health (SD/HDD status if available)
3. Confirm network coverage and data bundle
4. For urgent incidents: request on-site retrieval when upload is impossible
5. Keep customer updated with a clear ETA for evidence delivery (Progress Notifier)

## 16.3 Corrective vs Preventative Actions (Admin Must Decide)
1. Corrective action fixes the immediate incident (replace SIM, rewire harness, recalibrate sensor).
2. Preventative action eliminates recurrence (update install SOP, vendor QA, training refresher, alarm tuning). ✅
*Run‐in directive.* *If the same incident happens twice, it becomes a problem ticket.* That is where you stop firefighting and start fixing systems.

## 16.4 When to Trigger a Problem Management Review
You SHALL trigger problem management when:
 - the same issue repeats on the same asset/customer ≥ 2 times in 30 days
 - multiple customers show the same symptom pattern (possible platform/vendor issue)
 - the incident exposed a security/privacy risk
 - the incident caused SLA breach or reputational damage
Use Health Sentinel + Ops Insights to detect patterns early and reduce time-to-detect to minutes.

## 16.5 Admin "Do Not Do" List (Avoid Self‐Inflicted Outages) ⚠
1. Do not change alarm rules globally without a rollback plan.
2. Do not grant broad permissions "temporarily" without an expiry date.
3. Do not close tickets without evidence and customer update.
4. Do not dispatch field staff without access confirmation and spares confirmation.
5. Do not paste secrets/PII into AI tools or tickets. ✅

[PAGE BREAK]
✅ If you want me to keep going immediately: the next sections I will generate are (17) Appendix: Incident Forms & Templates, (18) Appendix: Product-Specific SOPs (Dash AI, OLIWA, Mafuta, Kago, Piki, etc.), and (19) Appendix: CMS Admin Checklists & Audit Sheets—continuing in the same format.
According to a document from 01.Nov.2024 (3DS-QSP-18), 3D Services Limited's escalation process sets mandatory support hours, response targets, and MTTR controls that MUST be operationalized inside NAVAS CMS for reliable delivery in Uganda & Kenya.
Below are Sections 17, 18, and 19 (continuation) — written in trainer-grade, implementable, system-admin language ✅.

# 17. APPENDIX A — ADMIN CHECKLISTS ✅

## 17.1 How To Use These Checklists
*Policy Statement:* You SHALL treat these checklists as non-negotiable operational controls. Any skipped control becomes a predictable incident, revenue leak, or compliance breach.
1. Execute on schedule
 - Daily: operational readiness + alarm triage + revenue protection.
 - Weekly: trends + hygiene + access governance.
 - Monthly: compliance + audit + resilience + pricing governance.
2. Capture evidence
 - Every "Done" item MUST be traceable to:
 - a CMS audit log entry,
 - a ticket reference,
 - a report export,
 - or a screenshot attachment in Odoo/Helpdesk.
3. HIC enforcement
 - If AI recommends an action that changes access, billing, or customer service state:
 - you MUST apply HIC approval (maker–checker) before execution. ✈
 - This aligns to NAVAS governance norms requiring human verification before merges/approvals and avoiding uncontrolled automation.
✅ Key Takeaway: The goal is not "activity." The goal is repeatable reliability and auditable control.

## 17.2 Support Hours & SLA Targets
*Operating Window:* Business hours are 08:30–17:30 EAT (Mon–Sat) excluding Ugandan public holidays; on-call exists for Sundays/public holidays, and urgent support may be handled outside hours.
### 17.2.1 Response Targets By Channel (Mandatory)
Use this table to enforce service quality and reduce "follow-up fatigue" for customers.
| Support Channel | Target Response Time | Enforcement Inside CMS |
| Phone (standard hours) | ≤ 15 min | SLA timers + escalation rules |
| Phone (after hours) | ≤ 60 min | On-call routing + P1 override |
| Email (standard hours) | ≤ 2 hrs | Queue aging + auto reminders |
| Email (after hours) | Next business day | Scheduled triage window |
| WhatsApp | ≤ 5 min | Fast-lane templates + routing |
| Walk-in | Immediate | "Live ticket" creation |
| On-site | 3–8 hrs (product-dependent) | Dispatch + ETA updates |

*Trainer Note:* In EA markets, WhatsApp is the highest-impact SLA channel for perception of speed. If you win WhatsApp response time, you win trust. ✅

## 17.3 MTTR Control Metrics You MUST Track
These are reliability KPIs, not "nice-to-haves." They MUST be visible in CMS dashboards and reviewed weekly.
| Metric | Definition | Target |
| RTRS | Response time to reach site | Based on distance (≤50km: 1hr; ≤100km: 2hrs; \\>110km: 24hrs) |
| FCR | First Contact Resolution | ≤ 30 mins |
| MRT | Mean Resolution Time | ≤ 24 hrs |
| TVTB | Ticket volume vs backlog | Reduce backlog by 10% per week |
| ER | Escalation rate | Keep escalations under 10% |
| ART | Average response time | ≤ 15 mins |

⚠ Risk Control: Escalation rate is the "silent killer." When ER rises, your field costs spike, your MTTR worsens, and customer churn follows.

## 17.4 Daily Admin Checklist (Command, Control & Reliability)  ̄
*Timebox:* 15–20 minutes (every morning, before customer peak time).
### 17.4.1 Platform Health & Incident Readiness
☐ Review system health widgets (ingestion, SMS/WhatsApp gateway status, queue lag).
☐ Confirm "P1/P2 routing" is active for Uganda & Kenya.
☐ Validate after-hours escalation path is reachable (do NOT test with live customer data).
☐ Verify that Alarm Center is not accumulating "unowned" alarms beyond threshold.
☐ Confirm audit logging is enabled for:
 - impersonation / act-on-behalf actions ✈
 - token policy edits
 - notification template changes
*HIC Gate:* If a setting affects multiple tenants, you MUST use maker–checker approval before saving.
### 17.4.2 Alarm Triage (Stop Revenue & Trust Bleeding)
☐ Sort alarms by: severity → customer tier → recurrence.
☐ Close duplicates using correlation rules (avoid "alarm storms").
☐ For offline/communication alarms:
 - tag SIM status,
 - last GPS time,
 - last power reading,
 - and device type.
### 17.4.3 Customer Communication (CX Discipline)
☐ Confirm WhatsApp templates are ready for top 5 alarms (offline, tamper, overspeed, fuel drop, geofence breach).
☐ Ensure quiet hours are respected for non-critical notifications (avoid customer anger).
☐ Ensure "ETA to fix" is communicated on any incident that exceeds FCR window.
✅ CX Tactic: Never say "We are checking." Say what you checked + what is next + when. This alone reduces follow-ups by 30–50%.

## 17.5 Daily Admin Checklist (Tokenomics & Margin Protection)
*Objective:* Keep pricing predictable, stop abuse, and protect margins.
### 17.5.1 Token Policy Safeguards (Non-Negotiable)
☐ Confirm low-balance alerts active at 80% usage (soft alert) and hard-stop thresholds configured where required.
☐ Confirm monthly caps (where applied) are not exceeded.
☐ Confirm "parameter-level usage logging" is active for auditability.
These safeguards are explicitly required in NAVAS token governance.
### 17.5.2 Token Burn Anomaly Scan
☐ Identify tenants with sudden spikes in:
 - messaging tokens (SMS/WhatsApp),
 - AI inference tokens,
 - video bandwidth/storage tokens.
 ☐ For each spike:
<!-- end list -->
1. confirm it is explained by real operational activity,
2. verify it is not caused by misconfigured notification rules,
3. check if a "runaway" template or repeated event trigger exists.
### 17.5.3 Pricing Governance (Admin Discipline)
*Core Formula Awareness:* Token pricing uses a formula multiplying base cost by commercial and technical factors (RPS, time, compute, market, scarcity). You MUST understand this because it explains why AI/video tokens are protected.
⚠ Margin Trap: If you discount GPU/video tokens casually, you create a loss-making contract that cannot be "optimized" later.

## 17.6 Daily Admin Checklist (Connectivity & SIM Intelligence)
☐ Review offline list sorted by "last seen" and "fleet importance."
☐ Check roaming mismatches (UG unit roaming in KE or vice versa) and confirm bundle coverage.
☐ Identify SIMs with high data consumption but low telematics value (misconfiguration suspected).
☐ Flag repeated drop-offs as potential:
 - antenna issue,
 - power instability,
 - SIM lock/expiry,
 - APN misconfig.

## 17.7 Daily Admin Checklist (Messaging & Alerts)
NAVAS supports a wide event trigger ecosystem. Admins MUST control:
 - who gets alerts,
 - when,
 - and how often.
### 17.7.1 High-Impact Event Triggers (Minimum Set)
You MUST ensure these triggers are configured for relevant products:
 - Overspeed alerts
 - Fuel drop / rapid fuel consumption
 - Geofence entry/exit
 - Panic button activation
 - Excessive idling
 - Temperature deviation (cold chain)
 - Driver fatigue / distracted driving alerts
These are explicitly listed among key triggers.
*Anti-spam tactic:* Bundle low-severity events into digest notifications to reduce alert fatigue.

## 17.8 Field Ops & Installation Checklists (Delivery Discipline)
*Purpose:* Every sloppy install becomes a support ticket. This checklist prevents "repeat failures."
### 17.8.1 Job Ticket Creation & Allocation Timing
☐ Ticket created immediately upon request / job confirmation.
☐ Device approval within 10 minutes of request (where applicable).
☐ Job allocation/ticketing within 15 minutes after request receipt.
☐ Device sign-out + testing completed within 30 minutes after ticket.
### 17.8.2 Target Install & Repair Times (By Product)
Use this as a planning and SLA enforcement table.
| Service Type | Product | Time To Install | Time To Repair |
| AI & Video | DASH AI | 4.5 hrs | 3 hrs |
| AI & Video | DASHCAM | 4 hrs | 3 hrs |
| AI & Video | MDVR | 8 hrs | 3 hrs |
| AI & Video | MDVR AI | 8 hrs | 3 hrs |
| Vehicle Telematics | iVMS | 3 hrs | 2 hrs |
| Vehicle Telematics | iVMS-PLUS | 4 hrs | 3 hrs |
| Vehicle Telematics | OLIWA | 3 hrs | 2 hrs |
| Vehicle Telematics | OLIWA-PLUS | 4 hrs | 3 hrs |
| Vehicle Telematics | Speed Governor | 2 hrs | 1 hr |
| Fuel Telematics | Mafuta FLS | 8 hrs | 3 hrs (+ recalibration 8 hrs) |
| Fuel Telematics | Mafuta CANBUS | 4 hrs | 3 hrs |
| Fuel Telematics | Mafuta Flow Meter | 3 hrs | 2 hrs |
| Personnel Tracing | CAPO | 1 hr | 30 min |
| Personnel Tracing | PIKI | 3 hrs | 2 hrs |
| Personnel Tracing | TOTO | 1 hr | 30 min |
| Personnel Tracing | WIATAG | 1 hr | 30 min |
| Personnel Tracing | PATROL | 4 hrs | 2 hrs |
| Goods & IoT | GENSET | 8 hrs | 3 hrs (+ recalibration 8 hrs) |
| Goods & IoT | KAGO | 4 hrs | 3 hrs |
| Goods & IoT | THERMO | 2 hrs | 1 hr |
| Goods & IoT | PASO | 1 hr | 1 hr |
| Goods & IoT | PAWA | 4 hrs | 3 hrs |

✅ Field Excellence Rule: If an install exceeds target time, you MUST capture a cause code (vehicle type, wiring complexity, access constraint, parts shortage). That data prevents future misses.

## 17.9 Preventative Maintenance (PM) Checklists By Product Family
PM is not only mechanical; it is data reliability maintenance.
### 17.9.1 AI & Video Telematics (DASH AI / DASHCAM / MDVR / MDVR AI)
☐ Lens cleanliness checked (front + cabin + side cameras if applicable).
☐ SD/HDD health checked; storage usage < 80%.
☐ Upload bandwidth validated (avoid silent failures).
☐ AI event thresholds reviewed monthly (reduce false positives).
☐ Night driving/low-light sensitivity reviewed (context-based tuning).
### 17.9.2 Fuel Telematics (MAFUTA FLS / FLOW METER / CANBUS / FUEL CARD / STATION) ⛽
☐ FLS calibration verified (especially after tank repairs).
☐ Flow meter seals checked (tamper risk).
☐ CANBUS MUST NOT be used alone as a fuel truth source; it must complement liquid level measurement where possible.
☐ Fuel drop thresholds reviewed per customer operations (avoid noise).
☐ Recalibration scheduled based on drift/variance patterns.
⚠ Fuel Risk Warning: Most "fuel theft disputes" are actually sensor drift + poor calibration discipline.
### 17.9.3 Vehicle Telematics (GUVNA / iVMS / iVMS-PLUS / OLIWA / OLIWA-PLUS)
☐ Device power stability check (brownouts cause ghost outages).
☐ GPS antenna placement re-validated after body repairs.
☐ Immobilizer relay wiring inspected (if installed).
☐ SIM expiry / bundle validity checked monthly.
☐ Overspeed rule alignment checked with customer policy.
### 17.9.4 Personnel Tracing (CAPO / PATROL / PIKI / TOTO / WIATAG) ♂
☐ Battery health and charging discipline verified.
☐ Location accuracy check (urban canyon vs rural).
☐ Panic button test scheduled monthly (controlled test).
☐ HR duty rules / resting hours alerts confirmed (where enabled).
☐ Device assignment audit (who has which tracker).
### 17.9.5 Goods-in-Transit & IoT (KAGO / PASO / PAWA / THERMO / GENSET)
☐ Temperature thresholds verified against cargo type (cold chain).
☐ Door open/close unauthorized rules active (intrusion).
☐ Genset service hours alerts enabled.
☐ Route risk / border exit alerts enabled for cross-border movements.
☐ Sensor integrity check: humidity, vibration, impact.
Many of these triggers exist as standard alert categories.

## 17.10 Corrective Maintenance (CM) Playbook — What You Do When Things Break
*Rule:* You MUST fix the root cause, not the symptom.
### 17.10.1 Unit Offline (Most Common Case)
1. Confirm "offline" is true:
 - last packet timestamp,
 - last GPS coordinates,
 - power state.
2. Classify:
 - SIM issue (bundle, APN, roaming, suspension)
 - power issue (wiring, fuse, ignition source)
 - device issue (firmware, hardware fault)
3. Apply response targets:
 - WhatsApp first response ≤ 5 min for urgent ops, and keep customer updated.
4. Decide remote vs on-site:
 - keep escalations under 10% (ER target).
### 17.10.2 Fuel Readings "Wrong"
1. Verify calibration history.
2. Compare:
 - consumption curve trend,
 - refuel events,
 - fuel drop events.
3. If CANBUS is the only source: you MUST treat it as supporting signal, not truth.
### 17.10.3 Video Events Missing
1. Check storage health and upload queue.
2. Validate triggers: harsh braking, FCW, LDW, fatigue events.
3. If AI inference results look wrong:
 - request evidence (clip ID, timestamps),
 - reduce scope,
 - document false positives for tuning. ✅
 (This pattern aligns to admin troubleshooting discipline.)

## 17.11 New Tenant Onboarding Checklist (Trainer-Grade)
*Commercial SLA expectation:* Standard lead times may be up to 21 business days for major service types; add-on apps can be faster (e.g., 3 business days) depending on scope.
### 17.11.1 Onboarding Gate 1 — Commercial Setup
☐ Tenant created with correct:
 - country (UG / KE),
 - currency (UGX/KES),
 - timezone (EAT),
 - territory ownership (dealer/reseller if relevant).
 ☐ Token SKU assigned (baseline bundle).
 ☐ Safeguards enabled: caps, alerts at 80%, hard stop thresholds if required.
### 17.11.2 Onboarding Gate 2 — Access & Governance
☐ RBAC roles created: Customer Admin, Operator, Auditor (least privilege).
☐ Impersonation ("act on behalf") enabled only for approved admins; audit log verified.
☐ AI features configured by policy:
 - Draft-only outputs initially, or
 - "HIC gated action" enabled for sensitive changes. ✈
### 17.11.3 Onboarding Gate 3 — Product Enablement (3D Portfolio Alignment)
☐ Enable correct apps based on customer solution:
 - Vehicle Telematics (GUVNA / iVMS / OLIWA / OLIWA-PLUS)
 - Fuel Telematics (MAFUTA family)
 - AI & Video Telematics (DASHCAM / MDVR / DASH AI)
 - Personnel Tracing (PIKI / PATROL / etc.)
 - Goods & IoT (KAGO / THERMO / etc.)
 - Add-on apps (BI Dashboards / ECO / Logistics / VEBA / etc.)
### 17.11.4 Onboarding Gate 4 — Alerts & Messaging
☐ Configure minimum notification triggers:
 - offline,
 - tamper,
 - overspeed,
 - fuel drop,
 - geofence entry/exit,
 - temperature deviation (cold chain),
 - fatigue/distracted driving (video/AI).
 ☐ WhatsApp templates loaded and tested (no spamming; bundling rules applied).
 ☐ Escalation routing verified (L1→L2→L3) without exposing personal numbers in customer-facing configs.
### 17.11.5 Onboarding Gate 5 — Training & Handover
☐ First report delivered successfully (sample run).
☐ Customer admin trained on:
 - maps/playback,
 - alerts,
 - driver behavior,
 - and basic troubleshooting.
✅ Go-Live Rule: No tenant goes live without passing all five onboarding gates.

## 17.12 AI + HIC Operational Tactics (Reduce MTTR, Protect Trust) ✈
NAVAS supports AI-driven helpdesk and ops workflows. Your job is to deploy AI where it increases speed, but enforce HIC where it protects trust.
### 17.12.1 AI Use Cases You SHOULD Activate
 - Access Governance Bot: automated access reviews and change logs to reduce permission delays and breaches.
 - Field Ops Router + Scheduler: route technicians and plan parts to hit on-site MTTR targets.
 - Self-Service Coach + Alert Orchestrator: WhatsApp instructions for drivers to take correct first actions and reduce escalations.
### 17.12.2 HITL Gates You MUST Enforce
 - First-month template sign-off (avoid spamming mistakes)
 - P1 triage approvals
 - Quote approvals
 - Finance approvals for suspension/resume
 These gates are explicitly required in hybrid workflows.

 [PAGE BREAK — END OF SECTION 17]

# 18. APPENDIX B — WIALON‐TO‐NAVAS ADMIN MAPPING

## 18.1 Purpose
*Trainer Statement:* This appendix converts Wialon CMS "muscle memory" into NAVAS CMS execution. You are a seasoned telematics administrator; therefore, this mapping is written for speed and precision ✅.
 Principle: Wialon organizes management around accounts/resources/units/billing plans.
NAVAS organizes management around tenants/accounts/resources + token governance + modular apps + HIC controls.

## 18.2 Object Model Mapping (Concept-to-Concept)
| Wialon CMS Concept | NAVAS CMS Equivalent | What Changes in Practice |
| Account | Tenant / Account hierarchy | NAVAS enforces stronger commercial boundaries via tokens |
| User | User + Role (RBAC) | Expect stronger least-privilege + audit trails |
| Unit | Unit / Asset | Same meaning; NAVAS layers product-app scope on top |
| Resource | Resource Library | Includes geofences/POIs/templates/report packs |
| Billing Plan | Token Policy / Token Catalog | NAVAS supports signal-level monetization, not just monthly fees |
| Notifications | Events + Notification Routing | More channels (WhatsApp) + bundling controls |
| CMS Logs | Audit Log | Impersonation and AI actions must be audit-visible |
| Trash | Trash & Restore | Same safety net; treat as recovery mechanism |

## 18.3 Workflow Mapping (Common Admin Tasks)
### 18.3.1 Create a New Customer / Account
1. Create tenant/account in NAVAS (territory + currency + timezone).
2. Assign baseline roles: Customer Admin, Operator, Auditor.
3. Attach product enablement package (OLIWA / MAFUTA / DASHCAM / etc.).
4. Assign token policy + safeguards (alerts, caps).
*HIC Rule:* Any creation that includes billing entitlements MUST be maker–checker approved. ✈✅

### 18.3.2 Provision an Add‐On App (VEBA Example)
NAVAS uses "provisioning drawers/blades" for app enablement.
*UI Pattern (Right Blade Drawer):* Provision App → tabs for Overview / Enablement / Billing Tokens / Payments / Audit Trail, and a visible "HITL Required" status.
Execution steps:
1. Open tenant → App Library → select app (e.g., VEBA).
2. Enablement checks:
 - require KYC for owners,
 - require telematics unit linked,
 - enable leakage shield (AI),
 - configure "cash trips" only for trusted profiles.
3. Token configuration:
 - register billable signals (listing time, trip/commission tokens, etc.).
 VEBA tokens are explicitly defined as disruptive growth drivers.
4. Attach payment rails:
 - EA mobile money (MTN MoMo / Airtel Money / M-Pesa) where supported.
5. Audit trail:
 - confirm approver and timestamp captured.
✅ HIC Tactic: Always start VEBA in "HITL Required" mode for the first 30 days of a tenant to prevent leakage and abuse.

### 18.3.3 Configure Notifications Without Creating Alert Fatigue
In Wialon, admins often create many triggers quickly. In NAVAS, you MUST balance "awareness" vs "noise."
Minimum high-value triggers to implement:
 - overspeed, harsh events, fuel drop, geofence entry/exit, panic button, temperature deviation, fatigue/distracted driving.
Bundling tactic:
 - High frequency events → digest every 60 minutes.
 - Critical safety/security events → immediate.

### 18.3.4 Billing & Entitlements (Wialon Billing Plans → NAVAS Token Policies)
NAVAS billing is designed to monetize signals, compute, inference, storage, transmission — not only "per unit per month."
Admin actions:
1. Ensure token usage events are captured (audit).
2. Enforce:
 - soft alert at 80%,
 - optional auto-pause,
 - hard stops where required.

## 18.4 HIC / Impersonation Mapping
Wialon admins often "log in as user." NAVAS allows similar capability but MUST be treated as controlled access.
1. Only approved admin roles may impersonate.
2. Every impersonation MUST record:
 - who initiated,
 - tenant targeted,
 - actions taken,
 - timestamp.
⚠ Compliance Risk: Impersonation without auditability is indistinguishable from insider abuse.

## 18.5 VEBA Governance Mapping (Marketplace Ops)
VEBA introduces marketplace behaviors: asset listings, booking approvals, conflict alerts, payments.
VEBA user stories explicitly require:
 - booking idle assets,
 - real-time availability,
 - cancel/reschedule,
 - conflict alerts,
 - owner approve/reject bookings,
 - usage history to schedule maintenance.
VEBA activity flows include:
 - Passenger Booking Flow
 - Driver Fatigue Alert Handling
 - Aggregator Commission Processing
 - Document Upload & Verification
 - Token Usage & Deduction
*Admin directive:* You MUST enable VEBA with:
 - KYC verification,
 - token deduction audit,
 - commission rules,
 - and HIC enforcement for payment disputes.

 [PAGE BREAK — END OF SECTION 18]

# 19. APPENDIX C — GLOSSARY, REFERENCES & TABLE OF ACRONYMS

## 19.1 Glossary (Operational Definitions)
*Purpose:* Remove ambiguity. When admins share a vocabulary, MTTR drops.
 - Account (NAVAS): A logical operational container within a tenant used to separate fleets, departments, or customer branches.
 - AI Inference Log: A record of AI computations executed (what model, what input scope, what output, what confidence). Required for audit and cost governance.
 - Alarm Storm: A burst of repeated alerts caused by misconfigured triggers or device instability; solved via bundling + threshold tuning.
 - ART (Average Response Time): Time from customer initial contact to first response; MUST be ≤ 15 minutes.
 - Bundling: Aggregating multiple low-severity events into a digest notification to prevent alert fatigue.
 - Dealer/Reseller: A delegated admin layer managing child tenants/accounts under a commercial umbrella.
 - ER (Escalation Rate): % of issues requiring field escalation; MUST be kept under 10%.
 - FCR (First Contact Resolution): Resolution during first interaction without escalation; target ≤ 30 minutes.
 - HIC (Human-in-Control): A governance model where automation may suggest or draft, but a human must approve or execute high-impact actions.
 - HITL (Human-in-the-Loop): Similar concept emphasizing human approval during automation steps (e.g., "HITL Required" in provisioning blades).
 - MRT (Mean Resolution Time): Average time to fully resolve issues; target ≤ 24 hours.
 - MTTR: Reliability metric family used to measure responsiveness and resolution discipline.
 - RTRS: Time-to-reach-site metric dependent on distance bands (1hr/2hrs/24hrs).
 - Token Definition: A reusable commercial rule describing what can be consumed, how it is measured, and how it is priced.
 - Token Queue (FIFO): Ordered list of active subscriptions consumed sequentially for predictability and auditability.
 - Usage Event: A factual record that something billable occurred (time elapsed, event triggered, data transmitted, AI inference executed).

## 19.2 References (Internal Source Pack)
*Admin directive:* You MUST use the source pack below as canonical internal references for training, escalation discipline, pricing governance, and automation guardrails.
 - 3DS Incident Management Escalation (3DS‐QSP‐18) — targets, responsibilities, install/repair times.
 - Event Triggers Catalog — baseline triggers for notifications/alarms.
 - NAVAS Token Billing Strategy (ver26.01.26a) — pricing formula + safeguards + audit requirements.
 - AI Agent Strategy V5 — HITL gates, KPIs, hybrid workflows.
 - AI Agent Customer Service User Stories — admin AI automations and MTTR impact.
 - VEBA User Stories + UML Activity Flows — marketplace governance flows.
 - CMS Mockup Redesign Request — provisioning blade pattern with HITL required.

## 19.3 TABLE OF ACRONYMS / ABBREVIATIONS
*(Place this table at the end of your Google Doc to comply with formatting policy.)* ✅
| Acronym | Meaning | NAVAS CMS Usage |
| AI | Artificial Intelligence | Recommendations, automations, inference logs |
| API | Application Programming Interface | Integrations, exports, monetization tokens |
| ART | Average Response Time | SLA tracking; target ≤ 15 mins |
| BI | Business Intelligence | BI Dashboards add-on, KPI reporting |
| CANBUS | Controller Area Network Bus | Vehicle telemetry; not fuel truth alone |
| CMS | Control/Management System | Admin cockpit for governance + monetization |
| CX | Customer Experience | Communication discipline + SLA adherence |
| DMS | Driver Monitoring System | Fatigue/distracted events (video/AI) |
| DR | Disaster Recovery | Backup/restore testing and continuity |
| ER | Escalation Rate | Keep escalations under 10% |
| FCR | First Contact Resolution | Target ≤ 30 mins |
| FIFO | First-In, First-Out | Token queue consumption policy |
| FLS | Fuel Level Sensor | Mafuta FLS deployments, calibration |
| FCW | Forward Collision Warning | Trigger events (video/AI) |
| GIS | Geographic Information System | Maps, geofences, POIs |
| GPS | Global Positioning System | Location tracking, playback |
| HIC | Human-in-Control | Admin approvals for sensitive actions |
| HITL | Human-in-the-Loop | "HITL Required" provisioning gates |
| IoT | Internet of Things | Goods sensors, genset, thermo, etc. |
| KYC | Know Your Customer | VEBA owner onboarding controls |
| KPI | Key Performance Indicator | MTTR metrics, reliability & finance |
| LDW | Lane Departure Warning | Trigger events (video/AI) |
| MDVR | Mobile Digital Video Recorder | Multi-camera video telematics |
| MRT | Mean Resolution Time | Target ≤ 24 hrs |
| MTTR | Mean Time To Repair/Resolve | Reliability governance framework |
| POI | Point of Interest | Geofence/landmark libraries |
| PM | Preventative Maintenance | Scheduled checks to prevent outages |
| RBAC | Role-Based Access Control | Roles/permissions governance |
| ROI | Return on Investment | Pricing, upsell, customer value |
| RTRS | Response Time to Reach Site | Distance-based on-site targets |
| RPS | Revenue Potential Score | Token pricing factor |
| SaaS | Software as a Service | NAVAS multi-tenant operations |
| SIM | Subscriber Identity Module | Connectivity + cost control |
| SLA | Service Level Agreement | Support performance commitments |
| SOP | Standard Operating Procedure | Repeatable admin processes |
| VEBA | Marketplace mobility product | Booking, listings, commissions |
| WLP | Work/Workplace Policy | Access governance checks (AI) |

If you want, I can immediately proceed to the next sections after 19 (e.g., References expansion, full product-specific SOP packs, or role-based training modules for Uganda vs Kenya operations) ✅
# SECTION 17 — APPENDIX A: ADMIN CHECKLISTS & RUNBOOKS ✅

✅ KEY TAKEAWAY: These checklists are mandatory operating procedure for NAVAS CMS administration at 3D Services Limited. Every major admin action MUST leave an evidence trail (ticket ID + CMS audit log + outcome proof). Deviations SHALL be logged as exceptions and reviewed.

## 17.1 Operating Rhythm: The Non‐Negotiable Admin Cadence
*Purpose:* Standardize how CMS is operated across Uganda o and Kenya a, reduce MTTR, prevent revenue leakage, and keep customer experience consistently excellent.
Table A1 — Admin Cadence Summary (Format: No borders  | Header shade #F5F5F5)
| Cadence | Primary Objective | Minimum Output (Evidence) | Owner |
| Daily | Prevent incidents + catch leakage early | Health check log + alarm review + billing exceptions list | System Admin |
| Weekly | Improve reliability + reduce recurring faults | Weekly Ops Report + top recurring faults + action list | System Admin + Support Lead |
| Monthly | Governance + compliance + pricing integrity | Access review + token policy version log + incident review | System Admin + Finance + Ops |
| Quarterly | Strategic optimization | QBR pack (ARPU, churn risk, product adoption, cost drivers) | Leadership + SysAdmin |

*HIC rule:* Any action that can suspend service, change pricing, or widen access MUST be maker–checker approved. ✈

## 17.2 New Tenant / Customer Onboarding Checklist
*Objective:* Provision a tenant that is commercially correct, technically stable, and support‐ready before the first device goes live.
### 17.2.1 Pre‐Provision Readiness (Commercial + CX) ✅
*Inputs required (DO NOT proceed without them):*
1. Customer legal name + trading name (for invoices & audit trails).
2. Territory: UG or KE (currency + pricing rules differ).
3. Primary contacts (Ops, Finance, Technical focal person).
4. Products purchased (from the 3D portfolio) and intended outcomes:
 - Vehicle Telematics: GUVNA / iVMS / iVMS‐PLUS / OLIWA / OLIWA‐PLUS
 - Personnel Tracing: CAPO / PATROL / PIKI / TOTO / WIATAG
 - Fuel Telematics: MAFUTA CANBUS / FLOW METER / FLS / FUEL CARD / STATION / GENSET
 - Goods‐in‐Transit & IoT: KAGO / PASO / PAWA / THERMO
 - AI & Video: DASH AI / DASHCAM / MDVR / MDVR AI
 - Add‐On Apps: BI Dashboards / DSC / ECO / FLEETRUN / INSPECTA / JMS / LOGISTICS / NIMBUS / VEBA
 - Value‐Added: Help Desk & Training / GIS & JMS / SATO / Local Owned Server / OEM Integrations
5. Implementation plan: #assets, asset types, installation sites, schedule.
 *Trainer tactic:* For enterprise customers, enforce a "Day‐0 demo tenant" (sandbox) before production to validate roles, alerts, and token burn behaviour.

### 17.2.2 Tenant Creation & Core Attributes (CMS)
*Run‐in steps (perform in this order):*
1. *Tenant creation:* Create tenant with correct:
 - Territory (UG/KE)
 - Currency (UGX/KES)
 - Timezone (EAT)
2. *Account structure:* Create account hierarchy (HQ → branch → departments) as needed.
3. *Naming policy:* Enforce standard naming patterns:
 - Tenant: ORG-COUNTRY
 - Branch: ORG-BRANCH-CITY
 - Groups: ORG-FLEETTYPE-REGION
✅ *Acceptance criteria:*
 - Tenant appears in CMS directory, searchable.
 - Account hierarchy matches the signed implementation plan.
 - Audit log shows creator, time, and reason code.

### 17.2.3 Roles, Users, and Least Privilege (RBAC)
*Minimum required roles (DO NOT improvise):*
 - Customer Admin (limited admin within tenant)
 - Operator / Dispatcher (day‐to‐day monitoring)
 - Auditor / Read‐Only (compliance, finance visibility)
 - Support Liaison (restricted support tools if applicable)
✈ *HIC gating:*
 - Creation of any privileged role (admin/supervisor/auditor) MUST be approved and recorded with a reason.
✅ *Acceptance criteria:*
 - Customer Admin can manage their users, but cannot change platform‐level policies.
 - Auditor can view logs and reports but cannot edit.

### 17.2.4 Product Enablement Matrix (Tenant Entitlements)
*Rule:* You SHALL NOT enable modules the customer has not contracted. This is a leakage risk and a support burden.
Table A2 — Product Enablement Checklist (No borders  | Header shade #F5F5F5)
| Product Family | Enablement Must Include | Verification Test (Required) |
| Vehicle Telematics (OLIWA/iVMS) | Core tracking + geofences + reports | Confirm live location + trip history |
| Personnel (PIKI/PATROL/TOTO) | Identity model + duty/shift logic | Confirm person tracking + alerts |
| Fuel (MAFUTA) | Fuel sensor mapping + theft rules | Simulate refill/drop thresholds |
| Goods IoT (THERMO/KAGO) | Sensor mapping + compliance report | Confirm temp/humidity deviation alert |
| AI/Video (DASH/MDVR) | Bandwidth controls + clip policy + AI inference gating | Confirm event → clip link (if enabled) |
| Add‐Ons (JMS/INSPECTA/VEBA etc.) | App-specific roles + token rules | App opens + data flows as expected |

✅ *Acceptance criteria:*
 - Only contracted menus and apps appear to end users.
 - Audit log shows enablement event + approver.

### 17.2.5 Token Setup (Wallet, SKU, Alerts)
*Policy rule:* If NAVAS can observe/compute/infer/store/transmit/visualize/act on it, it SHALL be billable. ✅
*Run‐in steps:*
1. Assign default token SKU(s) to the tenant.
2. Configure low‐balance alert thresholds (tiered):
 - Warning threshold (early)
 - Critical threshold (service risk)
3. Validate FIFO token consumption behaviour (simulation if available).
4. Confirm territory‐sensitive pricing rules are applied (UG vs KE).
✅ *Acceptance criteria:*
 - Wallet exists and displays balance clearly.
 - Low‐balance alerts trigger to the correct channel(s).
 - Token duration pricing tables align with product and territory (e.g., PIKI/OLIWA UG and PIKI/UKO KE).
✈ *HIC gating:* Price overrides, free tokens, or custom multipliers MUST be approved and time‐boxed.

### 17.2.6 Payment Rails Readiness (EA Market) 2
*Minimum requirement:* Test transaction + callback confirmation is mandatory before go‐live.
*Run‐in checks:*
 - Confirm mobile money rails and callback/webhook health (MTN/Airtel/Safaricom).
 - Confirm invoice reference formats and reconciliation method.
 - Confirm failed payments produce actionable alerts (Finance + System Admin).
✅ *Acceptance criteria:*
 - A test payment posts to wallet and is visible in ledger within expected time.
 - Failed payment generates notification + retry logic or manual workflow.

### 17.2.7 Device Onboarding & Installation Workflow (Governed)
*Operational discipline:* CMS provisioning and field installation MUST follow time‐bound task controls to reduce MTTR and wasted visits.
The 3D escalation and operations guidance defines time expectations for steps like device approval, job allocation, testing, and closure. You SHALL follow it.
*Standard workflow:*
1. *Create job/ticket* (system reference becomes the "single source of truth").
2. *Assign hardware & SIM profile* (warehouse sign‐out traceable).
3. *Apply provisioning profile* (protocol + intervals + sensor templates).
4. *Bench test* (confirm online, time sync, key IO).
5. *Install in field* (with QA checklist).
6. *Confirm reporting online* (admin verification).
7. *Close ticket with evidence* (photos, serials, screenshots, customer sign‐off).
✅ *Acceptance criteria:*
 - Unit appears online, and first messages are visible.
 - Device configuration is documented and repeatable.

### 17.2.8 Baseline Alerts & Notification Templates
*Rule:* Alerts exist to prevent loss, enforce compliance, and protect life/property. They SHALL be configured deliberately to avoid alert fatigue.
Use the platform's event trigger library as your baseline menu (examples include overspeed, fuel drop, tamper, temperature deviation, panic, driver fatigue alerts, maintenance milestones).
Baseline alert packs (recommended):
 - Vehicle Telematics: Overspeed + tamper + ignition abnormal + geofence entry/exit
 - Fuel: Fuel drop + rapid fuel consumption + low fuel + refill
 - Personnel: Panic + geofence breach + man‐down / fall detection (where supported)
 - Goods IoT: Temperature/humidity deviation + door intrusion + route deviation
 - AI/Video: Harsh events + fatigue/distraction + incident detection (carefully gated)
 *CX tactic:* Use bundled digests (hourly/daily) for non‐critical items to prevent WhatsApp/SMS fatigue.

### 17.2.9 Support Routing & Escalation Setup  ̄
*Rule:* Every tenant MUST have:
 - A support routing model
 - Business hours definition
 - Escalation ladder
 - After‐hours policy
3D's incident escalation process explicitly exists to improve MTTR and standardize escalation. You MUST align tenant support setup to that governance model.
✅ *Acceptance criteria:*
 - Support contacts are documented and tested.
 - A sample issue is logged and routed correctly.

### 17.2.10 AI + HIC Enablement Checklist (Waswa AI) ✈
*Policy position:* NAVAS uses AI to reduce costs and increase control, but humans retain authority through approvals, audit trails, and gating.
NAVAS AI is designed as a cascading hybrid model (edge logic → self‐hosted reasoning → external API for rare complex cases).
*Enablement steps:*
1. Decide AI mode per tenant:
 - Draft‐only (AI suggests; humans execute)
 - Action‐gated (AI proposes; approval required)
 - Auto‐action (restricted to safe, reversible actions)
2. Configure HIC checkpoints:
 - Billing/suspension proposals
 - Role privilege grants
 - Bulk edits
 - AI‐generated external communications
3. Confirm AI performance KPIs:
 - Helpdesk first response targets and MTTR alignment are expected in the strategy baseline.
✅ *Acceptance criteria:*
 - AI suggestions are logged with "who approved" and "why".
 - AI cannot execute irreversible actions without approval.

### 17.2.11 Go‐Live Sign‐Off (Hard Gate)
*Go‐live SHALL NOT occur until the following are true:*
 - Tenant structure verified ✅
 - Roles and least privilege verified ✅
 - Tokens + low balance alerts configured ✅
 - Payment test completed ✅
 - At least one device fully onboarded and confirmed online ✅
 - Alerts tested (at least one critical event) ✅
 - Customer admin trained and acknowledges operational responsibilities ✅
✈ *HIC gate:* Go‐live requires an explicit sign‐off by the responsible system administrator.

## 17.3 Daily Health Check Runbook
*Run‐in method:* Perform in the first 30–45 minutes of the day.
1. Platform health
 - Confirm CMS login performance and UI responsiveness.
 - Review critical alarms (P1/P2).
2. Token health
 - Review top tenants with low balances.
 - Review abnormal burn patterns (spikes).
3. Connectivity
 - Identify top "offline" units by tenant and region.
4. Notification delivery
 - Confirm SMS/WhatsApp success ratio (spot check).
5. Support queue
 - Check ticket backlog trend and unresolved high‐impact cases.
✅ *Daily output:* A short log note including:
 - What you checked
 - What you found
 - What actions you opened (ticket IDs)

## 17.4 Weekly Ops Checklist ✅
*Minimum required weekly actions:*
 - Review Alarm Center trends (top recurring alarms).
 - Review token burn anomalies and top message cost drivers.
 - Audit new privileged users and impersonation events.
 - Check SIM roaming and bundle mismatches (cost control).
 - Validate message gateways delivery health.
 *Opportunity tactic:* Weekly review SHOULD produce at least 3 opportunities:
 - Upsell (AI/Video, Compliance reporting, BI dashboards)
 - Risk mitigation (fuel theft rules, driver training triggers)
 - Operational improvement (template tuning, alert bundling)

## 17.5 Monthly Governance Checklist
*Mandatory monthly controls:*
1. Access review: confirm least privilege for all admins.
2. Token policy review: versions, pricing changes, promotions.
3. Audit sampling: pick 10 changes and verify reasons exist.
4. Incident review: postmortems and preventive actions.
5. Template governance: alert/report template updates.
✅ *Acceptance criteria:* Governance outputs are documented and auditable.

### Internal Source Pack (Keep for traceability)
 - NAVAS Token Billing Strategy (YES Rule, token classes, market pricing)
 - 3DS Incident Management Escalation Process (time targets, escalation governance)
 - Event Triggers Library (alerts/alarms baseline menu)
 - NAVAS IoT System Policy v26.0 (Cockpit, Waswa AI approach)
 - AI Agent Strategy (service KPIs and HITL controls)

⟪──────────── PAGE BREAK ────────────⟫
# SECTION 18 — APPENDIX B: WIALON CMS → NAVAS CMS MUSCLE‐MEMORY MAPPING

✅ KEY TAKEAWAY: If you have Wialon CMS Manager muscle memory, use this appendix to translate *what you already know* into NAVAS CMS execution—without importing legacy billing habits.

## 18.1 Mapping Rules (How to Use This Appendix)
1. Treat this mapping as functional equivalence, not UI equivalence.
2. NAVAS introduces two major differences you MUST internalize:
 - Token governance replaces per‐vehicle plans (metered, auditable, granular).
 - AI/HIC is a first‐class operating model (suggest → approve → execute).

## 18.2 Core Concept Mapping Table
Table B1 — Wialon vs NAVAS Admin Concepts (No borders  | Header shade #F5F5F5)
| Admin Concept | Typical Wialon CMS Mental Model | NAVAS Equivalent | What's Different in NAVAS (Critical) |
| Account hierarchy | Reseller → Customer accounts | Tenant → Accounts → Sub‐accounts | Hierarchical RBAC + multi‐product entitlement control |
| Users & rights | Users + access rights | Users + Roles (RBAC) + Approvals | Maker–checker for privileged changes (HIC) ✈ |
| Billing | Plans / units / renewals | Token SKUs + Wallet + FIFO burn | Billing is a language; "YES rule" applies to telemetry + AI + storage |
| Login as / impersonation | Act on behalf for troubleshooting | HIC "Act on behalf" session | Stronger audit trail + stricter controls |
| Logs | Action history | Audit log + approvals log + token ledger | Token ledger becomes commercial truth |
| Trash / restore | Deleted object recovery | Soft delete / restore workflow | Restore MUST preserve audit integrity |
| Apps | Add-ons via ecosystem | Add‐On App enablement (VEBA/JMS/INSPECTA etc.) | App entitlements are tied to tokens + RBAC |
| Notifications | Notification templates | Notification policies + event trigger library | Includes WhatsApp/SMS/email + bundling to reduce fatigue |

## 18.3 High‐Value Workflow Translations (Do This, Not That) ✅
### 18.3.1 Create a New Customer (Tenant)
*Wialon habit:* Create account → assign units → assign plan
*NAVAS required execution:* Create tenant → define entitlements → attach token SKU → configure wallet → onboard devices → validate burn & alerts.
✈ *HIC gate:* Token grants, pricing overrides, and role privileges MUST be approved.

### 18.3.2 Service Suspension for Non‐Payment ⚠
*Wialon habit:* Disable/limit service quickly
*NAVAS discipline:* Use policy‐driven suspension with evidence:
1. Confirm overdue status via finance workflow.
2. Confirm notification sequence issued.
3. Apply suspension action via CMS with reason code.
4. Ensure the action is reversible and logged.
 *CX tactic:* Always send a "restore path" message (how to pay, where to confirm) before suspension.

### 18.3.3 Replicate Customer Issue (Impersonation) ✈
*Required steps:*
1. Start "Act on behalf" session for the user.
2. Reproduce the issue with minimal scope.
3. Capture evidence (screens + IDs).
4. Exit impersonation immediately.
5. Attach evidence to ticket.
✅ *Rule:* Impersonation is for diagnosis, not daily operations.

## 18.4 Common Pitfalls for Wialon‐Experienced Admins (NAVAS Corrections) ⚠
1. Assuming billing is monthly-per-unit
 - NAVAS prices usage/value and supports parameter‐level billing. This is intentional. ✅
2. Over‐enabling menus
 - NAVAS must only enable what is contracted. Excess menus = leakage + confusion.
3. Letting alerts spam customers
 - Use bundling, quiet hours, and channel strategy to protect CX (especially WhatsApp).
4. Treating AI like a replacement for support staff
 - AI is an assistant. Humans MUST remain in control for approvals and irreversible actions. ✈

### Internal Source Pack (Keep for traceability)
 - NAVAS Token Billing Strategy (billing language + YES rule)
 - NAVAS IoT System Policy v26.0 (Cockpit + Waswa AI + RBAC multi-tenancy)
 - Event Trigger Library (alert categories)

⟪──────────── PAGE BREAK ────────────⟫
# SECTION 19 — APPENDIX C: GLOSSARY + TABLE OF ACRONYMS/ABBREVIATIONS

✅ KEY TAKEAWAY: Terminology drift causes misconfiguration, billing disputes, and support failures. This appendix defines the canonical language you SHALL use in tickets, training, reporting, and governance.

## 19.1 Glossary (Canonical Definitions) 3⁄4
*Account:* A logical business container within a tenant. Accounts may represent branches, departments, or customer sub‐entities.
*Action‐Gated AI:* AI that proposes actions but requires human approval before execution. ✈
*Add‐On App:* A modular capability enabled per tenant (e.g., INSPECTA, JMS, VEBA, ECO, BI Dashboards).
*Alarm Center:* CMS module that aggregates critical operational events requiring attention and often escalation.
*Approval Trail:* The auditable record of who approved what, when, and why (HIC governance).
*Asset:* Any trackable entity—vehicle, motorcycle, person, generator, trailer, cargo, cold chain container.
*Audit Log:* Immutable record of administrative actions (creates, edits, deletes, enablement, suspensions).
*Billing Dimension:* A component used to define token consumption (what/when/by/over/for/apply).
*Bundle (Token):* A commercial packaging of billing primitives into an outcome (e.g., "Fleet Safety AI+").
*CMS (NAVAS Cockpit):* The administrator command layer for provisioning, governance, token control, connectivity operations, and support enablement.
*Corrective Maintenance:* Actions taken to restore service after failure (replacement, rollback, hotfix, reconfiguration).
*Dealer/Reseller:* A delegated operator managing sub‐accounts under strict RBAC.
*Entitlement:* What a tenant is allowed to access (menus, apps, features, limits).
*Event Trigger:* A defined condition that generates an alert/alarm/notification (overspeed, fuel drop, temp deviation).
*FIFO (First‐In, First‐Out):* Token consumption method—earliest purchased token instance burns first.
*HIC (Human‐In‐Control):* Operating model where automation exists, but human authority remains final for critical changes. ✈
*IoT Sensor:* Device feeding telemetry (temperature, humidity, door, fuel, CANBUS, etc.).
*Ledger:* Financial/consumption record for tokens, payments, and usage events.
*Low‐Balance Alert:* Notification rules warning customers/admins that token balance is approaching service risk.
*MTTR:* Mean Time To Resolve—time from issue logged to resolution (operational KPI).
*Multi‐Tenancy:* Architecture where multiple customers share the platform while remaining isolated by design.
*Notification Policy:* Rules for who gets alerted, how, when, and how frequently (anti‐fatigue).
*Preventive Maintenance:* Actions taken to prevent failure (checks, calibrations, tuning, access review).
*RPS (Revenue Potential Score):* Pricing multiplier concept to align price with value and business impact. (Used in token pricing governance.)
*SKU:* Commercial sellable token construct.
*Suspension:* Controlled restriction of service due to policy events (non‐payment, abuse, compliance).
*Tenant:* The commercial + security boundary. No cross‐tenant access is permitted.
*Waswa AI:* NAVAS AI co‐pilot approach designed to reduce inference cost while increasing operational control.
*Wallet:* A tenant's token balance container.

## 19.2 Table of Acronyms/Abbreviations (MANDATORY END TABLE)
Table C1 — Acronyms/Abbreviations (No borders  | Header shade #F5F5F5)
| Acronym | Meaning | Where Used in NAVAS CMS | Admin Note |
| AI | Artificial Intelligence | Waswa AI, automation, insights | Must be HIC‐governed ✈ |
| API | Application Programming Interface | Integrations, OEM systems | Keys must be rotated periodically |
| ARPU | Average Revenue Per User | Finance dashboards | Track per tenant + per product |
| BI | Business Intelligence | BI Dashboards add‐on | Governance required for data access |
| CANBUS | Controller Area Network | Mafuta CANBUS | Vehicle diagnostics + fuel |
| CSAT | Customer Satisfaction | Support KPI | Target improves with proactive ops |
| CX | Customer Experience | Journey workflows | Reduce alert fatigue; clear comms |
| DMS | Driver Monitoring System | DASH AI / MDVR AI | High‐value token dimension |
| DSO | Days Sales Outstanding | Finance | Tighten collections automation |
| FCW | Forward Collision Warning | AI/Video alerts | Ensure driver coaching workflow |
| FIFO | First‐In, First‐Out | Token burn | Prevents "surprise expiry" |
| FLS | Fuel Level Sensor | Mafuta FLS | Requires calibration SOP |
| FMS | Fleet Management System | Platform scope | NAVAS is beyond "tracking" |
| GNSS | Global Navigation Satellite System | Device health | Drift alerts matter for compliance |
| HIC | Human‐In‐Control | Approvals, governance | Maker–checker is mandatory |
| HITL | Human‐In‐The‐Loop | AI triage/approval | Use for safety + billing actions |
| IoT | Internet of Things | Sensors + devices | Must standardize parameter mapping |
| KPI | Key Performance Indicator | Dashboards | Review weekly/monthly minimum |
| MDVR | Mobile Digital Video Recorder | DASHCAM/MDVR | Bandwidth/storage governance |
| MTTR | Mean Time To Resolve | Support ops | Targeted in escalation policy |
| P1/P2/P3 | Priority levels | Incident mgmt | P1 = immediate escalation |
| RBAC | Role‐Based Access Control | Users/roles | Least privilege ALWAYS |
| RPS | Revenue Potential Score | Token pricing | Drives value‐aligned pricing |
| SLA | Service Level Agreement | Support governance | Must align to escalation process |
| SKU | Stock Keeping Unit | Token catalog | Version carefully; audit changes |
| SOP | Standard Operating Procedure | Runbooks/checklists | Must be kept current |
| TTD | Time To Detect | Health Sentinel | Aim minutes not hours |
| VAS | Value Added Services | Training/helpdesk/GIS | Must be provisioned and documented |

## 19.3 References (Internal + External)
 - Internal governance and operating principles: NAVAS IoT System Policy v26.0
 - Token monetization governance: NAVAS Token Billing Strategy ver26.01.26a
 - Incident escalation governance (3D Services): 3DS Incident Management Escalation V.3
 - Alerts/events baseline library: List of Event Triggers
 - AI operations strategy and KPIs: 3D‐AI‐AGENT‐STRATEGY V5

✅ Footer standard (apply in Google Docs):
Left: NAVAS IoT System - CMS Module - 01.MAR. 2026 | Center: "You name it, we track it." ✅ | Page number: Bottom‐right
According to a document from 20 February 2026, NAVAS is operated as a multi‐tenant "IoT infrastructure platform" with tokenized monetization, Mobile Money rails (M‐Pesa/MTN/Airtel), and a cascading hybrid AI model (Waswa AI) to keep operational costs predictable while improving governance and customer experience.

⟂⟂⟂ PAGE BREAK — SECTION 17 ⟂⟂⟂
## 17. AUTOMATION & INTEGRATIONS ⚙
## 17.1 Purpose
CMS automation is not "extra." It is a mandatory operating system for 3D Services Limited (UG/KE) to:
1. Protect revenue (collections, credit control, billing integrity)
2. Accelerate onboarding (from quote → install → activation → training)
3. Reduce MTTR via proactive detection + faster routing  ̄
4. Improve CSAT/NPS through consistent multi‐channel comms ✅
5. Enforce governance (RBAC, audit logs, HIC gates)
Your posture as System Admin: Automate the predictable, control the irreversible. ✅

## 17.2 Integration Governance Model (Non‐Negotiable Controls)
*Scope.* This section covers the integrations typically used by NAVAS / 3D: Odoo, n8n, Wialon API / CMS actions, WhatsApp API, SMS Gateway, Gmail/SMTP, Payment Gateway, Power BI, AWS S3.
### 17.2.1 Roles and responsibilities
Use strict ownership:
 - System Admin (CMS Owner):
 - Owns credentials, webhooks, permissions, automation rollouts, rollbacks.
 - Finance (Odoo Owner):
 - Owns billing dates, DPD policy, credit limits, refund/credit notes rules.
 - Customer Journey / Support (Service Owner):
 - Owns message templates, SLA routing, customer comms approval.
 - Security/Compliance (Audit Owner):
 - Owns log retention, PII scope, access reviews.
### 17.2.2 Maker–Checker rules (HIC gates) ✈
You MUST implement Human‐In‐Control (HIC) approval for:
1. Blocking / unblocking customer service access (revenue + reputational risk).
2. Refunds, credit notes, ledger adjustments (financial integrity).
3. Permissions elevation (RBAC breach risk).
4. Device commands that can immobilize/disable or materially alter an asset state.
5. Mass messaging (>500 recipients or any "critical incident" broadcast).
 *HIC standard:* AI/automation may propose, draft, or queue actions; a human must approve before execution for high‐risk actions.

## 17.3 Integration Inventory (Minimum Required Register)
Table formatting rule (Google Doc): set width 100%, remove borders , shade header row #F5F5F5.
| Integration | Primary Purpose | Objects Exchanged | Typical Trigger | HIC Risk Level |
| Odoo | Billing, CRM, Projects/Tasks | Customers, invoices, subscriptions, tasks | Due date, paid/unpaid, install schedule | High |
| n8n | Workflow engine / orchestration | Webhooks, messages, approvals, sync jobs | Time schedules + events | Medium |
| Wialon API / CMS actions | Account/unit governance | Users, accounts, unit status | Suspend/unblock, create tenant/user | High |
| WhatsApp API | Customer comms | Templates, delivery receipts | Reminders, incidents, alerts | Medium |
| SMS Gateway | Comms fallback | SMS payloads, DLRs | If WhatsApp fails | Low |
| Gmail/SMTP | Email comms | Invoices, onboarding series | Billing + onboarding | Low |
| Payment Gateway | Collections | Payment refs, callbacks | Payment callback (webhook) | High |
| Power BI | KPI dashboards | Dataflows, metrics | Daily refresh | Low |
| AWS S3 | Audit + archives | JSON logs, documents | Nightly dump / weekly backups | Medium |

This alignment is directly reflected in the automation backlog requirements (Credit Control, Sales/Onboarding, CX, SLA monitoring, Reporting/Compliance).

## 17.4 Wialon‐Style "Act On Behalf" Governance (HIC Pattern) ✈
NAVAS HIC is intentionally comparable to the Wialon CMS operating model where administrators can log in on behalf of a user only if they have the appropriate right ("Act on behalf of this user"). ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/access-rights/user-access-rights?utm_source=chatgpt.com))
### Operational directives
1. Only impersonate for a specific task (e.g., create objects with correct creator/tenant context).
2. Record the reason in the audit note (ticket ID, who requested, what changed).
3. Exit impersonation immediately after completing the task.
4. Never use impersonation to bypass approvals (maker–checker remains mandatory).
*Why this matters.* In Wialon, "Act on behalf" enables performing actions as that user, including creating objects and changing passwords, so it must be tightly controlled. ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/access-rights/user-access-rights?utm_source=chatgpt.com))

## 17.5 Automation Standard: How to Build Workflows That Don't Break Production ✅
### 17.5.1 Naming conventions (must be consistent)
 - WF‐CC‐### = Credit Control
 - WF‐SO‐### = Sales/Onboarding
 - WF‐CX‐### = Customer Experience
 - WF‐SP‐### = Staff Productivity / SLA
 - WF‐AI‐### = AI Monitoring
 - WF‐RC‐### = Reporting/Compliance
### 17.5.2 Environment separation
1. DEV → sandbox credentials, test tenants only
2. UAT/STAGING → mirror production templates, limited customer impact
3. PROD → approval required for activation + rollback plan required
### 17.5.3 Idempotency (anti‐double‐charging rule)
 - Every workflow MUST have a unique correlation ID (Invoice ID / Ticket ID / Unit ID + timestamp window).
 - Payment allocation workflows MUST be idempotent to prevent double allocation.
### 17.5.4 Logging and evidence
Every workflow MUST write:
 - Execution timestamp
 - Trigger input
 - Decision path
 - Action output (success/fail)
 - Operator approvals (if HIC gate used)
 - Customer‐visible message payload references (template ID)
This is explicitly aligned with automated log storage requirements and S3 archival practices. 【689:3†3D AI Agent Development Backlog ver 1.0.pdf†L24-L41】

## 17.6 Automation Epic Playbooks (Implement Exactly)  ✅
### 17.6.1 EPIC 1 — Credit Control & Subscription Collections
Goal: Reduce revenuscalation, reconciliation, and forecasting. 【689:11†3D AI Agent Development Backlog ver 1.0.pdf†L9-L69】
#### A) Multi‐channel renewal reminders
Directive: n8n MUST send renewal reminders via SMS + WhatsApp + Email using Odoo billing dates and custoklog ver 1.0.pdf†L12-L16】
*Run‐in (italicized).* *Implementation steps.*
1. Trigger: T‐7, T‐3, T‐1, DUE, D+1, D+3 (configure per customer tier).
2. Pull: invoice balance + dic variables.
3. Send: WhatsApp first; fallback to SMS; send email copy to billing contacts.
4. Record: message delivery receipts (DLR/Meta callback).
✅ *Customer experience tactic:* Always include a self‐service payment link in reminders (mobile money/card) to reduce friction. 【689:2†3D AI Agent Development Backlog ver 1.0.pdf†L1-L4】
#### B) Automated suspend/unblock (Wialon/CMS actions)
Directive: Accounts MUST be suspended after due date grace period using API calls, and status Mnt Backlog ver 1.0.pdf†L18-L22】
⚠ *HIC Gate (mandatory).*
 - Automation may *queue* a suspension action.
 - A human must approve any action for:
 - strategic customers
 - cusdents
This aligns with "Act on behalf" governance patterns in Wialon (impersonation requires explicit rights and must be controlled). ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/access-rights/user-access-rights?utm_source=chatgpt.com))
#### C) Escalation when strategic clients exceed credit limits
Directive: Escalation alerts MUST notify CFO/Finance Head and log in Power BI dashboard when strategic‐tier clients exceed limits. 【689:11†3D AI Agent Development Backlog ver 1.0.pdf†L24-L28】
*Trainer note :* Escalation is not a "message." It is a workflow: notify → approve → action → log.
#### D) AI payment allocation (reconciliation accelerator)
Directive: AI matching MUST allocate payments across invoices by similarity (amount/date/refs) aog ver 1.0.pdf†L35-L39】
⚠ *HIC Gate.* Any AI‐based allocation above an approved threshold (e.g., >UGX [amount withheld: pricing]M or mismatched refs) MUST require human confirmation.
#### E) SLA credit notes
Directive: When uptime/downtime exceeds SLA thresholds, the system SHOULD trigger credit note issuanclog ver 1.0.pdf†L19-L23】
✅ *Risk mitigation:* Always attach incident evidence (timestamps, affected scope) before issuing credit notes.

### 17.6.2 EPIC 2 — Sales & Onboarding Automation
Goal: Remove manual bottlenecks and enforce "fast onboarding" discipline. 【689:7†3D AI Agent D creation
Directive: n8n MUST capture webform/Google Form data and create Odoo leads with unique IDs. 【689:2†3D AI Agent Development Backlog ver 1.0.pdf†L33-L37】
#### B) Auto account creation after approval
Directive: After customer approAPI flows and apply template settings. 【689:2†3D AI Agent Development Backlog ver 1.0.pdf†L39-L43】
*HIC Gate.* Production accoun
 - VEBA marketplace tenants (due to financial exposure)
 - any tenant with "dealer hierarchy" complexity
#### C) Automated quotations + discount logic
Directive: Quotes MUS and a standard template flow. 【689:2†3D AI Agent Development Backlog ver 1.0.pdf†L45-L48】
✅ *Service target alignment:* 3D's escalation guidance sets quote turnaround targets at 60 minutes across service types (AI/Video, Personnel, Vehicle, Fuel, Goods/IoT, Value Added, Add‐Ons). 【689:8†3DS Process for Incident Management Escalation V.3.pdf†L73-L96】
####* When installation is scheduled, job cards MUST be created and planned using map routing to reduce technician waste. 【689:2†3D AI Agent Development Backlog ver 1.0.pdf†L51-L55】

### 17.6.3 + measurable sentiment.
Key requirements include:
 - AI sentiment scoring for WhatsApp/email conversations stored in CRM tags 【689:9†3D AI Agent Development Backlog ver 1.0.pdf†L14-Lation 【689:9†3D AI Agent Development Backlog ver 1.0.pdf†L20-L23】
 - Automated NPS surveys with aggregation into Power BI 【689:9†3D AI Agent Development Backlog ver 1.0.pdf†L25-L28】
 - AI summaries of resolved tickeacklog ver 1.0.pdf†L30-L33】
#### Mandatory HIC controls f
1. Always include "next update time" in incident messagly to Support Supervisor + CJM (with evidence).

### 17 balance workload, flag SLA breaches early.
Requirements include:
 - automated daily task assignment by capacity 【689:10†3D AI Agent Development Backlog ver 1.0.pdf†L9-L20】
 - real-time alerts for overdue tickets by tier 【689:10†3D AI Agent Development Backlog ver 1.0.pdf†L17-L20】
 - dashboards showing agent performance vs SLA 【689:10†3D AI Agent Development Backlog ver 1.0.pdf†L22-L25】
 - technician mobile notifications on assignments 【6
✅ *Operational KPI alignment:* NAVAS policy expy, <24 hr resolution) to protect CSAT. 【6896.5 EPIC 5 — Predictive Analytics & AI Monitoring  - detect idle subscriptions by comparing active devices vs billed subscriptions 【689:10†3D AI Agent Development Backlog ver 1.0.pdf†L39-L41】
 - churn model†3D AI Agent Development Backlog ver 1.0.pdf†L6-L10】
 - anomaly detection in driving behavior reports (overspeeding/idling outliers) 【689:10†3D AI Agent Development Backlog ver 1.0.pdf†L48-L50】
⚠ *HIC Guarnals that MUST be verified against telemetry evidence an Storage & Compliance
Goal: auditability and unified performance tracking.
ly 【689:3†3D AI Agent Development Backlog ver 1.0.pdf†L24-L26】
 - weekly automated backups of client documents 【689:3†3D AI Agent Development Backlog ver 1.0.pdf†L34-L36】
 - reconciliation between tracking system data and billing data 【689:3†3D AI Agent Development Backlog ver 1.0.pdf†L38-L41】

## 17.7 Add‐On Apps Provisioni where you enable/disable capabilities per tenant JMS, Logistics, Nimbus).
*Run‐in.* *Module path.
Utility &→ Provisioning Blade
### Mandatory CRUD operations
1. Create: register add‐on app (metadata, dependencies, pricing category).
2. Read: view tenant entitlement, token burn policies, usage.
3. Update: enablement, billing rules, access rights, templates.
4. Delete/Archive: remove from active catalog (soft delete) and allow restore.
✅ *HIC practice:* The "Provisioning Blade" MUST display: prerequisites, token policy, dependencies, and rollback plan before applying changes.
Screen 27 (Add‐On Apps Library / Provisioning) assets & code reference:

## 17.8 AI + HIC Optimization Tactics (Trainer‐Grade) ✈
NAVAS adopts a tiered AI approach to remain profitable: Tier 1 edge rules, Tier 2 self‐hosted models, Tier 3 external API for rare deep analysis. 【689:12† NAVAS IOT SYSTEM POLICY_ .pdf†L101-L109】
### HIC tactics you MUST enforce
AI must cite inputs (unit IDs, time windows, invoice IDs).
 - Force reversibility: allow rollback for policy changes (token rules, suspensions).
 - Force audit: every AI suggestion accepted must be logged (who ae tenant‐scoped to prevent cross‐tenant leakage.

## 17.9 Key Takeaways (This Section) ✅
 - Automation is a governance layer, not a convenience.
 - High‐risk actions (billing, blocking, permissions) MUST be HIC gated.
 - The 3D automation backlog defines practical, implementable workflows across credit control, onboarding, CX, SLA, and compliance. 【689:11†3D AI Agent Development Backlog ver 1.0.pdf†L9-L44】【689:3†3D AI Agent Development Backlog ver 1.0.pdf†L24-L41】
 - Use Wialon‐style impersonation ("Act on behalf") only with explicit rights and logging. ([help.wialon.com](https://help.wialon.com/en/wialon-hosting/user-guide/management-system/access-rights/user-access-rights?utm_source=chatgpt.com))

⟂⟂⟂ PAGE BREAK — SECTION 18 ⟂⟂⟂
18. PREVENTATIVE & CORRECTIVE MAINTENANe is how you restore service fast when reality happens.
NAVAS is engineered as a high‐velocity pipeline (sockets → Kafka → DB/cache → UI). Maintenance MUST therefore cover both:
1. Platform reliability (backend, DB, cache, integrations)
2. Field reliability (devices, sensors, SIMs, power, installs)
Architecture components relevant to admin maintenance include Kafka streaming, Cassandra fast storage, PostgreSQL audit/RBAC, Redis cache, and React frontends. 【689:12† NAVAS IOT SYSTEM POLICY_ .pdf†L53-L90】

## 18.2 Maintenance Philosophy (Non‐Negotiable Rules) ✅
1. Detect early (alerts/health dashboards)
2. Fix remotely first (reduce field escalations)
3. Dispatch only with evidence (avoid wasted trips)
4. Document everything (audit + learning loop)
5. Automate recurring checks (daily/weekly schedules)
*Target KPI.* 3D's operational model explicitly pressures 3DS Process for Incident Management Escalation V.3.pdf†L96-L173】

## 18.3 Preventative Maintenance Schedule (Platform + Field)
Table formatting: 100% width, no borders, header row shade #F5F5F5.
| Cadence | Platform Tasks (CMS/Backend) | Field Tasks (Devices/Sensors) | Output Evidence |
| Daily | Monitor offline clusters, queue backlogs, message delivery failures | Spot check critical fleets, confirm highrification (restore test), integration error review, token anomaly review | Fuel calibration sampling, camera health sampling |
| Monthly | RBAC access review, cost review (SIM/Maps/WhatsApp), patch windows | Full PM on priority customers + random audits | Monthly governance report |
| Quarterly | Capacity planning, DR drill, incident trend review | Deep sensor checks + firmware/OTA planning | QBR pack + improvement plan |

✅ *Preventative maintenance must be measurable.* If it cannot be audited, it is not maintenance; it is hope.

## 18.4 Preventative Maintenance: Platform & Integrations
### 18.4.1 Core platform checks (daily/weekly)
*Run‐in.* *Health checks.*
1. Ingestion health: confirm packet parsing throughput and error rates.
2. Kafka health: consumer lag, partition availability, topic retention.
3. DB health: Cassandra write latency; PostgreSQL audit integrity.
4. Cache health: Redis hit rate; SSE latency.
5. Frontend health: UI error logs, API response times.
These components are core to NAVAS's architecture stack. 【689:12† NAVAS IOT SYSTEM POLICY_ .pdf†L53-L90】
### 18.4.2 Integration health checks
1. Payment callbacks: verify webhook success rate; reconcile missing callbacks.
2. WhatsApp/SMS delivery: monitor throttle/failure spikes.
3. Odoo sync jobs: ensure invoice status, subscriptions, tasks are consistent.
4. S3 audit logs: confirm daily write + retention policies.
These are mandated by reporting/compliance automation rlog ver 1.0.pdf†L24-L36】

## 18.5 Preventative Maintenance: Alerts & Triggers You MUST Configure
NAVAS should be configured around meaningful operational triggers across vehicle, driver, fuel, video, personnel, and IoT contexts.
Examples of trigger categories include:
 - Battery health warning
 - Engine fault codes (DTCs)
 - Fuel drop / rapid consumption
 - Geofence entry/exit & br Temperature deviation / humidity deviation
 - Panic button activation
 - Preventative maintenance (time‐based / mileage‐based) 【689:1†List of Event that Triggers notifications, alerts, alarms.pdf†L4-L91】
### 18.5.1 Trigger‐to‐Product alignment (3D portfolio)
*Run‐in.* *Your mapping MUST be deliberate.*
 - AI & Video (DASH AI / DASHCAM / MDVR / MDVR AI): fatigue, distracted, FCW/LDW/HMW, video health. 【689:1†List of Event that Triggers notifications, alerts, alarms.pdf†L22-L50】
 - Fuel (MAFUTA CANBUS / FLOW METER / FLS / FUEL CARD / STATION / GENSET): fu that Triggers notifications, alerts, alarms.pdf†L30-L41】
 - Goods‐in‐Transit & IoT (KAGO / PASO / PAWA / THERMO): door intrusion, temperature deviation, humidity deviation. 【689:1†List of Event that Triggers notifications, alerts, alarms.pdf†L56-L57】【689:1†List of Event that Triggers notifications, alerts, alarms.pdf†L84-L85】
 - Personnel n‐down, panic button. 【689:1†List of Event that Triggers notifications, alerts, alarms.pdf†L36-L44】【689:1†List of Event thlerts, alarms.pdf†L9-L10】【689:1†List of Event that Triggers notifications, alerts, alarms.pdf†L34-L35】【689:1†List ofrs; only escalate when risk is real.

## 18.6 Corrective Maintenance: MTTR Targets & Dispatch Discipline  ̄
3D's escal
 - Escalation rate target under 10%
 - Point of contact response time 15 minutes during standard support hours 【689:4†3DS Process for Incident Management Escalation V.3.pdf†L96-L193】
### 18.6.1 MTTR operational table (embed into CMS dashboards)
Table formatting: 100% width, no borders, header row shade #F5F5F5.
| Metric | Definition | Target |
| RTRS | Time from escalation → technician arrives on site | 50km: 1 hr; 100km: 2 hrs; \\>110km: 24 hrs 【689:4†3DS Process for Incident Management Escalation V.3.pdf†L96-L114】 |
| FCR | Resolv30 mins 【689:4†3DS Process for Incident Management Escalation V.3.pdf†L118-L129】 | |
| MRT | Average time from report → full resolution | ≤ 24 hrs 【689:4†3DS Process for Incident Management Escalation V.3.pdf†L131-L142】 |
| Escalation Rate | % tickets requiring on‐site visit | \\< 10% 【689:4ART / PoC response |
| *Run‐in.* \\*Folets + criticality (VIP, safety, revenue). | | |

1.
 Collect evidence: lasentify likely class of failure:
 - power (install/power cut)
 - connectivity (SIM/APN/carrier)
 - hardware failure (device dead)
 - sensor drift/calibration (fuel/temp)
 - platform outage (system‐side)
2. Attempt remote fix:
 - config correction
 - APN refresh
 - reboot command where applicable
 - device profile re‐push
3. Escalate to field only with evidence: include site, distance band (RTRS), required parts.
4. Close loop: confirm unit reporting online before closure; send customer update.

## 18.8 Operational Time Targets During Service Delivery (Internal Discipline)
3D's escalation matrix includes strict internal timing on service execution steps such as:
 - device approval within 10 minutes after email receipt
 - job allocation & ticketing within 15 minutes
 - device sign‐out & testing within 30 minutes
 - job execution communication within 10 minutes after ticket creation
 - job closure review within 12 hours after completion 【689:0†3DS Process for Incident Management Escalation V.3.pdf†L99-L179】
✅ *System Admin directive:* CMS should enforce these targets via:
 - auto‐timestamps
 - SLA timers
 - escalations to owners when breached
 - dashboards per department

## 18.9 Key Takeaways (This Section) ✅
 - Preventative maintenance is planned reliability; corrective maintenance is disciplined recovery.
 - Use the event trigger catalog to build proactrs notifications, alerts, alarms.pdf†L4-L91】
 - Embed MTTR targets into your CMS workflows and automate SLA breaches. 【689:4†3DS Process for Incident Management Escalation V.3.pdf†L96-L193】
 - Maintain both the platform pipeline and field installations; neglect either and the system degrades. 【689:12† NAVAS IOT SYSTEM POLICY_ .pdf†L53-L90】

⟂⟂⟂ PAGE BREAK — SECTION 19 ⟂⟂⟂
19. TABLE OF ACRO, header row shade #F5F5F5.
| Acronym | Meaning | Admin Context |
|---|-- Control / Management System | Admin console for tenants, billing, governance |
| HIC / HITL | Human‐In‐Control / automation |
| RBAC | Role‐Based Access Control | Permissions model for users/actions |
| MTTR | Mean Time To Reply/Resolve | Core KPI for service delivery & support |
| RTRS | Response Time to Reach Site | Field dispatch target (distance‐based) |
| FCR | First Contact Resolution | Remote resolution target |
| MRT | Mean Resolution Time | Resolution target metric |
| SLA | Service Level Agreement | Contracted service targets |
| DPD | Days Past Due | Credit control policy driver |
| DSO | Days Sales Outstanding | Finance collections KPI |
| KYC | Know Your Customer | Marketplace/finance gating |
| API | Application Programming Interface | Integration channel (Odoo/Wialon/Payments) |
| n8n | Workflow automation engine | Orchestrates workflows and integrations |
| Odoo | ERP/CRM | Billing, CRM, tasks, subscriptions |
| PoC | Point of Contact | Primary customer contact for comms |
| PII | Personally Identifiable Information | Privacy scope control |
| SMS | Short Message Service | Messaging fallback channel |
| DLR | Delivery Receipt | SMS/WhatsApp delivery confirmation |
| SIM | Subscriber Identity Module | Connectivity operations |
| APN | Access Point Name | SIM data configuration |
| ICCID | SIM identifier | SIM inventory tracking |
| IMEI | Device identifier | Tracker identification |
| GPS | Global Positioning System | Location source |
| GSM | Cellular network | Device communications |
| IoT | Internet of Things | Sensors, assets, telemetry devices |
| CANBUS | Vehicle CAN bus | Fuel/engine data integration |
| FLS | Fuel Level Sensor | Fuel telemetry hardware |
| DTC | Diagnostic Trouble Code | Engine fault codes |
| MDVR | Mobile Digital Video Recorder | Video telematics stack |
| ADAS | Advanced Driver Assistance Systems | AI safety features |
| FCW | Forward Collision Warning | Video/ADAS event |
| LDW | Lane Departure Warning | Video/ADAS event |
| HMW | Headway Monitoring Warning | Video/ADAS event |
| BI | Business Intelligence | Dashboards + reporting |
| S3 | Simple Storage Service | Audit logs and archives |
| DR | Disaster Recovery | Backup/restore readiness |
| QMS | Quality Management System | Controlled processes and compliance |
| VEBA | Equipment Marketplace module | Marketplace governance + billing |
| OLIWA | Vehicle tracking portal | Car tracking focus |
| PIKI | Motorcycle tracking portal | Boda sector focus |
| PATROL | Personnel tracking portal | Field staff monitoring |
| INSPECTA | Inspection add‐on app | Fleet inspections + checklists |
| ECO | Eco-driving add‐on app | Driver behavior & efficiency |
| JMS | Job/Journey Management System | Jobs, dispatch, workflows |
| DSC | Driver/Safety module (context) | Safety scoring & controls |
| KAGO / PASO / PAWA / THERMO | Goods‐in‐transit & IoT modules | Cargo/energy/temp monitoring |

✅ *Directive:* Keep this table at the end of the document and update it whenever a new module, KPI, or integration is introduced.

### Footer Configuration (Document‐Wide) ✅
 - Left: NAVAS IoT System - CMS Module - 01.MAR. 2026
 - Center: "You name it, we track it." ✅
 - Right: Page Number (bottom‐right)

## Supporting Source Files (for your QMS evidence pack)
 - NAVAS system policy (architecture, token engine, Waswa AI):
 - 3DS incident escalation + MTTR targets:
 - Automation + AI backlog (n8n/Odoo/Power BI/S3):
 - Event triggers catalog (alerts/alarms/notifications):
 - Screen 27 (Add‐On Apps Library / Provisioning) mockups + code ZIP:
According to a document from 20 February 2026, NAVAS CMS is designed as a command-and-control cockpit with tokenized monetization and a Waswa AI co‐pilot, operated under strict Human‐In‐Control (HIC) governance to prevent revenue leakage and operational drift.
Below is the requested continuation: Sections 17, 18, and 19 (with mandatory page breaks between them). ✅

# 17. ADMIN CHECKLISTS & OPERATING RHYTHM ✅

Purpose
This section defines the non‐negotiable operating rhythm for NAVAS CMS System Administrators supporting 3D Services Limited (UG/KE). It is built to:
1. Stabilize service delivery (reduce MTTR, eliminate avoidable outages).
2. Protect revenue (prevent token leakage, stop unpaid service drift).
3. Standardize governance (RBAC discipline, auditability, HIC gating).
4. Increase customer confidence (predictable comms, proactive prevention).

## 17.1 Operating Rules of Engagement (ROE) ✅
You SHALL:
1. Treat CMS data as the system of record for:
 - Tenant status, entitlements, add‐on enablement, token wallet and enforcement rules.
2. Treat Audit Logs as non‐optional evidence for:
 - Permission changes, billing plan changes, device command actions, AI approvals.
3. Use HIC gates for any action that can:
 - Disable tracking, change billing, alter alerts at scale, push device commands, or contact customers at scale. ✈
You SHALL NOT:
1. Make tenant‐wide changes "quietly" without a recorded reason.
2. Enable high‐risk modules (e.g., marketplace payments, AI enforcement actions) without:
 - A documented approval trail + rollback plan. ⚠

## 17.2 New Tenant Onboarding Checklist (UG/KE)
Training note (for seasoned admins): This is the fast path. Do not skip steps. The "5 minutes saved" becomes 5 days of MTTR later.
### A. Pre‐Provisioning Intake (Required Inputs)
1. Confirm the commercial identity:
 - Company name, territory (UG/KE), tax profile, billing contact, technical contact.
2. Confirm product scope (tick all that apply):
 - Vehicle Telematics: GUVNA / iVMS / iVMS‐PLUS / OLIWA / OLIWA‐PLUS
 - Personnel: CAPO / PATROL / PIKI / TOTO / WIATAG
 - Fuel: MAFUTA CANBUS / FLOW METER / FLS / FUEL CARD / STATION / GENSET
 - Goods & IoT: KAGO / PASO / PAWA / THERMO
 - AI & Video: DASH AI / DASHCAM / MDVR / MDVR AI
 - Add‐Ons: BI / DSC / ECO / FLEETRUN / INSPECTA / JMS / LOGISTICS / NIMBUS / VEBA
 - VAS: HELP DESK & TRAINING / GIS & JMS / SATO / LOCAL OWNED SERVER / OEM INTEGRATIONS
3. Confirm the service model:
 - PAYG token burn vs subscription bundle vs hybrid.
### B. Tenant Creation (CMS Governance)
1. Create Tenant / Account:
 - Territory: UG or KE
 - Currency: UGX or KES
 - Timezone: EAT
 - Language defaults (EN + locale fallback)
2. Apply hierarchy:
 - Dealer / Sub‐dealer / Organization / Department structure (multi‐tenancy discipline).
3. Configure RBAC (minimum set):
 - Customer Admin (tenant‐level control)
 - Dispatcher / Operator (ops only)
 - Finance Viewer (billing visibility, no device commands)
 - Auditor (read-only + audit export)
4. Enable Audit Mode (always on):
 - Log changes + enforce "Reason for Change".
### C. Token Wallet & Billing (Revenue Protection)
1. Assign the default Token SKU and pricing policy version.
2. Enable low‐balance alerts:
 - Threshold 1 (warn), threshold 2 (critical), threshold 3 (service restriction).
3. Configure token enforcement behavior (choose):
 - Soft enforcement (warnings only)
 - Hard enforcement (feature throttling)
 - Hard cut‐off (service suspension) ✅
4. Validate FIFO consumption rules and credits behavior.
 Tactic: Set enforcement to "Soft" for the first 7–14 days on enterprise pilots, but keep alarm thresholds live. You want learning without leakage.
### D. Payments & Mobile Money (UG/KE) 2
1. Enable payment rails:
 - M‐Pesa (KE), MTN MoMo (UG), Airtel Money (UG/KE)
2. Run a test transaction + callback validation:
 - Confirm wallet top‐up reflects correctly.
3. Configure payment links used in automated reminders (WhatsApp/SMS/Email).
### E. Device & Service Provisioning Profiles (Ops Stability)
1. Select device profile templates per product line:
 - GPS interval, heartbeat, IO mapping, power thresholds, sleep mode.
2. Enable mandatory alarms (baseline):
 - Offline, tamper, low voltage, overspeed, geofence violation (where applicable).
3. For fuel/video/IoT products: configure additional rules:
 - Fuel drop thresholds, calibration requirement flag, camera storage health rules.
### F. Messaging & Comms Readiness (CX Control)
1. Enable channels:
 - SMS / Email / WhatsApp templates
2. Activate onboarding templates:
 - Welcome message, first login, escalation path, how to raise tickets.
3. Set quiet hours + escalation ladder.
### G. Reporting Readiness (Proof of Value)
1. Assign report packs:
 - Fleet summary, trips, speeding, fuel variance, temperature logs, driver behavior.
2. Deliver a sample report to confirm:
 - Correct recipients, correct timezone, correct units.
### H. Add‐On Apps Enablement (Modular Growth)
1. Enable relevant add‐on apps (only those sold).
2. Confirm dependencies:
 - Maps, messaging, payments, BI connectors, API keys.
3. Run smoke test:
 - App visible, permissions correct, one action works.
### I. AI Feature Governance (HIC Enforcement) ✈
1. Enable Waswa AI per policy tier:
 - Draft‐only → Action gated → Auto‐execute (rare).
2. Confirm approval workflow:
 - Who approves, where approvals are logged, rollback process.

## 17.3 Field Install & Repair Target Times (Operational Standard)
You SHALL align dispatch scheduling and customer expectations to the documented target install/repair times per product.
Table style note: set 100% width, no borders , header row shaded #F5F5F5.
| Service Type | Product | Target Time To Install | Target Time To Repair |
| AI & Video Telematics | Dash AI | 4.5 Hrs | 3 Hrs |
| AI & Video Telematics | Dashcam | 4 Hrs | 3 Hrs |
| AI & Video Telematics | MDVR | 8 Hrs | 3 Hrs |
| AI & Video Telematics | MDVR AI | 8 Hrs | 3 Hrs |
| Vehicle Telematics | iVMS | 3 Hrs | 2 Hrs |
| Vehicle Telematics | iVMS‐PLUS | 4 Hrs | 3 Hrs |
| Vehicle Telematics | OLIWA | 3 Hrs | 2 Hrs |
| Vehicle Telematics | OLIWA‐PLUS | 4 Hrs | 3 Hrs |
| Fuel Telematics | Mafuta FLS | 8 Hrs | 3 Hrs (+ Recalibration 8 Hrs) |
| Fuel Telematics | Mafuta CanBus | 4 Hrs | 3 Hrs |
| Fuel Telematics | Mafuta Flow Meter | 3 Hrs | 2 Hrs |
| Personnel Tracing | CAPO | 1 Hr | 30 Min |
| Personnel Tracing | PIKI | 3 Hrs | 2 Hrs |
| Personnel Tracing | TOTO | 1 Hr | 30 Min |
| Personnel Tracing | WIATAG | 1 Hr | 30 Min |
| Personnel Tracing | PATROL | 4 Hrs | 2 Hrs |
| Goods & IoT | GENSET | 8 Hrs | 3 Hrs (+ Recalibration 8 Hrs) |
| Goods & IoT | KAGO | 4 Hrs | 3 Hrs |
| Goods & IoT | THERMO | 2 Hrs | 1 Hr |
| Goods & IoT | PASO | 1 Hr | 1 Hr |
| Goods & IoT | PAWA | 4 Hrs | 3 Hrs |

Trainer tactic :
When a product has recalibration time, you SHALL communicate it upfront. The customer perceives recalibration delays as incompetence unless you pre‐frame it.

## 17.4 Preventative Maintenance Checklists (System + Device)
### A. Daily CMS Health Routine (15–25 minutes)
1. Open Command & Control → System Health:
 - Verify ingestion, streaming, cache, database health indicators.
2. Check Alarm Center:
 - Identify top 3 recurring alarms (offline clusters, token depletion).
3. Check Token Engine:
 - Identify top 10 burn spikes (abnormal consumption).
4. Check Messaging Delivery Health:
 - WhatsApp/SMS failure rate, throttling, and cost spikes.
✅ Output required:
 - One "Daily Health Note" posted to the internal ops channel or ticketing system.
### B. Weekly Device & Connectivity Preventative Maintenance
1. Offline clusters (group by network operator/region):
 - Determine if outages are carrier‐related, APN‐related, or configuration‐related.
2. Voltage anomalies:
 - Detect chronic under‐voltage that will cause intermittent reporting.
3. Firmware / OTA queue:
 - Confirm no mass update in progress without a rollback plan.
4. SIM audit:
 - Roaming misuse, data bundle mismatch, top spend SIMs.
### C. Monthly Preventative Maintenance
1. Run Access Governance Bot / Access Review:
 - Validate least privilege and remove stale admin rights.
2. Review token pricing policy version changes:
 - Confirm policy notices prepared if pricing changes are planned.
3. Run "Top 20 noisy units":
 - Units generating excessive alarms/messages (optimize intervals).
4. Review "Top 20 silent units":
 - Units with suspiciously low telemetry (misconfiguration or tamper).

## 17.5 Corrective Maintenance Playbook (Standard Response)
### A. Corrective Maintenance Workflow (Mandatory Sequence)
1. Stabilize: stop the bleeding (restore comms, reduce false alarms).
2. Diagnose: confirm root cause using evidence (logs + telemetry).
3. Correct: implement minimal safe change.
4. Validate: confirm resolution with proof (unit online + report).
5. Prevent recurrence: implement guardrails and document.
✅ HIC rule: Waswa AI may propose the fix, but a human must approve the change if it affects billing, permissions, or mass device commands.

## 17.6 CX Improvement Tactics (UG/KE Realities)
1. Proactive customer comms:
 - "We detected X; we are doing Y; ETA Z."
 This reduces inbound calls and protects trust.
2. Token transparency:
 - Always show "why tokens burned" (video snapshots vs GPS vs alerts).
3. Self‐service first actions:
 - Provide drivers/managers simple steps via WhatsApp templates.
4. Field scheduling discipline:
 - Respect the install/repair time standards; don't promise fantasy timelines.

## 17.7 Operational Templates (Copy/Paste) 3⁄4
### A. Tenant Onboarding Completion Note (Internal)
 - Tenant:
 - Products Enabled:
 - Token SKU:
 - Payment Rails:
 - Key Contacts:
 - First Report Delivered: (Yes/No)
 - Alerts Enabled:
 - AI Policy Mode: Draft / Gated / Auto
 - Open Risks:
 - Next Review Date:
### B. Change Record (Mandatory for Risky Changes) ⚠
 - Change Type: RBAC / Billing / Device Profile / Messaging / AI Policy
 - Scope: Single tenant / Multiple tenants / Global
 - Reason:
 - Approval: (Name + timestamp)
 - Rollback Plan:
 - Validation Evidence:

--- PAGE BREAK ---
# 18. WIALON‐TO‐NAVAS ADMIN MAPPING

Purpose
This mapping exists to convert Wialon CMS muscle memory into NAVAS CMS execution without confusion. It focuses on:
 - Hierarchy & multi‐tenancy
 - RBAC & audit
 - Billing (subscription → token engine)
 - Resources & units
 - Messaging and workflow automation
 - HIC / AI governance layer
✅ Assumption: You already understand Wialon's account/resource/unit logic. This section teaches the NAVAS equivalent.

## 18.1 Core Object Mapping (Concepts → NAVAS Modules)
Table style note: set 100% width, no borders , header row shaded #F5F5F5.
| Wialon Concept (CMS Manager) | NAVAS CMS Equivalent | Primary Module | Admin Outcome |
| Account / Dealer hierarchy | Tenant tree (Dealer → Org → Dept) | Asset & Resource Governance  | Controlled delegation and revenue separation |
| Users | Users + RBAC roles + audit | Asset & Resource Governance  | Least privilege + accountability |
| Units | Assets + Devices + Product Profiles | Infrastructure & Connectivity  | Correct telemetry + stable operations |
| Resources (geofences, reports, notifications) | Resource Packs (rules/templates/report packs) | Telematics & GIS Ops  | Standardized reporting and alerts |
| Billing plans | Token SKUs + Policy Versions | Tokenomics & Revenue  | Prevent leakage + enable PAYG |
| Services / Features | Add‐On Apps Library | Utility & Support  | Modular enablement per tenant |
| Audit log | Audit Trails + Change Reason enforcement | Security & Compliance  | Non‐repudiation, governance |
| Notifications (SMS/email) | Messaging Portal (SMS/Email/WhatsApp) | Utility & Support  | Multi‐channel delivery + template discipline |
| Hosting health | Cockpit System Health + Alarm Center | Command & Control  | Proactive operations |
| Custom integrations | OEM Integrations + API Monetization | Infrastructure & Connectivity  | Controlled integrations and revenue |

This structure aligns to NAVAS's "command center + token engine + AI governance" architecture.

## 18.2 NAVAS UI Translation (Blades, Cards, CRUD)
In NAVAS CMS, the admin experience is optimized around:
1. Workspaces (Module landing pages)
2. Cards (summary metrics + quick actions)
3. Blades/Drawers (right-side detailed config)
4. CRUD actions (Create / Read / Update / Disable / Restore)
5. HIC gates (approval prompts + audit notes) ✈✅
### Run‐in (H3) — Key rule
*If an action changes money, access, or device control, it SHALL be gated by HIC and recorded.*

## 18.3 Common Admin Tasks: Wialon vs NAVAS (Step‐By‐Step) ✅
### Task 1 — Create a New Dealer / Tenant
Wialon muscle memory: create account → assign flags → create users → allocate units.
NAVAS execution:
1. Asset & Resource Governance → Tenants → +New Tenant
2. Complete:
 - Region (UG/KE), currency, timezone, parent dealer, status
3. Assign baseline:
 - RBAC templates (Customer Admin, Operator, Auditor)
4. Assign:
 - Token SKU policy version + enforcement thresholds
5. Save (HIC prompt may require reason). ✅
Trainer tactic :
Create a "Tenant Template" per vertical (e.g., Oil & Gas, Logistics, PSVs, BodaBoda). This reduces onboarding time and errors.

### Task 2 — Add Units (Vehicles, Bikes, People, Cargo, IoT)
NAVAS execution:
1. Infrastructure & Connectivity → Devices/Units → +Add
2. Choose product type:
 - OLIWA / PIKI / PATROL / KAGO / THERMO / MAFUTA / DASHCAM etc.
3. Apply profile:
 - Interval, IO map, alerts baseline
4. Bind SIM (if applicable):
 - APN, operator, roaming policy
5. Save and validate:
 - "Unit online + last message timestamp + GPS fix".
✅ Evidence required:
 - Screenshot/log of last communication timestamp and position update.

### Task 3 — Configure Resource Packs (Geofences, Reports, Alerts)
NAVAS execution:
1. Telematics & GIS Ops → Resource Packs
2. Select or create:
 - Geofence sets (depots, borders, restricted zones)
 - Report packs (daily trips, driver behavior, fuel variance)
 - Alert rules (overspeed, tamper, door, temp excursion)
3. Assign pack to tenant/department.
4. Validate:
 - Simulate event; confirm alert is delivered.

### Task 4 — Configure PAYG Monetization (Token Rules)
NAVAS execution:
1. Tokenomics & Revenue → Token Engine
2. Select:
 - Token SKU, policy version, burn rates by parameter/event.
3. Configure:
 - Threshold enforcement + top‐up triggers.
4. Test:
 - Generate known event (e.g., video snapshot) and confirm token deduction logic.
### Run‐in (H4) — HIC rule
*Any change that affects token burn rates SHALL be approved and audited.*

### Task 5 — Enable Add‐On Apps (Modular Provisioning)
NAVAS execution:
1. Utility & Support → Add‐On Apps Library
2. Select tenant → select app:
 - BI, VEBA, INSPECTA, ECO, FLEETRUN, JMS, LOGISTICS, NIMBUS, DSC
3. Verify dependencies:
 - Maps, messaging, payment rails, device compatibility
4. Enable trial/paid and configure enforcement
5. Smoke test:
 - Menu appears + one action completes successfully.

## 18.4 AI + HIC Layer: Where NAVAS Extends Beyond Wialon ✈
Wialon administration is powerful but typically operator-driven. NAVAS introduces a governance layer where AI can assist but humans remain accountable.
### AI Agents You SHALL Use (Standard Set)
1. Resolution Co‐Pilot
 - Summarizes ticket, attaches telemetry context, suggests SOP steps.
2. Progress Notifier
 - Sends milestone updates to customers to reduce follow‐up pressure.
3. Health Sentinel
 - Detects anomaly clusters early (offline/tamper/token depletion).
4. Access Governance Bot
 - Flags risky permission combinations and stale admins.
5. Renewal Minder
 - Drives renewal reminders and payment links to reduce service lapses.
### HIC Enforcement Examples (Mandatory) ✅
You SHALL require approval for:
 - Suspending a tenant due to non‐payment
 - Changing token burn rates
 - Bulk device command execution (reset/OTA/camera stream)
 - Bulk messaging to customers
 - Role escalation to SYSTEM_ADMIN
This is aligned to NAVAS's cost-aware hybrid AI model.

## 18.5 Uganda & Kenya Operational Reality Mapping oa
You SHALL design ops around:
1. Mobile money dominance (M‐Pesa, MTN, Airtel).
2. Variable connectivity quality (2G/3G zones).
3. High operational value of WhatsApp alerts (fastest response loop).
4. Preventing "silent churn":
 - Customers who stop paying but still expect service.

--- PAGE BREAK ---
# 19. TABLE OF ACRONYMS & ABBREVIATIONS

Purpose
This table is the mandatory reference for terminology used across NAVAS CMS operations, token billing, AI governance, and field support.
Table style note: set 100% width, no borders , header row shaded #F5F5F5.
| Acronym | Meaning | Where It Appears in CMS | Operational Use |
| AI | Artificial Intelligence | Waswa AI Console, Ticket Co‐Pilot | Recommendations, summaries, anomaly detection |
| API | Application Programming Interface | Integrations, OEM connectors | External system integrations, monetization |
| APN | Access Point Name | SIM Console | SIM connectivity configuration |
| ART | Average Response Time | Helpdesk KPIs | Support responsiveness governance |
| AUDIT | Audit Trail / Logs | Security & Compliance | Evidence of changes and actions |
| BI | Business Intelligence | BI Dashboards add‐on | Executive reporting and analytics |
| CANBus | Controller Area Network | Mafuta Canbus | Vehicle diagnostics and fuel telemetry |
| CMS | Customer Management System | Entire platform | Multi‐tenant administration |
| CSAT | Customer Satisfaction | Ops dashboards | Customer experience measurement |
| DSC | Driver Safety Console (3D add‐on) | Add‐Ons | Driver behavior/safety workflows |
| DMS | Driver Monitoring System | Dash AI / MDVR AI | Fatigue/distraction monitoring |
| DR | Disaster Recovery | Command & Control | Business continuity planning |
| ETA | Estimated Time of Arrival | Live Ops | Dispatch and customer comms |
| FIFO | First‐In First‐Out | Token Engine | Token consumption order enforcement |
| FCR | First Contact Resolution | Helpdesk KPIs | Reduce escalations and field dispatch |
| FLS | Fuel Level Sensor | Mafuta FLS | Fuel monitoring and theft detection |
| GIS | Geographic Information System | Maps/Geofences | Routing, geofencing, spatial analytics |
| HIC / HITL | Human‐In‐Control / Human‐In‐The‐Loop | AI Console, approvals | Mandatory governance for risky actions |
| IMEI | Device Identifier | Device provisioning | Unique tracking hardware identification |
| IoT | Internet of Things | Goods/IoT modules | Sensors, cold chain, environment monitoring |
| JMS | Job Management System | JMS add‐on | Field jobs, tickets, scheduling |
| KPI | Key Performance Indicator | Dashboards | Performance measurement |
| L1/L2/L3 | Support Levels 1–3 | Incident escalation | Escalation routing |
| MDVR | Mobile Digital Video Recorder | Video telematics | Multi-camera recording and events |
| MoMo | Mobile Money | Payments | Top‐ups and billing settlements |
| MRT | Mean Resolution Time | Helpdesk KPIs | End‐to‐end resolution speed |
| MTTR | Mean Time To Repair/Resolve | Ops KPIs | Reliability and support governance |
| OEM | Original Equipment Manufacturer | Integrations | Hardware/software integrations |
| PAYG | Pay‐As‐You‐Go | Token billing | Usage-based charging model |
| PSV | Public Service Vehicle | Fleet ops
