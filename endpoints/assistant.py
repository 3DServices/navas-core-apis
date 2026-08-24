"""
assistant.py — Waswa AI Assistant (OpenRouter proxy).

The OpenRouter API key lives server-side (config.OPENROUTER_API_KEY) and is
NEVER exposed to the mobile client. The app calls POST /assistant/chat with a
message (and optional short history + live account context); this endpoint
injects a scoped system prompt, forwards the conversation to OpenRouter's
chat-completions API, and returns the assistant's reply in the standard
{status, message, data} envelope.
"""

from flask import Blueprint, request
import requests

from .globals import reply, _extract_account_uid
from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
    OPENROUTER_SITE_NAME,
)

assistant_bp = Blueprint("Assistant", __name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# How much of the client-supplied conversation we forward, to cap token spend.
_MAX_HISTORY = 10

SYSTEM_PROMPT = (
    "You are Waswa, the in-app assistant for OLIWA — a smart fleet-tracking "
    "service (powered by the NAVAS IoT engine) used mainly in East Africa. "
    "You help users understand vehicle tracking, token billing, alerts, and "
    "reports.\n\n"
    "Key facts about OLIWA:\n"
    "- Tracking is paid for with prepaid TOKENS. Tokens are billed per event / "
    "per hour depending on the token package.\n"
    "- Users buy tokens via mobile money (MTN, Airtel, etc.).\n"
    "- Domains include GPS tracking, fuel monitoring, driver behaviour, and "
    "compliance.\n\n"
    "Rules:\n"
    "- Be concise, friendly, and practical. Prefer short answers.\n"
    "- Only use figures (token balances, vehicle counts, etc.) that are given "
    "to you in the 'Live account context'. NEVER invent numbers, prices, or "
    "account details. If you don't have a figure, say so and tell the user "
    "where to find it in the app.\n"
    "- You cannot perform actions yourself (you cannot buy tokens, pause "
    "tracking, or generate reports). Guide the user to the relevant screen "
    "instead, and never ask for PINs, passwords, or full payment details.\n"
    "- Stay on OLIWA / fleet-tracking topics. Politely decline unrelated "
    "requests.\n"
)


@assistant_bp.route("/assistant/chat", methods=["POST"])
def AssistantChat():
    try:
        # 1. Require a valid signed JWT (any authenticated user).
        account_uid = _extract_account_uid()
        if not account_uid:
            return reply("error", 401, "Authentication required.", "")

        # 2. Ensure the assistant is configured.
        if not OPENROUTER_API_KEY:
            return reply(
                "error", 503,
                "The assistant is not configured yet. Please try again later.",
                "",
            )

        payload = request.get_json(silent=True) or {}
        data = payload.get("data") or {}

        user_message = str(data.get("message", "")).strip()
        if not user_message:
            return reply("error", 400, "A message is required.", "")

        history = data.get("history") or []
        context = data.get("context")

        # 3. Build the message list: system prompt (+ live context) + history +
        #    the new user message.
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if context:
            messages.append({
                "role": "system",
                "content": "Live account context (authoritative — use these "
                           "figures):\n" + str(context),
            })

        if isinstance(history, list):
            for turn in history[-_MAX_HISTORY:]:
                if not isinstance(turn, dict):
                    continue
                role = turn.get("role")
                content = turn.get("content")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": str(content)})

        messages.append({"role": "user", "content": user_message})

        # 4. Forward to OpenRouter.
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": OPENROUTER_SITE_URL,
                    "X-Title": OPENROUTER_SITE_NAME,
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": messages,
                    "max_tokens": 600,
                    "temperature": 0.3,
                },
                timeout=45,
            )
        except requests.RequestException:
            return reply("error", 504, "The assistant took too long to respond.", "")

        if resp.status_code != 200:
            return reply("error", 502, "The assistant is unavailable right now.", "")

        body = resp.json()
        choices = body.get("choices") or []
        if not choices:
            return reply("error", 502, "The assistant returned no response.", "")

        text = (choices[0].get("message") or {}).get("content", "").strip()
        if not text:
            return reply("error", 502, "The assistant returned an empty response.", "")

        return reply("success", 200, "OK", {"reply": text, "model": OPENROUTER_MODEL})

    except Exception as error:
        return reply("error", 500, str(error), "")
