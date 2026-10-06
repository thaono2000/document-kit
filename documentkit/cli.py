from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import discover_config, load_config, DEFAULT_ALLOWED
from .core import doctor, status, initial_build, pull_and_update
from .gitops import is_git_repo
from .util import DocumentKitError, atomic_write_text


def _find_git_repos(workspace: Path) -> list[Path]:
    repos = []
    for child in sorted(workspace.iterdir()):
        if child.is_dir() and (child / ".git").exists():
            repos.append(child)
    return repos


def init_workspace(workspace: Path, output: Path) -> None:
    repos = _find_git_repos(workspace)
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
        "allowed_branches = [\"develop\", \"dev\", \"staging\", \"stg\", \"production\", \"prod\"]",
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
        'xlsx = "docs/SPEC.xlsx"',
        'changelog = "docs/CHANGELOG.md"',
        "",
    ]
    for repo in repos:
        lines += [
            "[[repositories]]",
            f'name = "{repo.name}"',
            f'path = "{repo.name}"',
            f'cbm_project = "{repo.name}"',
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
    sp.add_parser("doctor")
    sp.add_parser("status")
    pb = sp.add_parser("build", help="One-time full documentation build")
    pb.add_argument("--plan-only", action="store_true")
    pp = sp.add_parser("pull", help="git pull; auto-update docs only for allowed branches")
    pp.add_argument("remote", nargs="?", default="origin")
    pp.add_argument("branch")
    pp.add_argument("--repo", help="Configured repository name; otherwise inferred from cwd")
    pp.add_argument("--plan-only", action="store_true")
    pa = sp.add_parser("install-git-alias", help="Install local/global git alias that calls document-kit pull")
    pa.add_argument("--name", default="rpull")
    pa.add_argument("--global", dest="global_", action="store_true")
    return p


def _load(args):
    path = Path(args.config).expanduser().resolve() if args.config else discover_config()
    if not path:
        raise DocumentKitError("document-kit.toml not found. Run: document-kit init --workspace <workspace>")
    return load_config(path)


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "init":
            workspace = Path(args.workspace).expanduser().resolve()
            output = Path(args.output).expanduser()
            if not output.is_absolute():
                output = workspace / output
            init_workspace(workspace, output.resolve())
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
            repo = cfg.repo_by_name(args.repo) if args.repo else cfg.repo_for_path(Path.cwd())
            if not repo:
                raise DocumentKitError("Cannot infer configured repository from current directory. Use --repo <name>.")
            print(json.dumps(pull_and_update(cfg, repo, args.remote, args.branch, plan_only=args.plan_only), ensure_ascii=False, indent=2)); return
    except DocumentKitError as exc:
        print(f"document-kit: {exc}", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
