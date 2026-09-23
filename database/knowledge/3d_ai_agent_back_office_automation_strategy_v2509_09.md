# 3D-AI-AGENT-BACK OFFICE AUTOMATION STRATEGY V2509.09

<!-- page 1 -->
# 3D Services Limited — AI Agent

# Strategy for Back - Office Automation

# (Uganda & Kenya) — v5.0

## 0) Executive Summary & Context

Purpose. This document defines a comprehensive, human‐in‐the‐loop (HITL) strategy for selecting, implementing, and maintaining AI agents that automate routine back‐office work at 3D Services Limited, while improving speed, frequency, and consistency of reporting and communication to customers across Uganda and Kenya. It explicitly assumes that humans will inevitably be involved in critical steps such as manual ticket intake, approvals, field dispatch, and customer communication sign‐offs. Scope. The scope spans production telematics systems (Wialon Hosting; 3DTracking; in‐house Navas IoT at oliwa.live; video systems Howen VSS and Streamax Ceiba II) and productivity platforms (Odoo Online/Odoo.sh/On‐prem with SDK/Studio and External APIs; Microsoft 365/Power BI; WhatsApp; SMS; Email; Google Sheets; and selected social channels). Alignment with company materials. The design reflects the strategic directions and org structures captured in the '3DS‐STRATEGIC PRIORITY MAP (06‐Sept‐2024)' and '3D Organogram 03‐Nov‐2023', the customer journey mapping notes (CJM opps, CJM notes, CJM notes 2), the customer service strategy '3DS‐QMS‐WI‐72_PROJECT_WOW_TEPU_SUB_CONTRACTORS_21OCT24', the practical guide to building agents, and the documented causes of poor service. These inputs shape our agent selection, guardrails, and KPIs. Operating thesis. Telemetics is event‐rich but attention‐poor: success depends on converting noisy signals (trips, fuel level changes, overspeed, idling, geofence breaches, camera incidents) into timely, human‐readable actions that satisfy customers and reduce operational load. Therefore, we prioritize reversible automations, deterministic interfaces, auditability, and graceful degradation to manual operation.

## 1) Reference Architecture (Why this stack)

System spine. Odoo is the transactional backbone (CRM, Helpdesk, Orders, Billing, Inventory, HR). Every customer‐facing or financial action is persisted here and subject to the company's maker‐checker and QMS controls. Agents read from and write to Odoo via its SDK and REST APIs, and Odoo hosts the HITL approval surfaces (server actions, buttons, views, and access rules). Telemetry sources. Wialon remains the most mature source of deterministic telematics events; 3DTracking covers legacy estates; and Navas IoT provides in‐house, rapidly evolving analytics

<!-- page 2 -->
and anomaly scoring. Video platforms (Howen VSS, Streamax Ceiba II) are integrated for incident evidence (clips, snapshots, metadata) to improve ticket quality and driver coaching. Channels. WhatsApp Business, SMS, Email, and optional social handles deliver outbound comms (reports, alerts, notices, thank‐yous) and capture inbound signals (leads, complaints). Quiet‐hour rules, throttling, and bundling reduce fatigue. Screen‐pops surface context to call‐centre staff. Data & Intelligence layer. PostgreSQL (with pgvector) stores agent logs, embeddings, and prompt/response traces; an object store holds generated reports and media; Power BI and Google Sheets serve as analysis and export tools. The LLM layer (GPT‐4/Gemini via API) is mediated by LangChain/LlamaIndex tools with explicit JSON schema outputs and tool‐calling policies.

## 2) Agent Selection & Prioritization

Selection criteria. Each candidate workflow is scored on: (1) Business Impact, (2) Data Readiness, (3) Effort/Complexity, (4) Operational Risk and Reversibility, (5) QMS Criticality & Audit burden, and (6) Customer Value/CSAT uplift. Priority order (first 6 months). 1) Customer Reporting & Communications; 2) Incident Ticket Management; 3) Billing & Retention; 4) Sales Lead Management; 5) Back‐Office Document Automation; 6) Video Evidence Attachments. This aligns with CJM pain points, WOW service expectations, and observed causes of poor service (delays, missing follow‐ups, inconsistent updates).

