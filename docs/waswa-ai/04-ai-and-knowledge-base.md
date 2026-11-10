# 4. AI and Knowledge Base

[← Index](README.md)

## 4.1 How a question becomes an answer

All chat goes through **one endpoint**, `POST /assistant/chat` (`endpoints/assistant.py:775`). For each question:

```
User question (OLIWA app / CMS)
   │
   ▼
1. Check sign-in (JWT) ─────────────── no token → 401
   │
   ▼
2. Load the user's account context ──── tokens, products, units, alerts, payments
   Open or resume the conversation      (built on the server; anything the app sends is ignored)
   Decide audience: customer or staff
   │
   ▼
3. Pricing filter (no AI involved) ──── price/discount question → fixed hand-off reply, logged
   │
   ▼
4. Build instructions for the AI:
   active system prompt + account context + approved "verified answers"
   + rules (e.g. use the app guide for mobile how-to; never turn "unavailable" into zero;
   always state the date range; never mention price)
   │
   ▼
5. Pre-fetch obvious fleet data (vehicle named → look it up first)
   │
   ▼
6. AI model (OpenRouter, default GPT-4o) chooses tools ◄──┐
   Tools run on the NAVAS server, scoped to the account ──┘ up to 6 rounds
   │
   ▼
7. Clean-up: remove "Source:" lines for customers, strip anything secret-looking
   (optional v2 mode: check the answer and repair once)
   │
   ▼
8. Save the answer, the evidence used, model, prompt version and timing
   Return reply + message ID (for feedback) + verified-answer references
```

**Key settings** (`endpoints/assistant.py`):

| Setting | Value |
|---|---|
| Answer length limit | 1,200 tokens |
| Temperature (randomness) | 0.3 |
| Tool rounds per question | up to 6 |
| History replayed | last 10 messages |
| Timeout per AI call | 45 s (the app waits up to 90 s) |
| Network retries | 2, with short back-off |
| Fallback model | **none** |

If the AI provider key is missing, chat returns "not configured" (HTTP 503). This happened in production once, as recorded in `oliwa-mobile/docs/WORK_REPORT_2026-09-10.md`.

**Forcing look-ups.** For any question that is not small talk, the AI is *required* to call at least one tool before answering. This stops it answering account questions from memory (`assistant.py:304-321`; ✅ `tests/test_tool_forcing.py`).

**v1 and v2.** These are two modes of the same endpoint, not two products.
- v1 is the default.
- v2 adds a "wrong-corpus" filter (it drops non-mobile steps for mobile how-to questions) and an answer check with one repair attempt.
- The mode is chosen by the `WASWA_AGENT_VERSION` server setting, **or by any caller per request**. See [Security](06-security-and-privacy.md).

## 4.2 The system prompt

- The instructions given to the AI are versioned in the database (`dll_waswa_prompts`). Only one version is active at a time.
- Versions are managed with `scripts/waswa_prompt.py` (load, activate, roll back) and take effect without a restart.
- The newest file in the repo is `database/prompts/waswa_runtime_v7.md`.
- **Which version is live in production cannot be confirmed from the repository.** Evaluation records refer to prompt version 6 and later 9. Database version numbers do not necessarily match file names.

## 4.3 Where Waswa's knowledge comes from

Waswa draws on five sources, in this order of trust:

| Source | Trust | Who sees it |
|---|---|---|
| **Staff-approved corrections** ("verified answers") | Highest. Injected before the AI starts | Filtered by audience |
| **Live account and fleet data** (tools) | High: system of record | Own account only (staff: any) |
| **Product catalogue** | High (authority level 1) | Everyone; no prices |
| **Approved documents** | Weighted by authority level 2–4 | Customers: "everyone" documents only |
| **OLIWA app guide** (31 articles) | Level 2, audience "everyone" | Everyone |

### Document search (retrieval)

