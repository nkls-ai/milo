"""LibreOffice's live desktop implementation, isolated from the bundled Python ABI.

The system's python3-uno talks to a private per-workspace LibreOffice instance.
Only normalized data crosses stdin; no scripts, macro names or arbitrary UNO
method names come from the model. The Office actor owns operation cancellation.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from milo import system
from milo.core.secrets import read_secret
from milo.services import documents, sheets

from ._native_types import NativeError

CALC = "LibreOffice Calc"
WRITER = "LibreOffice Writer"
TIMEOUT_S = 12.0


class LibreOffice:
    def __init__(self, home: Path, *, transport: Callable[[dict], dict] | None = None, headless: bool = False):
        self.home = Path(home).expanduser().resolve()
        self._transport = transport
        self._headless = headless
        self._expected: dict | None = None

    def _supported(self, tool: str, args: dict):
        from ._office import OfficeUnavailable
        wanted = WRITER if tool == "write_document" else CALC
        if args.get("app") != wanted:
            raise OfficeUnavailable(f"Live Linux Office operations use {wanted} in Milo's LibreOffice instance.")

    def _connection(self) -> dict:
        from ._office import OfficeUnavailable
        python = Path("/usr/bin/python3")
        # The distro wrapper may run javaldx before starting Office. That probe
        # can scan mounted Windows drives in WSL; Calc/Writer need no Java.
        direct = (Path("/usr/lib/libreoffice/program/soffice.bin"),
                  Path("/usr/lib64/libreoffice/program/soffice.bin"))
        executable = next((path for path in direct if path.is_file()), Path("/usr/bin/libreoffice"))
        if not executable.is_file():
            found = shutil.which("libreoffice") or shutil.which("soffice")
            executable = Path(found) if found else executable
        if not python.is_file() or not executable.is_file():
            raise OfficeUnavailable("Live LibreOffice needs LibreOffice Calc/Writer and python3-uno installed. "
                                    "New documents can still be created as portable files.")
        run = self.home / "run"
        run.mkdir(parents=True, exist_ok=True)
        system.make_private(run, 0o700)
        record = run / "libreoffice.json"
        if not record.exists():
            try:
                fd = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as output:
                    system.make_private(output.fileno(), 0o600)
                    json.dump({"pipe": "milo-" + secrets.token_hex(24)}, output)
        try:
            pipe = json.loads(read_secret(record, "Milo's LibreOffice connection"))["pipe"]
        except (ValueError, KeyError, OSError) as error:
            raise NativeError("Milo's private LibreOffice connection record could not be read.") from error
        if not isinstance(pipe, str) or not re.fullmatch(r"milo-[a-f0-9]{48}", pipe):
            raise NativeError("Milo's LibreOffice connection record is invalid.")
        profile = self.home / "state" / "libreoffice"
        if profile.is_symlink() or profile.is_junction():
            raise NativeError("The LibreOffice profile must be a real folder.")
        profile.mkdir(parents=True, exist_ok=True)
        system.make_private(profile, 0o700)
        return {"pipe": pipe, "profile": profile.as_uri(), "executable": str(executable), "headless": self._headless}

    def _call(self, packet: dict) -> dict:
        if self._transport is not None:
            return self._transport(packet)
        from ._office import OfficeUnavailable
        bridge = Path(__file__).with_name("uno_bridge.py")
        request = {**self._connection(), "home": str(self.home), **packet}
        try:
            result = subprocess.run(["/usr/bin/python3", "-I", str(bridge)],
                input=json.dumps(request, ensure_ascii=False, allow_nan=False), text=True, encoding="utf-8",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT_S, check=False)
        except subprocess.TimeoutExpired:
            raise NativeError("LibreOffice did not answer in time. Inspect the document before trying again; "
                              "part of the operation may have completed.") from None
        except OSError:
            raise OfficeUnavailable("The system Python LibreOffice bridge could not start.") from None
        try:
            answer = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise OfficeUnavailable("LibreOffice's Python bridge is unavailable. Install python3-uno for the system Python.") from None
        if not answer.get("ok"):
            error = OfficeUnavailable if answer.get("unavailable") else NativeError
            raise error(str(answer.get("error") or "LibreOffice could not complete the operation."))
        return answer["result"]

    @staticmethod
    def _styles(args: dict, block) -> list[dict]:
        from ._office import _range
        result = []
        for reference in sheets.ranges(args.get("bold", "")):
            result.append({"range": _range(reference), "bold": True})
        if args.get("header") and block:
            end = sheets.column_letters(sheets.cell(block.last)[0]) + str(sheets.cell(block.first)[1])
            result.append({"range": block.first + ":" + end, "bold": True})
        for key, number in (("money", sheets.excel_money(args.get("locale", ""))), ("decimals", "0.00")):
            for reference in sheets.ranges(args.get(key, "")):
                result.append({"range": _range(reference), "number_format": number})
        for key, property_name in (("fill", "background"), ("font_color", "font_color")):
            for reference, (red, green, blue) in sheets.colours(args.get(key, "")):
                result.append({"range": reference if reference in sheets.WHOLE else _range(reference),
                               property_name: (red << 16) | (green << 8) | blue})
        return result

    def _sheet_packet(self, args: dict, *, writing: bool) -> dict:
        from ._office import _range, _validate
        block = _validate(args) if writing else None
        reference = block.range if block else _range(args["range"]) if args.get("range") else ""
        packet = {"range": reference, "has_rows": bool(block)}
        if writing:
            packet.update(rows=args.get("rows") or [], styles=self._styles(args, block), new=bool(args.get("new_document")))
        return packet

    def describe(self, tool: str, args: dict) -> dict:
        self._supported(tool, args)
        if tool == "write_document":
            if len(str(args.get("text", ""))) > documents.MAX_CHARS:
                raise NativeError("That document is too long for one operation.")
            return {"app": WRITER, "new": True}
        packet = self._sheet_packet(args, writing=tool == "sheet_write")
        if args.get("new_document"):
            return {"app": CALC, "new": True}
        result = self._call({"operation": "describe", **packet})
        snapshot = result.pop("snapshot")
        self._expected = {"target": dict(result), "snapshot": snapshot}
        from ._office import _fingerprint
        result["fingerprint"] = _fingerprint([self._expected["target"], snapshot])
        return result

    def run(self, tool: str, args: dict) -> dict:
        self._supported(tool, args)
        if tool == "write_document":
            text = str(args.get("text", ""))
            if len(text) > documents.MAX_CHARS:
                raise NativeError("That document is too long for one operation.")
            from ._office import new_document_path
            path = new_document_path(self.home, ".odt")
            return self._call({"operation": "writer", "text": text, "path": str(path)})
        if tool == "sheet_read":
            result = self._call({"operation": "read", **self._sheet_packet(args, writing=False)})
            return {"document": result["document"], "summary": f"LibreOffice Calc, “{result['document']}”, sheet “{result['sheet']}”",
                    "text": sheets.table_text({"first": result["range"].split(":")[0], "rows": result["rows"]})}
        packet = self._sheet_packet(args, writing=True)
        if packet["new"]:
            from ._office import new_document_path
            packet["path"] = str(new_document_path(self.home, ".ods"))
        elif self._expected is None:
            raise NativeError("Read the LibreOffice target again before writing.")
        else:
            packet["expected"] = self._expected
        result = self._call({"operation": "write", **packet})
        self._expected = None
        return result
