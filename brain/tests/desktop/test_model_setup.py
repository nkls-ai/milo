"""Plug in any model: presets, finding a local server, listing its models, Test, and saving a pasted key alone in
~/Milo/secrets, against a fake OpenAI-style server on a thread. Never the user's real Milo folder."""
import asyncio
import logging
import tomllib

import pytest

from milo.adapters.harness import openai_presets
from milo.adapters.harness.openai_compat import OpenAICompatModel
from milo.adapters.platform import WINDOWS
from milo.config_file import TomlConfigFile
from milo.core.secrets import SecretError, write_secret
from milo.core.types import HarnessError
from milo.desktop import model_probe
from milo.desktop.providers import CliStatus, ProviderSelection, ProviderSetup

from .fake_openai import FakeOpenAI, dead_url

CONFIG = '# my settings\n[chat]\nuse = "claude_live"   # talking\n[harness]\nuse = "claude"\n'


def setup(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG, encoding="utf-8")
    return path, ProviderSetup(TomlConfigFile(path, WINDOWS), detector=lambda name, *_: CliStatus(True))


# ---- presets

def test_presets_are_one_table_with_the_local_servers_first():
    ids = [p.id for p in openai_presets.PRESETS]
    assert ids == ["ollama", "lmstudio", "openai", "openrouter", "groq", "custom"]
    assert openai_presets.by_id("ollama").base_url == "http://localhost:11434/v1" and not openai_presets.by_id("ollama").key_ref
    assert openai_presets.by_id("lmstudio").base_url == "http://localhost:1234/v1"
    assert all(p.key_ref for p in openai_presets.PRESETS if not p.local and p.id != "custom")
    assert openai_presets.matching("http://127.0.0.1:11434/v1/").id == "ollama"
    assert openai_presets.matching("https://openrouter.ai/api/v1").id == "openrouter"
    assert openai_presets.matching("http://example.com:8000/v1").id == "custom"


# ---- listing and finding

def test_lists_the_models_of_an_openai_style_server():
    with FakeOpenAI(models=["zeta", "Alpha", "beta"]) as server:
        assert model_probe.list_models(server.url) == ["Alpha", "beta", "zeta"]


def test_a_key_goes_in_the_header_and_a_wrong_one_is_said_plainly():
    with FakeOpenAI(key="sk-right") as server:
        assert model_probe.list_models(server.url, "sk-right") == ["llama3.2:3b", "qwen2.5:7b"]
        with pytest.raises(model_probe.ProbeError, match="turned down the API key") as error:
            model_probe.list_models(server.url, "sk-wrong")
        assert "sk-wrong" not in str(error.value)


def test_ollama_without_v1_models_falls_back_to_its_tags(monkeypatch):
    monkeypatch.setattr(openai_presets, "matching", lambda url: openai_presets.by_id("ollama"))
    with FakeOpenAI(models=["gemma3:4b"], tags=True) as server:
        assert model_probe.list_models(server.url) == ["gemma3:4b"]


def test_nothing_listening_is_said_plainly():
    with pytest.raises(model_probe.ProbeError, match="can't reach"):
        model_probe.list_models(dead_url(), timeout=1)
    with pytest.raises(model_probe.ProbeError, match="http"):
        model_probe.list_models("localhost:11434")


def test_detect_finds_only_the_local_servers_that_answer(monkeypatch):
    with FakeOpenAI(models=["llama3.2:3b"]) as server:
        monkeypatch.setattr(openai_presets, "PRESETS", (
            openai_presets.Preset("ollama", "Ollama", server.url, "", True),
            openai_presets.Preset("lmstudio", "LM Studio", dead_url(), "", True),
            openai_presets.Preset("openai", "OpenAI", "https://api.openai.com/v1", "openai.key", False)))
        assert model_probe.detect(timeout=1) == [
            {"id": "ollama", "label": "Ollama", "baseUrl": server.url, "models": ["llama3.2:3b"]}]


# ---- Test: one tiny reply through Milo's own adapter

def test_try_reply_reports_the_time_to_the_first_word():
    with FakeOpenAI(reply="OK") as server:
        result = model_probe.try_reply(server.url, "qwen2.5:7b")
    assert result["ok"] and result["reply"] == "OK" and result["ms"] >= 0
    assert result["text"].startswith("Answered in ")


@pytest.mark.parametrize("server_options,model,key,expected", [
    ({"key": "sk-right"}, "qwen2.5:7b", "sk-wrong", "turned down the API key"),
    ({}, "no-such-model", "", "doesn't know the model"),
])
def test_try_reply_explains_what_to_change(server_options, model, key, expected):
    with FakeOpenAI(**server_options) as server:
        result = model_probe.try_reply(server.url, model, key=key)
    assert not result["ok"] and expected in result["text"]
    assert "sk-wrong" not in result["text"]


