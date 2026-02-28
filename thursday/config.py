"""
Configuration constants for Thursday AI assistant.
All tunables in one place. Modify as needed.
"""

from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).parent
PERSONALITY_FILE = BASE_DIR / "personality.txt"
DB_FILE = BASE_DIR / "thursday.db"

# --- LLM Server ---
API_BASE_URL = "http://localhost:8080"
CHAT_ENDPOINT = f"{API_BASE_URL}/v1/chat/completions"

# --- Model parameters ---
MODEL_NAME = "llama-3-8b-instruct"  # label only, server already has model loaded
TEMPERATURE = 0.7
MAX_TOKENS = 512
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
