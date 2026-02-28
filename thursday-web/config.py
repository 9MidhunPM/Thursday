"""
Configuration constants for Thursday Web.
All tunables in one place.
"""

from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).parent
PERSONALITY_FILE = BASE_DIR / "personality.txt"
DB_FILE = BASE_DIR / "thursday.db"

# --- LLM Server (llama-server) ---
LLAMA_BASE_URL = "http://localhost:8080"
LLAMA_CHAT_ENDPOINT = f"{LLAMA_BASE_URL}/v1/chat/completions"

# --- Proxy server ---
PROXY_HOST = "0.0.0.0"
PROXY_PORT = 5000

# --- Model parameters ---
MODEL_NAME = "llama-3-8b-instruct"
TEMPERATURE = 0.7
MAX_TOKENS = 512
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
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1473211981849956514/BNjMMxE6BHlkLVvE1Lu2P1R892DL7iax9H4W3A9vH2bh7Dz6-YafP6RYfQwoMCHq9UCt"
DISCORD_USER_ID = "789374384136519690"
REMINDER_CHECK_INTERVAL = 10  # seconds between due-reminder checks
