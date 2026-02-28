# Thursday — Local AI Assistant

Lightweight Python CLI assistant backed by a local `llama-server` instance.

## Prerequisites

- Python 3.11+
- `llama-server.exe` running with your model (Llama 3 8B Instruct Q4_K_M)
- The server exposes `http://localhost:8080`

## Quick Start

```bash
cd thursday
pip install -r requirements.txt
python main.py
```

## File Structure

```
thursday/
├── main.py            # CLI entry point — chat loop and commands
├── assistant.py       # Orchestrator — builds prompts, coordinates modules
├── api_client.py      # HTTP client — talks to llama-server
├── memory.py          # SQLite short-term + long-term memory
├── personality.py     # Loads personality.txt as system prompt
├── config.py          # All tunables in one place
├── personality.txt    # Editable personality definition
├── requirements.txt   # Python dependencies
└── thursday.db        # Created at runtime (SQLite)
```

## Commands

| Command        | Description                          |
|----------------|--------------------------------------|
| `/exit`        | Quit                                 |
| `/clear`       | Wipe conversation history            |
| `/memory`      | Show stored long-term facts          |
| `/forget <id>` | Remove a specific long-term memory   |
| `/reload`      | Reload personality.txt from disk     |
| `/help`        | Show available commands              |

## Long-Term Memory

Say things like:
- "Remember that I use Arch Linux"
- "My favorite language is C++"
- "I prefer dark mode"

Thursday detects these and stores them as persistent facts injected into every prompt.

## Configuration

Edit `config.py` to tune:
- `SHORT_TERM_LIMIT` — how many recent messages to include (default: 10)
- `LONG_TERM_MAX_INJECT` — max facts in prompt (default: 15)
- `TEMPERATURE`, `MAX_TOKENS`, `TOP_P` — model parameters
- `API_BASE_URL` — server address

## Architecture Notes

- **No frameworks** — raw `requests` + `sqlite3` + stdlib only.
- **Streaming** — tokens print as they arrive for fast perceived latency.
- **Prompt layout**: `[system: personality] [system: facts] [chat history]`
- **Extension-ready** — comments mark where to add embeddings, async, etc.
