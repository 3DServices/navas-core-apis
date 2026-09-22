# CMS_USER STORIES

<!-- page 1 -->
🌟 Absolutely Below is Version 1 of the CMS user stories , using the same seven personas you approved earlier. I'm treating CMS as the NAVAS / UKO control plane for hierarchy, access, settings,

### operations, billing, marketplace, SIMs, monitoring, reporting, and governance . These

stories are synthesized from the latest UKO user-story pack, the NAVAS hierarchy/customization model, the token billing strategy, the SIM/zAPP guidance, the procurement workflow, and the development playbook's MTTR / documentation discipline. I've kept the same practical priority order for story-writing:

### B → E → C → F → D → G → A

# CMS User Stories — Master Draft

# B. SYSTEM ADMINISTRATOR / PLATFORM ADMINS

These stories are grounded in the NAVAS hierarchy model, role customization, app control, settings governance, and system-wide security scope for Platform Admins / Server Admins.

### CMS-B-01

As a System Administrator , I want to create accounts by hierarchy type such as top account, account with dealer rights, and account without dealer rights , so as to structure the service correctly, in order to preserve governance from day one.

### CMS-B-02

As a System Administrator , I want parent accounts to automatically limit subordinate rights, so as to prevent privilege creep, in order to keep the hierarchy safe and predictable.

### CMS-B-03

As a Platform Admin , I want to manage global users, roles, permissions, and session policies , so as to control who can see and do what, in order to reduce security risk and operational confusion.

### CMS-B-04

<!-- page 2 -->
### As a Platform Admin , I want to enforce 2FA, trusted-device rules, login alerts, and recovery

settings , so as to reduce account takeover risk, in order to protect sensitive operational and billing data.

### CMS-B-05

As a Platform Admin , I want to issue and revoke API tokens by user, tenant, and environment, so as to govern integrations safely, in order to avoid uncontrolled external access.

### CMS-B-06

As a Platform Admin , I want to add, configure, enable, disable, and restore Apps from the appropriate hierarchy level, so as to manage platform capabilities centrally, in order to keep service packaging controlled.

### CMS-B-07

As a System Administrator , I want to apply organization-wide defaults for language,

### timezone, dashboard layout, notification channels, export formats, and AI behavior , so as

to balance standardization with flexibility, in order to simplify rollout across many customers.

### CMS-B-08

As a System Administrator , I want to bulk import and export users, account settings, and resources , so as to reduce repetitive setup work, in order to speed up onboarding and restructuring.

### CMS-B-09

As a Platform Admin , I want a service hierarchy view showing all subordinate accounts, creators, inherited rights, and object ownership, so as to understand structure at a glance, in order to debug access problems faster.

### CMS-B-10

As a Platform Admin , I want a bird's-eye system health dashboard for GPS, GSM, power integrity, server uptime, app reliability, and support responsiveness, so as to spot platform-wide issues early, in order to reduce MTTR.

### CMS-B-11

As a System Administrator , I want a full AI transparency log showing suggestions, confidence notes, approvals, overrides, and blocked actions, so as to keep Waswa AI auditable, in order to preserve Human-in-Control governance.

<!-- page 3 -->
### CMS-B-12

As a System Administrator , I want deleted objects to be restorable by authorized roles only, so as to recover from mistakes safely, in order to avoid avoidable data loss.

# E. DEALER

These stories are grounded in dealer-rights account behavior, subordinate account control, branding/report customization, client account segmentation, and governed app enablement.

### CMS-E-01

As a Dealer , I want to create and manage subordinate client accounts under my dealer scope, so as to serve multiple customers independently, in order to scale channel operations cleanly.

### CMS-E-02

As a Dealer , I want to assign only the billing plans, apps, and permissions allowed by my parent account, so as to stay within authorized scope, in order to prevent commercial and governance breaches.

### CMS-E-03

As a Dealer , I want to customize logos, themes, labels, and client-facing report packs per customer, so as to support white-label delivery, in order to improve channel value and retention.

### CMS-E-04

As a Dealer , I want to provision add-on apps per client with dependency checks, so as to avoid enabling broken combinations, in order to reduce support load and failed rollouts.

### CMS-E-05

As a Dealer , I want to clone account templates for similar customers by sector, country, or fleet type, so as to avoid repeating setup work, in order to onboard faster.

### CMS-E-06

As a Dealer , I want to monitor enabled-to-used-to-paid conversion for apps and value-added services, so as to know which offerings drive real adoption, in order to improve upsell decisions.

