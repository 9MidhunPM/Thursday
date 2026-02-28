"""
Configuration constants for Thursday Web.
All tunables in one place.  Secrets and paths are loaded from ../.env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level above this package)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

# --- Paths ---
BASE_DIR = Path(__file__).parent
PERSONALITY_FILE = BASE_DIR / "personality.txt"
DB_FILE = BASE_DIR / "thursday.db"

# --- LLM Server (llama-server) ---
LLAMA_HOST = os.getenv("LLAMA_HOST", "127.0.0.1")
LLAMA_PORT = int(os.getenv("LLAMA_PORT", "8080"))
LLAMA_BASE_URL = f"http://{LLAMA_HOST}:{LLAMA_PORT}"
LLAMA_CHAT_ENDPOINT = f"{LLAMA_BASE_URL}/v1/chat/completions"

# --- Proxy server ---
PROXY_HOST = "0.0.0.0"
PROXY_PORT = 5000

# --- Model parameters ---
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3-8b-instruct")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))
TOP_P = 0.9

# --- Memory ---
SHORT_TERM_LIMIT = 10
LONG_TERM_MAX_INJECT = 15
DB_PRUNE_THRESHOLD = 500

# --- Trigger phrases for long-term memory extraction ---
MEMORY_TRIGGER_PREFIXES = [
    "remember that",
    "remember:",
    "note that",
    "keep in mind",
    "don't forget",
    "my favorite",
    "my name is",
    "i use ",
    "i prefer ",
    "i like ",
    "i work ",
    "i live ",
    "i am ",
    "i'm ",
    "call me ",
]

# --- Discord / Reminders ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_USER_ID = os.getenv("DISCORD_USER_ID", "")
REMINDER_CHECK_INTERVAL = 10  # seconds between due-reminder checks

# --- Twilio / WhatsApp ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")
TWILIO_WHATSAPP_TO = os.getenv("TWILIO_WHATSAPP_TO", "")
