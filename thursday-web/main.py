"""
Thursday Web — FastAPI proxy server.

Routes:
  POST /v1/chat/completions           — main chat endpoint (raw or thursday mode)
  POST /whatsapp                      — Twilio WhatsApp webhook (full Thursday mode)
  GET  /v1/conversations              — list all conversations
  POST /v1/conversations              — create a new conversation
  GET  /v1/conversations/{id}         — get messages for a conversation
  DELETE /v1/conversations/{id}       — delete a conversation
  PATCH /v1/conversations/{id}        — rename a conversation
  GET  /v1/memory                     — list long-term facts
  DELETE /v1/memory/{id}              — delete a fact
  POST /v1/clear                      — clear short-term history
  GET  /health                        — server + llama-server health
  GET  /                              — serves the web UI

Architecture:
  Browser   → FastAPI (port 5000) → llama-server (port 8080)
  WhatsApp  → Twilio → ngrok → FastAPI → llama-server → TwiML → WhatsApp
                                 ↘ memory + personality (thursday mode)
"""

import json
import sys
import os
import asyncio
import logging
import time as _time
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import BackgroundTasks, FastAPI, Form, Response
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import PROXY_HOST, PROXY_PORT, REMINDER_CHECK_INTERVAL, DB_FILE
from llama_client import LlamaClient
from memory import MemoryStore
from personality import Personality
from reminder import (
    ReminderStore,
    extract_reminder_tags,
    strip_reminder_tags,
    parse_time_expression,
    send_reminder_set_notification,
    send_reminder_fire_notification,
    get_current_time_string,
    try_parse_user_reminder,
)


# ------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
# Suppress noisy uvicorn access logs for /health
logging.getLogger("uvicorn.access").addFilter(
    type("HealthFilter", (logging.Filter,), {
        "filter": staticmethod(lambda r: "/health" not in r.getMessage())
    })()
)
# Suppress Twilio SDK request/response logging
logging.getLogger("twilio.http_client").setLevel(logging.WARNING)
log = logging.getLogger("thursday")

# ------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------

llama: LlamaClient
memory: MemoryStore
personality: Personality
reminders: ReminderStore
_reminder_task: asyncio.Task | None = None


async def _reminder_check_loop():
    """Background loop: check for due reminders every N seconds."""
    while True:
        try:
            await asyncio.sleep(REMINDER_CHECK_INTERVAL)
            due = reminders.get_due_reminders()
            for r in due:
                log.info("⏰  Reminder #%d fired: %s", r.id, r.message)
                send_reminder_fire_notification(r.message)
                reminders.mark_fired(r.id)
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Reminder loop error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global llama, memory, personality, reminders, _reminder_task
    llama = LlamaClient()
    memory = MemoryStore()
    personality = Personality()
    reminders = ReminderStore(str(DB_FILE))
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("  Thursday Web starting on http://localhost:%d", PROXY_PORT)
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if llama.health_check():
        log.info("✓  LLM server connected")
    else:
        log.warning("✗  LLM server not reachable — start it first")

    _reminder_task = asyncio.create_task(_reminder_check_loop())
    log.info("✓  Reminder checker started (every %ds)", REMINDER_CHECK_INTERVAL)

    yield

    # Shutdown
    if _reminder_task:
        _reminder_task.cancel()
        try:
            await _reminder_task
        except asyncio.CancelledError:
            pass
    reminders.close()
    llama.close()
    memory.close()


