"""
HTTP client for llama-server's OpenAI-compatible API.

Supports both streaming and non-streaming responses.
Uses raw `requests` — no SDK dependencies.

Extension point: swap this for an async client (httpx / aiohttp)
if you later move to an async architecture.
"""

import json
import sys
from typing import Generator

import requests

from config import CHAT_ENDPOINT, MAX_TOKENS, MODEL_NAME, TEMPERATURE, TOP_P


class LlamaClient:
    """Thin wrapper around llama-server /v1/chat/completions."""

    def __init__(
        self,
        endpoint: str = CHAT_ENDPOINT,
        timeout: float = 120.0,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout
        self._session = requests.Session()
        # Keep-alive for lower latency on repeated calls.
        self._session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        *,
        stream: bool = True,
        temperature: float = TEMPERATURE,
        max_tokens: int = MAX_TOKENS,
    ) -> str:
        """
        Send a chat completion request.

        If `stream=True`, tokens are printed to stdout as they arrive
        and the full response text is returned at the end.
        """
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": TOP_P,
            "stream": stream,
        }

        if stream:
            return self._stream_response(payload)
        return self._blocking_response(payload)

    def health_check(self) -> bool:
        """Quick connectivity test against the server."""
        try:
            r = self._session.get(
                self._endpoint.replace("/v1/chat/completions", "/health"),
                timeout=5,
            )
            return r.status_code == 200
        except requests.ConnectionError:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _stream_response(self, payload: dict) -> str:
        """Stream SSE tokens, print live, return full text."""
        collected: list[str] = []
        try:
            resp = self._session.post(
                self._endpoint,
                json=payload,
                stream=True,
                timeout=self._timeout,
            )
            resp.raise_for_status()

            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            sys.stdout.write(token)
                            sys.stdout.flush()
                            collected.append(token)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue  # skip malformed chunks

            sys.stdout.write("\n")
            sys.stdout.flush()

        except requests.ConnectionError:
            return "[Error: Cannot reach llama-server. Is it running?]"
        except requests.Timeout:
            return "[Error: Request timed out.]"
        except requests.HTTPError as e:
            return f"[Error: HTTP {e.response.status_code}]"

        return "".join(collected)

    def _blocking_response(self, payload: dict) -> str:
        """Non-streaming single response."""
        try:
            resp = self._session.post(
                self._endpoint, json=payload, timeout=self._timeout
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.ConnectionError:
            return "[Error: Cannot reach llama-server. Is it running?]"
        except requests.Timeout:
            return "[Error: Request timed out.]"
        except requests.HTTPError as e:
            return f"[Error: HTTP {e.response.status_code}]"
        except (KeyError, IndexError):
            return "[Error: Unexpected response format.]"

    def close(self) -> None:
        self._session.close()
