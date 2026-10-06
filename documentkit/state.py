from __future__ import annotations

from pathlib import Path
from typing import Any
from .util import atomic_write_json, load_json

SCHEMA = 2


def state_path(state_dir: Path) -> Path:
    return state_dir / "state.json"


def load_state(state_dir: Path) -> dict[str, Any]:
    data = load_json(state_path(state_dir), None)
    if not isinstance(data, dict):
        data = {"schema_version": SCHEMA, "repositories": {}}
    data.setdefault("schema_version", SCHEMA)
    data.setdefault("repositories", {})
    if int(data.get("schema_version") or 1) < SCHEMA:
        # V1 stored pending_commit/status directly on the repository row. Keep
        # those fields readable and also normalize them into a pending object.
        for row in data["repositories"].values():
            if row.get("pending_commit") and not row.get("pending"):
                row["pending"] = {
                    "commit": row.get("pending_commit"),
                    "base_commit": row.get("verified_commit"),
                    "branch": row.get("branch"),
                    "reason": "migrated_from_state_v1",
                }
        data["schema_version"] = SCHEMA
    return data


def save_state(state_dir: Path, data: dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    data["schema_version"] = SCHEMA
    atomic_write_json(state_path(state_dir), data)


def route_key(r: dict[str, Any]) -> str:
    return "|".join(str(r.get(k, "")) for k in ("method", "path", "name", "qualified_name", "file"))


def diff_routes(old: list[dict], new: list[dict]) -> tuple[list[dict], list[dict]]:
    om = {route_key(x): x for x in old or []}
    nm = {route_key(x): x for x in new or []}
    return [nm[k] for k in sorted(nm.keys() - om.keys())], [om[k] for k in sorted(om.keys() - nm.keys())]
