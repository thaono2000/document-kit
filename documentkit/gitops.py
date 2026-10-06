from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .util import run, DocumentKitError

SOURCE_EXTENSIONS = {
    ".php", ".ts", ".tsx", ".js", ".jsx", ".vue", ".py", ".go", ".java", ".kt", ".kts",
    ".cs", ".rb", ".rs", ".c", ".h", ".cpp", ".hpp", ".swift", ".dart", ".sql", ".graphql",
    ".gql", ".proto", ".yaml", ".yml", ".json", ".toml"
}


@dataclass
class PullResult:
    before: str
    after: str
    changed: bool
    stdout: str
    changed_files: list[dict]


def _git(repo: Path, *args: str, check: bool = True):
    return run(["git", "-C", str(repo), *args], check=check)


def is_git_repo(repo: Path) -> bool:
    return _git(repo, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0


def current_branch(repo: Path) -> str:
    return _git(repo, "branch", "--show-current").stdout.strip()


def head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def short_head(repo: Path) -> str:
    return _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()


def dirty(repo: Path) -> list[str]:
    return [x for x in _git(repo, "status", "--porcelain").stdout.splitlines() if x.strip()]


def unresolved(repo: Path) -> list[str]:
    out = _git(repo, "diff", "--name-only", "--diff-filter=U").stdout
    return [x for x in out.splitlines() if x.strip()]


def changed_files(repo: Path, before: str, after: str) -> list[dict]:
    if not before or not after or before == after:
        return []
    out = _git(repo, "diff", "--name-status", "--find-renames", f"{before}..{after}").stdout
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            rows.append({"status": status, "old_path": parts[1], "path": parts[2]})
        elif len(parts) >= 2:
            rows.append({"status": status, "path": parts[1]})
    return rows


def has_potential_logic_changes(rows: list[dict]) -> bool:
    for row in rows:
        p = Path(row.get("path", ""))
        if p.suffix.lower() in SOURCE_EXTENSIONS:
            low = p.name.lower()
            if low in {"package-lock.json", "composer.lock", "yarn.lock", "pnpm-lock.yaml"}:
                continue
            return True
    return False


def capture_heads(repositories, *, require_clean: bool = True) -> dict[str, str]:
    """Capture an immutable analysis snapshot for all configured repositories."""
    snap: dict[str, str] = {}
    problems: list[str] = []
    for repo in repositories:
        if not repo.path.is_dir() or not is_git_repo(repo.path):
            problems.append(f"{repo.name}: not a Git repository at {repo.path}")
            continue
        if require_clean:
            rows = dirty(repo.path)
            if rows:
                problems.append(f"{repo.name}: dirty worktree: " + "; ".join(rows[:8]))
        unresolved_rows = unresolved(repo.path)
        if unresolved_rows:
            problems.append(f"{repo.name}: unresolved conflicts: " + ", ".join(unresolved_rows[:8]))
        snap[repo.name] = head(repo.path)
    if problems:
        raise DocumentKitError("Source snapshot is not safe for high-trust analysis:\n" + "\n".join(problems))
    return snap


def assert_heads_unchanged(repositories, expected: dict[str, str], *, require_clean: bool = True) -> None:
    problems: list[str] = []
    for repo in repositories:
        want = expected.get(repo.name)
        if want is None:
            problems.append(f"{repo.name}: missing expected commit in source snapshot")
            continue
        got = head(repo.path)
        if got != want:
            problems.append(f"{repo.name}: HEAD changed during analysis ({want[:12]} -> {got[:12]})")
        if require_clean:
            rows = dirty(repo.path)
            if rows:
                problems.append(f"{repo.name}: worktree became dirty during analysis")
        if unresolved(repo.path):
            problems.append(f"{repo.name}: unresolved conflict appeared during analysis")
    if problems:
        raise DocumentKitError("Source changed while documentation was being generated; publication aborted:\n" + "\n".join(problems))


def pull(repo: Path, remote: str, branch: str, *, require_clean: bool) -> PullResult:
    if require_clean:
        d = dirty(repo)
        if d:
            raise DocumentKitError(
                "Working tree is not clean. High-trust documentation sync refuses to mix local edits with a pull.\n"
                + "\n".join(d[:20])
            )
    before = head(repo)
    cp = _git(repo, "pull", "--ff-only", remote, branch, check=False)
    if cp.returncode != 0:
        raise DocumentKitError("git pull failed; documentation was not touched.\n" + (cp.stderr.strip() or cp.stdout.strip()))
    if unresolved(repo):
        raise DocumentKitError("Pull left unresolved conflicts; documentation was not touched.")
    after = head(repo)
    return PullResult(
        before=before,
        after=after,
        changed=(before != after),
        stdout=cp.stdout.strip(),
        changed_files=changed_files(repo, before, after),
    )
