from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from .evidence import EvidenceStore

VALID_CONF = {"cao", "trung bình", "thấp"}
ANCHOR_RE = re.compile(r"^(.+):(\d+)(?:-(\d+))?$")

def validate_spec(spec: dict[str, Any], repo_roots: dict[str, Path], store: EvidenceStore, *, require_evidence: bool = True) -> list[str]:
    errors: list[str] = []
    modules = spec.get("modules") or []
    if not modules:
        errors.append("spec has no modules")
    audit = store.audit()
    for module in modules:
        mname = module.get("ten", "")
        for feat in module.get("chuc_nang", []) or []:
            where = f"{mname} / {feat.get('ten','')}"
            for key in ("ten", "mo_ta", "luong_xu_ly", "neo"):
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
            refs = feat.get("evidence_refs") or []
            if require_evidence and not refs:
                errors.append(f"{where}: missing evidence_refs")
            for ref in refs:
                if not isinstance(ref, str):
                    errors.append(f"{where}: evidence ref must be cache key")
                    continue
                st = audit.get(ref)
                if not st:
                    errors.append(f"{where}: evidence {ref} not found")
                elif st.get("status") != "valid":
                    errors.append(f"{where}: evidence {ref} stale ({st.get('reason')})")
            for anchor in feat.get("neo", []) or []:
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
                    errors.append(f"{where}: anchor file not found {repo}:{rel}")
                    continue
                with p.open("r", encoding="utf-8", errors="replace") as fh:
                    count = sum(1 for _ in fh)
                if start < 1 or end > count:
                    errors.append(f"{where}: anchor line out of range {repo}:{text}")
    return errors
