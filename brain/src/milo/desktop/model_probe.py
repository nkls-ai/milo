"""Looks at an OpenAI-style API for Setup's Connections & models: is a local server running, which models does it
have, does a tiny reply come back. Blocking calls with short timeouts; SetupBackend runs them off the UI thread.

Keys pass through as arguments and go only into the Authorization header: never logged, never in an error.
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from milo.adapters.harness import openai_presets
from milo.adapters.harness.openai_compat import OpenAICompatModel, unreachable
from milo.core.types import HarnessError

DETECT_TIMEOUT_S = 0.8
LIST_TIMEOUT_S = 4.0
TEST_TIMEOUT_S = 20.0
TEST_PROMPT = "Reply with just the word OK."


class ProbeError(Exception):
    """Plain words for the user, with the fix where there is one."""


def _get(url: str, key: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "milo"})
    if key:
        request.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - http(s) only, checked
            return json.loads(response.read(2_000_000).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        host = urlsplit(url).netloc
        if e.code in (401, 403):
            raise ProbeError(f"{host} turned down the API key. Check it and try again.") from None
        raise ProbeError(f"{host} answered {e.code} {e.reason}.") from None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise ProbeError(unreachable(urlsplit(url).netloc)) from e
    except ValueError:
        raise ProbeError(f"{urlsplit(url).netloc} didn't answer like an OpenAI-style API.") from None


def _checked(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        raise ProbeError("Enter an http:// or https:// API base URL.")
    return url


def list_models(base_url: str, key: str = "", timeout: float = LIST_TIMEOUT_S) -> list[str]:
    """The model names the server offers: `<base>/models`, or Ollama's own `/api/tags`. Sorted, no duplicates."""
    url = _checked(base_url)
    try:
        data = _get(url + "/models", key, timeout)
        names = [str(m.get("id")) for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
    except ProbeError:
        if openai_presets.matching(url).id != "ollama":
            raise
        names = []
    if not names and openai_presets.matching(url).id == "ollama":
        parts = urlsplit(url)
        data = _get(f"{parts.scheme}://{parts.netloc}/api/tags", "", timeout)
        names = [str(m.get("name")) for m in data.get("models", []) if isinstance(m, dict) and m.get("name")]
    return sorted(set(names), key=str.lower)


def detect(timeout: float = DETECT_TIMEOUT_S) -> list[dict]:
    """The local servers that answer now, each {id, label, baseUrl, models}."""
    found = []
    for preset in openai_presets.PRESETS:
        if not preset.local:
            continue
        try:
            models = list_models(preset.base_url, timeout=timeout)
        except ProbeError:
            continue
        found.append({"id": preset.id, "label": preset.label, "baseUrl": preset.base_url, "models": models})
    return found


def try_reply(base_url: str, model: str, *, key: str = "", key_file: Path | None = None,
              timeout: float = TEST_TIMEOUT_S) -> dict:
    """One tiny reply through the very adapter Milo talks with: {ok, ms (to the first word), reply, text}."""
    try:
        url = _checked(base_url)
    except ProbeError as e:
        return {"ok": False, "ms": 0, "reply": "", "text": str(e)}
    if not model.strip():
        return {"ok": False, "ms": 0, "reply": "", "text": "Choose a model first."}
    chat = OpenAICompatModel(url, model.strip(), key=key, key_file=None if key else key_file, max_tokens=16,
                             temperature=0, timeout_s=timeout, cache_key=False, images=False)

    async def ask() -> tuple[float, str]:
        await chat.start("")
        started, first, parts = time.monotonic(), None, []
        async for delta in chat.turn(TEST_PROMPT):
            first = first or time.monotonic()
            parts.append(delta)
        return ((first or time.monotonic()) - started) * 1000, "".join(parts).strip()

    try:
        ms, reply = asyncio.run(ask())
    except HarnessError as e:
        return {"ok": False, "ms": 0, "reply": "", "text": e.said or str(e)}
    if not reply:
        return {"ok": False, "ms": round(ms), "reply": "", "text": "The model answered with nothing. Try another one."}
    return {"ok": True, "ms": round(ms), "reply": reply[:80], "text": f"Answered in {round(ms)} ms: “{reply[:40]}”"}
