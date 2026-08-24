"""
Standalone smoke test for the Waswa assistant's OpenRouter connection.

Runs WITHOUT the database or a JWT — it just confirms your OPENROUTER_API_KEY
and model work end-to-end and prints a sample Waswa reply.

Usage (from the navas-core-apis project root):
    python scripts/test_openrouter.py
    python scripts/test_openrouter.py "How do GPS tokens work?"

Reads OPENROUTER_API_KEY / OPENROUTER_MODEL from your .env (gitignored) or
environment. Never prints the full key.
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o")
SITE_URL = os.environ.get("OPENROUTER_SITE_URL", "https://narvas.3dservices.co.ug/")
SITE_NAME = os.environ.get("OPENROUTER_SITE_NAME", "OLIWA Mobile")

SYSTEM_PROMPT = (
    "You are Waswa, the in-app assistant for OLIWA, a smart fleet-tracking "
    "service. Tracking is paid for with prepaid TOKENS bought via mobile money. "
    "Be concise and friendly. Only use figures given in the live context; never "
    "invent numbers. You cannot perform actions — guide the user to the screen."
)

# A stand-in for the live account context the app sends per user.
SAMPLE_CONTEXT = (
    "Token balance: 420 tokens\n"
    "GPS tracking remaining: 288h 00m\n"
    "Vehicles: 44 active, 5 offline\n"
    "Alerts today: 2"
)


def main() -> int:
    if not API_KEY:
        print("[FAIL] OPENROUTER_API_KEY is not set (.env or environment).")
        return 1
    print(f"Key: {API_KEY[:10]}...{API_KEY[-4:]}   Model: {MODEL}")

    question = sys.argv[1] if len(sys.argv) > 1 else "How many tokens do I have?"
    print(f"Question: {question}\n")

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "HTTP-Referer": SITE_URL,
                "X-Title": SITE_NAME,
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "system",
                     "content": "Live account context:\n" + SAMPLE_CONTEXT},
                    {"role": "user", "content": question},
                ],
                "max_tokens": 600,
                "temperature": 0.3,
            },
            timeout=45,
        )
    except requests.RequestException as e:
        print(f"[FAIL] Network error reaching OpenRouter: {e}")
        return 1

    if resp.status_code != 200:
        print(f"[FAIL] HTTP {resp.status_code}: {resp.text[:400]}")
        return 1

    body = resp.json()
    reply = body["choices"][0]["message"]["content"].strip()
    usage = body.get("usage", {})
    print("[OK] Waswa replied:\n")
    print(reply)
    print(f"\n(tokens used: {usage})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
