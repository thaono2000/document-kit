from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from .evidence import EvidenceStore
from .specops import REMOVED_STATUS

VALID_CONF = {"cao", "trung bình", "thấp"}
ANCHOR_RE = re.compile(r"^(.+):(\d+)(?:-(\d+))?$")
MERMAID_PREFIXES = (
    "graph ", "flowchart ", "sequenceDiagram", "stateDiagram", "stateDiagram-v2",
    "classDiagram", "erDiagram", "journey", "gantt", "mindmap", "timeline"
)


def _where(prefix: str, name: Any) -> str:
    n = str(name or "").strip()
    return f"{prefix} / {n}" if n else prefix


def _is_removed(row: dict[str, Any]) -> bool:
    return str(row.get("trang_thai", "")).strip() == REMOVED_STATUS


def _validate_evidence_refs(
    where: str,
    row: dict[str, Any],
    audit: dict[str, dict[str, Any]],
    errors: list[str],
    *,
    required: bool,
    allow_historical_stale: bool = False,
) -> None:
    refs = row.get("evidence_refs") or []
    if required and not refs:
        errors.append(f"{where}: missing evidence_refs")
        return
    for ref in refs:
        if not isinstance(ref, str):
            errors.append(f"{where}: evidence ref must be cache key")
            continue
        st = audit.get(ref)
        if not st:
            if not allow_historical_stale:
                errors.append(f"{where}: evidence {ref} not found")
        elif st.get("status") != "valid" and not allow_historical_stale:
            errors.append(f"{where}: evidence {ref} stale ({st.get('reason')})")


def _validate_anchors(
    where: str,
    anchors: Any,
    repo_roots: dict[str, Path],
    errors: list[str],
    *,
    required: bool,
    allow_historical_missing: bool = False,
) -> None:
    rows = anchors if isinstance(anchors, list) else ([anchors] if anchors else [])
    if required and not rows:
        errors.append(f"{where}: missing source anchors")
        return
    for anchor in rows:
        if not isinstance(anchor, dict):
            errors.append(f"{where}: anchor must be {{repo,path}}")
            continue
        repo = str(anchor.get("repo", ""))
        text = str(anchor.get("path", ""))
        m = ANCHOR_RE.match(text)
        if repo not in repo_roots or not m:
            errors.append(f"{where}: invalid anchor {anchor}")
            continue
        rel, start, end = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
        p = repo_roots[repo] / rel
        if not p.is_file():
            if not allow_historical_missing:
                errors.append(f"{where}: anchor file not found {repo}:{rel}")
            continue
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            count = sum(1 for _ in fh)
        if (start < 1 or end > count) and not allow_historical_missing:
            errors.append(f"{where}: anchor line out of range {repo}:{text}")


def _route_identity(route: dict[str, Any]) -> tuple[str, str, str]:
    method = str(route.get("method") or route.get("phuong_thuc") or "").upper().strip()
    path = str(route.get("path") or route.get("endpoint") or "").strip()
    repo = str(route.get("repo") or "").strip()
    return method, path, repo


def _api_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    method = str(row.get("phuong_thuc") or "").upper().strip()
    path = str(row.get("endpoint") or "").strip()
    repo = str(row.get("repo") or "").strip()
    if not repo:
        for anchor in row.get("neo", []) or []:
            if isinstance(anchor, dict) and anchor.get("repo"):
                repo = str(anchor.get("repo"))
                break
    return method, path, repo


def _coverage_errors(spec: dict[str, Any], discovered_routes: list[dict[str, Any]], errors: list[str]) -> None:
    if not discovered_routes:
        return
    active = [_api_identity(x) for x in spec.get("api", []) or [] if isinstance(x, dict) and not _is_removed(x)]
    active_any_repo = {(m, p) for m, p, _r in active}
    active_exact = {(m, p, r) for m, p, r in active if r}
    missing: list[str] = []
    for route in discovered_routes:
        method, path, repo = _route_identity(route)
        # CBM may return partial Route nodes. Only enforce coverage when it has
        # a callable HTTP identity we can deterministically compare.
        if not method or not path:
            continue
        if repo:
            if (method, path, repo) not in active_exact and (method, path) not in active_any_repo:
                missing.append(f"{repo}:{method} {path}")
        elif (method, path) not in active_any_repo:
            missing.append(f"{method} {path}")
    if missing:
        shown = ", ".join(missing[:20])
        suffix = f" (+{len(missing)-20} more)" if len(missing) > 20 else ""
        errors.append(f"entry-point coverage gap: {shown}{suffix}")


