from __future__ import annotations
from datetime import datetime
from pathlib import Path
from .util import atomic_write_text

def append_changelog(path: Path, repo: str, branch: str, before: str, after: str, rows: list[dict]) -> None:
    if not rows:
        return
    current = path.read_text(encoding="utf-8") if path.is_file() else "# Documentation Changelog\n\n"
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    block = [f"## {stamp}", "", f"Repository: `{repo}`  ", f"Branch: `{branch}`  ", f"Revision: `{before[:12]}` → `{after[:12]}`", ""]
    for row in rows:
        block.append(f"### {str(row.get('type','changed')).upper()} — {row.get('title','Documentation change')}")
        block.append("")
        block.append(str(row.get("summary", "")).strip())
        ev = row.get("evidence") or []
        if ev:
            block.append("")
            block.append("Evidence:")
            for e in ev:
                block.append(f"- `{e.get('repo','')}` — `{e.get('path','')}`")
        block.append("")
    atomic_write_text(path, current.rstrip() + "\n\n" + "\n".join(block).rstrip() + "\n")
