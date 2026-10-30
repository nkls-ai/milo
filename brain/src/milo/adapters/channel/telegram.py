"""Telegram through the Bot API: HTTPS long polling, so nothing on the Mac listens for the network.

Standard library only (urllib on a daemon thread per request): seven Bot API methods don't justify a
framework, see docs/research/messaging.md. The token is read from a file only the user can read and never
appears in a log line or an error message. Message text is never logged either.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.registry import CHANNELS, AdapterContext, ConfigError, options_from
from milo.core.types import ChannelError, Inbound

log = logging.getLogger("milo.telegram")

TOKEN = re.compile(r"\d{5,16}:[A-Za-z0-9_-]{30,64}")
MAX_TEXT = 4096
"""Telegram's limit per message. Longer replies go out in parts."""
MAX_FILE_BYTES = 50 * 1024 * 1024
"""What a bot may upload."""
UPDATES = ("message", "callback_query")
_ATTACHMENTS = ("photo", "document", "voice", "audio", "video", "video_note", "sticker", "animation", "contact",
                "location", "venue", "poll")
_FORWARD_KEYS = ("forward_origin", "forward_from", "forward_from_chat", "forward_sender_name", "forward_date")
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


@dataclass(frozen=True)
class TelegramOptions:
    token_file: str = "secrets/telegram-token"
    """The bot token from @BotFather, alone in a file only you can read (chmod 600). Relative to ~/Milo."""
    api_root: str = "https://api.telegram.org"
    poll_s: int = 25
    """How long one long poll waits for a message before asking again."""

    def __post_init__(self):
        if not self.token_file:
            raise ConfigError("[messages.telegram] token_file must name a file")
        if isinstance(self.poll_s, bool) or not isinstance(self.poll_s, int) or not 1 <= self.poll_s <= 50:
            raise ConfigError("[messages.telegram] poll_s must be a whole number from 1 to 50")
        url = urllib.parse.urlsplit(self.api_root)
        if url.scheme != "https" and not (url.scheme == "http" and url.hostname in _LOCAL_HOSTS):
            raise ConfigError("[messages.telegram] api_root must be an https:// address")


def read_token(path: Path) -> str:
    """The bot token, if the file is the user's own, a plain file, and readable by nobody else."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise ChannelError(f"There's no Telegram bot token yet. Put the token from @BotFather in {path} "
                           f"(see docs/setup/messages.md).") from None
    except OSError as e:
        raise ChannelError(f"Can't read the Telegram token file {path}: {e.strerror}.") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ChannelError(f"The Telegram token file {path} must be a plain file, not a link or a folder.")
    if info.st_uid != os.getuid():
        raise ChannelError(f"The Telegram token file {path} belongs to another user.")
    if info.st_mode & 0o077:
        raise ChannelError(f"Others on this Mac can read the Telegram token. Run: chmod 600 {path}")
    token = path.read_text(encoding="utf-8").strip()
    if not TOKEN.fullmatch(token):
        raise ChannelError(f"{path} doesn't hold a bot token. It looks like 123456789:AAE… and comes from "
                           f"@BotFather in Telegram.")
    return token


class TelegramChannel:
    """The Channel port on a Telegram bot. The last update id is kept in `state_path`, so a message is
    never answered twice after a restart."""

    name = "telegram"
    label = "Telegram"

    def __init__(self, token_path: Path, state_path: Path, *, api_root: str = "https://api.telegram.org",
                 poll_s: int = 25):
        self._token_path = token_path
        self._state_path = state_path
        self._api_root = api_root.rstrip("/")
        self._poll_s = poll_s
        self._token: str | None = None
        self._offset = _load_offset(state_path)
        self.username = ""
        """The bot's @name, once started."""

    async def start(self) -> None:
        self._token = read_token(self._token_path)
        me = await self._call("getMe")
        self.username = str(me.get("username") or "")
        log.info("telegram bot ready (@%s)", self.username)

    async def receive(self) -> list[Inbound]:
        updates = await self._call("getUpdates", {"offset": self._offset, "timeout": self._poll_s,
                                                  "allowed_updates": list(UPDATES)}, timeout_s=self._poll_s + 15)
        if not isinstance(updates, list) or not updates:
            return []
        ids = [u["update_id"] for u in updates if isinstance(u, dict) and isinstance(u.get("update_id"), int)]
        if ids:
            self._offset = max(ids) + 1
            _save_offset(self._state_path, self._offset)
        return [i for i in (inbound(u) for u in updates if isinstance(u, dict)) if i is not None]

    async def send(self, chat: str, text: str) -> None:
        for part in split(text):
            await self._call("sendMessage", {"chat_id": chat, "text": part,
                                              "link_preview_options": {"is_disabled": True}})

    async def ask(self, chat: str, id: str, question: str) -> None:
        buttons = [[{"text": "Yes", "callback_data": f"yes:{id}"}, {"text": "No", "callback_data": f"no:{id}"}]]
        await self._call("sendMessage", {"chat_id": chat, "text": question[:MAX_TEXT],
                                          "reply_markup": {"inline_keyboard": buttons},
                                          "link_preview_options": {"is_disabled": True}})

    async def typing(self, chat: str) -> None:
        try:
            await self._call("sendChatAction", {"chat_id": chat, "action": "typing"}, timeout_s=10)
        except ChannelError:
            pass

    async def send_file(self, chat: str, name: str, data: bytes, caption: str = "") -> None:
        if len(data) > MAX_FILE_BYTES:
            raise ChannelError(f"{name} is too big for Telegram (bots may send up to 50 MB).")
        fields = {"chat_id": chat, **({"caption": caption[:1024]} if caption else {})}
        await self._call("sendDocument", fields, file=("document", name, data), timeout_s=300)

    async def acknowledge(self, inbound: Inbound, text: str = "") -> None:
        if not inbound.ref:
            return
        try:
            await self._call("answerCallbackQuery", {"callback_query_id": inbound.ref, "text": text[:200]},
                             timeout_s=10)
        except ChannelError:
            pass

    async def close(self) -> None:
        pass  # a poll still running ends on its own within poll_s; its thread doesn't keep the brain alive

    # ---- the Bot API

    async def _call(self, method: str, params: dict | None = None, *, file: tuple[str, str, bytes] | None = None,
                    timeout_s: float = 30) -> Any:
        if self._token is None:
            raise ChannelError("Telegram isn't started.")
        url = f"{self._api_root}/bot{self._token}/{method}"
        if file is None:
            body, kind = json.dumps(params or {}).encode(), "application/json"
        else:
            body, kind = _multipart(params or {}, *file)
        try:
            data = await _in_thread(_post, url, body, kind, timeout_s)
        except ChannelError as e:
            raise ChannelError(str(e).replace(self._token, "<token>")) from None
        if data.get("ok"):
            return data.get("result")
        code = data.get("error_code")
        log.warning("telegram %s failed: %s", method, code)
        if code == 401 or code == 404:
            raise ChannelError("Telegram doesn't accept the bot token. Make a new one with @BotFather and put "
                               "it in the token file.")
        if code == 409:
            raise ChannelError("Another program reads this bot's messages, or the bot has a webhook. Stop the "
                               "other program, or make a new bot for Milo.")
        if code == 429:
            retry = (data.get("parameters") or {}).get("retry_after")
            raise ChannelError(f"Telegram asks Milo to slow down (wait {retry} s).")
        if code == 403:
            raise ChannelError("The chat blocked the bot.")
        raise ChannelError(f"Telegram refused {method} ({code}).")


