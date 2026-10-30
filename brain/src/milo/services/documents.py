"""New text documents in TextEdit and Pages through AppleScript Milo writes himself.

Like sheets.py: the text goes in as one escaped AppleScript literal, never as code. The script makes a new
document and nothing else, so it needs no question. Pure.
"""

from __future__ import annotations

from milo.core.types import HandsError

from .sheets import literal

TEXTEDIT, PAGES = "TextEdit", "Pages"
APPS = (TEXTEDIT, PAGES)
MAX_CHARS = 100_000


def write_script(app: str, text: str) -> str:
    """Open `app`, make a new document holding `text`, and print its name as `document<TAB>name`."""
    if len(text) > MAX_CHARS:
        raise HandsError(f"That is more than {MAX_CHARS} characters; write it in parts.")
    if app == TEXTEDIT:
        make = f"  set doc to make new document with properties {{text:{literal(text)}}}\n"
    elif app == PAGES:
        make = f"  set doc to make new document\n  set body text of doc to {literal(text)}\n"
    else:
        raise HandsError(f"write_document works in {' and '.join(APPS)}, not {app!r}.")
    return (f'tell application "{app}"\n  activate\n' + make
            + '  set docName to name of doc\nend tell\nreturn "document" & tab & docName\n')
