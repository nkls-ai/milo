"""One desktop entry point for Windows and Linux (macOS has its own Swift app).

--brain runs the bundled brain process in a frozen distribution. --smoke-test renders the real QML offscreen with a
scripted brain, no devices, hooks or models, and saves screenshots. --diagnose checks the native desktop
capabilities without starting models. --ui widgets starts the older Qt Widgets desktop while it is still kept.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

HELPERS = ("milo.mcp_server", "milo.connect", "milo.desktop.office_worker")


def _helper_module() -> int | None:
    """`--module NAME`: a bundled helper process (MCP servers, the office worker) in a frozen build."""
    if len(sys.argv) < 3 or sys.argv[1] != "--module":
        return None
    import runpy
    name = sys.argv[2]
    if name not in HELPERS:
        raise SystemExit("Unknown bundled helper module")
    sys.argv = [name, *sys.argv[3:]]
    runpy.run_module(name, run_name="__main__")
    return 0


def arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Milo — your desktop coworker")
    parser.add_argument("--brain", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--home", type=Path, help="Milo workspace (default: MILO_HOME or ~/Milo)")
    parser.add_argument("--no-brain", action="store_true", help="Connect to an already running brain")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Render the UI with a scripted brain and no models or devices, then exit")
    parser.add_argument("--diagnose", action="store_true",
                        help="Check native desktop capabilities without starting models")
    parser.add_argument("--check-models", action="store_true",
                        help="Load local models and generate test audio without playback (downloads uncached weights)")
    parser.add_argument("--model-check-output", type=Path, default=Path("build/model-check"))
    parser.add_argument("--model-check-audio", type=Path, help="Optional mono 16 kHz PCM speech fixture for --check-models")
    parser.add_argument("--screenshot", type=Path,
                        help="--smoke-test: where the screenshots go (a folder; a .png path names the main shot)")
    return parser


def diagnose() -> int:
    from .platform import create
    with tempfile.TemporaryDirectory(prefix="milo-desktop-check-") as folder:
        native = create(Path(folder))
        capabilities = native.capabilities()
        report = {"capabilities": capabilities, "backend": type(getattr(native, "backend", native)).__name__,
                  "focus_role": ""}
        try:
            focus = native.backend.focus()
            report["focus_role"] = focus.role if focus is not None else ""
        except Exception as error:
            report["focus_error"] = type(error).__name__
        finally:
            native.close()
    if sys.stdout is not None:
        print(json.dumps(report, ensure_ascii=False))
    return 0 if capabilities.get("accessibility") else 1


def _shots(path: Path | None) -> Path:
    if path is None:
        return Path.cwd() / "build" / "qml-shots" / "smoke"
    return path.with_suffix("") if path.suffix.lower() == ".png" else path


def main() -> int:
    helper = _helper_module()
    if helper is not None:
        return helper
    args = arguments().parse_args()
    if args.check_models:
        from .model_check import check_models
        return check_models(args.model_check_output, args.model_check_audio)
    if args.home is not None:
        os.environ["MILO_HOME"] = str(args.home.expanduser().resolve())
    if args.brain:
        from milo.server import main as brain_main
        brain_main()
        return 0
    if args.diagnose:
        from .app import application
        application()
        return diagnose()
    from . import app
    if args.smoke_test:
        return app.smoke(_shots(args.screenshot).resolve())
    home = Path(os.environ.get("MILO_HOME", "~/Milo")).expanduser().resolve()
    return app.run(home, no_brain=args.no_brain)


if __name__ == "__main__":
    raise SystemExit(main())