app = FastAPI(title="Thursday Web", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    mode: str = "raw"
    conversation_id: str | None = None
    temperature: float = 0.7
    max_tokens: int = 512
    stream: bool = True


class RenameRequest(BaseModel):
    title: str


# ------------------------------------------------------------------
# Chat route
# ------------------------------------------------------------------

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    messages = [m.model_dump() for m in req.messages]

    if req.mode == "thursday":
        return _thursday_stream(messages, req.temperature, req.max_tokens, req.conversation_id)
    else:
        return _raw_stream(messages, req.temperature, req.max_tokens)


def _raw_stream(
    messages: list[dict], temperature: float, max_tokens: int
) -> StreamingResponse:
    def generate():
        yield from llama.stream_chat(messages, temperature, max_tokens)
    return StreamingResponse(generate(), media_type="text/event-stream")


def _thursday_stream(
    messages: list[dict], temperature: float, max_tokens: int,
    conversation_id: str | None = None,
) -> StreamingResponse:
    user_msg = messages[-1]["content"] if messages else ""
    conv_id = conversation_id
    t0 = _time.time()

    log.info("── Web prompt received (%d chars): %s", len(user_msg), user_msg[:80])

    # Step 1: extract long-term facts
    memory.try_extract_fact(user_msg)

    # Step 2: detect reminder intent from user message (server-side)
    reminder_result = try_parse_user_reminder(user_msg)
    reminder_created = None
    if reminder_result:
        time_expr, reminder_message = reminder_result
        trigger_at = parse_time_expression(time_expr)
        if trigger_at:
            reminder_created = reminders.add_reminder(reminder_message, trigger_at, conv_id)
            log.info("   ⏰ Reminder set: '%s' → fires in %.0fs", reminder_message, trigger_at - _time.time())
            send_reminder_set_notification(reminder_message, trigger_at)

    # Step 3: save user message
    memory.add_message("user", user_msg, conv_id)

    # Auto-title if first message in conversation
    if conv_id and memory.get_conversation_message_count(conv_id) == 1:
        memory.auto_title_conversation(conv_id, user_msg)

    # Step 4: build augmented messages (includes reminder context)
    augmented = _build_thursday_messages(conv_id, reminder_just_set=reminder_created)

    collected_tokens: list[str] = []

    def generate():
        nonlocal collected_tokens
        for sse_line, tokens in llama.stream_chat_and_collect(
            augmented, temperature, max_tokens
        ):
            collected_tokens = tokens
            yield sse_line

        full_reply = "".join(collected_tokens)
        if full_reply:
            _process_reminders(full_reply, conv_id)
            clean_reply = strip_reminder_tags(full_reply)
            memory.add_message("assistant", clean_reply, conv_id)

        elapsed = _time.time() - t0
        token_count = len(collected_tokens)
        reply_chars = len(full_reply) if full_reply else 0
        tps = token_count / elapsed if elapsed > 0 else 0
        log.info(
            "   ✓ Web response done — %d tokens, %d chars, %.1fs (%.1f tok/s)",
            token_count, reply_chars, elapsed, tps,
        )

    return StreamingResponse(generate(), media_type="text/event-stream")


def _process_reminders(full_reply: str, conversation_id: str | None) -> None:
    """Extract [REMIND: ...] tags from the AI reply and create reminders."""
    tags = extract_reminder_tags(full_reply)
    for full_match, time_expr, message in tags:
        trigger_at = parse_time_expression(time_expr)
        if trigger_at is None:
            log.warning("   Could not parse reminder time: '%s'", time_expr)
            continue
        reminder = reminders.add_reminder(message, trigger_at, conversation_id)
        log.info("   ⏰ Reminder #%d set: '%s'", reminder.id, message)
        send_reminder_set_notification(message, trigger_at)


def _build_thursday_messages(
    conversation_id: str | None = None,
    reminder_just_set: object | None = None,
) -> list[dict]:
    msgs: list[dict] = []

    # Build ONE consolidated system message to avoid confusing smaller models
    system_parts: list[str] = []

    # 1. Personality
    system_parts.append(personality.load())

    # 2. Current time
    time_str = get_current_time_string()
    system_parts.append(f"Current date and time: {time_str}")

    # 3. Long-term facts
    facts_block = memory.get_facts_block()
    if facts_block:
        system_parts.append(facts_block)

    # 4. Active reminders
    active = reminders.list_active()
    if active:
        from datetime import datetime
        lines = []
        for r in active:
            dt = datetime.fromtimestamp(r["trigger_at"])
            lines.append(f"- \"{r['message']}\" at {dt.strftime('%I:%M %p on %B %d')}")
        system_parts.append("Active reminders:\n" + "\n".join(lines))

    # 5. Reminder-just-set note
    if reminder_just_set:
        from datetime import datetime
        dt = datetime.fromtimestamp(reminder_just_set.trigger_at)
        system_parts.append(
            f"IMPORTANT: A reminder was just created: \"{reminder_just_set.message}\" "
            f"scheduled for {dt.strftime('%I:%M %p')}. Notifications were sent. "
            f"Briefly confirm this to the user."
        )

    msgs.append({"role": "system", "content": "\n\n".join(system_parts)})

    history = memory.get_recent_messages(conversation_id=conversation_id)
    msgs.extend(history)
    return msgs


# ------------------------------------------------------------------
# Conversation management routes
# ------------------------------------------------------------------

@app.get("/v1/conversations")
async def list_conversations():
    return JSONResponse({"conversations": memory.list_conversations()})


@app.post("/v1/conversations")
async def create_conversation():
    conv = memory.create_conversation()
    return JSONResponse(conv)


@app.get("/v1/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    messages = memory.get_conversation_messages(conv_id)
    return JSONResponse({"conversation_id": conv_id, "messages": messages})


@app.delete("/v1/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    ok = memory.delete_conversation(conv_id)
    if ok:
        return JSONResponse({"status": "deleted"})
    return JSONResponse({"status": "not_found"}, status_code=404)


@app.patch("/v1/conversations/{conv_id}")
async def rename_conversation(conv_id: str, req: RenameRequest):
    ok = memory.rename_conversation(conv_id, req.title)
    if ok:
        return JSONResponse({"status": "renamed", "title": req.title})
    return JSONResponse({"status": "not_found"}, status_code=404)


# ------------------------------------------------------------------
# Memory management routes
# ------------------------------------------------------------------

@app.get("/v1/memory")
async def get_memory():
    return JSONResponse({"facts": memory.list_facts()})


@app.delete("/v1/memory/{fact_id}")
async def delete_memory(fact_id: int):
    ok = memory.delete_fact(fact_id)
    if ok:
        return JSONResponse({"status": "deleted", "id": fact_id})
    return JSONResponse({"status": "not_found"}, status_code=404)


@app.post("/v1/clear")
async def clear_history():
    memory.clear_history()
    return JSONResponse({"status": "cleared"})


# ------------------------------------------------------------------
# Reminder management routes
# ------------------------------------------------------------------

@app.get("/v1/reminders")
async def list_reminders():
    return JSONResponse({"reminders": reminders.list_active()})


@app.get("/v1/reminders/all")
async def list_all_reminders():
    return JSONResponse({"reminders": reminders.list_all()})


@app.delete("/v1/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int):
    ok = reminders.delete_reminder(reminder_id)
    if ok:
        return JSONResponse({"status": "deleted", "id": reminder_id})
    return JSONResponse({"status": "not_found"}, status_code=404)


# ------------------------------------------------------------------
# WhatsApp webhook (Twilio) — uses full Thursday mode
# ------------------------------------------------------------------

# Dedicated conversation ID for WhatsApp — persists across messages
_WHATSAPP_CONV_ID = "whatsapp-main"


def _ensure_whatsapp_conversation() -> None:
    """Create the WhatsApp conversation if it doesn't exist yet."""
    convs = memory.list_conversations()
    if not any(c["id"] == _WHATSAPP_CONV_ID for c in convs):
        memory.create_conversation(title="WhatsApp", conv_id=_WHATSAPP_CONV_ID)


def _twiml(body: str) -> Response:
    """Wrap a text reply in Twilio TwiML XML."""
    safe = (
        body
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{safe}</Message>"
        "</Response>"
    )
    return Response(content=xml, media_type="application/xml")


@app.post("/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(""),
    From: str = Form(""),
    background_tasks: BackgroundTasks = None,
):
    """Receive a WhatsApp message via Twilio, run it through the full
    Thursday pipeline (personality + memory + reminders), and reply.

    Returns an empty TwiML response immediately so Twilio never times
    out.  The actual LLM reply is sent asynchronously via the Twilio
    REST API (supports multi-part messages for long / code responses).
    """
    sender = From.replace("whatsapp:", "")
    user_msg = Body.strip()

    if not user_msg:
        return _twiml("Send me a message and I'll respond!")

    log.info("── WhatsApp prompt from %s (%d chars): %s", sender, len(user_msg), user_msg[:80])

    # Kick off the heavy work in the background so Twilio gets an
    # immediate 200 and never hits its 15-second webhook timeout.
    background_tasks.add_task(_process_whatsapp_message, user_msg, sender)

    # Empty TwiML — the real reply comes via REST API
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


def _process_whatsapp_message(user_msg: str, sender: str) -> None:
    """Run the full Thursday pipeline for a WhatsApp message.

    Called as a FastAPI BackgroundTask so the webhook can return
    instantly.  The reply is delivered via the Twilio REST API.
    """
    from notifier import send_whatsapp_long, send_whatsapp

    t0 = _time.time()
    try:
        _ensure_whatsapp_conversation()

        # 1. Extract long-term facts
        memory.try_extract_fact(user_msg)

        # 2. Detect reminder intent
        reminder_result = try_parse_user_reminder(user_msg)
        reminder_created = None
        if reminder_result:
            time_expr, reminder_message = reminder_result
            trigger_at = parse_time_expression(time_expr)
            if trigger_at:
                reminder_created = reminders.add_reminder(
                    reminder_message, trigger_at, _WHATSAPP_CONV_ID
                )
                log.info("   ⏰ Reminder set: '%s' → fires in %.0fs", reminder_message, trigger_at - _time.time())
                send_reminder_set_notification(reminder_message, trigger_at)

        # 3. Save user message to memory
        memory.add_message("user", user_msg, _WHATSAPP_CONV_ID)

        # 4. Build augmented messages (personality + facts + history + reminders)
        augmented = _build_thursday_messages(
            _WHATSAPP_CONV_ID, reminder_just_set=reminder_created
        )

        # 5. Get blocking (non-streaming) response
        log.info("   Generating response...")
        reply = llama.blocking_chat(augmented, temperature=0.7, max_tokens=1024)

        # 6. Process any [REMIND:] tags in the reply
        _process_reminders(reply, _WHATSAPP_CONV_ID)
        clean_reply = strip_reminder_tags(reply)

        # 7. Save assistant reply to memory
        memory.add_message("assistant", clean_reply, _WHATSAPP_CONV_ID)

        elapsed = _time.time() - t0
        log.info(
            "   ✓ WhatsApp response done — %d chars, %.1fs",
            len(clean_reply), elapsed,
        )

        # 8. Send via Twilio REST API (auto-splits long messages)
        send_whatsapp_long(clean_reply)
        log.info("   ✓ Delivered to WhatsApp")

    except Exception as exc:
        log.error("   ✗ WhatsApp processing failed: %s", exc, exc_info=True)
        try:
            send_whatsapp("⚠️ Sorry, something went wrong. Try again in a moment.")
        except Exception:
            log.error("   ✗ Failed to send error message to WhatsApp")


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@app.get("/health")
async def health():
    llama_ok = llama.health_check()
    return JSONResponse({
        "proxy": "ok",
        "llama_server": "ok" if llama_ok else "unreachable",
    })


# ------------------------------------------------------------------
# Static files — serve the web UI
# ------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=os.path.join(
    os.path.dirname(__file__), "ui"
)), name="static")


@app.get("/")
async def serve_ui():
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "ui", "index.html"),
        media_type="text/html; charset=utf-8",
    )


# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=PROXY_HOST, port=PROXY_PORT, reload=False)