def test_try_reply_to_nothing_says_to_start_the_server():
    result = model_probe.try_reply(dead_url(), "llama3.2:3b", timeout=2)
    assert not result["ok"] and "can't reach" in result["text"] and "start it" in result["text"]


def test_a_missing_key_file_says_where_the_key_goes(tmp_path):
    with FakeOpenAI() as server:
        result = model_probe.try_reply(server.url, "qwen2.5:7b", key_file=tmp_path / "secrets" / "groq.key")
    assert not result["ok"] and "groq.key" in result["text"] and "Connections & models" in result["text"]


def test_a_server_that_refuses_openai_extras_is_asked_again_without_them():
    with FakeOpenAI(refuse_extras=True) as server:
        chat = OpenAICompatModel(server.url, "qwen2.5:7b")

        async def talk():
            await chat.start("")
            return "".join([d async for d in chat.turn("hi")]) + "".join([d async for d in chat.turn("again")])

        assert asyncio.run(talk()) == "OKOK"
        assert chat.lean and "stream_options" in server.bodies[0] and "stream_options" not in server.bodies[-1]
        assert len(server.bodies) == 3  # refused once, then two plain turns


def test_the_brain_names_the_fix_when_a_server_is_down():
    chat = OpenAICompatModel(dead_url(), "m", timeout_s=2)

    async def talk():
        await chat.start("")
        return [d async for d in chat.turn("hi")]

    with pytest.raises(HarnessError) as error:
        asyncio.run(talk())
    assert "can't reach" in error.value.said and "Connections & models" in error.value.said


# ---- saving: config keys and the secret file

def test_save_writes_the_key_alone_and_only_the_needed_config_keys(tmp_path, caplog):
    path, providers = setup(tmp_path)
    caplog.set_level(logging.DEBUG)
    providers.save(ProviderSelection("openai_compat", "claude", "https://api.groq.com/openai/v1",
                                     "llama-3.3-70b-versatile", "groq.key"), key="  gsk-secret-123  ")
    assert (tmp_path / "secrets" / "groq.key").read_text(encoding="utf-8") == "gsk-secret-123\n"
    text = path.read_text(encoding="utf-8")
    config = tomllib.loads(text)
    assert config["chat"]["openai_compat"] == {"base_url": "https://api.groq.com/openai/v1",
                                                "model": "llama-3.3-70b-versatile", "key_ref": "groq.key"}
    assert "# my settings" in text and "gsk-secret" not in text
    assert "gsk-secret" not in caplog.text


def test_a_key_without_a_file_name_is_refused_and_nothing_written(tmp_path):
    path, providers = setup(tmp_path)
    before = path.read_bytes()
    with pytest.raises(Exception, match="Name the file"):
        providers.save(ProviderSelection("openai_compat", "claude", "https://api.openai.com/v1", "gpt-5-mini", ""),
                       key="sk-x")
    assert path.read_bytes() == before and not (tmp_path / "secrets").exists()


def test_a_secret_is_one_line(tmp_path):
    with pytest.raises(SecretError):
        write_secret(tmp_path / "secrets" / "a.key", "line one\nline two", "The API key")


# ---- the backend: off the UI thread, results queued back

def _wait(condition, ms=5000):
    from PySide6.QtTest import QTest
    for _ in range(ms // 20):
        if condition():
            return True
        QTest.qWait(20)
    return False


@pytest.fixture
def backend(tmp_path, desktop_application):
    pytest.importorskip("PySide6.QtQuick")
    from milo.desktop.viewmodels.setup import SetupBackend
    path, providers = setup(tmp_path)
    b = SetupBackend(tmp_path, setup=providers)
    yield path, b
    b.deleteLater()


def test_backend_lists_models_and_tests_without_blocking(backend):
    path, b = backend
    with FakeOpenAI(key="sk-k") as server:
        choice = {"chat": "openai_compat", "helper": "claude", "endpoint": server.url, "model": "qwen2.5:7b",
                  "keyRef": "fake.key", "key": "sk-k"}
        b.fetchModels(choice)
        assert b.models["busy"]  # answered later, from its thread
        assert _wait(lambda: not b.models["busy"])
        assert b.models == {"endpoint": server.url, "names": ["llama3.2:3b", "qwen2.5:7b"], "error": "", "busy": False}
        b.test(choice)
        assert _wait(lambda: not b.testResult["busy"])
        assert b.testResult["ok"], b.testResult["text"]
        assert b.save(choice)
    assert (path.parent / "secrets" / "fake.key").read_text(encoding="utf-8") == "sk-k\n"
    assert b.keySaved("fake.key") and not b.keySaved("other.key")
    assert "sk-k" not in repr([b.selection, b.models, b.testResult, b.lastError])


def test_backend_keeps_only_the_newest_answer(backend):
    _, b = backend
    with FakeOpenAI(models=["new"]) as server:
        b.fetchModels({"endpoint": dead_url()})
        b.fetchModels({"endpoint": server.url})
        assert _wait(lambda: not b.models["busy"])
        assert b.models["names"] == ["new"]
