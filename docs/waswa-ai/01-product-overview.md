# 1. Product Overview

[← Index](README.md)

## What Waswa AI is

Waswa AI is the conversational assistant built into the NAVAS platform. A signed-in user types a question in plain language, such as "How many tokens do I have?", "Why is my truck offline?" or "How do I create a geofence?". Waswa answers using:

- **the user's own account data**: tokens, vehicles, trips, alerts, geofences and payments;
- **3D Services' approved documents**: manuals, procedures and the OLIWA app guide;
- **the product catalogue**: product capabilities and compatibility, but never prices;
- **corrections approved by 3D Services staff**, which take priority over everything else.

Technically, Waswa is a large language model (by default OpenAI GPT-4o, reached through the OpenRouter service). It is allowed to look things up only through a fixed set of read-only "tools" that the NAVAS backend controls. It cannot change anything in a customer's account.

## Who it is for

| User group | How they reach Waswa | What they get |
|---|---|---|
| **OLIWA mobile app customers** (fleet owners, managers) | Floating AI button on every screen, the side menu, Settings, Help & FAQ, Reports, and Token Billing | Answers about their own fleet and tokens, how to use the app, and report requests |
| **3D Services staff** (support, sales, operations) | The same chat, through the CMS and other surfaces (`surface` = `cms`, `oliwa_console`) | Answers from internal staff-only documents as well, source references, and the ability to look up any client's fleet |
| **Waswa reviewers and approvers** (internal) | Review console endpoints (`/assistant/console/*`), used by the CMS | Review flagged answers, write and approve corrections, manage the document library |

The backend supports a CMS chat surface and the console. The CMS front-end itself is in a separate repository that was **not inspected** for this report.

## Business value (as designed)

These are the intended benefits implied by the implementation. **None has been measured.** No usage, satisfaction, deflection or revenue metrics exist in the code or the repositories.

- **Self-service support.** Customers can answer "where is my vehicle / why is it offline / how many tokens are left" questions without calling support.
- **App adoption.** Step-by-step answers come from the official OLIWA app guide.
- **Consistent answers.** Staff corrections are reviewed by a second person before Waswa uses them, so one fix improves every future answer to that question.
- **Pricing protection.** Waswa never quotes prices or discounts; those questions are handed to the sales team.
- **Product discovery.** Waswa can recommend at most two suitable products, without prices. The [Handover](09-pm-handover.md) covers a conflict in this behaviour.

## Strategy vs. reality

The document `database/knowledge/navas_waswa_ai_strategy_feb2026.md` (a February 2026 strategy note) describes a three-tier "AI cascade":

1. free rule-based handling for about 90% of work;
2. a self-hosted model;
3. a paid external model for under 1% of traffic.

It also describes caching, batching and token-billing for "external AI", with a projected cost reduction.

**What is built is different:**

| Strategy item | Status |
|---|---|
| Rule-based tier | 🟡 Only the pricing filter and some automatic data look-ups run without the AI model |
| Self-hosted model | ⛔ Not built. A `router_tier` value of 2 is reserved in the database and never used |
| External model for most work | 🟢 Every non-pricing question goes to one external model (GPT-4o by default), not a cheaper "mini" model |
| Caching, batching, fine-tuning | ⛔ Not built |
| Charging customers tokens for AI use | ⛔ Not built. There is no per-user AI cost accounting |
| Cost reduction of the stated size | 📋 A projection in the strategy note; not measurable from the current system |

## Current maturity in one sentence

Waswa is a working, read-only question-answering assistant with real account isolation, a careful human review process for corrections, and an evaluation harness. It has **not yet been formally released** (the backend branch is unmerged), it has **no usage limits**, and several planned features (actions, smart routing, cost control) exist **only on paper**.
