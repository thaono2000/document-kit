from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent import CursorAgent
from .cbm import CBM
from .changelog import append_changelog
from .config import Config, Repository
from .evidence import EvidenceStore
from .gitops import (
    assert_heads_unchanged,
    capture_heads,
    changed_files as git_changed_files,
    current_branch,
    dirty,
    head,
    has_potential_logic_changes,
    is_git_repo,
    pull as git_pull,
)
from .html_render import render_html
from .prompts import incremental_prompt, build_prompt
from .render_spec import render_md, render_xlsx
from .specops import ensure_doc_ids, affected_by_audit, apply_patch
from .state import load_state, save_state, diff_routes
from .util import atomic_write_json, load_json, DocumentKitError, which
from .validation import validate_spec


def repo_roots(cfg: Config) -> dict[str, Path]:
    return {r.name: r.path for r in cfg.repositories}


def _clone_cache_for_transaction(cfg: Config, txn_root: Path) -> tuple[Path, EvidenceStore]:
    work = txn_root / "cache"
    if cfg.cache_dir.exists():
        shutil.copytree(cfg.cache_dir, work)
    else:
        work.mkdir(parents=True, exist_ok=True)
    return work, EvidenceStore(work, repo_roots(cfg))


def _normalize_refs(value: Any, store: EvidenceStore) -> Any:
    if not isinstance(value, list):
        return value
    out = []
    for ref in value:
        if isinstance(ref, str):
            out.append(ref)
        elif isinstance(ref, dict):
            out.append(store.key_for_identity(str(ref.get("repo", "")), str(ref.get("path", "")), str(ref.get("symbol", ""))))
        else:
            out.append(ref)
    return out


def _normalize_full_spec_refs(spec: dict, store: EvidenceStore) -> dict:
    spec = ensure_doc_ids(copy.deepcopy(spec))
    for module in spec.get("modules", []) or []:
        for feat in module.get("chuc_nang", []) or []:
            feat["evidence_refs"] = _normalize_refs(feat.get("evidence_refs", []), store)
    for key in ("api", "mo_hinh_du_lieu", "rui_ro", "diagrams", "ui_images"):
        for row in spec.get(key, []) or []:
            if isinstance(row, dict) and "evidence_refs" in row:
                row["evidence_refs"] = _normalize_refs(row.get("evidence_refs", []), store)
    return spec


def _staged_paths(cfg: Config, txn_root: Path) -> dict[Path, Path]:
    targets = [cfg.spec_json, cfg.markdown, cfg.html, cfg.changelog]
    if cfg.xlsx:
        targets.append(cfg.xlsx)
    out: dict[Path, Path] = {}
    for idx, target in enumerate(targets):
        staged = txn_root / "outputs" / f"{idx:02d}-{target.name}"
        staged.parent.mkdir(parents=True, exist_ok=True)
        out[target] = staged
    return out


def _render_staged(cfg: Config, spec: dict[str, Any], staged: dict[Path, Path]) -> None:
    atomic_write_json(staged[cfg.spec_json], spec)
    staged[cfg.markdown].write_text(render_md(spec, md_path=str(staged[cfg.markdown])), encoding="utf-8")
    staged[cfg.html].write_text(render_html(spec), encoding="utf-8")
    if cfg.xlsx:
        render_xlsx(spec, str(staged[cfg.xlsx]))


def _prepare_changelog(
    cfg: Config,
    staged: dict[Path, Path],
    *,
    repo: str | None = None,
    branch: str | None = None,
    before: str | None = None,
    after: str | None = None,
    rows: list[dict] | None = None,
) -> None:
    target = staged[cfg.changelog]
    if cfg.changelog.is_file():
        shutil.copy2(cfg.changelog, target)
    else:
        target.write_text("# Documentation Changelog\n\n", encoding="utf-8")
    if repo and branch and before and after and rows:
        append_changelog(target, repo, branch, before, after, rows)


