# Waswa AI — Product Documentation

**Audience:** Product Manager, 3D Services Ltd
**Prepared:** 20 October 2026
**Based on:** NAVAS backend `navas-core-apis` (branch `waswa-ai`, commit `4a76477`) and OLIWA mobile app `oliwa-mobile` (branch `new-ui`, commit `e82ac21`)

This folder describes Waswa AI as it is **actually built** today. Every statement was checked against the source code, tests, configuration or existing project documents. Anything that could not be confirmed is labelled as such.

---

## Documents

| # | Document | What it answers |
|---|---|---|
| 1 | [Product Overview](01-product-overview.md) | What Waswa is, who it is for, why it matters |
| 2 | [Features and Capabilities](02-features-and-capabilities.md) | What it can and cannot do, with the status of each feature |
| 3 | [User Guide](03-user-guide.md) | How customers use Waswa in OLIWA, and how staff use the review console |
| 4 | [AI and Knowledge Base](04-ai-and-knowledge-base.md) | How a question becomes an answer; where knowledge comes from; how documents are synced |
| 5 | [APIs and Integrations](05-apis-and-integrations.md) | Endpoints, authentication, and connections to NAVAS, OLIWA and third parties |
| 6 | [Security and Privacy](06-security-and-privacy.md) | Permissions, account isolation, data handling, safeguards and gaps |
| 7 | [Testing and Known Issues](07-testing-and-known-issues.md) | Real test results, evaluation history, bugs and unverified areas |
| 8 | [Recommendations and Roadmap](08-recommendations-and-roadmap.md) | Prioritised improvements with acceptance criteria |
| 9 | [Product Manager Handover](09-pm-handover.md) | Key findings, release readiness, risks, and decisions needed |

**Short on time?** Read the [Product Manager Handover](09-pm-handover.md) first.

---

## Status labels used throughout

| Label | Meaning |
|---|---|
| ✅ **Verified** | Built, and confirmed by an automated test or evaluation run |
| 🟢 **Built** | Present in the code and wired in, but not independently verified for this report |
| 🟡 **Partial** | Built but incomplete, inconsistent, or not reachable by users |
| ⛔ **Not built** | Mentioned in plans, prompts or the database, but no working code |
| 📋 **Plan only** | Described only in strategy documents |

## How this was produced

- Source code, database migrations, prompts, tests and scripts in both repositories were read in full for Waswa-related areas.
- Backend unit tests that do not need a database were **run on 20 Oct 2026** (results in [Testing](07-testing-and-known-issues.md)).
- Tests that connect to the shared database, and the mobile (Flutter) tests, were **not run**. The database tests use a remote server, and Flutter is not installed on the documenting machine. Their last recorded results are reported instead.
- No application code was changed. No credentials, customer data or server addresses appear in these documents.

## Source map

| Area | Main files |
|---|---|
| Chat engine | `navas-core-apis/endpoints/assistant.py`, `endpoints/waswa_v2.py` |
| Account context | `endpoints/waswa_context.py` |
| Data access layer | `endpoints/waswa_data_api.py`, `waswa_data_auth.py`, `waswa_data_client.py` |
| Tools | `endpoints/waswa_fleet.py`, `waswa_products.py`, `waswa_knowledge.py`, `waswa_app_guide.py` |
| Corrections & review | `endpoints/waswa_answers.py`, `waswa_console.py`, `waswa_documents.py` |
| Database | `database/migrations/030–046_waswa_*.sql`, `database/manual/waswa_readonly_role.sql` |
| Prompts | `database/prompts/waswa_runtime_v2.md` … `v7.md` |
| Evaluation | `tests/waswa_eval/`, `scripts/waswa_eval_*.py` |
| Mobile UI | `oliwa-mobile/lib/screens/waswa_assistant_screen.dart`, `lib/widgets/waswa_chat.dart`, `waswa_copilot.dart`, `ask_waswa_report_sheet.dart`, `lib/providers/waswa_provider.dart`, `lib/services/assistant_service.dart` |
| App guide (Waswa's knowledge of the app) | `oliwa-mobile/docs/user-guide/`, `.claude/skills/kb-sync/`, `.github/workflows/kb-sync.yml` |
