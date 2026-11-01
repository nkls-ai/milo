"""Build a self-contained desktop folder on the target OS (no Python/uv needed to run it).

Run: uv run --project brain --extra desktop --extra build python scripts/build-desktop.py
Windows produces Milo.exe plus a console runtime used only for redirected brain/MCP subprocesses.
"""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--allow-home-paths", action="store_true",
                        help="build even though the Python lives under your home folder (its path ships)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # On Linux the interpreter's sysconfig data and extensions compiled from source keep their build paths, so a
    # Python or uv cache under /home/<you> puts your user name into the release. Build with everything elsewhere,
    # e.g. UV_PYTHON_INSTALL_DIR, UV_CACHE_DIR and UV_PROJECT_ENVIRONMENT under /opt/milo-build.
    home = str(Path.home())
    if os.name != "nt" and not args.allow_home_paths and any(
            str(p).startswith(home + os.sep) for p in (sys.base_prefix, sys.prefix, os.environ.get("UV_CACHE_DIR", ""))):
        print(f"Refusing to build: Python ({sys.base_prefix}) or the uv cache is under {home}, whose path would ship "
              "in the release. See the comment above this check.", file=sys.stderr)
        return 2
    build = root / "build" / "desktop" / f"{sys.platform}-{platform.machine().lower()}"
    build.mkdir(parents=True, exist_ok=True)
    spec = build / "milo-desktop.spec"
    spec.write_text(f'''from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs
from pathlib import Path
root = Path({str(root)!r})
hidden = collect_submodules("milo")
hidden += ["win32timezone"] if {os.name == "nt"!r} else []
# QML imports are invisible to the analysis: name the Qt modules whose QML plugins the shell loads.
hidden += ["PySide6.QtQml", "PySide6.QtQuick"]
datas = collect_data_files("milo", includes=["workspace_template/**/*"])
datas += [(str(root / "brain" / "src" / "milo" / "desktop" / "uno_bridge.py"), "milo/desktop")]
# The QML shell: its files next to the frozen modules (qml_engine.qml_root), and the design tokens it reads.
datas += [(str(root / "brain" / "src" / "milo" / "desktop" / "qml"), "milo/desktop/qml")]
datas += [(str(root / "protocol" / "design.json"), "protocol")]
datas += collect_data_files("faster_whisper") + collect_data_files("pocket_tts")
datas += collect_data_files("sherpa_onnx") + collect_data_files("sqlite_vec")
datas += collect_data_files("docx")
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("sherpa_onnx")
binaries += collect_dynamic_libs("sqlite_vec")
a = Analysis([str(root / "scripts" / "desktop-entry.py")], pathex=[str(root / "brain" / "src")],
             binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "matplotlib", "IPython", "pytest"],
             noarchive=False)
# Qt WebEngine (a whole Chromium, ~200 MB) comes along with PySide6's hooks; nothing in Milo uses it.
unused = ("webengine", "qtwebview")
a.binaries = [b for b in a.binaries if not any(u in b[0].casefold() for u in unused)]
a.datas = [d for d in a.datas if not any(u in d[0].casefold() for u in unused)]
pyz = PYZ(a.pure)
options = [("X utf8", None, "OPTION")]
gui = EXE(pyz, a.scripts, options, [], exclude_binaries=True, name="Milo", console={os.name != "nt"!r},
          icon=str(root / "assets" / "icon.png") if {os.name == "nt"!r} else None)
runtime = EXE(pyz, a.scripts, options, [], exclude_binaries=True, name="Milo-runtime", console=True)
collection = COLLECT(gui, runtime, a.binaries, a.datas, strip=False, upx=False, name="Milo")
''', encoding="utf-8")
    return subprocess.call([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath",
                            str(args.output.resolve()), "--workpath", str(build / "work"), str(spec)], cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
