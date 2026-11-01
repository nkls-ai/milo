"""Installed application catalogs and data-file opening, never arbitrary command resolution."""
from __future__ import annotations

import configparser
import os
import shlex
import stat
import sys
import zipfile
from pathlib import Path

from ._native_types import NativeError


_DATA = frozenset(".txt .md .rst .pdf .docx .xlsx .pptx .odt .ods .odp .rtf .csv .tsv .json .toml .yaml .yml "
                  ".xml .log .ics .vcf .png .jpg .jpeg .gif .webp .bmp .tif .tiff .avif .ico .heic .heif "
                  ".wav .mp3 .flac .ogg .m4a .aac .opus .mp4 .mkv .mov .webm .avi .mpeg .mpg "
                  ".zip .tar .gz .bz2 .xz .7z .rar".split())
_EXEC_MAGIC = (b"MZ", b"\x7fELF", b"#!", b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
               b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")
_BROWSERS = frozenset({"chrome", "google chrome", "google-chrome", "google-chrome-stable", "chromium",
                        "chromium-browser", "msedge", "microsoft edge", "firefox", "firefox-esr", "brave",
                        "brave browser", "brave-browser", "vivaldi", "opera"})


def application_name(name: str) -> str:
    name = name.strip()
    if (not name or name in (".", "..") or len(name) > 120 or
            any(char in name for char in "\n\r\0/\\:") or Path(name).is_absolute()):
        raise NativeError("Name an installed application, without a path or command arguments.")
    return name


def data_file(path: Path) -> Path:
    path = path.expanduser().resolve(strict=True)
    if path.is_dir():
        if path.suffix.casefold() == ".app":
            raise NativeError("Application bundles must be opened by their installed application name.")
        return path
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise NativeError("Only a regular data file or directory can be opened.")
    extension = path.suffix.casefold()
    if extension not in _DATA:
        raise NativeError("This file type may execute code. Open an installed app by name instead.")
    with path.open("rb") as source:
        if source.read(8).startswith(_EXEC_MAGIC):
            raise NativeError("Executable file contents cannot be opened as a data document.")
    if extension in {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}:
        try:
            with zipfile.ZipFile(path) as archive:
                if len(archive.infolist()) > 50000:
                    raise NativeError("The document package has too many entries.")
                if any("vbaproject" in name.casefold() or name.casefold().startswith(("basic/", "scripts/"))
                       for name in archive.namelist()):
                    raise NativeError("Macro-containing documents cannot be opened through this action.")
                if "[Content_Types].xml" in archive.namelist():
                    info = archive.getinfo("[Content_Types].xml")
                    if info.file_size > 1024 * 1024 or b"macroenabled" in archive.read(info).lower():
                        raise NativeError("Macro-containing documents cannot be opened through this action.")
        except zipfile.BadZipFile:
            raise NativeError("This is not a valid data-document package.") from None
    return path


class ApplicationCatalog:
    def __init__(self, home: Path):
        self.home = home.resolve()

    def _outside_workspace(self, value: str) -> None:
        # Catalogs may name an executable and fixed arguments, but none may reach
        # helper-writable files, including through symlinks or --option=path.
        value = value.replace("~/", str(Path.home()) + "/")
        if self.home.as_posix().casefold() in value.replace("\\", "/").casefold():
            raise NativeError("An installed application cannot run files from Milo's workspace.")
        candidate = value.split("=", 1)[-1]
        if candidate and not any(char in candidate for char in "\n\r\0"):
            path = Path(candidate).expanduser()
            path = (Path.home() / path).resolve() if not path.is_absolute() else path.resolve()
            if path.is_relative_to(self.home):
                raise NativeError("An installed application cannot run files from Milo's workspace.")

    def _check(self, command: list[str]) -> list[str]:
        if not command:
            raise NativeError("The installed application has no launch command.")
        for value in command:
            self._outside_workspace(value)
        executable = Path(command[0]).expanduser().resolve()
        if not executable.is_file():
            raise NativeError("The installed application's executable is missing.")
        self._outside_workspace(str(executable))
        return [str(executable), *command[1:]]

    def environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        safe = []
        for value in os.get_exec_path():
            if not value:
                continue
            try:
                self._outside_workspace(value)
            except NativeError:
                continue
            safe.append(value)
        environment["PATH"] = os.pathsep.join(safe)
        return environment

    def command(self, name: str, *, browser: bool = False) -> list[str]:
        name = application_name(name)
        if browser and name.casefold().removesuffix(".exe") not in _BROWSERS:
            raise NativeError("A web address can only be passed to an installed browser.")
        aliases = {"google chrome": "chrome", "microsoft edge": "msedge", "microsoft word": "winword",
                   "microsoft excel": "excel", "text editor": "notepad" if sys.platform == "win32" else "gedit"}
        executable = aliases.get(name.casefold(), name).removesuffix(".exe")
        if sys.platform == "win32":
            import winreg
            system = Path(os.environ.get("WINDIR", "C:/Windows"))
            builtins = {"notepad": system / "System32/notepad.exe", "calc": system / "System32/calc.exe",
                        "calculator": system / "System32/calc.exe", "paint": system / "System32/mspaint.exe",
                        "mspaint": system / "System32/mspaint.exe", "explorer": system / "explorer.exe",
                        "file explorer": system / "explorer.exe", "cmd": system / "System32/cmd.exe",
                        "command prompt": system / "System32/cmd.exe",
                        "powershell": system / "System32/WindowsPowerShell/v1.0/powershell.exe"}
            if executable.casefold() in builtins and builtins[executable.casefold()].is_file():
                return self._check([str(builtins[executable.casefold()])])
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, "Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + executable + ".exe") as key:
                        registered = os.path.expandvars(str(winreg.QueryValue(key, None))).strip('"')
                        if Path(registered).suffix.casefold() != ".exe":
                            raise NativeError("The installed application must name an executable, not a script or shortcut.")
                        return self._check([registered])
                except OSError:
                    pass
        else:
            roots = [Path.home() / ".local/share/applications", Path("/usr/local/share/applications"), Path("/usr/share/applications")]
            for root in roots:
                for desktop in sorted(root.glob("*.desktop")):
                    config = configparser.ConfigParser(interpolation=None)
                    try:
                        config.read(desktop, encoding="utf-8")
                        entry = config["Desktop Entry"]
                        if name.casefold() not in (entry.get("Name", "").casefold(), desktop.stem.casefold()):
                            continue
                        self._outside_workspace(str(desktop.resolve()))
                        if entry.get("Type", "Application") != "Application" or entry.getboolean("Hidden", fallback=False):
                            continue
                        if entry.getboolean("Terminal", fallback=False):
                            raise NativeError("This catalog entry requires a terminal and cannot be opened silently.")
                        command = [value for value in shlex.split(entry.get("Exec", "")) if not value.startswith("%")]
                        if command and not Path(command[0]).is_absolute():
                            command[0] = next((str(directory / command[0]) for directory in
                                map(Path, ("/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"))
                                if (directory / command[0]).is_file()), "")
                        return self._check(command)
                    except (OSError, configparser.Error, ValueError):
                        continue
        raise NativeError(f"Could not find an installed application called {name}.")
