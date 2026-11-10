# 5. APIs and Integrations

[← Index](README.md)

## 5.1 System picture

```
 OLIWA mobile app ─┐                         ┌─► OpenRouter (AI model, default GPT-4o)
 CMS (web)        ─┼─► NAVAS backend ────────┼─► Google Places (route look-ups, optional)
 Eval scripts     ─┘   /assistant/*          │
                        │                    │
                        ▼                    │
                  Waswa data API  /waswa/data/*  (internal; own short-lived token)
                        │
                        ├─► PostgreSQL (accounts, tokens, payments, trips, alerts,
                        │               geofences, products, Waswa tables)
                        └─► Cassandra (device registry, heartbeats, positions)

 oliwa-mobile repo ── /kb-sync ──► POST /assistant/console/app-guide/oliwa-mobile/sync
```

**How the routes are wired:**
- The routes are registered in `endpoints/__init__.py`.
- Chat and console routes have no URL prefix. Several console routes are added with `add_url_rule` in `endpoints/waswa_console.py` and `waswa_app_guide.py`, rather than with decorators.
- The data API uses the prefix `/waswa/data`.

## 5.2 Authentication

| Who | Method | Details |
|---|---|---|
| App and CMS users | `Authorization: Bearer <JWT>` | From `/users/auth`; access token valid 30 min by default, refresh token 7 days (`config.py:53-54`). The mobile app refreshes once on a 401, then signs out |
| Waswa → data API | Separate **data token** | Created on the server for each chat turn and never sent to the app. Valid 10 min. Signed with its own key and bound to issuer, audience and scope, so it cannot be swapped with a user token (`endpoints/waswa_data_auth.py`; ✅ `tests/test_waswa_data_api.py`) |
| App-guide sync script | Staff JWT | Uses either a token or a staff username/password from environment variables (names: `NAVAS_KB_TOKEN`, `NAVAS_KB_USERNAME`, `NAVAS_KB_PASSWORD`) |
| NAVAS → OpenRouter | API key | `OPENROUTER_API_KEY` (server environment) |

## 5.3 Endpoints

### Chat and customer endpoints
Any signed-in user can call these. No extra permission is needed.

| Method | Path | Purpose | Source |
|---|---|---|---|
| POST | `/assistant/chat` | Ask a question | `assistant.py:775` |
| POST | `/assistant/feedback` | Rate an answer: `good`, `unhelpful` or `wrong` (only the conversation owner or a reviewer) | `waswa_console.py:168` |
| GET, POST | `/assistant/context` | Show what Waswa knows about the caller's account (diagnostic) | `assistant.py:691` |
| GET, POST | `/assistant/knowledge` | Show what a document search would return (diagnostic) | `assistant.py:723` |

**Chat request** (as sent by the mobile app, `oliwa-mobile/lib/services/assistant_service.dart:85-97`):
```json
{ "data": { "message": "How many tokens do I have?",
            "surface": "mobile",
            "conversation_uid": "<optional, to continue>",
            "module": "<optional screen name>" } }
```

**Chat response** (main fields):

| Field | Meaning |
|---|---|
| `reply` | The answer text |
| `message_uid` | The answer's ID, used for feedback |
| `conversation_uid` | The conversation's ID, sent back to continue it |
| `verified_answers[]` | The staff-approved corrections that were used |
| `evidence` | The data Waswa looked at |
| `tool_rounds` | How many tool rounds the turn took |
| `truncated` | Set when the answer hit the length limit |
| `model` | The AI model's name |

The server also accepts `agent_version` (`v1` or `v2`). The app ignores and does not send `context` and `history`, which the server ignores too.

### Review console: `waswa.review`
Staff only.

| Method | Path | Purpose |
|---|---|---|
| GET | `/assistant/console/summary` | Badge counts and the caller's permissions |
| GET | `/assistant/console/queue` | Review queue |
| GET | `/assistant/console/conversations`, `/conversations/<uid>` | All conversations; full transcript with evidence |
| GET, POST | `/assistant/console/answers`, `/answers/<uid>` | List, create or edit corrections |
| POST | `/assistant/console/answers/<uid>/submit`, `/retire`, `/delete` | Correction lifecycle (delete: unsubmitted drafts only) |
| POST | `/assistant/console/feedback/<uid>/resolve` | Close a flag |
| GET | `/assistant/console/sources`, `/sources/<uid>` | Document library |
| POST | `/assistant/console/sources/upload` | Upload a document (multipart, ≤25 MB) |
| GET | `/assistant/console/authority-levels` | Trust levels |
| GET, POST | `/assistant/console/match` | Preview which corrections a question matches |
| GET | `/assistant/console/app-guide/<app>` | App-guide articles and status |
| POST | `/assistant/console/app-guide/<app>/sync` | Sync the app guide (`dry_run`, `prune`, `publish` options) |