<!-- page 3 -->
HITL doctrine. Any irreversible action—financial postings, account suspension, quote issuance, KB publishing—must flow through a human approval widget in Odoo. The agent proposes; a named role approves; the action and rationale are logged and retrievable.

## 3) Target Agent Portfolio (roles, inputs, outputs, HITL gates)

RAA — Reporting & Alerts Agent.

- Inputs (data & triggers). Schedules, device events (overspeed, harsh, fuel, geofences, offline),
CRM states, billing dates, manual form inputs.

- Behaviours. Deterministic tool‐calls (queries, templating, file generation), retrieval‐augmented
guidance, channel selection & throttling.

- Outputs. Odoo records updated; PDFs/Excels; WhatsApp/SMS/Email messages; dashboards;
job‐cards/PFIs; ticket notes; attachments.

- HITL gates. First‐month template sign‐off; P1 triage approvals; quote approvals; finance
approvals for suspension/resume; KB publish review.

- KPIs. Delivery success rate; latency (P1 <2 min); FRT; MTTR; speed‐to‐lead; on‐time payment
rate; CSAT; audit completeness. ITA — Incident & Ticket Agent.

- Inputs (data & triggers). Schedules, device events (overspeed, harsh, fuel, geofences, offline),
CRM states, billing dates, manual form inputs.

<!-- page 4 -->
- Behaviours. Deterministic tool‐calls (queries, templating, file generation), retrieval‐augmented
guidance, channel selection & throttling.

- Outputs. Odoo records updated; PDFs/Excels; WhatsApp/SMS/Email messages; dashboards;
job‐cards/PFIs; ticket notes; attachments.

- HITL gates. First‐month template sign‐off; P1 triage approvals; quote approvals; finance
approvals for suspension/resume; KB publish review.

- KPIs. Delivery success rate; latency (P1 <2 min); FRT; MTTR; speed‐to‐lead; on‐time payment
rate; CSAT; audit completeness. SCA — Sales & Call - Centre Agent.

- Inputs (data & triggers). Schedules, device events (overspeed, harsh, fuel, geofences, offline),
CRM states, billing dates, manual form inputs.

- Behaviours. Deterministic tool‐calls (queries, templating, file generation), retrieval‐augmented
guidance, channel selection & throttling.

- Outputs. Odoo records updated; PDFs/Excels; WhatsApp/SMS/Email messages; dashboards;
job‐cards/PFIs; ticket notes; attachments.

- HITL gates. First‐month template sign‐off; P1 triage approvals; quote approvals; finance
approvals for suspension/resume; KB publish review.

- KPIs. Delivery success rate; latency (P1 <2 min); FRT; MTTR; speed‐to‐lead; on‐time payment
rate; CSAT; audit completeness. BRLA — Billing, Retention & Lifecycle Agent.

- Inputs (data & triggers). Schedules, device events (overspeed, harsh, fuel, geofences, offline),
CRM states, billing dates, manual form inputs.

- Behaviours. Deterministic tool‐calls (queries, templating, file generation), retrieval‐augmented
guidance, channel selection & throttling.

- Outputs. Odoo records updated; PDFs/Excels; WhatsApp/SMS/Email messages; dashboards;
job‐cards/PFIs; ticket notes; attachments.

- HITL gates. First‐month template sign‐off; P1 triage approvals; quote approvals; finance
approvals for suspension/resume; KB publish review.

- KPIs. Delivery success rate; latency (P1 <2 min); FRT; MTTR; speed‐to‐lead; on‐time payment
rate; CSAT; audit completeness. BOA — Back - Office Automation Agent.

- Inputs (data & triggers). Schedules, device events (overspeed, harsh, fuel, geofences, offline),
CRM states, billing dates, manual form inputs.

<!-- page 5 -->
- Behaviours. Deterministic tool‐calls (queries, templating, file generation), retrieval‐augmented
guidance, channel selection & throttling.

- Outputs. Odoo records updated; PDFs/Excels; WhatsApp/SMS/Email messages; dashboards;
job‐cards/PFIs; ticket notes; attachments.

- HITL gates. First‐month template sign‐off; P1 triage approvals; quote approvals; finance
approvals for suspension/resume; KB publish review.

