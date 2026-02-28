# Thursday — Local AI Assistant

A personal AI assistant powered by [llama.cpp](https://github.com/ggerganov/llama.cpp), running entirely on your own hardware.  
Comes in two flavours: a **CLI** chat and a **Web UI** with conversations, memory, and multi-channel notifications (Discord + WhatsApp).

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.11+** | Tested on 3.11 / 3.12 |
| **A Vulkan-capable GPU** | For GPU-accelerated inference (NVIDIA, AMD, Intel Arc) |
| **~5 GB disk space** | For the quantised model file |

---

## Quick Setup

### 1. Clone the repo

```bash
git clone https://github.com/9MidhunPM/ThursdayV2.git
cd ThursdayV2
```

### 2. Download the model

Download **Meta-Llama-3-8B-Instruct** in Q4_K_M quantisation (`.gguf` format) and place it in:

```
llama.cpp/models/meta-llama-3-8b-instruct.Q4_K_M.gguf
```

You can get it from [Hugging Face](https://huggingface.co/QuantFactory/Meta-Llama-3-8B-Instruct-GGUF) or quantise your own.

> **Using a different model?** Update `MODEL_PATH` in `.env` and `MODEL_NAME` to match.

### 3. Get the llama-server binary

Build [llama.cpp](https://github.com/ggerganov/llama.cpp) from source or download a pre-built release, then copy these files into `llama.cpp/build/bin/Release/`:

| File | Purpose |
|---|---|
| `llama-server.exe` | The inference server |
| `llama.dll` | Core llama library |
| `ggml.dll` | GGML tensor library |
| `ggml-base.dll` | GGML base backend |
| `ggml-cpu.dll` | CPU compute backend |
| `ggml-vulkan.dll` | Vulkan GPU backend |
| `mtmd.dll` | Multi-modal support |

### 4. Configure environment

```bash
copy .env.example .env        # Windows
# cp .env.example .env        # Linux/macOS
```

Edit `.env` with your values:

```env
# Required — paths to model and server
MODEL_PATH=llama.cpp/models/meta-llama-3-8b-instruct.Q4_K_M.gguf
SERVER_PATH=llama.cpp/build/bin/Release/llama-server.exe

# Optional — Discord reminders (leave empty to disable)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE
DISCORD_USER_ID=YOUR_DISCORD_USER_ID

# Server connection (defaults are fine for local use)
LLAMA_HOST=127.0.0.1
LLAMA_PORT=8080

# Model parameters
MODEL_NAME=llama-3-8b-instruct
TEMPERATURE=0.7
MAX_TOKENS=512
```

### 5. Install Python dependencies

```bash
pip install -r thursday-web/requirements.txt
```

### 6. Start the llama server

```bash
start-server.bat
```

This launches `llama-server` with GPU offloading, 2048 context, and KV-cache quantisation.

### 7. Start Thursday

**Web UI** (recommended):
```bash
cd thursday-web
python main.py
```
Then open **http://localhost:5000** in your browser.

**CLI mode**:
```bash
cd thursday
python main.py
```

---

## Project Structure

```
ThursdayV2/
├── .env.example           # Template — copy to .env
├── .env                   # Your local config (git-ignored)
├── .gitignore
├── Modelfile              # Personality reference (Ollama format)
├── start-server.bat       # Launches llama-server with optimal flags
│
├── thursday-web/          # Web UI version
│   ├── main.py            # FastAPI server (port 5000)
│   ├── llama_client.py    # HTTP client for llama-server
│   ├── memory.py          # SQLite short + long-term memory
│   ├── personality.py     # System prompt loader
│   ├── reminder.py        # Reminder system + notification triggers
│   ├── notifier.py        # Unified notifications (Discord + WhatsApp)
│   ├── config.py          # Configuration (reads .env)
│   ├── personality.txt    # Editable personality definition
│   ├── requirements.txt   # Python dependencies
│   └── ui/                # Frontend (HTML/CSS/JS)
│       ├── index.html
│       ├── style.css
│       └── app.js
│
├── thursday/              # CLI version
│   ├── main.py            # Terminal chat loop
│   ├── assistant.py       # Prompt orchestrator
│   ├── api_client.py      # HTTP client for llama-server
│   ├── memory.py          # SQLite memory
│   ├── personality.py     # System prompt loader
│   ├── config.py          # Configuration (reads .env)
│   ├── personality.txt    # Editable personality definition
│   └── requirements.txt   # Python dependencies
│
└── llama.cpp/             # Runtime only (source not included)
    ├── LICENSE
    ├── README.md           # Setup instructions for binaries
    ├── build/bin/Release/  # Server binary + DLLs (git-ignored)
    └── models/             # .gguf model files (git-ignored)
```

---

## Features

- **Fully local** — no API keys, no cloud, runs on your machine
- **Persistent memory** — remembers facts across sessions (SQLite)
- **Conversation management** — create, rename, delete conversations (Web UI)
- **Streaming responses** — real-time token-by-token output
- **Discord reminders** — set timed reminders that ping you via webhook
- **WhatsApp chat** — full Thursday experience via WhatsApp (Twilio + ngrok)
- **WhatsApp reminders** — optional Twilio-powered WhatsApp notifications with automatic fallback
- **Customisable personality** — edit `personality.txt` to change how Thursday talks
- **GPU accelerated** — Vulkan backend with KV-cache quantisation

---

## Discord Reminders (Optional)

1. Create a webhook in your Discord server (Server Settings → Integrations → Webhooks)
2. Copy the webhook URL into `DISCORD_WEBHOOK_URL` in `.env`
3. Put your Discord user ID in `DISCORD_USER_ID` (for @mentions)
4. In the chat, say something like *"remind me to check the build in 30 minutes"*

---

## WhatsApp Notifications via Twilio (Optional)

### 1. Create a Twilio account

- Sign up at [twilio.com](https://www.twilio.com/)
- From the console, note your **Account SID** and **Auth Token**

### 2. Set up the WhatsApp Sandbox

- Go to **Messaging → Try it out → Send a WhatsApp message**
- Follow the instructions to join the sandbox (send a code from your phone to the Twilio number)
- Note the sandbox number (e.g. `+14155238886`)

### 3. Add credentials to `.env`

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_FROM=+14155238886
TWILIO_WHATSAPP_TO=+1XXXXXXXXXX
```

| Variable | Description |
|---|---|
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID (starts with `AC`) |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token |
| `TWILIO_WHATSAPP_FROM` | Twilio sandbox/sender number (include `+` and country code) |
| `TWILIO_WHATSAPP_TO` | Your personal phone number (include `+` and country code) |

### 4. Install the SDK

**Windows (PowerShell):**
```powershell
pip install twilio
```

**Linux / macOS:**
```bash
pip install twilio
```

Or just run `pip install -r thursday-web/requirements.txt` — twilio is already included.

### 5. How it works

When a reminder fires, Thursday sends notifications to **both** Discord and WhatsApp (if configured).  
If one channel fails, the other still delivers. If WhatsApp is not configured, it silently skips it.

---

## WhatsApp Chat via Twilio + ngrok (Optional)

Chat with the **full Thursday** (same personality, memory, reminders) over WhatsApp.

### Prerequisites

- Twilio WhatsApp Sandbox set up (see above)
- [ngrok](https://ngrok.com/) installed

### Setup (one-time)

1. Start Thursday Web as usual (`python main.py` in `thursday-web/`)
2. In a separate terminal, start ngrok:
   ```powershell
   ngrok http 5000
   ```
3. Copy the `https://` URL from ngrok (e.g. `https://abc123.ngrok-free.app`)
4. Go to [Twilio Console → WhatsApp Sandbox](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
5. Under **Sandbox Configuration**, set:
   - **When a message comes in**: `https://YOUR-NGROK-URL.ngrok-free.app/whatsapp`
   - **Method**: `POST`
6. Click **Save**
7. Send any message from WhatsApp → Thursday replies with full memory + personality!

### How it works

```
WhatsApp → Twilio → ngrok → POST /whatsapp → Thursday (memory + personality + LLM) → TwiML → WhatsApp
```

- Uses the **same database** as the Web UI (shared memory, facts, reminders)
- WhatsApp messages appear in a dedicated "WhatsApp" conversation
- Reminders set via WhatsApp also fire as Discord/WhatsApp notifications
- To stop: close ngrok (`Ctrl+C`). Thursday Web keeps running for the browser UI.

### Troubleshooting

| Problem | Fix |
|---|---|
| No reply on WhatsApp | Check ngrok is running and URL is in Twilio sandbox |
| ngrok expired | Restart ngrok, update Twilio webhook URL |
| Slow responses | Normal — local LLM takes 5-30s depending on GPU |

---

## Configuration Reference

All settings live in `.env` at the project root. Both `thursday/` and `thursday-web/` read from the same file.

| Variable | Default | Description |
|---|---|---|
| `MODEL_PATH` | `llama.cpp/models/meta-llama-3-8b-instruct.Q4_K_M.gguf` | Path to your GGUF model |
| `SERVER_PATH` | `llama.cpp/build/bin/Release/llama-server.exe` | Path to llama-server binary |
| `LLAMA_HOST` | `127.0.0.1` | Host the llama-server listens on |
| `LLAMA_PORT` | `8080` | Port the llama-server listens on |
| `MODEL_NAME` | `llama-3-8b-instruct` | Display name for the model |
| `TEMPERATURE` | `0.7` | Sampling temperature |
| `MAX_TOKENS` | `512` | Max tokens per response |
| `DISCORD_WEBHOOK_URL` | *(empty)* | Discord webhook for reminders |
| `DISCORD_USER_ID` | *(empty)* | Your Discord ID for @mentions |
| `TWILIO_ACCOUNT_SID` | *(empty)* | Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | *(empty)* | Twilio Auth Token |
| `TWILIO_WHATSAPP_FROM` | *(empty)* | Twilio sandbox/sender number |
| `TWILIO_WHATSAPP_TO` | *(empty)* | Your WhatsApp phone number |

---

## License

llama.cpp is licensed under MIT — see [llama.cpp/LICENSE](llama.cpp/LICENSE).
