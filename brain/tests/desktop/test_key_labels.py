import sys

import pytest

from milo.desktop.platform import combo_label, key_label


@pytest.mark.skipif(sys.platform == "darwin", reason="PC keyboards")
def test_desktop_key_hints_use_this_keyboards_names():
    assert key_label("right_option") == "Right Alt"
    assert key_label("fn") == "Right Ctrl", "fn has no PC key; it is Right Ctrl there"
    assert combo_label("ctrl+option+m") == "Ctrl+Alt+M"


def test_presentation_labels_come_from_the_platform_layer():
    from milo.desktop.presentation.keys import key_label as shown
    assert shown("right_option") == key_label("right_option")