- KPIs. Delivery success rate; latency (P1 <2 min); FRT; MTTR; speed‐to‐lead; on‐time payment
rate; CSAT; audit completeness. KBCA — Knowledge Base & Compliance Agent.

- Inputs (data & triggers). Schedules, device events (overspeed, harsh, fuel, geofences, offline),
CRM states, billing dates, manual form inputs.

- Behaviours. Deterministic tool‐calls (queries, templating, file generation), retrieval‐augmented
guidance, channel selection & throttling.

- Outputs. Odoo records updated; PDFs/Excels; WhatsApp/SMS/Email messages; dashboards;
job‐cards/PFIs; ticket notes; attachments.

- HITL gates. First‐month template sign‐off; P1 triage approvals; quote approvals; finance
approvals for suspension/resume; KB publish review.

- KPIs. Delivery success rate; latency (P1 <2 min); FRT; MTTR; speed‐to‐lead; on‐time payment
rate; CSAT; audit completeness. VEA — Video Events Agent.

- Inputs (data & triggers). Schedules, device events (overspeed, harsh, fuel, geofences, offline),
CRM states, billing dates, manual form inputs.

- Behaviours. Deterministic tool‐calls (queries, templating, file generation), retrieval‐augmented
guidance, channel selection & throttling.

- Outputs. Odoo records updated; PDFs/Excels; WhatsApp/SMS/Email messages; dashboards;
job‐cards/PFIs; ticket notes; attachments.

- HITL gates. First‐month template sign‐off; P1 triage approvals; quote approvals; finance
approvals for suspension/resume; KB publish review.

- KPIs. Delivery success rate; latency (P1 <2 min); FRT; MTTR; speed‐to‐lead; on‐time payment
rate; CSAT; audit completeness.

## 4) Hybrid Workflows (Automation with human control)

Manual ticket intake. Helpdesk staff capture verbal/informal issues into Odoo within 2 minutes, using a minimal form. ITA proposes category, priority, and top‐3 KB steps; staff confirm or edit.

<!-- page 6 -->
Dispatch rules assign a technician based on region and skill. ETA is shared with the customer via WhatsApp/SMS. Evidence (photos, clips) is uploaded; closure requires QA and a CSAT message. Reporting preview & approval. RAA assembles a digest per customer contact matrix, bundles hourly events, applies quiet‐hours, and drafts a plain‐language summary with links. During the first month for each account, Helpdesk must approve or hold drafts before delivery. Sales lead handling. SCA captures website/WhatsApp/social inquiries, enriches with firmographics, dedupes, and schedules a call. Quotes are drafted from price books with taxes/currencies; Sales approves before sending. A seven‐day follow‐up cadence runs until closed. Billing & lifecycle. BRLA sends D‐7/D‐3/D‐1 reminders with payment links, D+1/D+7 nudges, and payment thank‐yous. D+30 suspension/resume is agent‐proposed but finance‐approved. Birthday/anniversary outreach draws from CRM preferences.

<!-- page 7 -->
## 5) Project Management & Governance

Delivery model. Scrum with two‐week sprints and a Kanban swimlane for operational fixes. Artefacts: Product Vision, Epic charters, Definition of Ready (DoR), Definition of Done (DoD), Sprint Review demo criteria, and Release checklists aligned to QMS.

<!-- page 8 -->
Work streams. (A) Integrations & Orchestration; (B) Data & Intelligence; (C) Experience & Channels; (D) Security & Compliance; (E) Change Management & Training. Each work stream has a Lead, a Deputy, and explicit RACI. Environments. Dev → Staging → Production with data masking, seeded test (cid:976)ixtures, and contract tests. Canary releases for risky flows (e.g., billing). Rollback scripts and feature flags are mandatory. Backlog structure. Epics per agent; stories follow INVEST; acceptance criteria in Given/When/Then; non‐functional requirements (NFRs) attached; test cases linked; performance budgets specified (latency, cost, throughput).

## 6) Step - by - Step Implementation Plan (0–6 months)

