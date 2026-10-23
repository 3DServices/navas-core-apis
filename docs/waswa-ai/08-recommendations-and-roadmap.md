# 8. Recommendations and Roadmap

[← Index](README.md)

These are recommendations, not existing features. Priorities follow customer impact, risk and effort.

- **P0**: before wider release
- **P1**: next phase
- **P2**: later

No effort or business-impact figures are claimed; they need estimation by the team.

## P0: before wider customer release

### R1. Usage limits and cost visibility
**Why:** Chat has no rate limit, length limit or spend cap (K1). One user or script could run up AI costs.
**Acceptance criteria:**
- Chat is limited per user, for example N messages per minute and M per day (values to be set by management). Excess requests get a friendly message and HTTP 429.
- Messages over an agreed length are refused before reaching the AI.
- Daily AI usage (requests and tokens) per account is recorded and viewable by staff.
- An automated test proves the limit triggers.

### R2. Privacy settings and a retention policy
**Why:** Customer fleet and payment data go to a third-party AI provider on default terms, and conversations are kept forever (K2).
**Acceptance criteria:**
- Management has approved a policy that names the provider, the data categories sent, and the retention period.
- OpenRouter requests use the provider's "no data retention / no training" options, or an approved alternative.
- A scheduled job deletes or anonymises conversations older than the agreed period. A test proves it.
- The customer privacy notice mentions Waswa.

### R3. Resolve the upsell contradiction
**Why:** The prompt forbids sales suggestions while the code demands them (K4).
**Acceptance criteria:**
- A management decision is recorded.
- The code and the active prompt say the same thing.
- One evaluation question checks the chosen behaviour.

### R4. Bring the app guide up to date, and verify it on a device
**Why:** Waswa reads the guide to customers. Stale steps produce wrong answers (K3, K15).
**Acceptance criteria:**
- Every article matches the current `new-ui` build.
- The four new screens have articles, or are listed as undocumented on purpose.
- At least the top 10 articles by expected usage are walked on a device and marked `verified: device`.
- The guide is re-published and approved by a second person.

### R5. Make the "Can chat with Waswa" switch real, or remove it
**Why:** Administrators believe they can turn Waswa off for a role; they cannot (K5).
**Acceptance criteria:**
- Either `/assistant/chat` refuses users without the permission (HTTP 403, with a clear app message) and a test proves it,
- or the unused permissions are removed from the catalogue.

### R6. Merge and release discipline
**Why:** 34 commits of Waswa work are not on `main`.
**Acceptance criteria:**
- `waswa-ai` is reviewed and merged.
- Database migrations 030–051 are confirmed applied in production.
- The production configuration checklist is signed off: AI key, CORS origins, prompt version.

## P1: next phase

### R7. Apply the restricted database role
**Acceptance criteria:**
- The grant script is updated to match the code (K8).
- `scripts/waswa_grant_check.py` passes.
- `WASWA_DATABASE_URL` is set in production.
- Draft delete, app-guide sync and geofence look-up still work.

### R8. Review staff access scope
**Acceptance criteria:**
- Management decides who may read any client's fleet through chat, and who may read all customers' conversations (see [Handover](09-pm-handover.md)).
- Permissions and their descriptions match that decision.
- Tests cover the permission matrix.

### R9. Turn on automatic app-guide sync
**Acceptance criteria:**
- The workflow is on the default branch, with its secrets configured.
- A push that changes a screen opens a guide-update PR.
- Publishing requires a second-person approval (no auto-publish).
- The workflow compares the whole push, not only the last commit.

### R10. Regular quality evaluation
**Acceptance criteria:**
- The evaluation runs on every merge, or weekly, against all 21+ questions, at least 3 times per run.
- Results are tracked over time.
- A release is blocked if the pass rate falls below an agreed threshold.
- The draft expectations are confirmed by a domain expert.
- A helpfulness / "no dead-end" judgement is added.

### R11. Document version rollback
**Acceptance criteria:**
- An approver can restore the previous version of a document in one action (K6).
- A test covers remove-new-version → previous version answers again.

### R12. Mobile chat polish
**Acceptance criteria:**
- Lists, tables and links render properly, and links are tappable (K14).
- All Waswa entry points respect the OFF switch (K10).
- The floating button is hidden while the chat is open (K11).
- Widget tests cover these.

### R13. Up-to-date API specification
**Acceptance criteria:**
- The OpenAPI file lists every `/assistant` route and the chat fields `module` and `agent_version` (K9).
- It is generated or checked automatically.

## P2: later

| # | Recommendation | Acceptance criteria (summary) |
|---|---|---|
| R14 | Meaning-based (semantic) search | Paraphrased versions of evaluation questions retrieve the same documents as the originals |
| R15 | Conversation history in the app | The user can see and reopen past conversations; archive from the app |
| R16 | Streaming answers | First words appear within an agreed time |
| R17 | Gated actions (e.g. schedule a demo, send a reminder) | Approval levels and approvers are confirmed by management for all ~30 actions; each action is logged; nothing runs without the defined approval |
| R18 | Cost tiering from the strategy document | Measured share of questions answered without the paid model; cost per conversation tracked |
| R19 | Language support (Swahili and others) | Agreed languages answered correctly in the evaluation set |
| R20 | Fix tool descriptions and v2 number check | Descriptions match code defaults; the v2 unsourced-number check receives context data in production (K12, K13) |
