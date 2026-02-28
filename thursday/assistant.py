"""
Core assistant orchestrator for Thursday.

Owns the prompt construction pipeline:
  1. System message  (personality)
  2. Long-term facts  (injected as a second system message)
  3. Recent chat history (short-term memory)
  4. Current user message

Coordinates memory extraction and API calls.

Extension point: add a retrieval step here that queries an embeddings
index before constructing the prompt, to pull in semantically relevant
past conversations or documents.
"""

from api_client import LlamaClient
from memory import MemoryStore
from personality import Personality


class Assistant:
    """Thursday assistant — ties personality, memory, and LLM together."""

    def __init__(self) -> None:
        self.personality = Personality()
        self.memory = MemoryStore()
        self.client = LlamaClient()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def respond(self, user_input: str) -> str:
        """
        Process a user message and return the assistant's reply.

        Steps:
          1. Check for long-term memory triggers and store facts.
          2. Save user message to short-term history.
          3. Build prompt (personality + facts + history).
          4. Call LLM.
          5. Save assistant reply to short-term history.
          6. Return reply text.
        """
        # --- Step 1: long-term extraction ---
        extracted = self.memory.try_extract_fact(user_input)

        # --- Step 2: persist user message ---
        self.memory.add_message("user", user_input)

        # --- Step 3: build messages array ---
        messages = self._build_messages()

        # --- Step 4: call LLM (streaming prints tokens live) ---
        reply = self.client.chat(messages, stream=True)

        # --- Step 5: persist assistant reply ---
        self.memory.add_message("assistant", reply)

        return reply

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_messages(self) -> list[dict]:
        """
        Assemble the full messages array for the API call.

        Layout:
          [system: personality]
          [system: long-term facts]   <- omitted if no facts
          [user/assistant history...]
        """
        messages: list[dict] = []

        # 1. Personality
        messages.append(self.personality.as_system_message())

        # 2. Long-term facts (optional second system block)
        facts_block = self.memory.get_facts_block()
        if facts_block:
            messages.append({"role": "system", "content": facts_block})

        # 3. Recent conversation history (already includes current user msg)
        history = self.memory.get_recent_messages()
        messages.extend(history)

        return messages

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def clear_history(self) -> None:
        """Wipe short-term conversation memory."""
        self.memory.clear_history()

    def show_memory(self) -> str:
        """Return formatted long-term facts."""
        return self.memory.list_facts_formatted()

    def health(self) -> bool:
        """Check if the LLM server is reachable."""
        return self.client.health_check()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Release resources."""
        self.client.close()
        self.memory.close()
