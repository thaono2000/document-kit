from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import tomllib

DEFAULT_ALLOWED = ["develop", "dev", "staging", "stg", "production", "prod"]


@dataclass
class Repository:
    name: str
    path: Path
    cbm_project: str | None = None


@dataclass
class Config:
    config_path: Path
    project_name: str
    workspace: Path
    state_dir: Path
    cache_dir: Path
    spec_json: Path
    markdown: Path
    html: Path
    xlsx: Path | None
    changelog: Path
    allowed_branches: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED))
    auto_update: bool = True
    require_current_branch_match: bool = True
    require_clean_worktree: bool = True
    cbm_enabled: bool = True
    cbm_command: str = "codebase-memory-mcp"
    cbm_depth: int = 5
    agent_command: str = "agent"
    agent_model: str = ""
    agent_timeout_seconds: int = 1800
    repositories: list[Repository] = field(default_factory=list)

    def repo_by_name(self, name: str) -> Repository | None:
        return next((r for r in self.repositories if r.name == name), None)

    def repo_for_path(self, path: Path) -> Repository | None:
        p = path.resolve()
        matches = []
        for repo in self.repositories:
            try:
                p.relative_to(repo.path.resolve())
                matches.append(repo)
            except ValueError:
                pass
        if not matches:
            return None
        return sorted(matches, key=lambda r: len(str(r.path.resolve())), reverse=True)[0]


def _resolve(base: Path, value: str | None, default: str) -> Path:
    raw = os.path.expanduser(value or default)
    p = Path(raw)
    return p.resolve() if p.is_absolute() else (base / p).resolve()


def load_config(path: str | Path) -> Config:
    cp = Path(path).expanduser().resolve()
    data = tomllib.loads(cp.read_text(encoding="utf-8"))
    base = cp.parent
    project = data.get("project", {})
    automation = data.get("automation", {})
    cbm = data.get("cbm", {})
    cursor = data.get("cursor", {})
    outputs = data.get("outputs", {})

    workspace = _resolve(base, project.get("workspace"), ".")
    state_dir = _resolve(base, project.get("state_dir"), ".document-kit")
    cache_dir = _resolve(base, project.get("cache_dir"), ".document-kit/cache")

    repos: list[Repository] = []
    seen_names: set[str] = set()
    for row in data.get("repositories", []):
        name = str(row["name"]).strip()
        if not name:
            raise ValueError("repository name must not be empty")
        if name in seen_names:
            raise ValueError(f"duplicate repository name: {name}")
        seen_names.add(name)
        repos.append(Repository(
            name=name,
            path=_resolve(base, row.get("path"), name),
            cbm_project=str(row.get("cbm_project") or name),
        ))

    xlsx_value = outputs.get("xlsx", "")

    return Config(
        config_path=cp,
        project_name=str(project.get("name") or base.name),
        workspace=workspace,
        state_dir=state_dir,
        cache_dir=cache_dir,
        spec_json=_resolve(base, outputs.get("spec_json"), "docs/spec.json"),
        markdown=_resolve(base, outputs.get("markdown"), "docs/SPEC.md"),
        html=_resolve(base, outputs.get("html"), "docs/index.html"),
        xlsx=_resolve(base, str(xlsx_value), "docs/SPEC.xlsx") if xlsx_value else None,
        changelog=_resolve(base, outputs.get("changelog"), "docs/CHANGELOG.md"),
        allowed_branches=[str(x) for x in automation.get("allowed_branches", DEFAULT_ALLOWED)],
        auto_update=bool(automation.get("auto_update", True)),
        require_current_branch_match=bool(automation.get("require_current_branch_match", True)),
        require_clean_worktree=bool(automation.get("require_clean_worktree", True)),
        cbm_enabled=bool(cbm.get("enabled", True)),
        cbm_command=str(cbm.get("command", "codebase-memory-mcp")),
        cbm_depth=int(cbm.get("depth", 5)),
        agent_command=str(cursor.get("command", "agent")),
        agent_model=str(cursor.get("model", "")),
        agent_timeout_seconds=int(cursor.get("timeout_seconds", 1800)),
        repositories=repos,
    )


def discover_config(start: str | Path | None = None) -> Path | None:
    env = os.environ.get("DOCUMENT_KIT_CONFIG")
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.is_file() else None
    cur = Path(start or os.getcwd()).resolve()
    for root in [cur, *cur.parents]:
        candidate = root / "document-kit.toml"
        if candidate.is_file():
            return candidate
    return None
