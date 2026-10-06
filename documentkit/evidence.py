from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from .util import atomic_write_json, load_json, DocumentKitError

SCHEMA_VERSION = 1
ANALYSIS_VERSION = "symbol-evidence-v2"

def norm_rel(path: str) -> str:
    s = str(path).replace("\\", "/").strip()
    while s.startswith("./"):
        s = s[2:]
    return s


def symbol_key(repo: str, path: str, symbol: str) -> str:
    raw = "\0".join([repo.strip(), norm_rel(path), symbol.strip()]).encode("utf-8")
    return "sym_" + hashlib.sha256(raw).hexdigest()[:24]


def _read_range(repo_root: Path, rel: str, start: int, end: int) -> str:
    p = repo_root / norm_rel(rel)
    if not p.is_file():
        raise DocumentKitError(f"source file not found: {p}")
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if start < 1 or end < start or end > len(lines):
        raise DocumentKitError(f"invalid source range {rel}:{start}-{end} (file has {len(lines)} lines)")
    return "".join(lines[start - 1:end])


def hash_body(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

class EvidenceStore:
    def __init__(self, root: Path, repo_roots: dict[str, Path]):
        self.root = root
        self.repo_roots = repo_roots
        self.symbols_dir = root / "symbols"
        self.index_path = root / "index.json"
        self.symbols_dir.mkdir(parents=True, exist_ok=True)
        self.index = load_json(self.index_path, None) or {
            "schema_version": SCHEMA_VERSION,
            "analysis_version": ANALYSIS_VERSION,
            "symbols": {},
        }
        self.index.setdefault("symbols", {})
        if not self.index_path.exists():
            self.save()

    def save(self):
        atomic_write_json(self.index_path, self.index)

    def get(self, key: str) -> dict | None:
        meta = self.index["symbols"].get(key)
        if not meta:
            return None
        p = self.root / meta.get("file", f"symbols/{key}.json")
        return load_json(p, None)

    def key_for_identity(self, repo: str, path: str, symbol: str) -> str:
        return symbol_key(repo, path, symbol)

    def validate(self, entry: dict[str, Any]) -> tuple[bool, str, str | None]:
        if entry.get("cache_schema_version") != SCHEMA_VERSION:
            return False, "cache schema mismatch", None
        if entry.get("analysis_version") != ANALYSIS_VERSION:
            return False, "analysis version mismatch", None
        repo = entry.get("repo", "")
        root = self.repo_roots.get(repo)
        if not root:
            return False, f"repo not configured: {repo}", None
        src = entry.get("source", {})
        try:
            body = _read_range(root, src.get("path", ""), int(src.get("start", 0)), int(src.get("end", 0)))
        except Exception as exc:
            return False, str(exc), None
        current = hash_body(body)
        if current != src.get("body_hash"):
            return False, "source hash changed", current
        return True, "hit", current

    def audit(self) -> dict[str, dict[str, Any]]:
        out = {}
        for key in sorted(self.index["symbols"]):
            entry = self.get(key)
            if not entry:
                out[key] = {"status": "missing", "reason": "cache file missing"}
                continue
            ok, reason, current = self.validate(entry)
            out[key] = {"status": "valid" if ok else "stale", "reason": reason, "current_hash": current, "entry": entry}
        return out

    def put(self, update: dict[str, Any]) -> str:
        repo = str(update.get("repo", "")).strip()
        path = norm_rel(update.get("path", ""))
        symbol = str(update.get("symbol", "")).strip()
        start, end = int(update.get("start", 0)), int(update.get("end", 0))
        analysis = update.get("analysis")
        if not repo or not path or not symbol or start < 1 or end < start:
            raise DocumentKitError("invalid evidence update identity/range")
        if repo not in self.repo_roots:
            raise DocumentKitError(f"evidence update references unconfigured repo: {repo}")
        if not isinstance(analysis, dict):
            raise DocumentKitError("evidence analysis must be an object")
        conf = str(analysis.get("confidence", "")).lower().strip()
        if conf not in {"high", "medium", "low", "cao", "trung bình", "thấp"}:
            raise DocumentKitError(f"invalid evidence confidence for {symbol}")
        body = _read_range(self.repo_roots[repo], path, start, end)
        key = symbol_key(repo, path, symbol)
        entry = {
            "key": key,
            "cache_schema_version": SCHEMA_VERSION,
            "analysis_version": ANALYSIS_VERSION,
            "repo": repo,
            "symbol": symbol,
            "source": {"path": path, "start": start, "end": end, "body_hash": hash_body(body)},
            "analysis": analysis,
        }
        rel = f"symbols/{key}.json"
        atomic_write_json(self.root / rel, entry)
        self.index["symbols"][key] = {"file": rel, "repo": repo, "path": path, "symbol": symbol}
        self.save()
        return key
