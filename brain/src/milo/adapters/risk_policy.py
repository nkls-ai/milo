"""OS-specific app names and effective shortcuts; no decisions live in this adapter."""
from __future__ import annotations

from dataclasses import replace

from milo.core.risk_policy import DEFAULT_RISK_POLICY, RiskPolicy


MACOS = DEFAULT_RISK_POLICY
_PC_KEYS = (("cmd", "ctrl"), ("command", "ctrl"), ("⌘", "ctrl"),
            ("delete", "forwarddelete"), ("del", "forwarddelete"), ("backspace", "backspace"))
_PC_COMBOS = (("shift+forwarddelete", "delete it for good"),
              ("ctrl+return", "send"), ("ctrl+shift+d", "send"), ("option+s", "send"),
              ("ctrl+shift+forwarddelete", "delete browsing data"))
_BROWSERS = frozenset({"google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                       "msedge", "microsoft edge", "firefox-esr", "brave", "vivaldi"})
_DOCUMENTS = frozenset({"notepad", "notepad++", "wordpad", "libreoffice", "libreoffice writer",
                       "libreoffice calc", "writer", "calc", "gedit", "kate", "xed", "mousepad"})
_SECRETS = frozenset({"windows security", "credential manager", "windows credential manager",
                     "keepass", "keepassxc", "seahorse", "gnome-keyring", "kwalletmanager"})

WINDOWS = RiskPolicy(
    code_apps=frozenset({"powershell", "pwsh", "cmd", "command prompt", "windows terminal", "windowsterminal",
                        "conhost", "wsl", "ubuntu", "debian", "windows powershell", "powershell ise",
                        "powershell_ise", "bash", "python", "pythonw", "node"}),
    settings_apps=frozenset({"settings", "systemsettings", "windows settings", "control panel", "regedit",
                            "registry editor", "mmc", "computer management", "device manager"}),
    secret_apps=_SECRETS,
    file_apps=frozenset({"file explorer", "explorer", "total commander", "directory opus"}),
    trash_apps=frozenset({"file explorer", "explorer", "outlook", "microsoft outlook", "thunderbird"}),
    document_apps=_DOCUMENTS | {"excel", "winword", "powerpnt"}, browsers=_BROWSERS,
    key_aliases=_PC_KEYS, risky_combos=_PC_COMBOS,
    key_labels=(("ctrl", "Ctrl"), ("shift", "Shift"), ("option", "Alt"), ("forwarddelete", "Delete"),
                ("backspace", "Backspace"), ("return", "Enter"), ("escape", "Escape")), key_separator="+")

LINUX = replace(WINDOWS,
    code_apps=frozenset({"gnome-terminal", "gnome terminal", "konsole", "xterm", "uxterm", "xfce4-terminal",
                        "mate-terminal", "qterminal", "terminator", "tilix", "ptyxis", "foot", "st",
                        "bash", "zsh", "fish", "python", "node"}),
    settings_apps=frozenset({"settings", "gnome-control-center", "gnome control center", "systemsettings",
                            "kde system settings", "dconf-editor", "dconf editor"}),
    file_apps=frozenset({"files", "nautilus", "dolphin", "thunar", "nemo", "caja", "pcmanfm"}),
    trash_apps=frozenset({"files", "nautilus", "dolphin", "thunar", "nemo", "caja", "pcmanfm",
                         "thunderbird", "evolution", "geary"}))


def for_platform(name: str) -> RiskPolicy:
    return {"macos": MACOS, "windows": WINDOWS, "linux": LINUX}.get(name, DEFAULT_RISK_POLICY)
