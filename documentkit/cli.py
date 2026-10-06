from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .config import discover_config, load_config
from .core import doctor, status, initial_build, pull_and_update, retry_pending
from .util import DocumentKitError, atomic_write_text


def _find_git_repos(workspace: Path) -> list[Path]:
    repos = []
    for child in sorted(workspace.iterdir()):
        if child.is_dir() and (child / ".git").exists() and child.name != "document-kit":
            repos.append(child)
    return repos


def _parse_repo_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise DocumentKitError("--repo must use NAME=PATH")
    name, raw = value.split("=", 1)
    name = name.strip()
    if not name or not raw.strip():
        raise DocumentKitError("--repo must use non-empty NAME=PATH")
    return name, Path(raw).expanduser().resolve()


def init_workspace(workspace: Path, output: Path, explicit_repos: list[str] | None = None, auto_detect: bool = True) -> None:
    repo_rows: list[tuple[str, Path]] = []
    if auto_detect:
        repo_rows.extend((p.name, p.resolve()) for p in _find_git_repos(workspace))
    for value in explicit_repos or []:
        parsed = _parse_repo_arg(value)
        repo_rows = [x for x in repo_rows if x[0] != parsed[0]]
        repo_rows.append(parsed)

    lines = [
        "[project]",
        f'name = "{workspace.name}"',
        'workspace = "."',
        'state_dir = ".document-kit"',
        'cache_dir = ".document-kit/cache"',
        "",
        "[automation]",
        "auto_update = true",
        "require_current_branch_match = true",
        "require_clean_worktree = true",
        'allowed_branches = ["develop", "dev", "staging", "stg", "production", "prod"]',
        "",
        "[cbm]",
        "enabled = true",
        'command = "codebase-memory-mcp"',
        "depth = 5",
        "",
        "[cursor]",
        'command = "agent"',
        'model = ""',
        "timeout_seconds = 1800",
        "",
        "[outputs]",
        'spec_json = "docs/spec.json"',
        'markdown = "docs/SPEC.md"',
        'html = "docs/index.html"',
        '# XLSX is optional. Set to "docs/SPEC.xlsx" only when the team needs it.',
        'xlsx = ""',
        'changelog = "docs/CHANGELOG.md"',
        "",
    ]
    for name, path in sorted(repo_rows, key=lambda x: x[0].lower()):
        try:
            rel = path.relative_to(output.parent.resolve())
            stored_path = str(rel)
        except ValueError:
            stored_path = str(path)
        lines += [
            "[[repositories]]",
            f'name = "{name}"',
            f'path = "{stored_path}"',
            f'cbm_project = "{name}"',
            "",
        ]
    atomic_write_text(output, "\n".join(lines))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="document-kit", description="High-trust source-to-spec documentation kit")
    p.add_argument("--config", help="Path to document-kit.toml (otherwise discovered upward)")
    sp = p.add_subparsers(dest="command", required=True)

    pi = sp.add_parser("init", help="Create document-kit.toml for a workspace")
    pi.add_argument("--workspace", default=".")
    pi.add_argument("--output", default="document-kit.toml")
    pi.add_argument("--repo", action="append", default=[], metavar="NAME=PATH", help="Add/override a repository; may point outside the workspace and may be repeated")
    pi.add_argument("--no-auto-detect", action="store_true", help="Do not scan direct child Git repositories")

    sp.add_parser("doctor")
    sp.add_parser("status")

    pb = sp.add_parser("build", help="One-time full documentation build")
    pb.add_argument("--plan-only", action="store_true")

    pp = sp.add_parser("pull", help="git pull; auto-update docs only for allowed branches")
    pp.add_argument("remote", nargs="?", default="origin")
    pp.add_argument("branch")
    pp.add_argument("--repo", help="Configured repository name; otherwise inferred from cwd")
    pp.add_argument("--plan-only", action="store_true")

    pr = sp.add_parser("retry", help="Retry a pending failed documentation update without requiring another source change")
    pr.add_argument("--repo", help="Configured repository name; otherwise inferred from cwd")
    pr.add_argument("--plan-only", action="store_true")

    pa = sp.add_parser("install-git-alias", help="Install local/global git alias that calls document-kit pull")
    pa.add_argument("--name", default="rpull")
    pa.add_argument("--global", dest="global_", action="store_true")
    return p


def _load(args):
    path = Path(args.config).expanduser().resolve() if args.config else discover_config()
    if not path:
        raise DocumentKitError("document-kit.toml not found. Run: document-kit init --workspace <workspace>")
    return load_config(path)


def _resolve_repo(cfg, name: str | None):
    repo = cfg.repo_by_name(name) if name else cfg.repo_for_path(Path.cwd())
    if not repo:
        raise DocumentKitError("Cannot infer configured repository from current directory. Use --repo <name>.")
    return repo


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "init":
            workspace = Path(args.workspace).expanduser().resolve()
            output = Path(args.output).expanduser()
            if not output.is_absolute():
                output = workspace / output
            init_workspace(workspace, output.resolve(), args.repo, auto_detect=not args.no_auto_detect)
            print(f"Created {output.resolve()}")
            return
        if args.command == "install-git-alias":
            scope = ["--global"] if args.global_ else []
            cmd = ["git", "config", *scope, f"alias.{args.name}", "!document-kit pull"]
            subprocess.run(cmd, check=True)
            print(f"Installed git alias: git {args.name} <remote> <branch>")
            return

        cfg = _load(args)
        if args.command == "doctor":
            print(json.dumps(doctor(cfg), ensure_ascii=False, indent=2)); return
        if args.command == "status":
            print(json.dumps(status(cfg), ensure_ascii=False, indent=2)); return
        if args.command == "build":
            print(json.dumps(initial_build(cfg, plan_only=args.plan_only), ensure_ascii=False, indent=2)); return
        if args.command == "pull":
            repo = _resolve_repo(cfg, args.repo)
            print(json.dumps(pull_and_update(cfg, repo, args.remote, args.branch, plan_only=args.plan_only), ensure_ascii=False, indent=2)); return
        if args.command == "retry":
            repo = _resolve_repo(cfg, args.repo)
            print(json.dumps(retry_pending(cfg, repo, plan_only=args.plan_only), ensure_ascii=False, indent=2)); return
    except (DocumentKitError, ValueError) as exc:
        print(f"document-kit: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