def inbound(update: dict) -> Inbound | None:
    """One getUpdates entry as an Inbound. None for kinds Milo doesn't handle (edits, channel posts)."""
    query = update.get("callback_query")
    if isinstance(query, dict):
        message = query.get("message") or {}
        chat = message.get("chat") or {}
        sender = query.get("from") or {}
        return Inbound(chat=_id(chat), sender=_id(sender), name=_name(sender), private=chat.get("type") == "private",
                       answer=str(query.get("data") or "")[:64], ref=str(query.get("id") or ""))
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    text = message.get("text") or message.get("caption") or ""
    quote = message.get("quote") or {}
    quoted = str(quote.get("text") or "") if isinstance(quote, dict) else ""
    if not quoted and isinstance(message.get("external_reply"), dict):
        quoted = "(a message from another chat)"
    return Inbound(chat=_id(chat), sender=_id(sender), text=str(text), name=_name(sender),
                   private=chat.get("type") == "private" and not sender.get("is_bot", False),
                   forwarded=any(k in message for k in _FORWARD_KEYS), quoted=quoted,
                   attachments=sum(1 for k in _ATTACHMENTS if k in message))


def split(text: str, limit: int = MAX_TEXT) -> list[str]:
    """Text in parts Telegram accepts, cut at paragraph or line ends where possible."""
    text = text.strip()
    parts: list[str] = []
    while len(text) > limit:
        cut = max(text.rfind("\n\n", 0, limit), text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        cut = cut if cut > limit // 2 else limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return [*parts, text] if text else parts


def _id(entity: object) -> str:
    value = entity.get("id") if isinstance(entity, dict) else None
    return str(value) if isinstance(value, int) else ""


def _name(user: dict) -> str:
    name = " ".join(str(user.get(k) or "") for k in ("first_name", "last_name")).strip()
    handle = user.get("username")
    return (f"{name} (@{handle})" if handle else name)[:80]


def _post(url: str, body: bytes, kind: str, timeout_s: float) -> dict:
    request = urllib.request.Request(url, data=body, headers={"Content-Type": kind}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:  # the Bot API answers errors with a JSON body
        try:
            return json.loads(e.read())
        except ValueError:
            raise ChannelError(f"Telegram answered with an error ({e.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ChannelError(f"Can't reach Telegram ({type(reason).__name__}).") from None
    except ValueError:
        raise ChannelError("Telegram sent something that isn't JSON.") from None


async def _in_thread(fn, *args):
    """Run blocking `fn` on a daemon thread: a long poll still waiting when the brain stops must not hold up
    its exit, which the default executor's threads would."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def settle(result, error) -> None:
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def run() -> None:
        try:
            result, error = fn(*args), None
        except BaseException as e:  # noqa: BLE001 - handed to the waiting coroutine
            result, error = None, e
        try:
            loop.call_soon_threadsafe(settle, result, error)
        except RuntimeError:
            pass  # the loop is gone: the brain is stopping

    threading.Thread(target=run, name="telegram", daemon=True).start()
    return await future


def _multipart(fields: dict, field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    safe_name = re.sub(r'["\r\n\\]', "_", filename) or "file"
    out = bytearray()
    for key, value in fields.items():
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode()
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{safe_name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode()
    out += data + f"\r\n--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _load_offset(path: Path) -> int:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("offset", 0)
    except (OSError, ValueError, AttributeError):
        return 0
    return value if isinstance(value, int) and value >= 0 else 0


def _save_offset(path: Path, offset: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"offset": offset}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        log.exception("could not save the telegram offset")


@CHANNELS.register("telegram")
def _telegram(options: Mapping[str, Any], ctx: AdapterContext) -> TelegramChannel:
    o = options_from(TelegramOptions, options, "messages.telegram")
    token = Path(o.token_file).expanduser()
    return TelegramChannel(token if token.is_absolute() else ctx.home / token, ctx.state_dir / "telegram.json",
                           api_root=o.api_root, poll_s=o.poll_s)
