"""Exercise dedicated, disposable Excel/Word COM instances; never opens user documents."""
from __future__ import annotations
import json
from pathlib import Path
import pythoncom
import win32com.client
from milo.desktop._office import WindowsOffice


def main():
    pythoncom.CoInitialize()
    apps = {}
    checks = []
    def call(program, create, operation):
        if program not in apps:
            apps[program] = win32com.client.DispatchEx(program)
            apps[program].DisplayAlerts = False
        return operation(apps[program])
    office = WindowsOffice(call)
    try:
        args = dict(app="Microsoft Excel", new_document=True, rows=[["Day", "Total"], ["Monday", 42],
                      ["Formula", "=SUM(B2:B2)"]], header=True, decimals="B2:B3", fill="header blue")
        office.describe("sheet_write", args)
        result = office.run("sheet_write", args)
        excel = apps["Excel.Application"]
        sheet = excel.ActiveSheet
        assert sheet.Range("A1").Value2 == "Day"
        assert sheet.Range("B2").Value2 == 42
        assert sheet.Range("B3").Value2 == 42
        assert bool(sheet.Range("A1").Font.Bold)
        checks.append("real Excel bulk cells, formula, header and formatting")
        read = office.run("sheet_read", dict(app="Microsoft Excel", range="A1:B3"))
        assert "Monday" in read["text"] and "SUM" in read["text"]
        checks.append("real Excel values and formula readback")
        edit = dict(app="Microsoft Excel", rows=[[84]], start="B2")
        office.describe("sheet_write", edit)
        office.run("sheet_write", edit)
        assert sheet.Range("B2").Value2 == 84
        checks.append("real Excel existing target verification and update")
        office.run("write_document", dict(app="Microsoft Word", text="Milo disposable document. Grüße!"))
        assert "Milo disposable document. Grüße!" in apps["Word.Application"].ActiveDocument.Content.Text
        checks.append("real Word Unicode document creation")
        output = Path("build/office-e2e-windows.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(dict(ok=True, checks=checks), indent=2), encoding="utf-8")
        print(output.read_text(encoding="utf-8"))
    finally:
        for program, app in apps.items():
            try:
                collection = app.Workbooks if program.startswith("Excel") else app.Documents
                for index in range(collection.Count, 0, -1):
                    collection.Item(index).Close(False if program.startswith("Excel") else 0)
                app.Quit()
            except Exception:
                pass
        apps.clear()
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    main()