### CMS-E-07

<!-- page 4 -->
As a Dealer , I want visibility into client payment status, suspension risk, and renewal status within my authorized scope, so as to intervene early, in order to reduce churn and service interruption.

### CMS-E-08

As a Dealer , I want to see support trends by client, product, and asset class, so as to identify which accounts are becoming expensive to serve, in order to act before satisfaction drops.

### CMS-E-09

As a Dealer , I want to segment clients by country, branch, industry, fleet size, and product bundle, so as to manage my portfolio intelligently, in order to support targeted growth.

### CMS-E-10

As a Dealer , I want a full audit trail of who changed branding, permissions, apps, billing plans, and account status, so as to investigate disputes quickly, in order to strengthen accountability.

# C. FINANCE MANAGER

These stories are grounded in the canonical token billing design: composable billing, FIFO consumption, quote-before-purchase, usage simulation, immutable ledger, reporting, caps, safeguards, and SIM/data cost visibility.

### CMS-C-01

As a Finance Manager , I want to define token bundles around outcomes such as safety,

### compliance, AI insight, route optimization, and cold-chain integrity , so as to price value in

business language, in order to improve adoption and ARPU.

### CMS-C-02

As a Finance Manager , I want to create quotes before token purchase with clear breakdowns of base rate, multiplier, discount, and expiry , so as to make pricing predictable, in order to reduce disputes and approval delays.

### CMS-C-03

As a Finance Manager , I want to simulate hypothetical usage without ledger impact, so as to test margin and customer impact before launch, in order to avoid pricing mistakes.

<!-- page 5 -->
### CMS-C-04

As a Finance Manager , I want a unified wallet view by product, class, department, branch, and country , so as to see where spend is concentrated, in order to manage budgets before interruptions occur.

### CMS-C-05

As a Finance Manager , I want to allocate tokens from a central company pool down to departments, projects, branches, and assets, so as to enforce spending discipline, in order to map usage to the organogram.

### CMS-C-06

As a Finance Manager , I want token packs for the same asset to be consumed in FIFO order , so as to preserve continuity transparently, in order to avoid silent downtime and reconciliation ambiguity.

### CMS-C-07

### As a Finance Manager , I want configurable soft alerts, hard stops, caps, and optional

auto-pause by product or token class, so as to prevent runaway spend, in order to protect gross margin.

### CMS-C-08

As a Finance Manager , I want an immutable billing ledger with separate adjustment entries, so as to satisfy audits and disputes, in order to keep revenue evidence-grade.

### CMS-C-09

As a Finance Manager , I want burn-rate dashboards by product, class, parameter family, market, and customer outcome , so as to see what consumes value fastest, in order to tune bundles and pricing strategy.

### CMS-C-10

As a Finance Manager , I want to manage collections, disputes, refunds, dunning stages, and reconciliation mismatches in one workflow, so as to keep payments trustworthy, in order to reduce leakage and service pauses.

### CMS-C-11

<!-- page 6 -->
As a Finance Manager , I want to support multi-level billing where sub-managers can pay for departments while the master account retains oversight, so as to mirror real organizations, in order to improve collections and accountability.

### CMS-C-12

As a Finance Manager , I want daily, weekly, and monthly SIM/data spend summaries by telco, country, product, and customer account, so as to detect unnoticed margin erosion, in order to keep connectivity profitable.

# F. FIELD HARDWARE INSTALLER

These stories are grounded in the units, sensors, SIMs, jobs, health, and field evidence patterns across the UKO pack, plus the need for guided diagnostics, MTTR-conscious workflows, and low-bandwidth operation.

### CMS-F-01

As a Field Hardware Installer , I want to register a unit with asset metadata, device serial, and installation status, so as to create a reliable digital twin, in order to make future support easier.

### CMS-F-02

As a Field Hardware Installer , I want to pair each tracker with the correct SIM, ICCID, IMEI, APN profile, tariff, and telco , so as to avoid connectivity ambiguity, in order to reduce no-data incidents.

### CMS-F-03

As a Field Hardware Installer , I want to attach and map sensors to the correct unit and parameter library, so as to ensure data is interpreted properly, in order to prevent bad reports and false alerts.

### CMS-F-04

As a Field Hardware Installer , I want guided installation jobs and tasks with checklists, photos, notes, and signoff fields, so as to work consistently, in order to improve first-time quality and reduce repeat visits.

### CMS-F-05

