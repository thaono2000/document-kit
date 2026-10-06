from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent import CursorAgent
from .cbm import CBM
from .changelog import append_changelog
from .config import Config, Repository
from .evidence import EvidenceStore
from .gitops import current_branch, head, pull as git_pull, has_potential_logic_changes, is_git_repo
from .prompts import incremental_prompt, build_prompt
from .specops import ensure_doc_ids, affected_by_audit, apply_patch
from .state import load_state, save_state, diff_routes
from .util import atomic_write_json, load_json, DocumentKitError
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


def _commit_cache(cfg: Config, work: Path) -> None:
    cfg.cache_dir.parent.mkdir(parents=True, exist_ok=True)
    backup = cfg.cache_dir.with_name(cfg.cache_dir.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    if cfg.cache_dir.exists():
        os.replace(cfg.cache_dir, backup)
    try:
        shutil.copytree(work, cfg.cache_dir)
    except Exception:
        if cfg.cache_dir.exists():
            shutil.rmtree(cfg.cache_dir)
        if backup.exists():
            os.replace(backup, cfg.cache_dir)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _render(cfg: Config) -> None:
    # Reuse the battle-tested V3 renderer as a module script.
    import subprocess, sys
    cmd = [sys.executable, str(Path(__file__).with_name("render_spec.py")), str(cfg.spec_json), "--md", str(cfg.markdown)]
    if cfg.xlsx:
        cmd.extend(["--xlsx", str(cfg.xlsx)])
    cp = subprocess.run(cmd, text=True, capture_output=True)
    if cp.returncode != 0:
        raise DocumentKitError("render failed: " + (cp.stderr.strip() or cp.stdout.strip()))


def _write_context(cfg: Config, name: str, data: dict[str, Any]) -> Path:
    run_dir = cfg.state_dir / "runs" / name
    run_dir.mkdir(parents=True, exist_ok=True)
    p = run_dir / "context.json"
    atomic_write_json(p, data)
    return p


def _snapshot_doc_files(cfg: Config) -> dict[Path, bytes | None]:
    targets = [cfg.spec_json, cfg.markdown, cfg.changelog] + ([cfg.xlsx] if cfg.xlsx else [])
    return {p: p.read_bytes() if p and p.is_file() else None for p in targets if p}


def _restore_doc_files(snapshot: dict[Path, bytes | None]) -> None:
    for p, data in snapshot.items():
        if data is None:
            if p.exists():
                p.unlink()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)


def _normalize_full_spec_refs(spec: dict, store: EvidenceStore) -> dict:
    spec = ensure_doc_ids(copy.deepcopy(spec))
    for module in spec.get("modules", []) or []:
        for feat in module.get("chuc_nang", []) or []:
            refs = []
            for ref in feat.get("evidence_refs", []) or []:
                if isinstance(ref, str):
                    refs.append(ref)
                elif isinstance(ref, dict):
                    refs.append(store.key_for_identity(str(ref.get("repo","")), str(ref.get("path","")), str(ref.get("symbol",""))))
            feat["evidence_refs"] = refs
    return spec


