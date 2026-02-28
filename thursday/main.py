#!/usr/bin/env python3
"""
Thursday — CLI chat interface.

Usage:
    python main.py

Commands:
    /exit    — quit
    /clear   — wipe short-term conversation history
    /memory  — show stored long-term facts
    /forget <id> — remove a long-term fact by ID
    /reload  — reload personality.txt from disk
    /help    — show this help
"""

import sys
import os

# Ensure the thursday package directory is on sys.path so bare imports work
# regardless of where the user invokes `python main.py` from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from assistant import Assistant


BANNER = r"""
  _____ _                        _
 |_   _| |__  _   _ _ __ ___  __| | __ _ _   _
   | | | '_ \| | | | '__/ __|/ _` |/ _` | | | |
   | | | | | | |_| | |  \__ \ (_| | (_| | |_| |
   |_| |_| |_|\__,_|_|  |___/\__,_|\__,_|\__, |
                                           |___/
   Local AI Assistant • Llama 3 8B
"""

HELP_TEXT = """
Commands:
  /exit          Quit Thursday
  /clear         Clear conversation history
  /memory        Show long-term memories
  /forget <id>   Remove a long-term memory by ID
  /reload        Reload personality.txt
  /help          Show this help
"""


def main() -> None:
    print(BANNER)

    bot = Assistant()

    # Pre-flight check
    if not bot.health():
        print("[!] Warning: llama-server is not reachable at the configured endpoint.")
        print("[!] Make sure it's running before chatting.\n")
    else:
        print("[✓] Connected to llama-server.\n")

    print("Type /help for commands.\n")

    try:
        _chat_loop(bot)
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        bot.shutdown()
        print("Goodbye, Midhun. 👋")


def _chat_loop(bot: Assistant) -> None:
    """Main read-eval-print loop."""
    while True:
        try:
            user_input = input("\033[96mYou:\033[0m ").strip()
        except EOFError:
            break

        if not user_input:
            continue

        # --- Commands ---
        if user_input.startswith("/"):
            if _handle_command(user_input, bot):
                break  # /exit was issued
            continue

        # --- Normal chat ---
        print("\033[93mThursday:\033[0m ", end="", flush=True)
        bot.respond(user_input)
        # Response is printed via streaming inside api_client; newline already added.


def _handle_command(cmd: str, bot: Assistant) -> bool:
    """
    Process slash commands.
    Returns True if the loop should exit.
    """
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()

    if command == "/exit":
        return True

    elif command == "/clear":
        bot.clear_history()
        print("[✓] Conversation history cleared.\n")

    elif command == "/memory":
        print(bot.show_memory())
        print()

    elif command == "/forget":
        if len(parts) < 2 or not parts[1].isdigit():
            print("Usage: /forget <id>  (use /memory to see IDs)\n")
        else:
            fact_id = int(parts[1])
            if bot.memory.delete_fact(fact_id):
                print(f"[✓] Removed memory #{fact_id}.\n")
            else:
                print(f"[!] No memory with ID {fact_id}.\n")

    elif command == "/reload":
        bot.personality.reload()
        print("[✓] Personality reloaded from disk.\n")

    elif command == "/help":
        print(HELP_TEXT)

    else:
        print(f"[!] Unknown command: {command}. Type /help for options.\n")

    return False


if __name__ == "__main__":
    main()
