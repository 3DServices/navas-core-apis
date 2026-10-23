# 7. Testing and Known Issues

[← Index](README.md)

## 7.1 Automated tests run for this report (20 Oct 2026)

Backend tests that do **not** need a database or the AI model were run on the current code (`waswa-ai` @ `4a76477`). Some files are written as standalone scripts, so they were run with `python tests/<file>.py`; the others were run with pytest.

| Test file | What it checks | Result |
|---|---|---|
| `test_waswa_v2.py` | v2 agent end-to-end with a fake model: wrong-corpus guard, retrieval recovery, "live" claims | ✅ 69 checks passed |
| `test_waswa_fleet.py` | Whose fleet a call may read, route-probe cost caps, trip building | ✅ 45 passed |
| `test_reply_scrub.py` | Secrets removed from replies | ✅ 65 passed |
| `test_payment_standing.py` | Payment totals; withholds totals when amounts are unreadable | ✅ 37 passed |
| `test_zero_state.py` | Empty-wallet guidance never guesses or mentions price | ✅ 26 passed |
| `test_fleet_liveness.py` | A failed read is never reported as "offline" | ✅ 18 passed |
| `test_wallet_owner.py` | The right account's token balance is used | ✅ 16 passed |
| `test_eval_runner.py` | Evaluation runner HTTP mode and crash recovery | ✅ 16 passed |
| `test_tool_forcing.py` | Account questions force a data look-up | ✅ 14 passed |
| `test_signed_in_gate.py` | Anonymous callers get 401 | ✅ 10 passed |
| `test_waswa_ivms_lookup.py` | "iVMS product" resolves correctly; empty product filter is widened | ✅ 7 passed |
| `test_product_search_words.py` | Loose product search ("fuel") | ✅ 5 passed |
| `test_pricing_gate.py` | Customers never get prices; staff may ask about the discount *process* | ✅ 4 passed |
| `test_alerts_tool.py` | Alert summary shape and severity | ✅ 4 passed |
| `test_tracking_time_left.py` | Time left matches the dashboard | ✅ 3 passed |
| `test_waswa_geofences.py` | Geofence shape wording | ✅ 3 passed |

**Total: 16 Waswa-related test files, 342 checks, 0 failures.** Other non-Waswa backend tests run at the same time also passed.

`test_permission_loader.py` and `test_blacklist_cache.py` (platform auth, not Waswa-specific) could not be collected, because a library was missing in the local test environment. This is an environment issue, not a test failure.

### Not run for this report

| Tests | Why not run | Last recorded result |
|---|---|---|
| `test_waswa_app_guide.py` (11 tests: guide sync, versioning, publish rules, permissions) | Connects to the shared remote database | Recorded as **failing** in the local pytest cache (16 Oct 2026), most likely because no database was reachable at that time. **Unverified** |
| `test_waswa_data_api.py` (12 tests: token separation, ownership, isolation) | Needs the database **and** a live AI call | Recorded as failing to load (16 Oct 2026). **Unverified** |
| OLIWA Flutter tests: `waswa_copilot_test.dart` (~20), `waswa_chat_format_test.dart` (2), Waswa parts of `services_test.dart` and `integration_test.dart` | Flutter SDK not installed on the documenting machine | No recorded result found. **Unverified** |

> **Note:** five backend test files are standalone scripts. A plain `pytest` run does not pick them up, so they only run when someone runs them by hand. No CI configuration for the backend was found.

## 7.2 Answer-quality evaluation (recorded results)

Taken from `tests/waswa_eval/runs/*.json` and the local MLflow log. These runs were **not repeated** for this report.

| Date | Pass rate (15 questions) | Notes |
|---|---|---|
| 9 Oct | 73% → 80% | Early runs; scoring rules changed several times |
| 10 Oct | 0% / 20% | Not quality failures: authentication error (401) against production, then an AI-provider outage (502) |
| 10 Oct | 67% → 93% | Steady improvement; v1 and v2 compared side by side |
| **11 Oct (latest)** | **100% (15/15)** for v1 and v2 | v2 average answer time about 18.5 s, 95th percentile about 22 s |