- **Keyword search, not meaning-based.** Search uses PostgreSQL full-text search. Paraphrased questions can miss relevant text. Semantic (vector) search is planned but not available, because pgvector is not installed (`endpoints/waswa_knowledge.py:10-28`).
- **Chunking.** Documents are split by heading into pieces of up to about 1,800 characters. Each piece keeps its heading path.
- **Search order.** Exact phrase first, then all words, then at least half of the distinctive words.
- **Ranking.** Relevance is multiplied by document authority, so an official manual outranks a user story on an equal match.
- **Filters.** Only approved, active, current-version documents are searched, and only those allowed for the caller's audience. Authority levels 5–6 are never quoted.
- **Volume.** Up to 6 pieces (maximum 7,000 characters) per search. App-guide search returns up to 3 whole articles.
- **Caveats to the AI.** The search adds warnings when, for example, it found only loose matches or only specification-level documents.

### Current document library

Twelve documents are listed in `database/knowledge/manifest.json`:

| Authority | Documents |
|---|---|
| 2 (official) | Sales Procedures (v26), NAVAS CMS User Manual |
| 3 | Customer Journey Maps (2024), Token Billing Strategy, Ecosystem Vision & Scope, Waswa AI Strategy |
| 4 (specifications) | OLIWA, CMS and Marketplace user stories; UKO Dashboard KPIs |
| 5 (never quoted) | Two internal strategy documents |

Points the PM should know:

- The 12 documents were loaded by script **without an audience setting**, so they default to **staff only**. Unless someone changed them in the console, customers cannot get answers from them; only the app guide is customer-visible. The live database state was not checked.
- The authority levels 2–6 are marked "proposed, unconfirmed" in migration 035.
- The file labelled "UKO" user stories is a mislabelled copy of the OLIWA stories.
- Some documents are old (journey maps from 2024). The Sales Procedures lack the discount threshold figure.
- Prices are deliberately removed from every document at upload.

## 4.4 Keeping the app guide in sync

The OLIWA app guide lives in the mobile repository (`oliwa-mobile/docs/user-guide/articles/`, 31 articles) so that it is updated alongside the app.

**How it reaches Waswa:**
1. A developer runs the `/kb-sync` skill (`oliwa-mobile/.claude/skills/kb-sync/`). It finds articles affected by code changes, updates them, and validates them: no prices, no internal names, all referenced screens exist.
2. The script `kb_sync.py publish` sends the articles to `POST /assistant/console/app-guide/oliwa-mobile/sync`, signed in as a staff user with `waswa.review`.
3. The server compares each article with what it holds and creates, updates, leaves alone or (optionally) removes it. All of this happens in one database transaction.
4. New versions wait for approval, unless an admin publishes directly.

**Automatic sync (CI).** A GitHub workflow (`oliwa-mobile/.github/workflows/kb-sync.yml`) is designed to do this on every push to `main`: Claude updates the articles, then they are published. **It is not active today**:

- The workflow file exists only on the `new-ui` branch. GitHub only runs push workflows from the default branch, so it has never run.
- The secrets it needs (an AI key and a NAVAS staff login) could not be verified.
- It compares only the last commit, so changes spread across several commits can be missed.

**Current state.** Publishing has been done manually. The last publish (14 Oct 2026, commit `4b7e9b1`) was self-approved by an admin. Since then, nine app screens have changed and four new screens have no article (alert analytics, fleet status, geofence presence, token analytics). All 31 articles are marked "verified from code", **not checked on a device**, although the guide's README says otherwise.

## 4.5 Learning from mistakes ("training")

Waswa is **not retrained**. "Training" means curating what it reads:

1. A customer taps **Not helpful**.
2. Staff review the answer and write a correction.
3. A second person approves it.
4. Waswa finds the approved correction by keyword match (up to 3 per question) and places it at the top of its instructions.

Corrections are re-checked after 180 days, or when their source document changes.

## 4.6 Evaluation harness

`tests/waswa_eval/` holds 21 test questions:
- 12 taken from real user complaints
- 3 pricing rules
- 6 document facts

`scripts/waswa_eval_run.py` asks each question and scores the answer with fixed rules, for example "must call the right tool", "must not contain a price" and "every number must come from the data". Results are recorded in `tests/waswa_eval/runs/` and a local MLflow tracker. See [Testing](07-testing-and-known-issues.md) for the results.
