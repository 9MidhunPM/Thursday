"""
HTTP client for llama-server.

Provides both streaming (generator-based) and blocking calls.
Used by the FastAPI proxy for both raw and Thursday modes.

All JSON SSE chunks are re-serialised with ensure_ascii=True so
that emoji / non-ASCII content becomes \\uXXXX escapes.  This
guarantees the stream is pure ASCII and cannot be garbled by any
intermediate encoding layer (requests, uvicorn, or the browser).
"""

import json
from typing import Generator

import requests

from config import LLAMA_CHAT_ENDPOINT, MAX_TOKENS, MODEL_NAME, TEMPERATURE, TOP_P


def _reencode_sse_line(raw_line: bytes) -> str:
    """Take a raw SSE bytes line from llama-server and return a
    pure-ASCII SSE string (with \\n\\n appended).

    If the line is a JSON data payload, re-serialise it with
    ensure_ascii=True so every non-ASCII codepoint is escaped.
    Non-data lines are passed through as-is.
    """
    text = raw_line.decode("utf-8", errors="replace")
    if text.startswith("data: "):
        payload = text[6:].strip()
        if payload and payload != "[DONE]":
            try:
                obj = json.loads(payload)
                payload = json.dumps(obj, ensure_ascii=True)
                return f"data: {payload}\n\n"
            except (json.JSONDecodeError, ValueError):
                pass
    return f"{text}\n\n"


class LlamaClient:
    """Thin wrapper around llama-server /v1/chat/completions."""

    def __init__(
        self,
        endpoint: str = LLAMA_CHAT_ENDPOINT,
        timeout: float = 120.0,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def health_check(self) -> bool:
        try:
            r = self._session.get(
                self._endpoint.replace("/v1/chat/completions", "/health"),
                timeout=5,
            )
            return r.status_code == 200
        except requests.ConnectionError:
            return False

    # ----------------------------------------------------------------
    # Raw mode — proxy SSE with ASCII-safe re-encoding
    # ----------------------------------------------------------------

    def stream_chat(
        self,
        messages: list[dict],
        temperature: float = TEMPERATURE,
        max_tokens: int = MAX_TOKENS,
    ) -> Generator[str, None, None]:
        """Yield SSE strings (pure-ASCII) from llama-server."""
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": TOP_P,
            "stream": True,
        }

        try:
            resp = self._session.post(
                self._endpoint,
                json=payload,
                stream=True,
                timeout=self._timeout,
            )
            resp.raise_for_status()

            for raw_line in resp.iter_lines():
                if not raw_line:
                    yield "\n"
                    continue
                sse = _reencode_sse_line(raw_line)
                yield sse
                if raw_line.startswith(b"data: ") and raw_line[6:].strip() == b"[DONE]":
                    break

        except requests.ConnectionError:
            yield f"data: {json.dumps(_make_error_chunk('Cannot reach llama-server. Is it running?'))}\n\n"
            yield "data: [DONE]\n\n"
        except requests.Timeout:
            yield f"data: {json.dumps(_make_error_chunk('Request timed out.'))}\n\n"
            yield "data: [DONE]\n\n"
        except requests.HTTPError as e:
            yield f"data: {json.dumps(_make_error_chunk(f'HTTP {e.response.status_code}'))}\n\n"
            yield "data: [DONE]\n\n"

    # ----------------------------------------------------------------
    # Thursday mode — proxy SSE + collect tokens for memory
    # ----------------------------------------------------------------

    def stream_chat_and_collect(
        self,
        messages: list[dict],
        temperature: float = TEMPERATURE,
        max_tokens: int = MAX_TOKENS,
    ) -> Generator[tuple[str, list[str]], None, None]:
        """Yield (sse_string, collected_tokens) tuples.
        SSE data is pure ASCII (ensure_ascii).
        Tokens are full-Unicode strings kept for memory storage.
        """
        collected: list[str] = []
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": TOP_P,
            "stream": True,
        }

        try:
            resp = self._session.post(
                self._endpoint,
                json=payload,
                stream=True,
                timeout=self._timeout,
            )
            resp.raise_for_status()

            for raw_line in resp.iter_lines():
                if not raw_line:
                    yield "\n", collected
                    continue

                # Parse token for collection (full Unicode)
                if raw_line.startswith(b"data: "):
                    data_bytes = raw_line[6:]
                    if data_bytes.strip() == b"[DONE]":
                        yield "data: [DONE]\n\n", collected
                        break
                    try:
                        chunk = json.loads(data_bytes)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            collected.append(token)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass

                # Yield the ASCII-safe SSE line
                yield _reencode_sse_line(raw_line), collected

        except requests.ConnectionError:
            yield f"data: {json.dumps(_make_error_chunk('Cannot reach llama-server.'))}\n\n", collected
            yield "data: [DONE]\n\n", collected
        except requests.Timeout:
            yield f"data: {json.dumps(_make_error_chunk('Request timed out.'))}\n\n", collected
            yield "data: [DONE]\n\n", collected

    def close(self) -> None:
        self._session.close()


def _make_error_chunk(message: str) -> dict:
    """Build a fake SSE chunk carrying an error message."""
    return {
        "choices": [
            {
                "index": 0,
                "delta": {"content": f"[Error: {message}]"},
                "finish_reason": "stop",
            }
        ]
    }