### Approval console: `waswa.approve`

| Method | Path | Purpose |
|---|---|---|
| POST | `/assistant/console/answers/<uid>/decide`, `/confirm` | Approve or reject a correction; confirm at re-check |
| POST | `/assistant/console/sources/<uid>/review`, `/audience`, `/remove`, `/restore`, `/details` | Document approval and management |
| POST | `/assistant/console/conversations/<uid>/archive`, `/restore` | Archive or restore a conversation |

### Internal data API: data token only
Not for apps.

| Path | Purpose |
|---|---|
| `GET /waswa/data/caller`, `/context`, `/prompt` | Audience, account context, active prompt |
| `POST /waswa/data/conversations`; `GET/POST /conversations/<uid>/messages`; `POST /conversations/<uid>/transparency` | Conversation storage (owner-checked) |
| `POST /waswa/data/messages/<uid>/evidence` | Evidence trail |
| `POST /waswa/data/answers/match` | Verified-answer matching |
| `GET /waswa/data/knowledge/sources`; `POST /knowledge/search` | Documents |
| `POST /waswa/data/tools/<name>` | Runs one of the 15 tools |

By default the chat engine calls these **inside the same server process**. Setting `WASWA_DATA_API_URL` makes it call them over HTTP instead (`endpoints/waswa_data_client.py`).

### API specification status
`docs/waswa_api_openapi.json` is **out of date**:

- It is dated to migration 041 (22 Sep 2026).
- It documents 21 of the 35 `/assistant` method/path pairs.
- It covers none of the 12 data-API routes.
- It omits the `module` and `agent_version` chat fields.

This folder's table above is the current reference.

## 5.4 Integration with OLIWA (mobile)

| Item | Detail |
|---|---|
| Endpoints used | `/assistant/chat`, `/assistant/feedback` (`oliwa-mobile/lib/core/constants/api_constants.dart:115-116`) |
| Timeout | 90 s for chat; 20 s for feedback |
| Streaming | No; one complete JSON response |
| State | `WaswaProvider` (app-wide) keeps the current conversation in memory |
| Screen context | 23 screens send their name as `module` |
| Not used by the app | Conversation archive and history endpoints; `agent_version` |

## 5.5 Integration with NAVAS data

Waswa reads only. The tables it reads are listed in `database/manual/waswa_readonly_role.sql` and in [AI and Knowledge Base](04-ai-and-knowledge-base.md):

- **PostgreSQL:** account relay, token accounts and registry, device subscriptions, event notifications (alerts), payment logs, pause rules, trips, geofences, location registry, product catalogue.
- **Cassandra:** device basic data, heartbeats ("pulse"), positions.

**Waswa's own tables** (migrations 030–046) hold:

| Area | Tables |
|---|---|
| Conversations and messages | `dll_waswa_conversations`, `dll_waswa_messages` |
| Evidence | `dll_waswa_evidence` |
| Transparency log | `dll_waswa_transparency_log` |
| Prompts | `dll_waswa_prompts` |
| Documents and chunks | `dll_waswa_sources`, `dll_waswa_chunks` |
| App guide | `dll_waswa_app_guide` |
| Feedback | `dll_waswa_feedback` |
| Corrections and approvals | `dll_waswa_answers`, `dll_waswa_answer_approvals` |
| Gated actions (unused) | `dll_waswa_gated_actions` |

## 5.6 Third-party services

| Service | What is sent | Configuration |
|---|---|---|
| **OpenRouter** (to OpenAI GPT-4o by default) | System prompt, the user's account context (tenant name, token balance, payment summary, products, vehicles), up to 10 previous messages, tool results (plates, IMEIs, trips, locations, alerts) | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_SITE_URL`, `OPENROUTER_SITE_NAME` |
| **Google Places** | Route coordinates (route look-ups only) | `GOOGLE_MAPS_API_KEY` |
| **GitHub Actions + Anthropic** (planned CI for the guide) | App source code and guide articles | Not active |

## 5.7 Configuration reference

Variable **names** only, as listed in `.env.example`.

| Variable | Purpose | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | AI provider key. If empty, chat is off | — |
| `OPENROUTER_MODEL` | Model | `openai/gpt-4o` |
| `WASWA_AGENT_VERSION` | `v1` or `v2` | `v1` |
| `WASWA_DATABASE_URL` | Optional restricted database login | falls back to the main DB login |
| `WASWA_DATA_TOKEN_SECRET` | Data-token signing key | derived from `JWT_SECRET` |
| `WASWA_DATA_TOKEN_TTL_SECONDS` | Data-token lifetime | 600 |
| `WASWA_DATA_API_URL` | Run the data API over HTTP | in-process |
| `GOOGLE_MAPS_API_KEY` | Route place look-ups | off |
