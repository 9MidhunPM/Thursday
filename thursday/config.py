"""
Configuration constants for Thursday AI assistant.
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

# --- LLM Server ---
LLAMA_HOST = os.getenv("LLAMA_HOST", "127.0.0.1")
LLAMA_PORT = int(os.getenv("LLAMA_PORT", "8080"))
API_BASE_URL = f"http://{LLAMA_HOST}:{LLAMA_PORT}"
CHAT_ENDPOINT = f"{API_BASE_URL}/v1/chat/completions"

# --- Model parameters ---
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3-8b-instruct")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))
TOP_P = 0.9

# --- Memory ---
SHORT_TERM_LIMIT = 10          # max recent messages sent in context
LONG_TERM_MAX_INJECT = 15      # max long-term facts injected per prompt
DB_PRUNE_THRESHOLD = 500       # prune short-term history when rows exceed this

# --- Trigger phrases for long-term memory extraction ---
# These are checked case-insensitively at the start of user messages.
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