<!-- page 7 -->
As a Field Hardware Installer , I want to test live packet flow immediately after installation, so as to confirm the asset is reporting, in order to catch power, GPS, GSM, or sensor faults before leaving site.

### CMS-F-06

As a Field Hardware Installer , I want to verify history playback and recent telemetry after commissioning, so as to confirm the system is storing usable evidence, in order to prevent hidden post-install failures.

### CMS-F-07

As a Field Hardware Installer , I want to record removed and replaced hardware by old serial, new serial, reason, and receiving store, so as to preserve chain of custody, in order to support warranty and accountability.

### CMS-F-08

As a Field Hardware Installer , I want guided diagnostics for no data, GNSS drift, external power loss, poor signal, and sensor calibration issues , so as to troubleshoot methodically, in order to reduce MTTR.

### CMS-F-09

As a Field Hardware Installer , I want key CMS functions to remain usable in low-bandwidth conditions and sync later, so as to keep work moving in remote corridors, in order to make field operations dependable.

### CMS-F-10

As a Field Hardware Installer , I want to request reserved spares, tools, or consumables directly from my assigned job, so as to avoid stock confusion, in order to shorten turnaround time.

# D. SALES & MARKETING MANAGER

These stories are grounded in token pricing logic, marketplace/app monetization, outcome-based packaging, white-label/commercial packaging, and contextual upsell thinking.

### CMS-D-01

<!-- page 8 -->
As a Sales & Marketing Manager , I want to package CMS products and apps around outcomes rather than technical IOs, so as to make value easy to understand, in order to improve conversion and upsell quality.

### CMS-D-02

As a Sales & Marketing Manager , I want to quote tokenized services with a clear commercial breakdown before purchase, so as to set expectations properly, in order to speed up approvals and reduce objections.

### CMS-D-03

As a Sales & Marketing Manager , I want to publish and curate the app marketplace and e-shop catalog with enablement status, dependencies, and pricing visibility, so as to support discovery, in order to improve cross-sell performance.

### CMS-D-04

As a Sales & Marketing Manager , I want to see conversion funnels from enabled → trial → used → paid , so as to understand where interest is lost, in order to improve GTM execution.

### CMS-D-05

As a Sales & Marketing Manager , I want contextual upsell prompts when a customer reaches a token, AI, video, or reporting threshold, so as to sell more naturally, in order to grow ARPU without heavy renegotiation.

### CMS-D-06

As a Sales & Marketing Manager , I want product bundles localized by country, language, currency, and market type , so as to sell more appropriately across East Africa, in order to reduce rollout friction.

### CMS-D-07

As a Sales & Marketing Manager , I want white-label proposal templates for dealers, resellers, and enterprise accounts, so as to present commercially polished offers fast, in order to shorten sales cycles.

### CMS-D-08

As a Sales & Marketing Manager , I want to attach sample dashboards, compliance reports, AI insights, and ROI narratives to offers, so as to sell evidence not just promises, in order to improve close rates.

<!-- page 9 -->
### CMS-D-09

As a Sales & Marketing Manager , I want compatibility views by asset type, hardware, sensor, and add-on app, so as to avoid overselling impossible combinations, in order to protect trust and reduce rework.

### CMS-D-10

As a Sales & Marketing Manager , I want campaign and source attribution from first contact to closed deal and activated app, so as to know which channels work, in order to focus budget where returns are strongest.

# G. PROCUREMENT / INVENTORY MANAGER

These stories are grounded in the purchasing workflow, stock logic, supplier comparison, landed cost, digital service renewals, and serial-level traceability for hardware, sensors, SIMs, and related supplies.

### CMS-G-01

As a Procurement / Inventory Manager , I want to create RFQs and compare suppliers by

### price, quality, lead time, payment terms, and available quantity , so as to buy more

intelligently, in order to improve value-for-money.

### CMS-G-02

As a Procurement / Inventory Manager , I want a compatibility registry for trackers, sensors, SIM profiles, cameras, and accessories, so as to prevent wrong purchases, in order to reduce installation delays.

### CMS-G-03

As a Procurement / Inventory Manager , I want landed cost views including purchase value, freight, customs, and clearance costs, so as to know the true cost of hardware, in order to improve pricing and replenishment decisions.

### CMS-G-04

As a Procurement / Inventory Manager , I want minimum stock, maximum stock, and reorder triggers tied to project demand and service schedules, so as to prevent shortages, in order to avoid job delays.

<!-- page 10 -->
### CMS-G-05

