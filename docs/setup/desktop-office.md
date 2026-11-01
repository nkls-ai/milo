# Documents and spreadsheets on Windows and Linux

Milo's `sheet_write`, `sheet_read` and `write_document` tools use the same
validation and approval flow on every desktop. The Windows/Linux app receives
structured values and formatting, rather than generated AppleScript. The Mac
app continues to use its existing Office and document integrations.

## Windows with Microsoft Office

The desktop adapter can create a new Excel workbook, read the active worksheet,
and update the active worksheet's values, formulas, header, bold ranges,
background/text colors, currency formats and decimal formats. It can also
create a new Word document containing the requested text.

For an existing workbook, open Excel and select the worksheet first. Milo reads
the target before changing it. Replacing populated cells keeps the existing
confirmation gate. The app checks the workbook, worksheet and target content
again before writing; if anything changed, it refuses and asks the helper to
read the target again. A table is written with one COM array assignment, rather
than one cross-process call per cell. Calls are bounded to 2,000 cells.

Ordinary formulas such as `=SUM(B2:B9)` work. Supported functions come from an
allowlist of common calculation, lookup, date and text functions. External
workbook references, DDE, custom executable functions and network/link functions
are refused. Literal cell text
remains text. There is no arbitrary VBA, PowerShell or shell execution behind
these structured tools.

Microsoft Office must be installed for live Excel operations. No Office process
or user document is closed or saved automatically. New Word documents and Excel
workbooks remain visible for review and saving.

Office operations run in a separate actor process. The desktop stays responsive
if an Office dialog waits for attention. Stop cancels the actor, and an operation
that does not answer within 15 seconds is stopped. Because an Office call may
already have applied part of a change, Milo asks you to inspect the document
before retrying rather than replaying a timed-out operation.

Live Office changes currently use Milo's recorded helper Undo flow. The Mac's automatic Excel workbook-copy
restore is AppleScript-specific and has not been ported to COM/UNO; do not rely on a guaranteed one-click
workbook rollback on Windows/Linux. Text-field Undo and protected file undo use their portable implementations.

## Live LibreOffice on Linux

Install LibreOffice Calc, LibreOffice Writer and the distribution's `python3-uno`
package. On Ubuntu these are `libreoffice-calc`, `libreoffice-writer` and
`python3-uno`. The standalone app uses `/usr/bin/python3` for UNO, so its bundled
Python does not need to match the distribution's Python ABI.

Milo opens a separate LibreOffice instance for its workspace. The random local
pipe name is stored in the private `~/Milo/run/libreoffice.json` file, and its
profile lives in `~/Milo/state/libreoffice/`. New Calc and Writer documents are
saved with unique names under `~/Milo/work/created/` before the operation returns.
These windows are real LibreOffice windows; they survive Milo's Stop or Quit,
and a later Milo process can reconnect to them.

Live reading and editing apply to documents in **Milo's LibreOffice instance**.
Milo does not silently attach to an arbitrary LibreOffice instance using your
normal profile. Bring the workbook in Milo's instance to the front before
working with several Calc documents. Existing document, sheet, range and content
are checked against the preceding description before a write. If the target
changed, the write is refused. Existing workbook changes remain unsaved for you
to review and save; unrelated user edits are never saved automatically.

Calc receives a bulk array of values and formulas, with literal text escaped.
The same bounds and formula allowlist as the Windows implementation apply.
Supported styles include bold headers/ranges, fill and text colors, currency and
two-decimal formats. Writer accepts Unicode text and paragraph breaks. Factory
documents are opened with macros disabled. Office calls run in the cancellable
actor, so a stalled UNO call cannot freeze the desktop.

## Portable new files

When the live Office application or UNO bridge is unavailable, Milo can create
new `.xlsx` and `.docx` files under `~/Milo/work/created/`. File names are unique;
existing documents are not overwritten. Spreadsheets preserve values, formulas
and the supported formatting. Word-compatible documents preserve text and
paragraph breaks.

For LibreOffice, Milo opens the file in Calc or Writer when LibreOffice is on
PATH. Otherwise it asks the operating system to open the generated file with
the associated document application. If opening is unavailable, the result
provides the saved path and says to open it yourself.

This fallback creates new files. It does not claim to have edited an existing
window. An existing workbook request without its live integration fails
explicitly.

## Verification

```sh
uv run --project brain pytest brain/tests/desktop/test_office.py brain/tests/desktop/test_office_actor.py brain/tests/services/test_office_hands.py
uv run --project brain pytest brain/tests/desktop/test_office_uno.py
uv run --project brain python scripts/uno-office-e2e.py --output build/uno-office-e2e
```

The tests cover fake-COM operations, stale-target refusal, the existing approval
gate, literal text and formula guards. Generated `.xlsx` and `.docx` files are
reopened to verify their actual values and formatting. Fake-COM tests do not
claim validation against a particular installed Microsoft Office version.
The Windows integration check in `scripts/office-e2e.py` additionally passed
against the installed Excel and Word: bulk values and formulas, styles,
readback, an existing target update, and Unicode Word document creation. It
creates dedicated test instances and closes only its own disposable documents.

The Linux UNO check uses a unique temporary profile and disposable documents,
without a model account or personal documents. It checks actual Calc values,
formula calculation, literal text, styles, target-change refusal, reconnecting,
and saved Unicode Writer content. Only that test profile is terminated at the
end. Its generated ODS/ODT files and check results are copied to the output folder.
On 2026-11-01, this check passed all seven checks in Ubuntu 20.04 under WSL2 with
LibreOffice 6.4.7.2: managed ODS creation, calculated bulk data, literal text,
styles, stale-target refusal, existing updates/reconnection, and Unicode Writer
output. The run's evidence is `build/uno-office-e2e/results.json`; rerun the
command above to verify another installation.
