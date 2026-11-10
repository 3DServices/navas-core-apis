# 3. User Guide

[← Index](README.md)

This guide describes the OLIWA mobile app as it is in the code on branch `new-ui` (commit `e82ac21`). The official customer-facing articles are in `oliwa-mobile/docs/user-guide/articles/ask-waswa.md` and `ask-waswa-for-a-report.md`. Where those articles differ from the app, it is noted in **⚠**.

## 3.1 Who can use Waswa

- **Any signed-in OLIWA user.** The app has no role, plan or permission check for Waswa (`oliwa-mobile/lib/widgets/waswa_copilot.dart:131-148`).
- The backend decides what data the user may see, always based on their own account.

## 3.2 Ways to open Waswa

| Where | What to tap |
|---|---|
| **Any screen** (except Reports) | The round floating **AI** button. It can be dragged out of the way |
| **Dashboard** | ☰ menu → **Waswa AI** (sparkle icon) |
| **Settings** | The dark card **Help (Chat with Waswa)** |
| **Settings → Help & FAQ** | Banner "Still need help? Ask Waswa AI." → **Chat** |
| **Reports → Generate** | **Ask Waswa AI** card (opens the report assistant; see 3.5) |
| **Token Billing → Buy** | **Ask AI** chip (a separate token-buying assistant; see 3.6) |

The first four all open the **same conversation**.

⚠ The guide says the AI button "floats over every screen". It is hidden on Reports.

## 3.3 Asking a question

1. Open Waswa. A greeting appears with four quick questions:
   - "How many tokens do I have?"
   - "Why is a vehicle offline?"
   - "How do tracking tokens work?"
   - "Explain my charges"
2. Tap a quick question, or type in the box **"Ask Waswa about…"** and tap the green send button.
3. For more ideas, tap the **sparkle** button (tooltip "Suggested questions"). It offers six topics: GPS tokens, balance, charges, buying tokens, auto-renew, pausing tracking.
   ⚠ The guide calls this the **+** button.
4. While Waswa works, "Waswa is typing…" is shown. Answers can take up to 90 seconds; in the last recorded evaluation answers averaged about 18 seconds.
5. Ask follow-ups normally. Waswa remembers the conversation.

**Screen context.** The header shows **Context: _screen name_**, meaning Waswa knows which screen you came from (for example Live Tracking). This helps it give relevant answers.

## 3.4 After an answer

- **Helpful** (thumbs up) or **Not helpful** (flag) appear under each answer.
  - "Not helpful" shows *"Sent for correction — our team will fix this"* and puts the answer in the staff review queue.
- **Verified answer** chip: the answer used a correction approved by 3D Services staff. Tap it to see which approved question was matched.
- **Errors.** If the network fails, a red message such as *"Cannot reach the server. Check your internet connection."* appears with **Try again**.
  ⚠ The guide quotes a different error text that users will rarely see.

## 3.5 Asking Waswa for a report (BETA)

1. Go to **Reports → Generate** and tap **Ask Waswa AI**.
2. Describe the report, for example "Overspeeding for all trucks last week". You can also tap one of the **TRY** examples.
3. Tap **Fetch Report**. Waswa works out the report type, dates and vehicles.
   - Supported report types: trips, overspeeding, fuel, geozone, night driving, idling, parking.
   - If you don't say otherwise, it uses the last 7 days and all vehicles.
4. The Reports form is filled in and the report is generated. A message "Waswa: …" explains what was chosen.

Notes:

- This does not appear in the main chat history.
- It works even if Waswa is switched off.

## 3.6 Ask AI on Token Billing

On **Token Billing → Buy**, the **Ask AI** chip opens a separate assistant for choosing a token package. If its reply names a package, a **Buy** card appears that leads into the normal purchase flow.

Notes:

- This assistant has no feedback buttons.
- It also works when Waswa is switched off.
- ⚠ Waswa never quotes prices (the `buy-tokens` guide says so too), yet the starter suggestions are phrased around a budget. Users may expect a price.

## 3.7 Switching Waswa off and on

Tap the **ON/OFF** pill in the chat header.

- When off, an amber banner *"Waswa is switched off."* appears with **Switch on**.
- Your choice is remembered on the device.

## 3.8 Starting over and privacy

- **New conversation.** ⋮ menu → **New conversation**.
- **Signing out** clears the conversation from the phone.
  - There is no history list in the app.
  - Conversations remain stored on the server (see [Security](06-security-and-privacy.md)).

## 3.9 What to tell customers Waswa cannot do

- It cannot quote prices or discounts. It will direct them to sales.
- It cannot make changes, such as pausing tracking, buying tokens or editing geofences. It explains how to do these in the app instead.
- It can only see the customer's own account.

---

## 3.10 Staff: reviewing and correcting Waswa (back office)

The console is available through the API (`/assistant/console/*`). The screens are provided by the CMS, which was not inspected for this report.

**Who.**
- Users holding `waswa.review` (reviewers) or `waswa.approve` (approvers).
- Super admins, system accounts and internal admins get these automatically.
- Customer accounts can never hold them.

**Typical workflow:**
1. **Queue.** Open the review queue. It shows flagged answers, corrections awaiting approval, corrections due for re-check, and new documents.
2. **Inspect.** Open the conversation to see the full messages, the data Waswa used ("evidence"), and the customer's feedback.
3. **Correct.** Draft a *verified answer*.
   - Currency amounts are not allowed.
   - Text touching money, approvals or account actions is classed as "policy" and needs **two** approvers. Routine fixes need one.
4. **Submit** the draft. Drafts that were never submitted can be deleted.
5. **Approve.** A *different* person approves it. Waswa starts using it at once for matching questions.
6. **Resolve** the original flag.
7. **Upkeep.** Approved answers come back for re-check after 180 days, or when the document they rely on changes.

**Documents:**
1. **Upload** (PDF/Word/Excel/Markdown/text, ≤25 MB). Choose an authority level (2–6), a document type, and an audience: "staff" (default) or "everyone", meaning customers too.
2. A **different person** approves it. Admins may self-approve, and this is logged.
3. To update a document, upload a **new version**. The old version keeps answering until the new one is approved.
4. **Remove** hides a document (reversible). See Known Issues for the rollback limitation.

**OLIWA app guide sync.** Done by a developer using the `/kb-sync` skill in the `oliwa-mobile` repo; see [AI and Knowledge Base](04-ai-and-knowledge-base.md#44-keeping-the-app-guide-in-sync).