Phase 0 — Foundations (Weeks 0‐2). Establish repositories, branching, and CI/CD. Provision secrets vault and API gateway. Define canonical event contracts (DeviceEvent, VideoEvent, CustomerEvent, BillingEvent). Map contact matrices per account. Connect webhooks/cron for Wialon, 3DTracking, and Navas. Implement central logging, metrics, and tracing with dashboards. Phase 1 — MVP Agents (Weeks 3‐6). Build adapters for Odoo, WhatsApp/SMS/Email. Implement RAA daily scorecards and hourly alert bundling with quiet‐hours and approval preview. Implement ITA manual intake with AI triage suggestions and dispatch rules. Implement BRLA D‐7/D‐3/D‐1 reminders and payment thank‐yous. Phase 2 — Field & Sales (Weeks 7‐10). Add field evidence pipeline, CSAT, and closure QA. Implement SCA lead sequencer and quote copilot from price books; introduce bilingual templates (EN/Swahili). Bring KBCA search online with SOPs/wiring diagrams/CJM extracts. Phase 3 — Expansion (Weeks 11‐14). Extend triggers (fuel theft heuristics; offline tiers; geofence dwell). Launch VEA video incident attachments. Introduce churn‐risk heuristics and save‐offer prompts. Optimize LLM/tool latency and cost. Deliver team training and runbooks. Months 4‐6 — Navas model pilots. Correlate fused anomalies, benchmark against Wialon/3DTracking events, and ship canary updates. Plan migration for legacy 3DTracking estates where appropriate.

## 7) Technology Stack — Rationale

Why Odoo. Odoo unifies CRM, Helpdesk, Billing, and Inventory while exposing a mature SDK and studio tooling for rapid, auditable surfaces. This reduces integration sprawl and centralizes HITL approvals. Alternatives (Salesforce, Dynamics) have higher TCO and longer lead‐times. Why Wialon + 3DTracking + Navas. Wialon offers depth and scale of device integrations and battle‐tested reporting; 3DTracking covers legacy customers; Navas delivers in‐house agility for advanced analytics and model experimentation. The trio maximizes coverage while avoiding lock‐in.

<!-- page 9 -->
Why LangChain/LlamaIndex + GPT‐4/Gemini. These enable tool‐using agents with strict JSON schemas and deterministic policies. Using hosted LLM APIs avoids heavy MLOps upfront while allowing gradual specialization (domain prompts, small adapters, retrieval). Why Postgres + pgvector. A single relational store for operational data and embeddings simplifies compliance and reporting. Power BI and Google Sheets meet customer export expectations without tying analytics to a single vendor. Why n8n/Temporal orchestrator. We require retries, schedules, idempotency, and audit trails for flows; an orchestrator provides these natively, reducing custom cron code and widening observability.

## 8) Security, Privacy, and Compliance

Identity & Access. Company‐wide SSO with RBAC; least privilege for agent service accounts. Access reviews quarterly. Secrets in Vault. Data Protection. PII redaction at ingestion; per‐field encryption for sensitive attributes; signed webhooks; region tagging for UG/KE residency. Audit & QMS. Every automated message, approval, and financial action produces an immutable log entry. Quarterly ISO/QMS evidence pack export. Safety. Guardrails on prompts; banned actions without approval; rate limits. Explicit fail‐open to manual processes during outages.

## 9) Maintenance, Monitoring, and Continual Improvement

Runbooks. Per‐agent runbooks define SLOs (availability, latency), dashboards, alerts, and playbooks for common failures (API limits, timeouts, template errors). Maker‐checker workflows are verified weekly. Model/Pipeline upkeep. Weekly prompt review for drift; monthly KB refresh; quarterly LLM provider evaluation; canary releases; rollback if CSAT drops or error budgets exceed thresholds. Cost governance. Per‐agent cost dashboards (LLM tokens, SMS/WhatsApp, storage, compute). Budgets and alarms. Continuous template optimization to reduce verbosity and token usage. Capacity & DR. Autoscaling for the orchestrator and agent runtime. Backup policies for Postgres and object store. DR run annually.

## 10) KPIs, SLAs, and Expected Impact

Reports: 99% delivery, daily scorecards by 07:00 local; event digest latency <10 minutes. Alerts: P1 <2 minutes end‐to‐end; false‐positive rate <2%; opt‐out rate <1% per month.

