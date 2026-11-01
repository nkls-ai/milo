"""Real LibreOffice UNO check on disposable documents in an isolated temporary profile.

Run on Linux with: uv run --project brain python scripts/uno-office-e2e.py
Requires system LibreOffice Calc/Writer and python3-uno. No model or account is used.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from xml.etree import ElementTree

import psutil

from milo.desktop._office_uno import LibreOffice
from milo.desktop._native_types import NativeError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/uno-office-e2e"))
    parser.add_argument("--runtime", type=Path, help="Also test the packaged Office actor and its bundled UNO bridge")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix="milo-uno-e2e-") as temporary:
        home = Path(temporary)
        office = LibreOffice(home, headless=True)
        profile_flag = "-env:UserInstallation=" + (home / "state/libreoffice").as_uri()
        try:
            result = office.run("sheet_write", {"app": "LibreOffice Calc", "new_document": True,
                "rows": [["Item", "Amount"], ["Apples", 2], ["Pears", 3], ["Total", "=SUM(B2:B3)"],
                         ["+literal", "0012"]], "header": True, "fill": "A1:B1 blue", "font_color": "header white",
                "money": "B2:B4", "locale": "de_DE"})
            assert Path(result["path"]).is_file()
            checks.append("created and saved managed ODS")
            cells = office._call({"operation": "read", "range": "A1:B5", "has_rows": False})
            assert cells["values"][3][1] == 5
            assert cells["values"][4] == ["+literal", "0012"]
            checks += ["bulk data and calculated formula results", "literal prefix and zero-padded text"]
            header = office._call({"operation": "read", "range": "A1:B1", "has_rows": False})
            assert header["styles"]["CharWeight"] == 150
            assert header["styles"]["CellBackColor"] == 0x0070C0
            assert header["styles"]["CharColor"] == 0xFFFFFF
            checks.append("header weight, fill and font color")
            change = {"app": "LibreOffice Calc", "rows": [[7]], "start": "B2"}
            office.describe("sheet_write", change)
            other = LibreOffice(home, headless=True)
            other.describe("sheet_write", change)
            other.run("sheet_write", {**change, "rows": [[99]]})
            try:
                office.run("sheet_write", change)
            except NativeError as error:
                assert "changed" in str(error)
            else:
                raise AssertionError("A stale target was accepted")
            checks.append("stale target refused before overwriting user changes")
            office.describe("sheet_write", change)
            office.run("sheet_write", change)
            again = LibreOffice(home, headless=True)
            assert again._call({"operation": "read", "range": "B2", "has_rows": False})["values"] == [[7.0]]
            checks.append("existing workbook update and reconnect")
            text = "Grüße von Milo.\n日本語 and emojis 🐦"
            document = office.run("write_document", {"app": "LibreOffice Writer", "text": text})
            with zipfile.ZipFile(document["path"]) as archive:
                root = ElementTree.fromstring(archive.read("content.xml"))
            content = "".join(root.itertext())
            assert "Grüße von Milo." in content and "日本語 and emojis 🐦" in content
            checks.append("saved Unicode Writer document")
            if args.runtime:
                messages = [
                    {"id": 1, "operation": "run", "tool": "sheet_write", "args": {
                        "app": "LibreOffice Calc", "new_document": True, "rows": [["Frozen runtime", 42]]}},
                    {"id": 2, "operation": "run", "tool": "write_document", "args": {
                        "app": "LibreOffice Writer", "text": text}},
                ]
                actor = subprocess.run([str(args.runtime.resolve()), "--module", "milo.desktop.office_worker",
                                        "--home", str(home)],
                                       input="".join(json.dumps(m) + "\n" for m in messages), text=True,
                                       encoding="utf-8", capture_output=True, timeout=35)
                replies = [json.loads(line) for line in actor.stdout.splitlines()]
                assert actor.returncode == 0 and len(replies) == 2, actor.stdout + actor.stderr
                assert all(reply.get("ok") for reply in replies), replies
                for reply in replies:
                    generated = Path(reply["result"]["path"])
                    with zipfile.ZipFile(generated) as archive:
                        assert archive.testzip() is None
                        assert "content.xml" in archive.namelist()
                checks.append("packaged Office actor and bundled bridge create real Calc and Writer documents")
            for source in (result["path"], document["path"]):
                shutil.copy2(source, output / Path(source).name)
        finally:
            # Only this test's unique, temporary LibreOffice profile is closed.
            owned = []
            for process in psutil.process_iter(["cmdline"]):
                try:
                    if profile_flag in (process.info["cmdline"] or []):
                        process.terminate()
                        owned.append(process)
                except psutil.Error:
                    pass
            _, alive = psutil.wait_procs(owned, timeout=3)
            for process in alive:
                process.kill()
            psutil.wait_procs(alive, timeout=2)
    (output / "results.json").write_text(json.dumps({"checks": checks, "passed": len(checks)}, indent=2), encoding="utf-8")
    print(json.dumps({"passed": len(checks), "checks": checks, "output": str(output)}))


if __name__ == "__main__":
    main()
