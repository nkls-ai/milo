"""Changes one setting in config.toml in place, so the user's comments and layout stay as they were."""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path


def set_value(path: Path, section: str, key: str, value: str) -> None:
    """Set `key` in `[section]` to the string `value`: replace its value (keeping a trailing comment), or add
    the key under the section, or add the section at the end. Raises ValueError, and writes nothing, if
    the file isn't valid TOML afterwards."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines(keepends=True)
    quoted = json.dumps(value, ensure_ascii=False)
    header = re.compile(rf"^\s*\[\s*{re.escape(section)}\s*\]\s*(#.*)?$")
    entry = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*)("(?:[^"\\]|\\.)*"|\'[^\']*\'|[^#\s]+)(.*)$', re.DOTALL)
    start = next((i for i, line in enumerate(lines) if header.match(line)), None)
    if start is None:
        lines += [] if not lines or lines[-1].endswith("\n") else ["\n"]
        lines += ["\n", f"[{section}]\n", f"{key} = {quoted}\n"]
    else:
        end = next((i for i in range(start + 1, len(lines)) if re.match(r"^\s*\[", lines[i])), len(lines))
        found = next((i for i in range(start + 1, end) if entry.match(lines[i])), None)
        if found is not None:
            lines[found] = entry.sub(lambda m: m.group(1) + quoted + m.group(3), lines[found])
        else:
            last = max((i for i in range(start, end) if lines[i].strip()), default=start)
            if not lines[last].endswith("\n"):
                lines[last] += "\n"
            lines.insert(last + 1, f"{key} = {quoted}\n")
    new = "".join(lines)
    try:
        written = tomllib.loads(new)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{path} would not be valid TOML: {e}") from None
    if written.get(section, {}).get(key) != value:
        raise ValueError(f"could not set [{section}] {key} in {path}")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new, encoding="utf-8")
    os.replace(tmp, path)