<!-- page 10 -->
Helpdesk: First Response Time (P2/3) <15 minutes; MTTR 24–48h; First Contact Resolution uptrend; CSAT ≥ 4.5/5. Sales: Speed‐to‐lead <10 minutes during business hours; conversion rate +X%; quote turnaround median <24h. Billing: On‐time payment ≥90%; DSO reduced by Y days; churn <5%; suspension accuracy 100% (no false suspensions).

## 11) User Stories (INVEST) with Acceptance Criteria

RAA‐1: As a Transport Supervisor, I receive a daily fleet scorecard by 07:00, so I can plan coaching. ‐ Given recipients and data are valid ‐ When the scheduler runs at 06:50–07:00 ‐ Then PDF/Excel + summary is delivered & audit‐logged RAA‐2: As a Safety Manager, I receive hourly bundled harsh/fuel alerts, so I avoid alert fatigue. ‐ Given multiple events occur within 60 minutes ‐ When bundling runs ‐ Then one digest is sent respecting quiet hours & channel policy ITA‐1: As a Helpdesk Agent, I can create a ticket from a phone call, so informal issues are tracked. ‐ Given a verbal report ‐ When I enter minimum required fields ‐ Then a ticket with unique ID is created within 2 minutes ITA‐2: As Support, I see AI‐suggested class/priority & top‐3 KB steps, so I triage faster. ‐ Given a new ticket ‐ When ITA runs retrieval ‐ Then suggestions appear for approval with citations SCA‐1: As a Sales Rep, new leads are auto‐enriched and deduped, so I respond within 10 minutes. ‐ Given an inbound lead ‐ When enrichment completes

<!-- page 11 -->
‐ Then CRM has normalized contacts and sector; duplicates merged SCA‐2: As Sales, I get a PFI draft from price books, so quotes are consistent. ‐ Given an approved opportunity ‐ When I request PFI ‐ Then a draft with correct taxes/currency is produced for approval BRLA‐1: As Finance, D‐7/D‐3/D‐1 reminders are sent with links, so collections improve. ‐ Given invoices due ‐ When schedule runs ‐ Then reminders are sent via preferred channel with tracking BRLA‐2: As Finance, D+30 suspensions require approval, so policy is followed. ‐ Given overdue >30 days ‐ When agent proposes suspension ‐ Then Finance approves/denies; action is audit‐logged BOA‐1: As Operations, PFIs/job‐cards are auto‐generated from templates, so documents are consistent. ‐ Given an approved work order ‐ When BOA runs ‐ Then documents are produced & stored; e‐sign requested KBCA‐1: As a CS Agent, I can query the KB copilot, so I resolve faster. ‐ Given a ticket context ‐ When I ask the KB ‐ Then curated snippets with SOP links are returned VEA‐1: As a Support Engineer, I want incident video snippets attached to tickets, so evidence is clear. ‐ Given an incident ‐ When matching video exists ‐ Then a 30–60s clip is linked with timestamps and privacy mask

<!-- page 12 -->
## 12) Human Roles & RACI (where humans stay in the loop)

Helpdesk: Manual intake, approval of RAA previews (first month), closure QA, CSAT handling. Sales: Lead follow‐up, quote approvals, pricing exceptions, opportunity hygiene. Finance: Suspension/resume approvals, payment reconciliations, dunning policy oversight. Operations: Dispatch rules, job‐card standards, evidence quality, field coaching loops. Compliance: KB publish gate, audit sampling, quarterly ISO/QMS packs. Engineering: Connectors, orchestrations, observability, reliability, cost controls.

## 13) Risks, Assumptions, and Mitigations

Data quality inconsistencies across Wialon, 3DTracking, and Navas → Mitigation: canonical contracts + reconciliation jobs. Over‐noti(cid:976)ication fatigue → Mitigation: bundling, quiet‐hours, opt‐down preferences, A/B tuned thresholds. Model drift / hallucinations → Mitigation: retrieval‐first prompts, schema validation, HITL confirmations, canaries. Vendor API limits/outages → Mitigation: backoff/retry, circuit breakers, fail‐open to manual processes. Privacy or compliance breaches → Mitigation: masking, RBAC, approvals, audit trails, incident playbooks.

<!-- page 13 -->
## Appendix A — UML & Diagrams

<!-- page 14 -->
<!-- page 15 -->
