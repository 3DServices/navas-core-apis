# 6. Security and Privacy

[← Index](README.md)

This section describes protections and gaps factually. It contains no credentials and no exploit details.

## 6.1 Permissions

**Who can use chat.** Every signed-in user. No permission is checked (`endpoints/assistant.py:775+`).

**Waswa permissions that are enforced** (`endpoints/waswa_answers.py:42-116`):

| Permission | Unlocks |
|---|---|
| `waswa.staff_knowledge` | "Staff" audience: internal documents, source references, **and the ability to read any client's fleet through chat** |
| `waswa.review` | The review console; also staff audience |
| `waswa.approve` | Approving corrections and documents, managing the library, archiving conversations; also staff audience |

**Who gets them:**
- **No role receives them by explicit grant.** The seed scripts create the permissions but assign them to nobody.
- They are given **automatically** to super admins, system accounts, and admin/sysadmin roles on internal (non-customer) accounts.
- **Customer accounts** (`client`, `customer`, `customer_tracker`) are always stripped of every `waswa.*` permission, even if a role ticks it.

**Permissions that look active but are not.** The RBAC catalogue contains "Can chat with Waswa", "Can access Waswa AI", "Can approve AI action", "Can view AI cost" and others (migrations 013, 018). **No code checks them.** An administrator who un-ticks "Can chat with Waswa" will see no effect.

## 6.2 Account data isolation (customers)

This is the strongest part of the design.

| Safeguard | How | Evidence |
|---|---|---|
| The account is always taken from the sign-in token | Nothing in the request can change whose data is read | `endpoints/waswa_context.py`, `waswa_data_api.py` |
| The app cannot inject context or history | `context` and `history` sent by a client are ignored | `assistant.py:803-806` |
| The AI cannot widen its own access | The server strips `scope`, `audience`, `client_uid` and similar arguments from tool calls before they run | `waswa_data_api.py:66, 389-426`; ✅ tested |
| Another customer's vehicle is invisible | Returns "not found", never "belongs to someone else" | `waswa_fleet.py`; ✅ `tests/test_waswa_fleet.py` |
| Another person's conversation is invisible | Ownership checked on every read/write; returns 404 | ✅ `tests/test_waswa_data_api.py` |
| The AI never touches the database directly | All data goes through the data API with a separate 10-minute token | ✅ `tests/test_waswa_data_api.py` |
| Customers see only "everyone" documents and corrections | Audience filter on every search | `waswa_knowledge.py:130-141` |
| Prices never reach customers | Pricing questions are stopped before the AI; currency amounts are blocked in corrections and redacted from documents | ✅ `tests/test_pricing_gate.py` |
| Secrets never appear in answers | Replies are scrubbed of credential-like text | ✅ `tests/test_reply_scrub.py` (65 checks) |
| SQL injection | All database queries use parameters; Cassandra uses prepared statements | Code review |

## 6.3 Staff access (by design, but worth a decision)

1. **Staff can read any client's fleet through chat.** This includes vehicles, positions, trips and alerts. Anyone with *any* `waswa.*` permission counts as staff (`waswa_data_api.py:154-162`). The permission's description mentions only documents.
2. **Reviewers can read every customer's conversations**, across all tenants, with no tenant filter (`waswa_console.py:273-366`).
3. **Admins can bypass the second-person check for documents.** They can self-approve an upload and publish the app guide in one step. This is logged as `self_approved`, but there is no second person. Corrections, by contrast, can never be self-approved.

## 6.4 Privacy and data handling

- **Storage.** Every question and answer is stored word-for-word in `dll_waswa_messages`.
- **Retention.** There is **no retention or deletion policy**. Archiving hides a conversation but keeps it.
- **Data sent to a third party.** Each chat turn sends the user's account context and fleet data to **OpenRouter**, which forwards it to the model provider (OpenAI by default). This includes tenant name, token balance, payment summary, vehicle plates, IMEIs, locations and trips.
  - The request sets **no "do not retain / do not train" options**.
  - No data-processing agreement was found in the repository.
- **Route look-ups.** These send coordinates to Google Places (when enabled).
- **Server logs.** Logs record errors and tool failures, not message text.
- **Signing out** on mobile clears the conversation from the phone.

## 6.5 Abuse and cost protection

| Protection | Status |
|---|---|
| Rate limit on chat | ⛔ **None**. Only login, refresh and forgot-password are rate-limited (`app.py:29-39`) |
| Message length limit | ⛔ None |
| Per-user or per-account AI spend cap | ⛔ None |
| Per-answer limits | 🟢 1,200-token answers, 6 tool rounds, 10 history messages, 45 s timeout |
| Upload limit | 🟢 25 MB, fixed file types |
| Prompt-injection defence | 🟡 Structural only: the AI cannot widen scope, pricing bypasses the AI, and documents must be approved. There is no filter on user text or document content |
| `agent_version` switch | 🟡 Any caller can choose v1 or v2 per request (meant for testing) |

## 6.6 Other technical findings

| # | Finding | Location |
|---|---|---|
| 1 | The restricted "read-only" database role for Waswa exists as a script but is **not active** until `WASWA_DATABASE_URL` is set. Until then Waswa uses the main database login. The script has also **drifted from the code**: applying it as written would break draft deletion, app-guide sync and geofence look-ups | `database/manual/waswa_readonly_role.sql` |
| 2 | Credential rotation is recorded as **not started**. Five of six secrets can be recovered from git history. The AI provider key is not among them | `database/manual/a2_credential_rotation.md` |
| 3 | Console permission errors return internal detail (the caller's role and permissions, raw error text). Chat responses include the model name and internal "unknown context" reasons | `waswa_console.py:82-97`, `assistant.py:1231-1261` |
| 4 | The logout blacklist check lets tokens through if the database is unavailable ("fails open") | `endpoints/jwt_utils.py:115-120` |
| 5 | The default allowed web origins include localhost addresses, unless production overrides `CORS_ORIGINS` | `config.py:92-98` |
| 6 | Data tokens can be reused within their 10-minute life. The data API is reachable from outside even though it is normally called in-process | `waswa_data_auth.py`, `endpoints/__init__.py` |
| 7 | The customer-account check used by Waswa looks at account type only; the platform-wide check also looks at role | `waswa_answers.py:84-88` vs `globals.py:346-369` |

## 6.7 What is tested and what is not

| Area | Status |
|---|---|
| Data-token separation; conversation ownership; fleet scoping; secret scrubbing; pricing gate; signed-in gate | ✅ Tested |
| Console permission matrix (review vs approve; customer admin refused) | ⛔ No tests |
| Staff cross-client fleet access | ⛔ No tests |
| Stripping of `waswa.*` from customer accounts | ⛔ No tests |
| Tenant scoping in console views | ⛔ No tests |