def _publish_transaction(cfg: Config, staged_files: dict[Path, Path], staged_cache: Path) -> None:
    """Publish all docs + evidence cache as one rollback-capable transaction.

    Every replacement is first copied beside its destination, then old paths are
    renamed to backups. If any replace fails, all already-replaced outputs are
    restored. State is intentionally committed only *after* this succeeds.
    """
    token = uuid.uuid4().hex[:10]
    file_new: dict[Path, Path] = {}
    file_backup: dict[Path, Path] = {}
    cache_new = cfg.cache_dir.with_name(cfg.cache_dir.name + f".new-{token}")
    cache_backup = cfg.cache_dir.with_name(cfg.cache_dir.name + f".bak-{token}")
    replaced_files: list[Path] = []
    cache_replaced = False
    published = False

    try:
        for target, staged in staged_files.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            new = target.with_name(target.name + f".new-{token}")
            if new.exists():
                new.unlink()
            shutil.copy2(staged, new)
            file_new[target] = new
            file_backup[target] = target.with_name(target.name + f".bak-{token}")

        if cache_new.exists():
            shutil.rmtree(cache_new)
        cache_new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged_cache, cache_new)

        for target, new in file_new.items():
            backup = file_backup[target]
            if backup.exists():
                backup.unlink()
            if target.exists():
                os.replace(target, backup)
            replaced_files.append(target)
            os.replace(new, target)

        if cache_backup.exists():
            shutil.rmtree(cache_backup)
        if cfg.cache_dir.exists():
            os.replace(cfg.cache_dir, cache_backup)
        os.replace(cache_new, cfg.cache_dir)
        cache_replaced = True
        published = True

    except Exception:
        if cache_replaced and cfg.cache_dir.exists():
            shutil.rmtree(cfg.cache_dir)
        if cache_backup.exists():
            os.replace(cache_backup, cfg.cache_dir)
        for target in reversed(replaced_files):
            backup = file_backup[target]
            if target.exists():
                target.unlink()
            if backup.exists():
                os.replace(backup, target)
        raise
    finally:
        for new in file_new.values():
            if new.exists():
                new.unlink()
        # Keep surviving backups if rollback itself fails, so recovery remains possible.
        if published:
            for backup in file_backup.values():
                if backup.exists():
                    backup.unlink()
        if cache_new.exists():
            shutil.rmtree(cache_new)
        if published and cache_backup.exists():
            shutil.rmtree(cache_backup)


def _write_context(cfg: Config, name: str, data: dict[str, Any]) -> Path:
    run_dir = cfg.state_dir / "runs" / name
    run_dir.mkdir(parents=True, exist_ok=True)
    p = run_dir / "context.json"
    atomic_write_json(p, data)
    return p


