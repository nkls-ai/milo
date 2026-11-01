import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from milo.desktop._native_opening import ApplicationCatalog, application_name, data_file
from milo.desktop._native_types import NativeError, UnavailableAccessibility
from milo.desktop.native import NativeBridge


@pytest.mark.parametrize("name", [r"C:\tmp\payload.exe", "/tmp/payload", "./payload", "../payload", "work/payload",
                                  r"work\payload", "https://example.com", "payload\ncommand"])
def test_application_paths_are_not_application_names(name):
    with pytest.raises(NativeError, match="installed application"):
        application_name(name)


def test_open_app_never_launches_a_payload_found_on_path(tmp_path, monkeypatch):
    import milo.desktop.native as native
    payload = tmp_path / "work" / "milo-test-payload.exe"
    payload.parent.mkdir()
    payload.write_bytes(b"MZ-not-a-real-program")
    monkeypatch.setenv("PATH", str(payload.parent) + os.pathsep + os.environ.get("PATH", ""))
    launches = []
    monkeypatch.setattr(native.subprocess, "Popen", lambda *a, **k: launches.append(a))
    bridge = NativeBridge(tmp_path, backend=UnavailableAccessibility("not running"))
    with pytest.raises(NativeError):
        bridge.hands_request("open_app", {"name": "milo-test-payload"})
    assert not launches


@pytest.mark.skipif(os.name != "nt", reason="Windows App Paths catalog")
def test_an_app_paths_registration_cannot_execute_a_helpers_workspace_payload(tmp_path, monkeypatch):
    import winreg
    payload = tmp_path / "work" / "payload.exe"
    payload.parent.mkdir()
    payload.write_bytes(b"MZ-test")
    class Key:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            pass
    monkeypatch.setattr(winreg, "OpenKey", lambda *a: Key())
    monkeypatch.setattr(winreg, "QueryValue", lambda *a: str(payload))
    with pytest.raises(NativeError, match="workspace"):
        ApplicationCatalog(tmp_path).command("Payload")


@pytest.mark.parametrize("extension", [".exe", ".cmd", ".bat", ".ps1", ".hta", ".lnk", ".url", ".desktop",
                                       ".AppImage", ".sh", ".py", ".js", ".vbs", ".docm", ".xlsm", ".pptm", ".xlsb"])
def test_open_file_never_launches_executable_shortcut_or_macro_payload(tmp_path, monkeypatch, extension):
    from PySide6.QtGui import QDesktopServices
    payload = tmp_path / ("payload" + extension)
    payload.write_text("payload", encoding="utf-8")
    launches = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda value: launches.append(value) or True)
    bridge = NativeBridge(tmp_path, backend=UnavailableAccessibility("test"))
    with pytest.raises(NativeError):
        bridge.hands_request("open_file", {"path": str(payload)})
    assert not launches


@pytest.mark.parametrize("magic", [b"MZ", b"\x7fELF", b"#!/bin/sh\n", b"\xcf\xfa\xed\xfe"])
def test_executable_magic_cannot_be_hidden_under_a_data_extension(tmp_path, magic):
    payload = tmp_path / "picture.pdf"
    payload.write_bytes(magic + b"payload")
    with pytest.raises(NativeError, match="Executable"):
        data_file(payload)


def test_extensionless_executable_is_refused(tmp_path):
    payload = tmp_path / "payload"
    payload.write_text("echo payload", encoding="utf-8")
    payload.chmod(0o700)
    with pytest.raises(NativeError):
        data_file(payload)


def test_a_macro_package_cannot_be_renamed_to_docx(tmp_path):
    document = tmp_path / "document.docx"
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("word/vbaProject.bin", b"macro")
    with pytest.raises(NativeError, match="Macro"):
        data_file(document)


def test_regular_documents_and_directories_are_allowed(tmp_path):
    document = tmp_path / "notes.txt"
    document.write_text("Some data", encoding="utf-8")
    assert data_file(document) == document.resolve()
    assert data_file(tmp_path) == tmp_path.resolve()


def test_arbitrary_cli_cannot_receive_a_web_address_as_command_arguments(tmp_path):
    with pytest.raises(NativeError, match="browser"):
        ApplicationCatalog(tmp_path).command("PowerShell", browser=True)


def test_a_catalog_command_rejects_workspace_arguments_even_with_a_trusted_executable(tmp_path):
    executable = tmp_path.parent / "installed-editor.exe"
    executable.write_bytes(b"MZ-installed")
    catalog = ApplicationCatalog(tmp_path)
    with pytest.raises(NativeError, match="workspace"):
        catalog._check([str(executable), "--load=" + str(tmp_path / "work" / "payload.py")])


def test_catalog_launch_environment_excludes_helper_writable_path_entries(tmp_path, monkeypatch):
    safe = tmp_path.parent / "installed"
    unsafe = tmp_path / "work"
    monkeypatch.setenv("PATH", os.pathsep.join((str(unsafe), "", str(safe))))
    assert ApplicationCatalog(tmp_path).environment()["PATH"] == str(safe)


def test_linux_installed_catalog_can_launch_but_never_from_the_milo_workspace(tmp_path, monkeypatch):
    import milo.desktop._native_opening as opening
    user = tmp_path / "user"
    home = user / "Milo"
    catalog_dir = user / ".local/share/applications"
    catalog_dir.mkdir(parents=True)
    installed = tmp_path / "installed" / "editor"
    installed.parent.mkdir()
    installed.write_bytes(b"installed test executable")
    monkeypatch.setattr(opening.sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", classmethod(lambda _: user))
    (catalog_dir / "editor.desktop").write_text(f"[Desktop Entry]\nType=Application\nName=Editor\nExec={installed.as_posix()} %U\n", encoding="utf-8")
    assert ApplicationCatalog(home).command("Editor") == [str(installed)]
    payload = home / "work" / "payload"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"payload")
    (catalog_dir / "editor.desktop").write_text(f"[Desktop Entry]\nName=Editor\nExec={payload.as_posix()}\n", encoding="utf-8")
    with pytest.raises(NativeError, match="workspace"):
        ApplicationCatalog(home).command("Editor")
