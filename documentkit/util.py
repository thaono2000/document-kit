from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

class DocumentKitError(RuntimeError):
    pass


def run(cmd: list[str], *, cwd: Path | None = None, input_text: str | None = None,
        timeout: int | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if check and cp.returncode != 0:
        raise DocumentKitError(
            "command failed ({}): {}\n{}".format(cp.returncode, " ".join(cmd), cp.stderr.strip() or cp.stdout.strip())
        )
    return cp


def which(command: str) -> str | None:
    return shutil.which(command)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def extract_json_object(text: str) -> dict[str, Any]:
    s = text.strip()
    # Strip common fenced wrapper.
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.S | re.I)
    if m:
        s = m.group(1)
    else:
        first, last = s.find("{"), s.rfind("}")
        if first >= 0 and last > first:
            s = s[first:last + 1]
    try:
        value = json.loads(s)
    except Exception as exc:
        raise DocumentKitError(f"Cursor output is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DocumentKitError("Cursor output JSON must be an object")
    return value