As a Procurement / Inventory Manager , I want stock to be reservable to jobs, installers, branches, and projects, so as to prevent double allocation, in order to improve field readiness.

### CMS-G-06

As a Procurement / Inventory Manager , I want serial-level tracking for each item from supplier to store to field installation or return, so as to preserve accountability, in order to support warranty, audit, and recovery workflows.

### CMS-G-07

As a Procurement / Inventory Manager , I want to manage RMAs, warranty claims, damaged returns, and test-bench items separately, so as to distinguish usable stock from pending stock, in order to keep inventory accurate.

### CMS-G-08

As a Procurement / Inventory Manager , I want purchasing needs to include digital services such as subscriptions, tokens, or credit alongside hardware, so as to manage all operational dependencies in one workflow, in order to avoid service gaps.

# A. SCRUM MASTER

These stories are grounded in the playbook's responsibilities for ceremonies, blockers, metrics, SLOs, documentation, review discipline, linked defects, and dashboard-driven supervision.

### CMS-A-01

As a Scrum Master , I want a CMS delivery board grouped by module, persona, epic, and sprint, so as to track flow clearly, in order to improve delivery predictability.

### CMS-A-02

As a Scrum Master , I want each story to require acceptance criteria, test notes, and performance expectations before development starts, so as to improve story readiness, in order to reduce churn during sprint execution.

### CMS-A-03

<!-- page 11 -->
As a Scrum Master , I want defects and incidents linked back to the originating module and user story, so as to see recurring weaknesses, in order to improve root-cause learning and quality control.

### CMS-A-04

As a Scrum Master , I want severity-based triage for CMS issues with SLA and MTTR targets, so as to distinguish emergencies from minor defects, in order to guide correct response speed.

### CMS-A-05

As a Scrum Master , I want weekly dashboards for latency, error rates, adoption, billing risk, and support backlog per module, so as to see the health of delivery and operations together, in order to guide sprint decisions.

### CMS-A-06

As a Scrum Master , I want maker-checker evidence and release checklist completion before risky CMS changes go live, so as to strengthen governance, in order to reduce regression risk.

### CMS-A-07

As a Scrum Master , I want runbooks, ADRs, and postmortems updated as part of closure criteria, so as to preserve team memory, in order to improve sustainability and onboarding.

### CMS-A-08

As a Scrum Master , I want a module-level view of business impact such as safety, spend, uptime, adoption, and complaint volume, so as to prioritize the highest-value work, in order to align execution with outcomes.

# Cross-Persona CMS Epics

To make these easier to load into Odoo / Jira / Linear, I'd group them into these epics:

# Epic 1 — Hierarchy, Identity & Access

Covers:

- CMS-B-01 to CMS-B-06
- CMS-E-01 to CMS-E-03
<!-- page 12 -->
- CMS-A-06
# Epic 2 — Tenant Setup, Branding & Governance

Covers:

- CMS-B-07 to CMS-B-12
- CMS-E-04 to CMS-E-10
# Epic 3 — Token Billing, Payments & Revenue Control

Covers:

- CMS-C-01 to CMS-C-12
- CMS-D-01 to CMS-D-06
# Epic 4 — Field Operations, Units, Sensors & SIMs

Covers:

- CMS-F-01 to CMS-F-10
- CMS-G-02, CMS-G-05, CMS-G-06
# Epic 5 — Marketplace, E-Shop & Commercial Packaging

Covers:

- CMS-D-03 to CMS-D-10
- CMS-E-04 to CMS-E-06
# Epic 6 — Procurement, Inventory & Supplier Control

Covers:

- CMS-G-01 to CMS-G-08
# Epic 7 — Delivery Governance & Quality Control

Covers:

- CMS-A-01 to CMS-A-08
<!-- page 13 -->
# Recommended next sequencing

If you want the strongest implementation order, I would stage them like this:

# Phase 1 — Foundation

- All B stories
- E-01 to E-04
- C-01 to C-08
- A-01 to A-04
# Phase 2 — Operational rollout

- All F stories
- G-01 to G-06
- E-05 to E-10
# Phase 3 — Commercial scale

- Remaining C stories
- All D stories
- Remaining G stories
- A-05 to A-08
# Best next deliverable

The cleanest next step is to convert this into a full CMS BRD-style user story pack with:

- Epic
- User story
- Acceptance criteria
- Priority
- Dependencies
- Notes / assumptions
That would make it ready for direct backlog loading.

<!-- page 14 -->
