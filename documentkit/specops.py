from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from .evidence import EvidenceStore
from .util import DocumentKitError

REMOVED_STATUS = "REMOVED_PENDING_REVIEW"


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:48] or "item"


def ensure_doc_ids(spec: dict[str, Any]) -> dict[str, Any]:
    used = set()
    for module in spec.get("modules", []):
        for feat in module.get("chuc_nang", []):
            if feat.get("doc_id"):
                used.add(feat["doc_id"])
                continue
            base = f"{module.get('ten','')}\0{feat.get('ten','')}".encode("utf-8")
            doc_id = "doc_" + hashlib.sha256(base).hexdigest()[:16]
            i = 2
            candidate = doc_id
            while candidate in used:
                candidate = f"{doc_id}_{i}"; i += 1
            feat["doc_id"] = candidate
            used.add(candidate)
    return spec


def feature_map(spec: dict[str, Any]) -> dict[str, tuple[dict, dict]]:
    out = {}
    for module in spec.get("modules", []):
        for feat in module.get("chuc_nang", []):
            if feat.get("doc_id"):
                out[feat["doc_id"]] = (module, feat)
    return out


def affected_by_audit(spec: dict[str, Any], audit: dict[str, dict]) -> list[dict]:
    result = []
    for module in spec.get("modules", []):
        for feat in module.get("chuc_nang", []):
            # Historical evidence for removed functionality is intentionally allowed
            # to go stale/missing. It must not block unrelated future updates.
            if feat.get("trang_thai") == REMOVED_STATUS:
                continue
            refs = feat.get("evidence_refs") or []
            bad = []
            for ref in refs:
                if not isinstance(ref, str):
                    continue
                st = audit.get(ref)
                if not st or st.get("status") != "valid":
                    bad.append({"ref": ref, "status": (st or {}).get("status", "missing"), "reason": (st or {}).get("reason", "not in cache")})
            if bad or not refs:
                result.append({
                    "doc_id": feat.get("doc_id"),
                    "module": module.get("ten", ""),
                    "name": feat.get("ten", ""),
                    "reason": "stale/missing evidence" if bad else "no evidence refs",
                    "bad_evidence": bad,
                })
    return result


def _resolve_ref(ref: Any, store: EvidenceStore) -> str:
    if isinstance(ref, str):
        return ref
    if isinstance(ref, dict):
        return store.key_for_identity(str(ref.get("repo", "")), str(ref.get("path", "")), str(ref.get("symbol", "")))
    raise DocumentKitError("unsupported evidence_refs item")


def _resolve_refs_in_row(row: dict[str, Any], store: EvidenceStore) -> dict[str, Any]:
    row = copy.deepcopy(row)
    if "evidence_refs" in row:
        row["evidence_refs"] = [_resolve_ref(x, store) for x in row.get("evidence_refs", [])]
    return row


def _mark_removed(row: dict[str, Any], reason: str, removed_commit: str | None = None) -> None:
    row["trang_thai"] = REMOVED_STATUS
    row["removal_reason"] = reason
    row.setdefault("removed_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if removed_commit:
        row["removed_commit"] = removed_commit
    note = str(row.get("ghi_chu", "")).strip()
    marker = "[DocumentKit] " + reason
    if marker not in note:
        row["ghi_chu"] = (note + "\n" if note else "") + marker


def apply_patch(spec: dict[str, Any], patch: dict[str, Any], store: EvidenceStore) -> dict[str, Any]:
    out = ensure_doc_ids(copy.deepcopy(spec))
    fmap = feature_map(out)

    for ev in patch.get("evidence_updates", []) or []:
        store.put(ev)

    for row in patch.get("spec_updates", []) or []:
        doc_id = str(row.get("doc_id", ""))
        replacement = row.get("replacement")
        if doc_id not in fmap or not isinstance(replacement, dict):
            raise DocumentKitError(f"invalid spec update: {doc_id}")
        module, old = fmap[doc_id]
        replacement = _resolve_refs_in_row(replacement, store)
        replacement["doc_id"] = doc_id
        idx = module["chuc_nang"].index(old)
        module["chuc_nang"][idx] = replacement
        fmap[doc_id] = (module, replacement)

    for row in patch.get("spec_additions", []) or []:
        module_name = str(row.get("module", "")).strip()
        feat = row.get("function")
        if not module_name or not isinstance(feat, dict):
            raise DocumentKitError("invalid spec addition")
        feat = _resolve_refs_in_row(feat, store)
        module = next((m for m in out.setdefault("modules", []) if m.get("ten") == module_name), None)
        if module is None:
            module = {"ten": module_name, "mo_ta": str(row.get("module_description", "")), "doi_tuong": [], "chuc_nang": []}
            out["modules"].append(module)
        feat.setdefault("doc_id", "doc_" + hashlib.sha256((module_name + "\0" + str(feat.get("ten", ""))).encode()).hexdigest()[:16])
        module.setdefault("chuc_nang", []).append(feat)

    for row in patch.get("spec_removals", []) or []:
        doc_id = str(row.get("doc_id", ""))
        if doc_id in fmap:
            _, feat = fmap[doc_id]
            _mark_removed(
                feat,
                str(row.get("reason", "entry point removed or no longer reachable")),
                str(row.get("removed_commit") or "") or None,
            )

    # API removals are historical records too. Do not silently delete rows.
    api = out.setdefault("api", [])
    removals = {
        (str(x.get("phuong_thuc", "")).upper(), str(x.get("endpoint", ""))): x
        for x in (patch.get("api_removals", []) or [])
    }
    for existing in api:
        key = (str(existing.get("phuong_thuc", "")).upper(), str(existing.get("endpoint", "")))
        if key in removals:
            rem = removals[key]
            _mark_removed(existing, str(rem.get("reason", "route removed")), str(rem.get("removed_commit") or "") or None)

    for row in patch.get("api_upserts", []) or []:
        if not isinstance(row, dict):
            raise DocumentKitError("api_upserts items must be objects")
        row = _resolve_refs_in_row(row, store)
        key = (str(row.get("phuong_thuc", "")).upper(), str(row.get("endpoint", "")))
        if not key[0] or not key[1]:
            raise DocumentKitError("api_upsert requires phuong_thuc + endpoint")
        existing = next((x for x in api if (str(x.get("phuong_thuc", "")).upper(), str(x.get("endpoint", ""))) == key), None)
        if existing is None:
            api.append(row)
        else:
            existing.clear(); existing.update(row)

    allowed_top = {
        "tong_quan_md", "mo_hinh_du_lieu", "bao_mat", "rui_ro", "ghi_chu_md",
        "pham_vi", "du_an", "diagrams", "ui_images"
    }
    for key, value in (patch.get("top_level_updates") or {}).items():
        if key not in allowed_top:
            raise DocumentKitError(f"unsupported top_level_updates key: {key}")
        value = copy.deepcopy(value)
        if key in {"mo_hinh_du_lieu", "rui_ro", "diagrams", "ui_images"} and isinstance(value, list):
            value = [_resolve_refs_in_row(x, store) if isinstance(x, dict) else x for x in value]
        out[key] = value

    return ensure_doc_ids(out)
