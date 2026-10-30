import tomllib

import pytest

from milo.config_edit import set_value

CONFIG = """\
# Milo configuration.

[dictation]
use = "fillers"                   # fillers | plain
keep_history = true
stream = "preview"                # the live words

[dictation.fillers]
languages = ["en", "de"]
"""


def test_a_value_changes_in_place_and_its_comment_stays(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG)
    set_value(path, "dictation", "stream", "type")
    assert path.read_text() == CONFIG.replace('stream = "preview"', 'stream = "type"')
    assert tomllib.loads(path.read_text())["dictation"]["stream"] == "type"


def test_a_missing_key_is_added_to_its_section(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG.replace('stream = "preview"                # the live words\n', ""))
    set_value(path, "dictation", "stream", "off")
    parsed = tomllib.loads(path.read_text())
    assert parsed["dictation"]["stream"] == "off"
    assert parsed["dictation"]["fillers"] == {"languages": ["en", "de"]}
    assert 'keep_history = true\nstream = "off"\n\n[dictation.fillers]' in path.read_text()


def test_a_missing_section_is_added_at_the_end(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[ui]\ncharacter = \"pip\"")
    set_value(path, "dictation", "stream", "preview")
    assert tomllib.loads(path.read_text()) == {"ui": {"character": "pip"}, "dictation": {"stream": "preview"}}


def test_a_sub_table_is_not_its_parent(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[dictation.fillers]\nstream = \"x\"\n")
    set_value(path, "dictation", "stream", "type")
    parsed = tomllib.loads(path.read_text())
    assert parsed["dictation"]["stream"] == "type" and parsed["dictation"]["fillers"]["stream"] == "x"


def test_a_broken_file_is_left_alone(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[dictation\nstream = 1\n")
    with pytest.raises(ValueError):
        set_value(path, "dictation", "stream", "type")
    assert path.read_text() == "[dictation\nstream = 1\n"
