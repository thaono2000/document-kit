from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from .util import run, which, DocumentKitError

class CBM:
    def __init__(self, command: str = "codebase-memory-mcp", timeout: int = 600):
        self.command = command
        self.timeout = timeout

    def available(self) -> bool:
        return which(self.command) is not None

    def invoke(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.available():
            raise DocumentKitError(f"CBM command not found: {self.command}")
        cmd = [self.command, "cli", "--quiet", tool, "--format", "json"]
        payload = json.dumps(args or {}, ensure_ascii=False) if args else None
        cp = run(cmd, input_text=payload, timeout=self.timeout)
        raw = cp.stdout.strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DocumentKitError(f"CBM returned invalid JSON for {tool}: {raw[:500]}") from exc

    def index_repository(self, repo_path: Path) -> dict[str, Any]:
        return self.invoke("index_repository", {"repo_path": str(repo_path)})

    def list_projects(self) -> dict[str, Any]:
        if not self.available():
            raise DocumentKitError(f"CBM command not found: {self.command}")
        cp = run([self.command, "cli", "--quiet", "list_projects", "--format", "json"], timeout=self.timeout)
        return json.loads(cp.stdout or "{}")

    def detect_changes(self, project: str, before_sha: str, depth: int = 5) -> dict[str, Any]:
        # CBM's branch scope accepts a git rev as base_branch on current releases.
        # Fall back to an empty result if an installed build rejects it; git file diff
        # is still passed to the agent so correctness does not depend on this call.
        try:
            return self.invoke("detect_changes", {
                "project": project,
                "scope": "branch",
                "base_branch": before_sha,
                "depth": depth,
            })
        except Exception as exc:
            return {"_warning": str(exc), "changed_symbols": [], "impacted_symbols": []}

    def architecture(self, project: str) -> dict[str, Any]:
        try:
            return self.invoke("get_architecture", {"project": project, "aspects": ["all"]})
        except Exception as exc:
            return {"_warning": str(exc)}

    def routes(self, project: str, max_rows: int = 10000) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        page = 500
        while len(rows) < max_rows:
            res = self.invoke("search_graph", {
                "project": project,
                "label": "Route",
                "limit": page,
                "offset": offset,
            })
            candidates = res.get("results") or res.get("nodes") or []
            if not isinstance(candidates, list):
                break
            rows.extend(x for x in candidates if isinstance(x, dict))
            if len(candidates) < page:
                break
            offset += page
        # Keep a stable compact representation for snapshot/diff.
        compact = []
        for r in rows[:max_rows]:
            compact.append({
                "name": r.get("name") or r.get("route") or r.get("qualified_name") or "",
                "method": r.get("method") or r.get("http_method") or "",
                "path": r.get("path") or r.get("route_path") or "",
                "qualified_name": r.get("qualified_name") or "",
                "file": r.get("file") or r.get("file_path") or "",
            })
        return compact
