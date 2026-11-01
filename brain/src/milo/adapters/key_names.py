"""How each keyboard names Milo's keys: the Mac's words and a PC's (Windows, Linux)."""
from __future__ import annotations

from dataclasses import replace

from milo.core.key_names import KeyNames

MAC_KEY_NAMES = KeyNames(
    keys=(("fn", "fn"), ("right_option", "Right Option"), ("right_command", "Right Command"),
          ("right_control", "Right Control")),
    modifiers=(("ctrl", "Control"), ("control", "Control"), ("option", "Option"), ("alt", "Option"),
               ("cmd", "Command"), ("command", "Command"), ("shift", "Shift")),
    separator="-")

PC_KEY_NAMES = KeyNames(
    keys=(("fn", "Fn"), ("right_option", "Right Alt"), ("right_command", "Right Windows"),
          ("right_control", "Right Ctrl")),
    modifiers=(("ctrl", "Ctrl"), ("control", "Ctrl"), ("option", "Alt"), ("alt", "Alt"),
               ("cmd", "Win"), ("command", "Win"), ("super", "Win"), ("shift", "Shift")),
    separator="+")

LINUX_KEY_NAMES = replace(PC_KEY_NAMES,
                          keys=tuple((k, "Right Super" if k == "right_command" else v) for k, v in PC_KEY_NAMES.keys),
                          modifiers=tuple((k, "Super" if v == "Win" else v) for k, v in PC_KEY_NAMES.modifiers))
