"""
Unified notification module for Thursday.

Supports:
  - Discord (webhook)
  - WhatsApp (Twilio)

Usage:
    from notifier import notify

    notify("Hello!", channel="discord")       # Discord only
    notify("Hello!", channel="whatsapp")      # WhatsApp only
    notify("Hello!", channel="all")           # Both channels
    notify("Hello!")                           # Default: Discord

If a channel fails, the module falls back to the other channel
automatically.  All errors are logged, never raised.
"""

import logging
import os

import requests

log = logging.getLogger("thursday.notifier")

# ---------------------------------------------------------------------------
# Environment variables  (loaded once at import time via dotenv in config.py)
# ---------------------------------------------------------------------------
DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_USER_ID: str = os.getenv("DISCORD_USER_ID", "")

TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM: str = os.getenv("TWILIO_WHATSAPP_FROM", "")
TWILIO_WHATSAPP_TO: str = os.getenv("TWILIO_WHATSAPP_TO", "")


# ---------------------------------------------------------------------------
# Channel availability checks
# ---------------------------------------------------------------------------

def discord_configured() -> bool:
    return bool(DISCORD_WEBHOOK_URL)


def whatsapp_configured() -> bool:
    return all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                TWILIO_WHATSAPP_FROM, TWILIO_WHATSAPP_TO])


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

def send_discord(message: str, *, username: str = "Thursday AI") -> bool:
    """Send a message via Discord webhook.  Returns True on success."""
    if not discord_configured():
        log.warning("Discord webhook not configured — skipping.")
        return False
    try:
        r = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": message, "username": username},
            timeout=10,
        )
        ok = r.status_code in (200, 204)
        if not ok:
            log.error("Discord returned %s: %s", r.status_code, r.text[:200])
        return ok
    except Exception as exc:
        log.error("Discord webhook error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# WhatsApp (Twilio)
# ---------------------------------------------------------------------------

def send_whatsapp(message: str) -> bool:
    """Send a WhatsApp message via Twilio.  Returns True on success."""
    if not whatsapp_configured():
        log.warning("Twilio WhatsApp not configured — skipping.")
        return False
    try:
        from twilio.rest import Client

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            body=message,
            from_=f"whatsapp:{TWILIO_WHATSAPP_FROM}",
            to=f"whatsapp:{TWILIO_WHATSAPP_TO}",
        )
        log.info("WhatsApp message sent — SID: %s", msg.sid)
        return True
    except Exception as exc:
        log.error("WhatsApp (Twilio) error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Unified dispatcher with automatic fallback
# ---------------------------------------------------------------------------

def notify(message: str, channel: str = "discord") -> bool:
    """Send a notification on the chosen channel.

    Args:
        message:  Text to send.
        channel:  "discord" | "whatsapp" | "all"

    Fallback logic:
        - If the primary channel fails, the other channel is tried.
        - ``channel="all"`` sends to both; returns True if at least one
          succeeds.

    Returns True if at least one channel delivered successfully.
    """
    channel = channel.lower().strip()

    if channel == "all":
        d = send_discord(message)
        w = send_whatsapp(message)
        return d or w

    if channel == "whatsapp":
        if send_whatsapp(message):
            return True
        log.warning("WhatsApp failed — falling back to Discord.")
        return send_discord(message)

    # default: discord
    if send_discord(message):
        return True
    log.warning("Discord failed — falling back to WhatsApp.")
    return send_whatsapp(message)
