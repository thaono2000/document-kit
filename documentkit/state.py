from __future__ import annotations

from pathlib import Path
from typing import Any
from .util import atomic_write_json, load_json

SCHEMA = 1

def state_path(state_dir: Path) -> Path:
    return state_dir / "state.json"


def load_state(state_dir: Path) -> dict[str, Any]:
    data = load_json(state_path(state_dir), None)
    if not isinstance(data, dict):
        data = {"schema_version": SCHEMA, "repositories": {}}
    data.setdefault("schema_version", SCHEMA)
    data.setdefault("repositories", {})
    return data


def save_state(state_dir: Path, data: dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(state_path(state_dir), data)


def route_key(r: dict[str, Any]) -> str:
    return "|".join(str(r.get(k, "")) for k in ("method", "path", "name", "qualified_name", "file"))


def diff_routes(old: list[dict], new: list[dict]) -> tuple[list[dict], list[dict]]:
    om = {route_key(x): x for x in old or []}
    nm = {route_key(x): x for x in new or []}
    return [nm[k] for k in sorted(nm.keys() - om.keys())], [om[k] for k in sorted(om.keys() - nm.keys())]
