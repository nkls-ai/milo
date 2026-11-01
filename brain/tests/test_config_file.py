import pytest

from milo.config_file import TomlConfigFile
from milo.core.registry import ConfigError
from milo.memory.workspace import Workspace


@pytest.fixture
def file(tmp_path):
    ws = Workspace(tmp_path)
    ws.ensure()
    return TomlConfigFile(ws.config_path)


def test_a_change_keeps_every_comment_and_the_column_of_the_one_on_its_line(file):
    # Test an existing explicit value; the shipped template intentionally leaves OS defaults out.
    template = file.path.read_text(encoding="utf-8")
    file.path.write_text(template.replace("[ui]\n", '[ui]\ndictate_key = "fn"                # my custom key\n'), encoding="utf-8")
    before = file.path.read_text(encoding="utf-8")
    config = file.write("ui", "dictate_key", "right_command")
    after = file.path.read_text(encoding="utf-8")
    assert config.ui.dictate_key == "right_command" and file.read().ui.dictate_key == "right_command"
    old_line = next(line for line in before.splitlines() if line.startswith("dictate_key ="))
    new_line = next(line for line in after.splitlines() if line.startswith("dictate_key ="))
    assert new_line.index("#") == old_line.index("#")
    assert before.replace(old_line, new_line) == after


def test_a_missing_key_is_added_to_its_own_table(file):
    file.path.write_text("[chat]\nuse = \"claude_live\"\n\n[chat.claude_live]\n\n[ui]\nvoice = false\n", encoding="utf-8")
    assert file.write("chat", "updates", "chatty").chat.updates == "chatty"
    assert file.write("dictation", "stream", "type").dictation.stream == "type"
    assert file.read().chat.updates == "chatty"
    assert file.path.read_text(encoding="utf-8").index("updates") < file.path.read_text(encoding="utf-8").index("[chat.claude_live]")


def test_an_invalid_value_writes_nothing(file):
    before = file.path.read_text(encoding="utf-8")
    with pytest.raises(ConfigError, match="same key"):
        file.write("ui", "talk_key", "fn")
    with pytest.raises(ConfigError, match="voice"):
        file.write("ui", "voice", "loud")
    assert file.path.read_text(encoding="utf-8") == before
    assert not list(file.path.parent.glob(".config.toml*"))


def test_a_file_that_is_already_broken_is_left_alone(file):
    file.path.write_text("[ui\nvoice = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid TOML"):
        file.write("ui", "voice", "true")
    assert file.path.read_text(encoding="utf-8") == "[ui\nvoice = 1\n"


def test_a_sub_table_is_not_its_parent(file):
    file.path.write_text("[dictation]\nstream = \"off\"\n\n[dictation.fillers]\nlanguages = [\"en\"]\n", encoding="utf-8")
    assert file.write("dictation", "stream", "type").dictation.stream == "type"
    text = file.path.read_text(encoding="utf-8")
    assert text == "[dictation]\nstream = \"type\"\n\n[dictation.fillers]\nlanguages = [\"en\"]\n"


def test_a_missing_section_is_added_and_a_missing_file_is_made(file):
    file.path.write_text("[ui]\nvoice = false", encoding="utf-8")
    assert file.write("dictation", "stream", "preview").dictation.stream == "preview"
    assert file.read().ui.voice is False
    file.path.unlink()
    assert file.write("dictation", "stream", "type").dictation.stream == "type"
    assert file.path.read_text(encoding="utf-8").strip() == "[dictation]\nstream = \"type\""
