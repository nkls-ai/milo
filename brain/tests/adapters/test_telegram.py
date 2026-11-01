"""The Telegram channel against a local fake of the Bot API: no real bot, no real token, nothing leaves the Mac."""

import asyncio
import json
import os
import stat
import threading
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from milo.adapters.channel.telegram import TelegramChannel, TelegramOptions, inbound, read_token, split
from milo.core.registry import ConfigError
from milo.core.types import ChannelError, Inbound

TOKEN = "123456789:AAEexampleexampleexampleexample_-xyz"


class FakeBotApi:
    """Answers /bot<TOKEN>/<method> like Telegram. `replies[method]` is a result or a list of them (one per
    call); an int is an error code. Every call is kept in `calls` as (method, body)."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.replies: dict[str, object] = {"getMe": {"id": 1, "is_bot": True, "username": "milo_test_bot"}}
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                prefix, _, method = self.path.rpartition("/")
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                kind = self.headers.get("Content-Type", "")
                if kind.startswith("multipart/"):
                    message = BytesParser(policy=HTTP).parsebytes(
                        f"Content-Type: {kind}\r\n\r\n".encode() + body)
                    parsed = {part.get_param("name", header="content-disposition"):
                              (part.get_filename(), part.get_content()) if part.get_filename()
                              else part.get_content() for part in message.iter_parts()}
                else:
                    parsed = json.loads(body or b"{}")
                api.calls.append((method, parsed))
                if prefix != f"/bot{TOKEN}":
                    return self.answer(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
                reply = api.replies.get(method, True)
                if isinstance(reply, list):
                    reply = reply.pop(0) if len(reply) > 1 else reply[0]
                if isinstance(reply, int) and not isinstance(reply, bool):
                    extra = {"parameters": {"retry_after": 7}} if reply == 429 else {}
                    return self.answer(reply, {"ok": False, "error_code": reply, "description": "nope", **extra})
                self.answer(200, {"ok": True, "result": reply})

            def answer(self, code, data):
                body = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.root = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def methods(self) -> list[str]:
        return [m for m, _ in self.calls]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def api():
    fake = FakeBotApi()
    yield fake
    fake.close()


@pytest.fixture
def token_file(tmp_path):
    path = tmp_path / "secrets" / "telegram-token"
    path.parent.mkdir()
    path.write_text(TOKEN + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def channel(api, token_file, tmp_path, **kw) -> TelegramChannel:
    return TelegramChannel(token_file, tmp_path / "state" / "telegram.json", api_root=api.root, poll_s=1, **kw)


def message(update_id: int, text: str = "hi", chat_id: int = 42, user_id: int = 42, **extra) -> dict:
    return {"update_id": update_id, "message": {
        "message_id": update_id, "date": 0, "text": text, "chat": {"id": chat_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Niklas", "username": "niklas"}, **extra}}


# ---- the token


def test_the_token_file_must_be_private_plain_and_hold_a_token(tmp_path, token_file):
    assert read_token(token_file) == TOKEN
    with pytest.raises(ChannelError, match="There's no Telegram bot token yet"):
        read_token(tmp_path / "missing")
    os.chmod(token_file, 0o644)
    assert read_token(token_file) == TOKEN, "a token only others could read too is made private, not refused"
    from milo import system
    assert system.owned_by_me(token_file) and not system.open_to_others(token_file)
    link = tmp_path / "link"
    link.symlink_to(token_file)
    with pytest.raises(ChannelError, match="plain file"):
        read_token(link)
    token_file.write_text("my password", encoding="utf-8")
    with pytest.raises(ChannelError, match="doesn't hold a bot token") as e:
        read_token(token_file)
    assert "my password" not in str(e.value)


def test_options_want_https_except_for_a_local_test_server():
    TelegramOptions(api_root="http://127.0.0.1:8080")
    with pytest.raises(ConfigError, match="https"):
        TelegramOptions(api_root="http://api.telegram.org")
    with pytest.raises(ConfigError, match="poll_s"):
        TelegramOptions(poll_s=0)


# ---- talking to the Bot API


def test_start_checks_the_token_with_get_me(api, token_file, tmp_path):
    ch = channel(api, token_file, tmp_path)
    asyncio.run(ch.start())
    assert ch.username == "milo_test_bot" and api.methods() == ["getMe"]


def test_a_refused_token_never_shows_in_the_error_or_the_log(api, tmp_path, caplog):
    path = tmp_path / "token"
    path.write_text("987654321:BBEwrongwrongwrongwrongwrongwrong123", encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(ChannelError, match="doesn't accept the bot token") as e:
        asyncio.run(channel(api, path, tmp_path).start())
    assert "BBEwrong" not in str(e.value) and "BBEwrong" not in caplog.text


@pytest.mark.parametrize("code, words", [(409, "Another program reads this bot"), (429, "wait 7 s"),
                                         (500, "refused getUpdates")])
def test_api_errors_are_plain_words(api, token_file, tmp_path, code, words):
    ch = channel(api, token_file, tmp_path)
    asyncio.run(ch.start())
    api.replies["getUpdates"] = code
    with pytest.raises(ChannelError, match=words):
        asyncio.run(ch.receive())


def test_no_network_is_a_channel_error(token_file, tmp_path):
    ch = TelegramChannel(token_file, tmp_path / "t.json", api_root="http://127.0.0.1:9", poll_s=1)
    with pytest.raises(ChannelError, match="Can't reach Telegram"):
        asyncio.run(ch.start())


def test_receive_long_polls_and_never_sees_an_update_twice(api, token_file, tmp_path):
    api.replies["getUpdates"] = [[message(7, "hello"), {"update_id": 8, "edited_message": {}}], []]
    ch = channel(api, token_file, tmp_path)

    async def go():
        await ch.start()
        return await ch.receive(), await ch.receive()

    first, second = asyncio.run(go())
    assert first == [Inbound(chat="42", sender="42", text="hello", name="Niklas (@niklas)")] and second == []
    polls = [body for method, body in api.calls if method == "getUpdates"]
    assert polls[0] == {"offset": 0, "timeout": 1, "allowed_updates": ["message", "callback_query"]}
    assert polls[1]["offset"] == 9
    again = channel(api, token_file, tmp_path)  # after a restart
    asyncio.run(again.start())
    asyncio.run(again.receive())
    assert [body for method, body in api.calls if method == "getUpdates"][-1]["offset"] == 9


def test_updates_become_inbound_with_outside_text_marked():
    forwarded = message(1, "pay this", forward_origin={"type": "user", "date": 0})
    quoted = message(2, "what's this?", quote={"text": "click here", "position": 0})
    external = message(3, "and this?", external_reply={"origin": {"type": "hidden_user", "date": 0}})
    group = message(4, "hi all", chat_id=-100)
    group["message"]["chat"]["type"] = "group"
    photo = message(5, "", photo=[{"file_id": "x"}], caption="look")
    bot = message(6)
    bot["message"]["from"]["is_bot"] = True
    button = {"update_id": 7, "callback_query": {"id": "cb1", "data": "yes:abc", "from": {"id": 42},
                                                 "message": {"chat": {"id": 42, "type": "private"}}}}
    assert inbound(forwarded).forwarded and not inbound(message(9)).forwarded
    assert inbound(quoted).quoted == "click here"
    assert inbound(external).quoted == "(a message from another chat)"
    assert not inbound(group).private and not inbound(bot).private
    assert inbound(photo).attachments == 1 and inbound(photo).text == "look"
    assert inbound(button) == Inbound(chat="42", sender="42", answer="yes:abc", ref="cb1")
    assert inbound({"update_id": 8, "channel_post": {}}) is None


def test_sending_text_questions_and_typing(api, token_file, tmp_path):
    ch = channel(api, token_file, tmp_path)

    async def go():
        await ch.start()
        await ch.send("42", "Your standup is at 10.")
        await ch.ask("42", "q1", "Send the draft to Anna?")
        await ch.typing("42")
        await ch.acknowledge(Inbound(chat="42", sender="42", answer="yes:q1", ref="cb1"), "Yes")

    asyncio.run(go())
    sent = dict((m, b) for m, b in api.calls[1:])
    assert sent["sendMessage"]["reply_markup"] == {"inline_keyboard": [[
        {"text": "Yes", "callback_data": "yes:q1"}, {"text": "No", "callback_data": "no:q1"}]]}
    first = api.calls[1][1]
    assert first == {"chat_id": "42", "text": "Your standup is at 10.", "link_preview_options": {"is_disabled": True}}
    assert "parse_mode" not in first, "plain text: no markup from the model or the user reaches Telegram"
    assert sent["sendChatAction"] == {"chat_id": "42", "action": "typing"}
    assert sent["answerCallbackQuery"] == {"callback_query_id": "cb1", "text": "Yes"}


def test_long_replies_go_out_in_parts():
    text = ("word " * 900).strip() + "\n\n" + "x" * 100
    parts = split(text, limit=4096)
    assert all(len(p) <= 4096 for p in parts) and len(parts) == 2
    assert " ".join(parts).replace("\n\n", " ").split() == text.replace("\n\n", " ").split()
    assert split("") == []


def test_a_file_goes_as_a_document_with_its_name_and_caption(api, token_file, tmp_path):
    ch = channel(api, token_file, tmp_path)

    async def go():
        await ch.start()
        await ch.send_file("42", 'Q3 "review".key', b"\x00deck bytes", "today's slides")

    asyncio.run(go())
    method, body = api.calls[-1]
    assert method == "sendDocument"
    assert body["chat_id"] == "42" and body["caption"] == "today's slides"
    assert body["document"] == ("Q3 _review_.key", b"\x00deck bytes")
    with pytest.raises(ChannelError, match="too big"):
        asyncio.run(ch.send_file("42", "big", b"x" * (50 * 1024 * 1024 + 1)))


def test_end_to_end_pairing_and_a_conversation_over_the_fake_bot_api(api, token_file, tmp_path):
    """The real channel and the real MessageService: a stranger can't get in, the owner pairs with the code
    from the Mac and gets an answer, all through HTTP like the real Bot API."""
    from milo.services.pairing import Pairing
    from tests.fakes import FakeLiveModel, MemoryRemoteState
    from tests.services.stack import Stack, settle

    s = Stack(model=FakeLiveModel(["[happy] Your standup is at 10."]), remote=MemoryRemoteState())
    ch = channel(api, token_file, tmp_path)
    from milo.services.messages import MessageService

    messages = MessageService(ch, s.live_talk, s.approvals, s.remote, s.speaker, s.ui, s.context, s.clock,
                              wait_for_mac_s=0.01, typing_every_s=0.05)
    messages.pairing = Pairing(s.clock, code=lambda: "246810")
    api.replies["getUpdates"] = [[message(1, "/start")], [message(2, "246 810")],
                                 [message(3, "let me in", chat_id=666, user_id=666)],
                                 [message(4, "when is my standup?")], []]

    async def go():
        task = asyncio.create_task(messages.run())
        for _ in range(100):
            await asyncio.sleep(0.02)
            await settle()
            if sum(1 for m, b in api.calls if m == "sendMessage") >= 3:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(go())
    sent = [(b["chat_id"], b["text"]) for m, b in api.calls if m == "sendMessage"]
    assert sent[0][0] == "42" and "send me the 6-digit code" in sent[0][1]
    assert sent[1][0] == "42" and sent[1][1].startswith("Connected!")
    assert sent[2] == ("42", "Your standup is at 10.")
    assert all(chat != "666" for chat, _ in sent), "the stranger got nothing"
    assert s.remote.data["owner"]["chat"] == "42"
    assert "sendChatAction" in api.methods()