def _annotate_routes(repo_name: str, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for route in routes or []:
        row = dict(route)
        row["repo"] = repo_name
        out.append(row)
    return out


def _all_discovered_routes(cfg: Config, state: dict[str, Any], override_repo: str | None = None, override_routes: list[dict] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for repo in cfg.repositories:
        if repo.name == override_repo:
            routes = override_routes or []
        else:
            routes = state.get("repositories", {}).get(repo.name, {}).get("routes", []) or []
        out.extend(_annotate_routes(repo.name, routes))
    return out


def _set_pending(
    cfg: Config,
    repo: Repository,
    *,
    commit: str,
    base_commit: str,
    branch: str,
    remote: str,
    reason: str,
    run_context: str | None,
    pending_routes: list[dict] | None = None,
) -> None:
    state = load_state(cfg.state_dir)
    row = state["repositories"].setdefault(repo.name, {})
    row["status"] = "NEEDS_REVIEW"
    row["branch"] = branch
    row["pending_commit"] = commit  # compatibility with V1 status readers
    row["pending"] = {
        "commit": commit,
        "base_commit": base_commit,
        "branch": branch,
        "remote": remote,
        "reason": reason,
        "run_context": run_context,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "routes": pending_routes or [],
    }
    save_state(cfg.state_dir, state)


def _clear_pending(row: dict[str, Any]) -> None:
    row.pop("pending", None)
    row.pop("pending_commit", None)


def doctor(cfg: Config) -> dict[str, Any]:
    cbm = CBM(cfg.cbm_command)
    agent = CursorAgent(cfg.agent_command, cfg.workspace, cfg.agent_model, cfg.agent_timeout_seconds)
    repos = []
    for r in cfg.repositories:
        exists = r.path.is_dir()
        git = is_git_repo(r.path) if exists else False
        repo_head = None
        repo_dirty: list[str] = []
        head_error = None
        if git:
            try:
                repo_head = head(r.path)
                repo_dirty = dirty(r.path)
            except Exception as exc:
                head_error = str(exc)
        repos.append({
            "name": r.name,
            "path": str(r.path),
            "exists": exists,
            "git": git,
            "head": repo_head,
            "dirty": repo_dirty,
            "head_error": head_error,
        })
    xlsx_dependency = None
    if cfg.xlsx:
        xlsx_dependency = importlib.util.find_spec("openpyxl") is not None
    checks = {
        "python_3_11_plus": sys.version_info >= (3, 11),
        "git_available": which("git") is not None,
        "cbm_available": cbm.available() if cfg.cbm_enabled else None,
        "cursor_agent_available": agent.available(),
        "openpyxl_available": xlsx_dependency,
    }
    return {
        "ok": all(v is not False for v in checks.values()) and all(x["git"] and not x.get("head_error") for x in repos),
        "config": str(cfg.config_path),
        "workspace": str(cfg.workspace),
        "checks": checks,
        "spec_exists": cfg.spec_json.is_file(),
        "html_exists": cfg.html.is_file(),
        "repositories": repos,
    }


def status(cfg: Config) -> dict[str, Any]:
    state = load_state(cfg.state_dir)
    rows = []
    for repo in cfg.repositories:
        if not repo.path.is_dir():
            rows.append({"repo": repo.name, "status": "MISSING"})
            continue
        branch = current_branch(repo.path)
        sha = head(repo.path)
        saved = state.get("repositories", {}).get(repo.name, {})
        verified = saved.get("verified_commit")
        pending = saved.get("pending") or ({} if not saved.get("pending_commit") else {"commit": saved.get("pending_commit")})
        if pending:
            s = "NEEDS_REVIEW" if pending.get("commit") == sha else "SOURCE_AHEAD_OF_DOCUMENTATION"
        elif branch not in cfg.allowed_branches:
            s = "OUTSIDE_TRIGGER_BRANCH"
        elif not verified:
            s = "UNINITIALIZED"
        elif verified == sha:
            s = "VERIFIED"
        else:
            s = "SOURCE_AHEAD_OF_DOCUMENTATION"
        rows.append({
            "repo": repo.name, "branch": branch, "head": sha,
            "verified_commit": verified, "pending": pending or None, "status": s,
        })
    return {"project": cfg.project_name, "repositories": rows}


def initial_build(cfg: Config, *, plan_only: bool = False) -> dict[str, Any]:
    if cfg.spec_json.is_file() and not plan_only:
        raise DocumentKitError("Initial build is allowed only when spec.json does not exist. Use document-kit pull/retry after initialization.")
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    source_snapshot = capture_heads(cfg.repositories, require_clean=cfg.require_clean_worktree)
    cbm = CBM(cfg.cbm_command)
    if cfg.cbm_enabled and not cbm.available():
        raise DocumentKitError("CBM-first is enabled but codebase-memory-mcp is not installed/on PATH")

    repo_ctx = []
    all_routes: list[dict[str, Any]] = []
    for repo in cfg.repositories:
        if cfg.cbm_enabled:
            cbm.index_repository(repo.path)
            routes = cbm.routes(repo.cbm_project or repo.name)
            arch = cbm.architecture(repo.cbm_project or repo.name)
        else:
            routes, arch = [], {}
        all_routes.extend(_annotate_routes(repo.name, routes))
        repo_ctx.append({
            "name": repo.name, "path": str(repo.path), "branch": current_branch(repo.path),
            "commit": source_snapshot[repo.name], "routes": routes, "architecture": arch,
        })

    run_name = "build-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    context = {
        "mode": "full_build", "project": cfg.project_name, "workspace": str(cfg.workspace),
        "repositories": repo_ctx, "source_snapshot": source_snapshot,
        "cache_index": str(cfg.cache_dir / "index.json"), "output_spec": str(cfg.spec_json),
        "rules": {
            "cbm_first": True, "source_verification": "required", "grouping_shortcut": False,
            "symbol_cache": True, "entry_point_coverage": "required", "diagrams": "only_when_helpful_and_source_backed",
        },
    }
    ctx_path = _write_context(cfg, run_name, context)
    if plan_only:
        return {"status": "planned", "context": str(ctx_path)}

    agent = CursorAgent(cfg.agent_command, cfg.workspace, cfg.agent_model, cfg.agent_timeout_seconds)
    result = agent.ask_json(build_prompt(ctx_path))
    atomic_write_json(ctx_path.parent / "agent-result.json", result)
    if result.get("status") != "ok":
        atomic_write_json(ctx_path.parent / "needs-review.json", result)
        return {"status": "needs_review", "context": str(ctx_path), "review_items": result.get("review_items", [])}

    try:
        with tempfile.TemporaryDirectory(prefix="txn-build-", dir=cfg.state_dir) as td:
            txn_root = Path(td)
            work_cache, txn_store = _clone_cache_for_transaction(cfg, txn_root)
            for ev in result.get("evidence_updates", []) or []:
                txn_store.put(ev)
            spec = result.get("full_spec")
            if not isinstance(spec, dict):
                raise DocumentKitError("full build agent did not return full_spec")
            spec = _normalize_full_spec_refs(spec, txn_store)
            spec.setdefault("phan_tich", {})["source_snapshot"] = source_snapshot
            errors = validate_spec(spec, repo_roots(cfg), txn_store, require_evidence=True, discovered_routes=all_routes)
            if errors:
                atomic_write_json(ctx_path.parent / "validation-errors.json", {"errors": errors, "proposed_spec": spec})
                return {"status": "needs_review", "context": str(ctx_path), "validation_errors": errors}
            assert_heads_unchanged(cfg.repositories, source_snapshot, require_clean=cfg.require_clean_worktree)
            staged = _staged_paths(cfg, txn_root)
            _render_staged(cfg, spec, staged)
            _prepare_changelog(cfg, staged)
            assert_heads_unchanged(cfg.repositories, source_snapshot, require_clean=cfg.require_clean_worktree)
            _publish_transaction(cfg, staged, work_cache)
    except Exception as exc:
        atomic_write_json(ctx_path.parent / "build-error.json", {"error": str(exc)})
        raise

    state = load_state(cfg.state_dir)
    for repo, rc in zip(cfg.repositories, repo_ctx):
        row = state["repositories"].setdefault(repo.name, {})
        row.update({"branch": rc["branch"], "verified_commit": rc["commit"], "routes": rc["routes"], "status": "VERIFIED"})
        _clear_pending(row)
    save_state(cfg.state_dir, state)
    return {"status": "updated", "spec": str(cfg.spec_json), "markdown": str(cfg.markdown), "html": str(cfg.html)}


def _analyze_incremental(
    cfg: Config,
    repo: Repository,
    *,
    remote: str,
    branch: str,
    base_commit: str,
    target_commit: str,
    changed_files: list[dict[str, Any]],
    trigger_type: str,
    pull_output: str = "",
    plan_only: bool = False,
) -> dict[str, Any]:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    if not plan_only and cfg.auto_update:
        # Persist before discovery/agent calls: any failure must remain retryable.
        _set_pending(cfg, repo, commit=target_commit, base_commit=base_commit, branch=branch,
                     remote=remote, reason="analysis_not_completed", run_context=None)
    source_snapshot = capture_heads(cfg.repositories, require_clean=cfg.require_clean_worktree)
    if source_snapshot.get(repo.name) != target_commit:
        raise DocumentKitError(f"{repo.name}: target commit {target_commit[:12]} is not current HEAD {source_snapshot.get(repo.name,'')[:12]}")

    state = load_state(cfg.state_dir)
    store = EvidenceStore(cfg.cache_dir, repo_roots(cfg))
    audit = store.audit()
    spec = ensure_doc_ids(load_json(cfg.spec_json, {"modules": [], "api": []}) or {"modules": [], "api": []})
    stale = affected_by_audit(spec, audit)

    cbm = CBM(cfg.cbm_command)
    if cfg.cbm_enabled:
        if not cbm.available():
            raise DocumentKitError("Documentation update requires CBM-first but CBM is unavailable")
        cbm.index_repository(repo.path)
        changes = cbm.detect_changes(repo.cbm_project or repo.name, base_commit, cfg.cbm_depth)
        new_routes = cbm.routes(repo.cbm_project or repo.name)
    else:
        changes, new_routes = {}, []

    saved = state.get("repositories", {}).get(repo.name, {})
    old_routes = saved.get("routes", []) or []
    added_routes, removed_routes = diff_routes(old_routes, new_routes)
    needs_analysis = bool(stale or added_routes or removed_routes or has_potential_logic_changes(changed_files))
    discovered_routes = _all_discovered_routes(cfg, state, repo.name, new_routes)

    run_name = f"{trigger_type}-{repo.name}-{target_commit[:12]}-{datetime.now().strftime('%H%M%S')}"
    context = {
        "mode": "incremental_after_pull" if trigger_type == "pull" else "incremental_retry",
        "project": cfg.project_name,
        "trigger": {"type": trigger_type, "remote": remote, "branch": branch, "before": base_commit, "after": target_commit, "pull_output": pull_output},
        "repository": {"name": repo.name, "path": str(repo.path), "cbm_project": repo.cbm_project or repo.name},
        "source_snapshot": source_snapshot,
        "changed_files": changed_files,
        "cbm_detect_changes": changes,
        "routes_added": added_routes,
        "routes_removed": removed_routes,
        "stale_or_untracked_spec_sections": stale,
        "existing_spec": str(cfg.spec_json),
        "cache_index": str(store.index_path),
        "cache_symbols_dir": str(store.symbols_dir),
        "rules": {
            "cbm_first": True, "source_verification": "mandatory", "grouping_shortcut": False,
            "symbol_cache_reuse": True, "update_only_affected_docs": True,
            "entry_point_coverage": "required", "removed_items_are_historical": True,
            "diagrams": "only_when_helpful_and_source_backed",
        },
    }
    ctx_path = _write_context(cfg, run_name, context)
    out: dict[str, Any] = {
        "repo": repo.name, "branch": branch, "before": base_commit, "after": target_commit,
        "docs_triggered": needs_analysis, "context": str(ctx_path), "trigger": trigger_type,
    }

    if not needs_analysis:
        assert_heads_unchanged(cfg.repositories, source_snapshot, require_clean=cfg.require_clean_worktree)
        row = state["repositories"].setdefault(repo.name, {})
        row.update({"branch": branch, "verified_commit": target_commit, "routes": new_routes, "status": "VERIFIED"})
        _clear_pending(row)
        save_state(cfg.state_dir, state)
        out.update({"status": "verified", "reason": "no_business_logic_impact_detected"})
        return out

    if plan_only or not cfg.auto_update:
        out["status"] = "planned"
        return out

    agent = CursorAgent(cfg.agent_command, cfg.workspace, cfg.agent_model, cfg.agent_timeout_seconds)
    patch = agent.ask_json(incremental_prompt(ctx_path))
    atomic_write_json(ctx_path.parent / "agent-patch.json", patch)
    if patch.get("status") != "ok":
        atomic_write_json(ctx_path.parent / "needs-review.json", patch)
        _set_pending(cfg, repo, commit=target_commit, base_commit=base_commit, branch=branch, remote=remote,
                     reason="agent_needs_review", run_context=str(ctx_path), pending_routes=new_routes)
        out.update({"status": "needs_review", "review_items": patch.get("review_items", []), "retry_command": f"document-kit retry --repo {repo.name}"})
        return out

    try:
        with tempfile.TemporaryDirectory(prefix="txn-update-", dir=cfg.state_dir) as td:
            txn_root = Path(td)
            work_cache, txn_store = _clone_cache_for_transaction(cfg, txn_root)
            proposed = apply_patch(spec, patch, txn_store)
            proposed.setdefault("phan_tich", {})["source_snapshot"] = source_snapshot
            errors = validate_spec(proposed, repo_roots(cfg), txn_store, require_evidence=True, discovered_routes=discovered_routes)
            if errors:
                atomic_write_json(ctx_path.parent / "validation-errors.json", {"errors": errors, "proposed_spec": proposed})
                _set_pending(cfg, repo, commit=target_commit, base_commit=base_commit, branch=branch, remote=remote,
                             reason="validation_failed", run_context=str(ctx_path), pending_routes=new_routes)
                out.update({"status": "needs_review", "validation_errors": errors, "retry_command": f"document-kit retry --repo {repo.name}"})
                return out

            assert_heads_unchanged(cfg.repositories, source_snapshot, require_clean=cfg.require_clean_worktree)
            staged = _staged_paths(cfg, txn_root)
            _render_staged(cfg, proposed, staged)
            _prepare_changelog(cfg, staged, repo=repo.name, branch=branch, before=base_commit, after=target_commit, rows=patch.get("changelog", []) or [])
            assert_heads_unchanged(cfg.repositories, source_snapshot, require_clean=cfg.require_clean_worktree)
            _publish_transaction(cfg, staged, work_cache)
    except Exception as exc:
        atomic_write_json(ctx_path.parent / "publication-error.json", {"error": str(exc)})
        _set_pending(cfg, repo, commit=target_commit, base_commit=base_commit, branch=branch, remote=remote,
                     reason="publication_failed", run_context=str(ctx_path), pending_routes=new_routes)
        raise DocumentKitError(f"documentation publication failed; previous outputs/cache were preserved. Retry with: document-kit retry --repo {repo.name}. Cause: {exc}") from exc

    state = load_state(cfg.state_dir)
    row = state["repositories"].setdefault(repo.name, {})
    row.update({"branch": branch, "verified_commit": target_commit, "status": "VERIFIED", "routes": new_routes})
    _clear_pending(row)
    save_state(cfg.state_dir, state)
    out.update({"status": "updated", "spec": str(cfg.spec_json), "markdown": str(cfg.markdown), "html": str(cfg.html)})
    return out


def pull_and_update(cfg: Config, repo: Repository, remote: str, branch: str, *, plan_only: bool = False) -> dict[str, Any]:
    actual_branch = current_branch(repo.path)
    if cfg.require_current_branch_match and actual_branch != branch:
        raise DocumentKitError(f"Current branch is '{actual_branch}' but requested pull source is '{branch}'. High-trust mode requires them to match.")
    allowed = branch in cfg.allowed_branches
    pull_result = git_pull(repo.path, remote, branch, require_clean=cfg.require_clean_worktree)
    result: dict[str, Any] = {
        "repo": repo.name, "branch": branch, "before": pull_result.before, "after": pull_result.after,
        "pull_output": pull_result.stdout, "source_changed": pull_result.changed, "docs_triggered": False,
    }
    if not allowed:
        result["reason"] = "branch_not_allowed_for_documentation_update"
        return result

    state = load_state(cfg.state_dir)
    saved = state.get("repositories", {}).get(repo.name, {})
    pending = saved.get("pending") or {}
    if not pull_result.changed:
        if pending and pending.get("commit") == pull_result.after:
            result.update({"reason": "already_up_to_date_but_documentation_pending", "status": "needs_review", "retry_command": f"document-kit retry --repo {repo.name}"})
        else:
            result["reason"] = "already_up_to_date"
        return result

    # If documentation was already behind, analyze the whole range from the last
    # verified commit rather than only the newest pull delta.
    base_commit = str(saved.get("verified_commit") or pending.get("base_commit") or pull_result.before)
    full_changed = git_changed_files(repo.path, base_commit, pull_result.after)
    result.update(_analyze_incremental(
        cfg, repo, remote=remote, branch=branch, base_commit=base_commit, target_commit=pull_result.after,
        changed_files=full_changed, trigger_type="pull", pull_output=pull_result.stdout, plan_only=plan_only,
    ))
    result["source_changed"] = True
    return result


def retry_pending(cfg: Config, repo: Repository, *, plan_only: bool = False) -> dict[str, Any]:
    state = load_state(cfg.state_dir)
    saved = state.get("repositories", {}).get(repo.name, {})
    pending = saved.get("pending") or {}
    if not pending:
        raise DocumentKitError(f"{repo.name}: no pending documentation update to retry")
    target = str(pending.get("commit") or "")
    current = head(repo.path)
    if current != target:
        raise DocumentKitError(
            f"{repo.name}: pending documentation targets {target[:12]}, but current HEAD is {current[:12]}. "
            "Pull/update through DocumentKit first so pending state can be superseded safely."
        )
    branch = str(pending.get("branch") or current_branch(repo.path))
    if branch not in cfg.allowed_branches:
        raise DocumentKitError(f"{repo.name}: pending branch '{branch}' is not allowlisted")
    if cfg.require_current_branch_match and current_branch(repo.path) != branch:
        raise DocumentKitError(f"{repo.name}: checkout pending branch '{branch}' before retry")
    base = str(pending.get("base_commit") or saved.get("verified_commit") or "")
    if not base:
        raise DocumentKitError(f"{repo.name}: pending update has no base commit")
    remote = str(pending.get("remote") or "origin")
    rows = git_changed_files(repo.path, base, target)
    return _analyze_incremental(
        cfg, repo, remote=remote, branch=branch, base_commit=base, target_commit=target,
        changed_files=rows, trigger_type="retry", plan_only=plan_only,
    )
