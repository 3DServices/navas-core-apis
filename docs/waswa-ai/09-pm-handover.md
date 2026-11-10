# 9. Product Manager Handover

[← Index](README.md)

## 9.1 Key findings

1. **Waswa works as a read-only assistant.** It answers questions about a customer's own tokens, vehicles, trips, alerts, geofences and payments, how the OLIWA app works, and which products fit a need. It does this with GPT-4o (through OpenRouter) and 15 controlled look-up tools.
2. **Customer data isolation is well designed and tested.**
   - The account always comes from the sign-in token.
   - The AI cannot widen its own access.
   - Other customers' data is invisible.
   - Prices are never given.
   - 342 automated checks passed on 20 Oct 2026.
3. **Quality is improving but thinly measured.**
   - The last recorded evaluation (11 Oct) passed 15 of 15 questions. That was one run, with rule-based scoring.
   - Six newer questions and a week of code changes have not been evaluated.
   - Real-usage data is limited: of 92 early answers, only 14 were rated, and 8 of those as wrong.
4. **There is a solid human-review loop.** Customer "Not helpful" flags feed a staff queue. Corrections need a second approver (two for policy topics) and are re-checked every 180 days.
5. **Much of the strategy is not built.**
   - No actions: the ~30 "gated actions" exist only as a database table.
   - No cheaper model tier, no caching, no AI cost billing, no semantic search.
6. **Waswa's knowledge of the app is out of date.** The app guide has not kept pace with the app (9 changed screens, 4 new ones). The automatic sync has never run.

## 9.2 Release readiness

| Area | Readiness | Notes |
|---|---|---|
| Core chat (mobile) | 🟢 Functional | Working in code; real-phone AI answer still a manual acceptance item |
| Data isolation | 🟢 Good | Tested |
| Pricing protection | 🟢 Good | Tested |
| Answer quality | 🟡 Promising, not proven | One 100% run; no recent evaluation; no helpfulness measure |
| App-guide accuracy | 🟡 Needs update | See R4 |
| Cost control | 🔴 Missing | No rate limit or spend cap |
| Privacy and retention | 🔴 Undecided | Data goes to a third-party AI on default terms; conversations kept indefinitely |
| Permissions / admin controls | 🟡 Misleading | "Can chat with Waswa" switch does nothing |
| Code merged to main | 🔴 No | `waswa-ai` is 34 commits ahead of `origin/main` |
| Documentation (API) | 🟡 Out of date | OpenAPI file stale; this folder is current |

**Overall assessment:**

- **Suitable for a controlled pilot** with selected customers, provided the AI key and production configuration are confirmed.
- **Not yet ready for general release.** That requires at minimum R1 (usage limits), R2 (privacy decision), R3 (upsell decision), R4 (guide refresh) and R6 (merge and configuration sign-off) from the [Roadmap](08-recommendations-and-roadmap.md).

## 9.3 Outstanding risks

| Risk | Likelihood / impact | Mitigation |
|---|---|---|
| Unbounded AI costs from heavy or abusive use | Possible / High | R1 |
| Customer data handled by a third party without an agreed policy | Already happening / High (legal and trust) | R2 |
| Wrong how-to answers from a stale app guide | Likely / Medium | R4, R9 |
| Inconsistent sales behaviour (upsell vs no-sales rule) | Already happening / Medium | R3 |
| Admins believe they can disable Waswa per role | Likely / Medium | R5 |
| Staff with any Waswa permission can read any client's fleet and all conversations | By design / Medium (insider risk) | R8 |
| AI provider outage = Waswa down (no fallback model) | Has happened (502s on 10 Oct; missing key in production in Sep) / Medium | Add a fallback model and monitoring |
| Credentials still in git history (rotation "not started") | Present / High, platform-wide | Complete `database/manual/a2_credential_rotation.md` |
| A bad document version cannot be rolled back | Possible / Medium | R11 |

## 9.4 Decisions needed from management

1. **Sales behaviour.** Should Waswa recommend products (upsell and cheaper options) to customers now, or not until a later phase? Today the prompt and the code disagree.
2. **AI data policy.** Which customer data may be sent to an external AI provider, under which terms (no retention, no training, region), and how long should conversations be kept?
3. **Usage limits.** What message limits per user, per day, and what monthly AI budget? Should AI usage eventually consume customer tokens, as the strategy suggests?
4. **Staff access scope.** Who may:
   - look up any client's fleet through Waswa?
   - read all customers' conversations?

   Should admins be allowed to self-approve documents and app-guide publishes?
5. **Document visibility.** Which of the 12 internal documents (e.g. the CMS manual, token billing strategy) should customers be able to get answers from? Today they are staff-only by default. Confirm the proposed authority levels 2–6.
6. **Gated actions roadmap.** Should Waswa ever take actions? If so, who approves the 11 sensitive actions that currently have no approver (immobilise, suspend account, billing adjustment, etc.), and what are the discount thresholds?
7. **Release scope.** Pilot first (which customers, success measures) or general release? Which success metrics should be tracked (none exist today)? Suggested candidates:
   - share of answers rated Helpful
   - share of conversations with no support follow-up
   - average answer time
   - cost per conversation
8. **App-guide publishing.** Allow automatic publishing from CI, or always require a human approver?

## 9.5 Suggested next steps (first two weeks)

1. Decide items 1–3 above.
2. Merge `waswa-ai`, then confirm migrations and production configuration (R6).
3. Implement usage limits (R1) and the provider privacy settings (R2).
4. Refresh and device-check the app guide (R4), then re-run the full evaluation 3× and record results (R10).
5. Run a pilot with a small group of customers, reviewing the "Not helpful" queue weekly.
