# WhatsApp AI Demo — Exhibition Mode

A minimal WhatsApp AI assistant that runs **entirely locally** using llama.cpp.  
Built for temporary exhibition demos — easy to start, easy to stop.

```
WhatsApp → Twilio Sandbox → ngrok → FastAPI → llama-server → reply → WhatsApp
```

---

## Prerequisites

| Requirement | Status |
|---|---|
| Python 3.11+ | Required |
| llama-server running on port 8080 | Required |
| ngrok installed | Required |
| Twilio account with WhatsApp Sandbox | Required |

---

## Quick Start (3 Terminals)

### Terminal 1 — Start llama-server

```powershell
cd D:\Codaing\ThursdayV2
.\start-server.bat
```

Wait until you see `server listening` in the output.

### Terminal 2 — Start the demo server

```powershell
cd D:\Codaing\ThursdayV2\whatsapp-demo
pip install -r requirements.txt        # first time only
python main.py
```

You should see:
```
  WhatsApp AI Demo — Exhibition Mode
  LLM endpoint : http://localhost:8080/v1/chat/completions
  Listening on : http://localhost:5050
```

### Terminal 3 — Start ngrok

```powershell
ngrok http 5050
```

You'll see something like:
```
Forwarding  https://abc123.ngrok-free.app → http://localhost:5050
```

Copy the `https://...ngrok-free.app` URL.

---

## Twilio Sandbox Setup

1. Go to [Twilio Console → WhatsApp Sandbox](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)

2. Under **Sandbox Configuration**, set:

   | Field | Value |
   |---|---|
   | **When a message comes in** | `https://YOUR-NGROK-URL.ngrok-free.app/whatsapp` |
   | **Method** | `POST` |

3. Click **Save**

4. Make sure you've joined the sandbox from your phone:
   - Open WhatsApp
   - Send the join code (e.g. `join something-something`) to the Twilio sandbox number
   - You'll get a confirmation reply

5. **Send any message** from WhatsApp → you'll get an AI response!

---

## How It Works

```
Your Phone (WhatsApp)
    │
    ▼
Twilio Sandbox
    │  POST /whatsapp  (Body="hello", From="whatsapp:+91...")
    ▼
ngrok (public tunnel)
    │
    ▼
FastAPI (localhost:5050)
    │  POST to llama-server
    ▼
llama-server (localhost:8080)
    │  LLM generates response
    ▼
FastAPI returns TwiML XML
    │
    ▼
Twilio sends reply to WhatsApp
    │
    ▼
Your Phone sees the reply ✓
```

---

## Stopping Everything

| What | How |
|---|---|
| ngrok | `Ctrl+C` in Terminal 3 |
| Demo server | `Ctrl+C` in Terminal 2 |
| llama-server | `Ctrl+C` in Terminal 1 (or close window) |

**That's it.** No services to disable, no cloud to clean up.

---

## Files

```
whatsapp-demo/
├── main.py            # FastAPI server (the entire backend)
├── requirements.txt   # Python dependencies
├── .env.example       # Environment template
├── start-demo.bat     # One-click server start
├── start-ngrok.bat    # One-click ngrok start
└── README.md          # This file
```

---

## Configuration

Edit `.env` (or the project root `.env`) to change settings:

```env
LLAMA_ENDPOINT=http://localhost:8080/v1/chat/completions
WHATSAPP_DEMO_PORT=5050
```

The demo uses port **5050** by default to avoid conflicting with thursday-web (port 5000).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Assistant is currently offline" | Make sure llama-server is running (`start-server.bat`) |
| No reply on WhatsApp | Check ngrok is running and URL is in Twilio sandbox settings |
| ngrok says "tunnel expired" | Free ngrok sessions expire after ~2 hours — restart ngrok and update Twilio URL |
| Twilio returns error 11200 | Your ngrok URL changed — update it in Twilio sandbox |
| Slow responses | Normal — local LLM inference takes 5-30s depending on GPU |
| "429 Too Many Requests" | Wait a moment — llama-server is busy with another request |
| WhatsApp says "failed to send" | Make sure you've joined the Twilio sandbox (`join xxx` message) |
| Port 5050 in use | Change `WHATSAPP_DEMO_PORT` in `.env` or kill the process using that port |

### Quick health check

Open in browser: `http://localhost:5050/health`

Should show:
```json
{"demo": "ok", "llama_server": "ok"}
```

---

## Exhibition Tips

- **Start everything 10 min before** the demo to let the model warm up
- **Keep a phone ready** with WhatsApp open to the sandbox number
- **Test with a simple message** first: "Hello" or "What can you do?"
- If ngrok expires mid-demo, just restart it and update the Twilio URL (takes 30 seconds)
- The system prompt can be changed in `main.py` → `SYSTEM_PROMPT` variable
