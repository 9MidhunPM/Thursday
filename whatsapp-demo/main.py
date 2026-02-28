"""
WhatsApp AI Demo — Exhibition Mode

Minimal FastAPI server that bridges Twilio WhatsApp ↔ llama-server.

Flow:
  WhatsApp → Twilio → ngrok → POST /whatsapp → llama-server → TwiML → WhatsApp

Usage:
  1. Start llama-server  (start-server.bat from project root)
  2. python main.py       (this file)
  3. ngrok http 5000      (in another terminal)
  4. Paste ngrok URL into Twilio sandbox webhook
"""

import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Response
from fastapi.responses import PlainTextResponse
import requests
import uvicorn

# ── Load .env ──────────────────────────────────────────────────────
# Try local .env first, then project root .env
_here = Path(__file__).resolve().parent
for _env in [_here / ".env", _here.parent / ".env"]:
    if _env.exists():
        load_dotenv(_env)
        break

LLAMA_ENDPOINT = os.getenv("LLAMA_ENDPOINT", "http://localhost:8080/v1/chat/completions")
PORT = int(os.getenv("WHATSAPP_DEMO_PORT", os.getenv("PORT", "5000")))

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("whatsapp-demo")

# ── System prompt ──────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are Thursday — a friendly, witty AI assistant. "
    "Keep replies concise (1-3 sentences). "
    "Be helpful and conversational. "
    "You are being accessed via WhatsApp."
)

# ── FastAPI app ────────────────────────────────────────────────────
app = FastAPI(title="WhatsApp AI Demo", version="1.0.0")


def _twiml(body: str) -> Response:
    """Wrap a text reply in Twilio's TwiML XML format."""
    # Escape XML special characters
    safe = (
        body
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{safe}</Message>"
        "</Response>"
    )
    return Response(content=xml, media_type="application/xml")


def _ask_llama(user_message: str) -> str:
    """Send a single-turn message to llama-server and return the reply."""
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 200,
        "temperature": 0.7,
        "stream": False,
    }
    try:
        r = requests.post(LLAMA_ENDPOINT, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.ConnectionError:
        log.error("llama-server is not reachable at %s", LLAMA_ENDPOINT)
        return "⚠️ Assistant is currently offline. Please try again later."
    except requests.Timeout:
        log.error("llama-server timed out")
        return "⚠️ The assistant is taking too long. Please try again."
    except Exception as exc:
        log.error("llama-server error: %s", exc)
        return "⚠️ Something went wrong. Please try again later."


# ── Webhook endpoint ──────────────────────────────────────────────
@app.post("/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(""),
    From: str = Form(""),
):
    """Receive a WhatsApp message from Twilio, query the LLM, reply."""
    sender = From.replace("whatsapp:", "")
    user_msg = Body.strip()

    if not user_msg:
        return _twiml("Send me a message and I'll respond!")

    log.info("📩 %s: %s", sender, user_msg[:80])

    reply = _ask_llama(user_msg)

    # Twilio WhatsApp limit: 1600 chars
    if len(reply) > 1500:
        reply = reply[:1497] + "..."

    log.info("📤 Reply (%d chars): %s", len(reply), reply[:80])
    return _twiml(reply)


# ── Health check ──────────────────────────────────────────────────
@app.get("/")
async def root():
    return PlainTextResponse("WhatsApp AI Demo is running ✓")


@app.get("/health")
async def health():
    try:
        r = requests.get(
            LLAMA_ENDPOINT.replace("/v1/chat/completions", "/health"),
            timeout=5,
        )
        llama_ok = r.status_code == 200
    except Exception:
        llama_ok = False
    return {
        "demo": "ok",
        "llama_server": "ok" if llama_ok else "offline",
    }


# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("=" * 50)
    log.info("  WhatsApp AI Demo — Exhibition Mode")
    log.info("  LLM endpoint : %s", LLAMA_ENDPOINT)
    log.info("  Listening on : http://localhost:%d", PORT)
    log.info("=" * 50)
    log.info("")
    log.info("  Next steps:")
    log.info("  1. Run: ngrok http %d", PORT)
    log.info("  2. Copy the https://xxxx.ngrok.io URL")
    log.info("  3. Paste into Twilio sandbox as: https://xxxx.ngrok.io/whatsapp")
    log.info("")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