def validate_spec(
    spec: dict[str, Any],
    repo_roots: dict[str, Path],
    store: EvidenceStore,
    *,
    require_evidence: bool = True,
    discovered_routes: list[dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    modules = spec.get("modules") or []
    if not modules:
        errors.append("spec has no modules")
    audit = store.audit()

    for module in modules:
        mname = module.get("ten", "")
        features = module.get("chuc_nang", []) or []
        if not features:
            errors.append(f"module {mname}: has no functions")
        for feat in features:
            where = _where(str(mname), feat.get("ten", ""))
            removed = _is_removed(feat)
            for key in ("ten", "mo_ta"):
                if not feat.get(key):
                    errors.append(f"{where}: missing {key}")

            if removed:
                if not str(feat.get("removal_reason") or feat.get("ghi_chu") or "").strip():
                    errors.append(f"{where}: removed item must keep a removal reason")
                # Historical source/evidence may legitimately no longer resolve.
                _validate_evidence_refs(where, feat, audit, errors, required=False, allow_historical_stale=True)
                _validate_anchors(where, feat.get("neo"), repo_roots, errors, required=False, allow_historical_missing=True)
                continue

            for key in ("luong_xu_ly", "neo", "phan_quyen"):
                if not feat.get(key):
                    errors.append(f"{where}: missing {key}")
            if not feat.get("dau_vao") and not feat.get("dau_vao_mo_ta"):
                errors.append(f"{where}: missing input description")
            output = feat.get("dau_ra") or {}
            if not str(output.get("thanh_cong", "")).strip() and not [x for x in output.get("loi", []) or [] if str(x).strip()]:
                errors.append(f"{where}: output is empty")
            conf = str(feat.get("do_tin_cay", "")).lower().strip()
            if conf not in VALID_CONF:
                errors.append(f"{where}: confidence must be cao/trung bình/thấp")
            if conf == "thấp" and not str(feat.get("ghi_chu", "")).strip():
                errors.append(f"{where}: low confidence requires explanation")
            _validate_evidence_refs(where, feat, audit, errors, required=require_evidence)
            _validate_anchors(where, feat.get("neo"), repo_roots, errors, required=True)

    for api in spec.get("api", []) or []:
        if not isinstance(api, dict):
            errors.append("api item must be an object")
            continue
        where = f"API {str(api.get('phuong_thuc','')).upper()} {api.get('endpoint','')}"
        removed = _is_removed(api)
        for key in ("phuong_thuc", "endpoint", "chuc_nang"):
            if not str(api.get(key, "")).strip():
                errors.append(f"{where}: missing {key}")
        if removed:
            if not str(api.get("removal_reason") or api.get("ghi_chu") or "").strip():
                errors.append(f"{where}: removed API must keep a removal reason")
            _validate_evidence_refs(where, api, audit, errors, required=False, allow_historical_stale=True)
            _validate_anchors(where, api.get("neo"), repo_roots, errors, required=False, allow_historical_missing=True)
            continue
        if not str(api.get("quyen", "")).strip():
            errors.append(f"{where}: missing authorization/quyen")
        _validate_evidence_refs(where, api, audit, errors, required=require_evidence)
        _validate_anchors(where, api.get("neo"), repo_roots, errors, required=True)

    for model in spec.get("mo_hinh_du_lieu", []) or []:
        if not isinstance(model, dict):
            errors.append("data model item must be an object")
            continue
        where = _where("Data model", model.get("ten"))
        if not str(model.get("ten", "")).strip():
            errors.append(f"{where}: missing name")
        _validate_evidence_refs(where, model, audit, errors, required=require_evidence)
        _validate_anchors(where, model.get("neo"), repo_roots, errors, required=True)

    for risk in spec.get("rui_ro", []) or []:
        if not isinstance(risk, dict):
            errors.append("risk item must be an object")
            continue
        where = _where("Risk", risk.get("hang_muc") or risk.get("van_de"))
        for key in ("muc_do", "van_de", "anh_huong"):
            if not str(risk.get(key, "")).strip():
                errors.append(f"{where}: missing {key}")
        _validate_evidence_refs(where, risk, audit, errors, required=require_evidence)
        _validate_anchors(where, risk.get("neo"), repo_roots, errors, required=True)

    for diagram in spec.get("diagrams", []) or []:
        if not isinstance(diagram, dict):
            errors.append("diagram item must be an object")
            continue
        where = _where("Diagram", diagram.get("title"))
        for key in ("title", "type", "mermaid"):
            if not str(diagram.get(key, "")).strip():
                errors.append(f"{where}: missing {key}")
        mermaid = str(diagram.get("mermaid", "")).lstrip()
        if mermaid and not mermaid.startswith(MERMAID_PREFIXES):
            errors.append(f"{where}: mermaid source has unsupported/unknown diagram header")
        _validate_evidence_refs(where, diagram, audit, errors, required=require_evidence)
        _validate_anchors(where, diagram.get("neo"), repo_roots, errors, required=True)

    for image in spec.get("ui_images", []) or []:
        if not isinstance(image, dict):
            errors.append("ui_images item must be an object")
            continue
        where = _where("UI image", image.get("title") or image.get("path"))
        if not str(image.get("path", "")).strip():
            errors.append(f"{where}: missing path")
        if not image.get("verified", False):
            errors.append(f"{where}: UI image must be explicitly source-verified")
        _validate_evidence_refs(where, image, audit, errors, required=require_evidence)
        _validate_anchors(where, image.get("neo"), repo_roots, errors, required=True)

    _coverage_errors(spec, discovered_routes or [], errors)
    return errors