def doctor(cfg: Config) -> dict[str, Any]:
    cbm = CBM(cfg.cbm_command)
    agent = CursorAgent(cfg.agent_command, cfg.workspace, cfg.agent_model, cfg.agent_timeout_seconds)
    repos = []
    for r in cfg.repositories:
        repos.append({"name": r.name, "path": str(r.path), "exists": r.path.is_dir(), "git": is_git_repo(r.path) if r.path.is_dir() else False})
    return {
        "config": str(cfg.config_path),
        "workspace": str(cfg.workspace),
        "cbm_available": cbm.available() if cfg.cbm_enabled else None,
        "cursor_agent_available": agent.available(),
        "spec_exists": cfg.spec_json.is_file(),
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
        saved_status = saved.get("status")
        if saved_status == "NEEDS_REVIEW" and saved.get("pending_commit") == sha:
            s = "NEEDS_REVIEW"
        elif branch not in cfg.allowed_branches:
            s = "OUTSIDE_TRIGGER_BRANCH"
        elif not verified:
            s = "UNINITIALIZED"
        elif verified == sha:
            s = "VERIFIED"
        else:
            s = "SOURCE_AHEAD_OF_DOCUMENTATION"
        rows.append({"repo": repo.name, "branch": branch, "head": sha, "verified_commit": verified, "status": s})
    return {"project": cfg.project_name, "repositories": rows}


def initial_build(cfg: Config, *, plan_only: bool = False) -> dict[str, Any]:
    if cfg.spec_json.is_file() and not plan_only:
        raise DocumentKitError("Initial build is allowed only when spec.json does not exist. After initialization, documentation updates only through document-kit pull on allowed branches.")
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    store = EvidenceStore(cfg.cache_dir, repo_roots(cfg))
    cbm = CBM(cfg.cbm_command)
    if cfg.cbm_enabled and not cbm.available():
        raise DocumentKitError("CBM-first is enabled but codebase-memory-mcp is not installed/on PATH")
    repo_ctx = []
    state = load_state(cfg.state_dir)
    for repo in cfg.repositories:
        if cfg.cbm_enabled:
            cbm.index_repository(repo.path)
            routes = cbm.routes(repo.cbm_project or repo.name)
            arch = cbm.architecture(repo.cbm_project or repo.name)
        else:
            routes, arch = [], {}
        repo_ctx.append({"name": repo.name, "path": str(repo.path), "branch": current_branch(repo.path), "commit": head(repo.path), "routes": routes, "architecture": arch})
    run_name = "build-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    context = {
        "mode": "full_build",
        "project": cfg.project_name,
        "workspace": str(cfg.workspace),
        "repositories": repo_ctx,
        "cache_index": str(store.index_path),
        "output_spec": str(cfg.spec_json),
        "rules": {"cbm_first": True, "source_verification": "required", "grouping_shortcut": False, "symbol_cache": True},
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
    with tempfile.TemporaryDirectory(prefix="document-kit-build-") as td:
        work_cache, txn_store = _clone_cache_for_transaction(cfg, Path(td))
        for ev in result.get("evidence_updates", []) or []:
            txn_store.put(ev)
        spec = result.get("full_spec")
        if not isinstance(spec, dict):
            raise DocumentKitError("full build agent did not return full_spec")
        spec = _normalize_full_spec_refs(spec, txn_store)
        errors = validate_spec(spec, repo_roots(cfg), txn_store, require_evidence=True)
        if errors:
            atomic_write_json(ctx_path.parent / "validation-errors.json", {"errors": errors, "proposed_spec": spec})
            return {"status": "needs_review", "context": str(ctx_path), "validation_errors": errors}
        cfg.spec_json.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(cfg.spec_json, spec)
        _render(cfg)
        _commit_cache(cfg, work_cache)
    for repo, rc in zip(cfg.repositories, repo_ctx):
        state["repositories"].setdefault(repo.name, {})
        state["repositories"][repo.name].update({
            "branch": rc["branch"], "verified_commit": rc["commit"], "routes": rc["routes"]
        })
    save_state(cfg.state_dir, state)
    return {"status": "updated", "spec": str(cfg.spec_json), "markdown": str(cfg.markdown)}


def pull_and_update(cfg: Config, repo: Repository, remote: str, branch: str, *, plan_only: bool = False) -> dict[str, Any]:
    actual_branch = current_branch(repo.path)
    if cfg.require_current_branch_match and actual_branch != branch:
        raise DocumentKitError(
            f"Current branch is '{actual_branch}' but requested pull source is '{branch}'. "
            "High-trust mode requires them to match."
        )
    allowed = branch in cfg.allowed_branches
    pull_result = git_pull(repo.path, remote, branch, require_clean=cfg.require_clean_worktree)
    result: dict[str, Any] = {
        "repo": repo.name,
        "branch": branch,
        "before": pull_result.before,
        "after": pull_result.after,
        "pull_output": pull_result.stdout,
        "source_changed": pull_result.changed,
        "docs_triggered": False,
    }
    if not allowed:
        result["reason"] = "branch_not_allowed_for_documentation_update"
        return result
    if not pull_result.changed:
        result["reason"] = "already_up_to_date"
        return result

    # At this point a qualifying pull succeeded and changed HEAD: this is the ONLY automatic update trigger.
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    store = EvidenceStore(cfg.cache_dir, repo_roots(cfg))
    audit = store.audit()
    spec = ensure_doc_ids(load_json(cfg.spec_json, {"modules": [], "api": []}) or {"modules": [], "api": []})
    stale = affected_by_audit(spec, audit)

    cbm = CBM(cfg.cbm_command)
    if cfg.cbm_enabled:
        if not cbm.available():
            raise DocumentKitError("Qualifying pull changed source but CBM-first is enabled and CBM is unavailable")
        cbm.index_repository(repo.path)
        changes = cbm.detect_changes(repo.cbm_project or repo.name, pull_result.before, cfg.cbm_depth)
        new_routes = cbm.routes(repo.cbm_project or repo.name)
    else:
        changes, new_routes = {}, []

    state = load_state(cfg.state_dir)
    old_routes = state.get("repositories", {}).get(repo.name, {}).get("routes", [])
    added_routes, removed_routes = diff_routes(old_routes, new_routes)
    needs_analysis = bool(stale or added_routes or removed_routes or has_potential_logic_changes(pull_result.changed_files))

    run_name = f"pull-{repo.name}-{pull_result.after[:12]}"
    context = {
        "mode": "incremental_after_pull",
        "project": cfg.project_name,
        "trigger": {"type": "git_pull", "remote": remote, "branch": branch, "before": pull_result.before, "after": pull_result.after},
        "repository": {"name": repo.name, "path": str(repo.path), "cbm_project": repo.cbm_project or repo.name},
        "changed_files": pull_result.changed_files,
        "cbm_detect_changes": changes,
        "routes_added": added_routes,
        "routes_removed": removed_routes,
        "stale_or_untracked_spec_sections": stale,
        "existing_spec": str(cfg.spec_json),
        "cache_index": str(store.index_path),
        "cache_symbols_dir": str(store.symbols_dir),
        "rules": {
            "cbm_first": True,
            "source_verification": "mandatory",
            "grouping_shortcut": False,
            "symbol_cache_reuse": True,
            "update_only_affected_docs": True,
        }
    }
    ctx_path = _write_context(cfg, run_name, context)
    result["context"] = str(ctx_path)
    if not needs_analysis:
        state["repositories"].setdefault(repo.name, {})
        state["repositories"][repo.name].update({"branch": branch, "verified_commit": pull_result.after, "routes": new_routes})
        save_state(cfg.state_dir, state)
        result.update({"docs_triggered": False, "reason": "no_business_logic_impact_detected"})
        return result
    result["docs_triggered"] = True
    if plan_only or not cfg.auto_update:
        result["status"] = "planned"
        return result

    snapshot = _snapshot_doc_files(cfg)
    agent = CursorAgent(cfg.agent_command, cfg.workspace, cfg.agent_model, cfg.agent_timeout_seconds)
    patch = agent.ask_json(incremental_prompt(ctx_path))
    atomic_write_json(ctx_path.parent / "agent-patch.json", patch)
    if patch.get("status") != "ok":
        atomic_write_json(ctx_path.parent / "needs-review.json", patch)
        state["repositories"].setdefault(repo.name, {})
        state["repositories"][repo.name].update({
            "branch": branch, "pending_commit": pull_result.after, "status": "NEEDS_REVIEW", "routes": new_routes
        })
        save_state(cfg.state_dir, state)
        result.update({"status": "needs_review", "review_items": patch.get("review_items", [])})
        return result

    try:
        with tempfile.TemporaryDirectory(prefix="document-kit-pull-") as td:
            work_cache, txn_store = _clone_cache_for_transaction(cfg, Path(td))
            proposed = apply_patch(spec, patch, txn_store)
            errors = validate_spec(proposed, repo_roots(cfg), txn_store, require_evidence=True)
            if errors:
                atomic_write_json(ctx_path.parent / "validation-errors.json", {"errors": errors, "proposed_spec": proposed})
                raise DocumentKitError("proposed documentation failed validation: " + "; ".join(errors[:8]))
            atomic_write_json(cfg.spec_json, proposed)
            _render(cfg)
            append_changelog(cfg.changelog, repo.name, branch, pull_result.before, pull_result.after, patch.get("changelog", []) or [])
            _commit_cache(cfg, work_cache)
    except Exception:
        _restore_doc_files(snapshot)
        raise

    state["repositories"].setdefault(repo.name, {})
    state["repositories"][repo.name].update({
        "branch": branch,
        "verified_commit": pull_result.after,
        "status": "VERIFIED",
        "routes": new_routes,
    })
    state["repositories"][repo.name].pop("pending_commit", None)
    save_state(cfg.state_dir, state)
    result.update({"status": "updated", "spec": str(cfg.spec_json), "markdown": str(cfg.markdown)})
    return result