**How to read this:**
- Scoring is rule-based (right tool used, no price, figures traceable to data). It does **not** judge helpfulness or tone. The "no dead-end answers" check has never been scored.
- The latest result comes from **one run per version**. The evaluation tooling itself warns that one run is not a measurement, and answers vary between runs.
- **Six document-fact questions** added on 14 Oct have **never been run**. The latest result therefore covers 15 of 21 questions.
- **No evaluation since 11 Oct.** Changes from 12–17 Oct (dashboard, alerts, iVMS, deletion/archiving) have not been evaluated.
- The question set's expected answers are marked "draft — correct by hand".
- Baseline from real usage (`scripts/waswa_eval_build.py`): of 92 early answers, 14 received user verdicts (8 wrong, 3 unhelpful, 3 good), and 78 were never reviewed. This is the only real-usage quality figure in the repository.

## 7.3 Known issues and bugs

Severity is our assessment: **High** affects customers or data protection; **Medium** affects correctness or operations; **Low** is cosmetic or internal.

| # | Issue | Severity | Evidence |
|---|---|---|---|
| K1 | No rate limit, message-length limit or spend cap on chat, so cost exposure is unbounded | High | `app.py:29-39`, `assistant.py:789` |
| K2 | Customer data sent to OpenRouter/OpenAI with no retention/no-training settings, and no retention policy for stored conversations | High | `assistant.py:554-594` |
| K3 | The app guide is out of date: 9 screens changed since the last publish, 4 new screens have no article, and nothing has been checked on a device | Medium–High | `oliwa-mobile/docs/user-guide/` |
| K4 | Prompt v7 says "do not raise sales opportunities"; the code tells the AI to upsell/downsell on every turn | Medium | `database/prompts/waswa_runtime_v7.md:140`, `assistant.py:936-951` |
| K5 | RBAC switches "Can chat with Waswa" and similar do nothing | Medium | Migrations 013/018; no code checks them |
| K6 | Removing a bad approved document version leaves **no** live version (the old one cannot be restored or re-uploaded) | Medium | `waswa_documents.py:447-453, 492-498` |
| K7 | Automatic app-guide sync (CI) has never run | Medium | `oliwa-mobile/.github/workflows/kb-sync.yml` exists only on `new-ui` |
| K8 | Restricted database role not applied, and out of step with the code | Medium | `database/manual/waswa_readonly_role.sql` |
| K9 | API specification (OpenAPI) is out of date | Medium | `docs/waswa_api_openapi.json` |
| K10 | Report assistant and Token Billing "Ask AI" ignore the user's Waswa OFF switch | Medium | `oliwa-mobile/lib/widgets/ask_waswa_report_sheet.dart`, `token_billing_screen.dart` |
| K11 | Likely UI bug: opening Waswa from the side menu, Settings or FAQ may leave the floating button visible on top of the chat, and tapping it opens a second copy. **Inferred from code; confirm on a device** | Low–Medium | `oliwa-mobile/lib/widgets/waswa_copilot.dart` |
| K12 | Tool descriptions given to the AI are wrong: `fleet_activity` claims a 7-day default (actually 2); knowledge searches claim 4 results (actually 6 and 3) | Low | `waswa_fleet.py:785, 1094`; `waswa_knowledge.py:65, 492` |
| K13 | In v2 mode, the "unsourced numbers" check never runs in production (needed data is not passed) | Low | `assistant.py:1198-1222`, `waswa_v2.py:385` |
| K14 | Mobile chat shows tables, lists and links as raw text; links not tappable | Low | `oliwa-mobile/lib/widgets/waswa_chat.dart:16-38` |
| K15 | User guide text differs from the app ("+" button, error message, "every screen") | Low | `oliwa-mobile/docs/user-guide/articles/ask-waswa.md` |
| K16 | Orphan upload folders left on disk by rolled-back uploads and tests | Low | `waswa_documents.py:352-362` |
| K17 | Many commit messages are vague ("updates", "local tests"), which makes changes hard to audit | Low | git history |

## 7.4 Unverified functionality

These are present in the code, but nothing in the repository proves they work end-to-end:

- The CMS chat and review console screens (the CMS repository was not inspected).
- A real AI answer on a physical phone: mobile acceptance test #15 is marked 🟡 manual (`oliwa-mobile/docs/ACCEPTANCE_TESTS.md:40`).
- App-guide sync against the current database (its test needs the DB).
- Report-request parsing and Token Billing Ask AI (no tests).
- Which system prompt version is live in production.
- Whether any of the 12 core documents have been made visible to customers.
- Production configuration: AI key present, CORS origins, restricted DB role.
