from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from documentkit.config import Config, Repository
from documentkit.core import doctor, pull_and_update, retry_pending, _publish_transaction
from documentkit.evidence import EvidenceStore
from documentkit.gitops import head
from documentkit.specops import ensure_doc_ids, REMOVED_STATUS
from documentkit.state import load_state, save_state
from documentkit.util import DocumentKitError
from documentkit.validation import validate_spec
from documentkit.html_render import render_html


def sh(cwd: Path, *args: str) -> str:
    cp = subprocess.run(list(args), cwd=cwd, text=True, capture_output=True, check=True)
    return cp.stdout.strip()


class V2SafetyTests(unittest.TestCase):
    def setup_repo(self, root: Path, branch: str = "develop"):
        bare = root / "remote.git"; sh(root, "git", "init", "--bare", str(bare))
        seed = root / "seed"; sh(root, "git", "clone", str(bare), str(seed))
        sh(seed, "git", "config", "user.email", "t@x"); sh(seed, "git", "config", "user.name", "T")
        (seed / "app.py").write_text("x=1\n", encoding="utf-8")
        sh(seed, "git", "add", "."); sh(seed, "git", "commit", "-m", "init")
        sh(seed, "git", "branch", "-M", branch); sh(seed, "git", "push", "-u", "origin", branch)
        work = root / "RepoA"; sh(root, "git", "clone", "-b", branch, str(bare), str(work))
        sh(work, "git", "config", "user.email", "t@x"); sh(work, "git", "config", "user.name", "T")
        return seed, work

    def cfg(self, root: Path, work: Path):
        return Config(
            config_path=root / "document-kit.toml", project_name="P", workspace=root,
            state_dir=root / ".document-kit", cache_dir=root / ".document-kit/cache",
            spec_json=root / "docs/spec.json", markdown=root / "docs/SPEC.md", html=root / "docs/index.html",
            xlsx=None, changelog=root / "docs/CHANGELOG.md", cbm_enabled=False,
            repositories=[Repository("RepoA", work, "RepoA")],
        )

    def seed_spec_state(self, cfg: Config, work: Path):
        spec = ensure_doc_ids({
            "du_an": {"ten": "P"},
            "modules": [{"ten": "M", "chuc_nang": [{
                "ten": "F", "mo_ta": "old", "dau_vao_mo_ta": "Không có", "luong_xu_ly": ["old"],
                "dau_ra": {"thanh_cong": "ok", "loi": []}, "phan_quyen": "Công khai",
                "neo": [{"repo": "RepoA", "path": "app.py:1"}], "evidence_refs": [],
                "do_tin_cay": "cao", "ghi_chu": "",
            }]}],
            "api": [], "mo_hinh_du_lieu": [], "rui_ro": [], "diagrams": [], "pham_vi": {},
        })
        cfg.spec_json.parent.mkdir(parents=True, exist_ok=True)
        cfg.spec_json.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        cfg.markdown.write_text("OLD MARKDOWN\n", encoding="utf-8")
        cfg.html.write_text("OLD HTML\n", encoding="utf-8")
        cfg.changelog.write_text("# Documentation Changelog\n\n", encoding="utf-8")
        state = load_state(cfg.state_dir)
        state["repositories"]["RepoA"] = {"branch": "develop", "verified_commit": head(work), "routes": [], "status": "VERIFIED"}
        save_state(cfg.state_dir, state)
        return spec

    def ok_patch(self, spec):
        did = spec["modules"][0]["chuc_nang"][0]["doc_id"]
        return {
            "status": "ok", "review_items": [],
            "evidence_updates": [{
                "repo": "RepoA", "path": "app.py", "symbol": "module", "start": 1, "end": 1,
                "analysis": {"inputs": [], "behavior": ["sets x"], "outputs": [], "errors": [], "side_effects": [], "calls": [], "confidence": "high", "notes": []},
            }],
            "spec_updates": [{"doc_id": did, "replacement": {
                "ten": "F", "mo_ta": "new", "dau_vao_mo_ta": "Không có", "luong_xu_ly": ["new"],
                "dau_ra": {"thanh_cong": "ok", "loi": []}, "phan_quyen": "Công khai",
                "neo": [{"repo": "RepoA", "path": "app.py:1"}],
                "evidence_refs": [{"repo": "RepoA", "path": "app.py", "symbol": "module"}],
                "do_tin_cay": "cao", "ghi_chu": "",
            }}],
            "spec_additions": [], "spec_removals": [], "api_upserts": [], "api_removals": [],
            "top_level_updates": {}, "changelog": [{"type": "changed", "title": "F", "summary": "updated", "evidence": []}],
        }

    def test_retry_after_failed_analysis_even_when_no_new_pull(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); seed, work = self.setup_repo(root); cfg = self.cfg(root, work); spec = self.seed_spec_state(cfg, work)
            (seed / "app.py").write_text("x=2\n", encoding="utf-8"); sh(seed, "git", "add", "."); sh(seed, "git", "commit", "-m", "change"); sh(seed, "git", "push")
            with patch("documentkit.core.CursorAgent.ask_json", return_value={"status": "needs_review", "review_items": [{"reason": "ambiguous"}]}):
                out = pull_and_update(cfg, cfg.repositories[0], "origin", "develop")
            self.assertEqual("needs_review", out["status"])
            self.assertTrue(load_state(cfg.state_dir)["repositories"]["RepoA"].get("pending"))
            # A normal pull is now a no-op but must surface the retry path.
            noop = pull_and_update(cfg, cfg.repositories[0], "origin", "develop")
            self.assertEqual("already_up_to_date_but_documentation_pending", noop["reason"])
            with patch("documentkit.core.CursorAgent.ask_json", return_value=self.ok_patch(spec)):
                retried = retry_pending(cfg, cfg.repositories[0])
            self.assertEqual("updated", retried["status"])
            row = load_state(cfg.state_dir)["repositories"]["RepoA"]
            self.assertFalse(row.get("pending"))
            self.assertEqual(head(work), row["verified_commit"])
            self.assertIn("new", cfg.spec_json.read_text(encoding="utf-8"))

    def test_render_failure_preserves_previous_outputs_and_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); seed, work = self.setup_repo(root); cfg = self.cfg(root, work); spec = self.seed_spec_state(cfg, work)
            cfg.cache_dir.mkdir(parents=True, exist_ok=True)
            (cfg.cache_dir / "sentinel.txt").write_text("OLD CACHE", encoding="utf-8")
            (seed / "app.py").write_text("x=2\n", encoding="utf-8"); sh(seed, "git", "add", "."); sh(seed, "git", "commit", "-m", "change"); sh(seed, "git", "push")
            with patch("documentkit.core.CursorAgent.ask_json", return_value=self.ok_patch(spec)), patch("documentkit.core.render_html", side_effect=RuntimeError("boom")):
                with self.assertRaises(DocumentKitError):
                    pull_and_update(cfg, cfg.repositories[0], "origin", "develop")
            self.assertEqual("OLD MARKDOWN\n", cfg.markdown.read_text(encoding="utf-8"))
            self.assertEqual("OLD HTML\n", cfg.html.read_text(encoding="utf-8"))
            self.assertEqual("OLD CACHE", (cfg.cache_dir / "sentinel.txt").read_text(encoding="utf-8"))
            self.assertTrue(load_state(cfg.state_dir)["repositories"]["RepoA"].get("pending"))

    def test_execution_failure_keeps_update_retryable(self):
        failures = [
            ("documentkit.core.CursorAgent.ask_json", subprocess.TimeoutExpired("agent", 1)),
            ("documentkit.core.CBM.index_repository", DocumentKitError("CBM index failed")),
        ]
        for method, error in failures:
            with self.subTest(method=method), tempfile.TemporaryDirectory() as td:
                root = Path(td); seed, work = self.setup_repo(root); cfg = self.cfg(root, work)
                spec = self.seed_spec_state(cfg, work)
                before = head(work)
                outputs = {p: p.read_bytes() for p in (cfg.spec_json, cfg.markdown, cfg.html, cfg.changelog)}
                (seed / "app.py").write_text("x=2\n", encoding="utf-8")
                sh(seed, "git", "add", "."); sh(seed, "git", "commit", "-m", "change"); sh(seed, "git", "push")
                cfg.cbm_enabled = "CBM" in method
                with patch("documentkit.core.CBM.available", return_value=True), patch(method, side_effect=error):
                    with self.assertRaises(type(error)):
                        pull_and_update(cfg, cfg.repositories[0], "origin", "develop")
                row = load_state(cfg.state_dir)["repositories"]["RepoA"]
                self.assertEqual(before, row["verified_commit"])
                self.assertEqual(before, row["pending"]["base_commit"])
                self.assertEqual(head(work), row["pending"]["commit"])
                self.assertEqual(outputs, {p: p.read_bytes() for p in outputs})
                noop = pull_and_update(cfg, cfg.repositories[0], "origin", "develop")
                self.assertEqual("already_up_to_date_but_documentation_pending", noop["reason"])
                cfg.cbm_enabled = False
                with patch("documentkit.core.CursorAgent.ask_json", return_value=self.ok_patch(spec)):
                    self.assertEqual("updated", retry_pending(cfg, cfg.repositories[0])["status"])
                self.assertFalse(load_state(cfg.state_dir)["repositories"]["RepoA"].get("pending"))

    def test_publication_failure_restores_backed_up_outputs(self):
        import os
        original_replace = os.replace
        for fail_at in ("first", "second", "cache", "restore"):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as td:
                root = Path(td); cfg = self.cfg(root, root / "RepoA")
                cfg.cache_dir.mkdir(parents=True)
                (cfg.cache_dir / "sentinel").write_text("OLD CACHE")
                staged_cache = root / "new-cache"; staged_cache.mkdir()
                staged = {}
                for target in (cfg.spec_json, cfg.markdown):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("OLD " + target.name)
                    source = root / ("new-" + target.name); source.write_text("NEW")
                    staged[target] = source

                def fail_replace(src, dst):
                    src = Path(src)
                    name = cfg.markdown.name if fail_at == "second" else cfg.spec_json.name
                    if (fail_at == "cache" and src.name.startswith("cache.new-")) or (
                        fail_at != "cache" and src.name.startswith(name + ".new-")
                    ) or (fail_at == "restore" and ".bak-" in src.name):
                        raise OSError("simulated replace failure")
                    return original_replace(src, dst)

                with patch("documentkit.core.os.replace", side_effect=fail_replace):
                    with self.assertRaises(OSError):
                        _publish_transaction(cfg, staged, staged_cache)
                for target in staged:
                    if fail_at == "restore" and target == cfg.spec_json:
                        backups = list(target.parent.glob(target.name + ".bak-*"))
                        self.assertEqual(1, len(backups))
                        self.assertEqual("OLD " + target.name, backups[0].read_text())
                    else:
                        self.assertEqual("OLD " + target.name, target.read_text())
                self.assertEqual("OLD CACHE", (cfg.cache_dir / "sentinel").read_text())

    def test_removed_function_allows_historical_missing_source_and_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = root / "RepoA"; repo.mkdir(); src = repo / "old.py"; src.write_text("x=1\n")
            store = EvidenceStore(root / "cache", {"RepoA": repo})
            key = store.put({"repo": "RepoA", "path": "old.py", "symbol": "old", "start": 1, "end": 1,
                             "analysis": {"inputs": [], "behavior": [], "outputs": [], "errors": [], "side_effects": [], "calls": [], "confidence": "high", "notes": []}})
            src.unlink()
            spec = {"modules": [{"ten": "M", "chuc_nang": [{
                "ten": "Old", "mo_ta": "historical", "trang_thai": REMOVED_STATUS, "removal_reason": "route removed",
                "neo": [{"repo": "RepoA", "path": "old.py:1"}], "evidence_refs": [key]
            }]}], "api": [{"phuong_thuc": "GET", "endpoint": "/old", "chuc_nang": "Old", "trang_thai": REMOVED_STATUS,
                            "removal_reason": "route removed", "neo": [{"repo": "RepoA", "path": "old.py:1"}], "evidence_refs": [key]}]}
            self.assertEqual([], validate_spec(spec, {"RepoA": repo}, store, discovered_routes=[]))

    def test_html_contains_search_filters_and_mermaid(self):
        spec = {"du_an": {"ten": "P"}, "modules": [{"ten": "M", "chuc_nang": [{
            "ten": "F", "mo_ta": "desc", "phan_quyen": "Admin", "luong_xu_ly": ["step"], "dau_vao_mo_ta": "none",
            "dau_ra": {"thanh_cong": "ok", "loi": []}, "do_tin_cay": "cao", "neo": []
        }]}], "api": [], "diagrams": [{"title": "Flow", "mermaid": "flowchart TD\nA-->B"}]}
        text = render_html(spec)
        self.assertIn('id="q"', text)
        self.assertIn('id="fm"', text)
        self.assertIn('class="mermaid"', text)
        self.assertIn("flowchart TD", text)

    def test_doctor_checks_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); _seed, work = self.setup_repo(root); cfg = self.cfg(root, work)
            out = doctor(cfg)
            self.assertTrue(out["checks"]["python_3_11_plus"])
            self.assertTrue(out["checks"]["git_available"])

    def test_initial_build_render_failure_publishes_nothing(self):
        from documentkit.core import initial_build
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); _seed, work = self.setup_repo(root); cfg = self.cfg(root, work)
            result = {
                "status": "ok", "review_items": [],
                "evidence_updates": [{
                    "repo": "RepoA", "path": "app.py", "symbol": "module", "start": 1, "end": 1,
                    "analysis": {"inputs": [], "behavior": ["sets x"], "outputs": [], "errors": [], "side_effects": [], "calls": [], "confidence": "high", "notes": []},
                }],
                "full_spec": {
                    "du_an": {"ten": "P"}, "modules": [{"ten": "M", "chuc_nang": [{
                        "ten": "F", "mo_ta": "desc", "dau_vao_mo_ta": "Không có", "luong_xu_ly": ["step"],
                        "dau_ra": {"thanh_cong": "ok", "loi": []}, "phan_quyen": "Công khai",
                        "neo": [{"repo": "RepoA", "path": "app.py:1"}],
                        "evidence_refs": [{"repo": "RepoA", "path": "app.py", "symbol": "module"}],
                        "do_tin_cay": "cao", "ghi_chu": ""
                    }]}], "api": [], "mo_hinh_du_lieu": [], "rui_ro": [], "diagrams": [], "pham_vi": {}
                }
            }
            with patch("documentkit.core.CursorAgent.ask_json", return_value=result), patch("documentkit.core.render_html", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    initial_build(cfg)
            self.assertFalse(cfg.spec_json.exists())
            self.assertFalse(cfg.markdown.exists())
            self.assertFalse(cfg.html.exists())
            self.assertFalse(cfg.cache_dir.exists())

    def test_entry_point_coverage_detects_undocumented_route(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = root / "RepoA"; repo.mkdir(); (repo / "a.py").write_text("x=1\n")
            store = EvidenceStore(root / "cache", {"RepoA": repo})
            key = store.put({"repo": "RepoA", "path": "a.py", "symbol": "route", "start": 1, "end": 1,
                             "analysis": {"inputs": [], "behavior": [], "outputs": [], "errors": [], "side_effects": [], "calls": [], "confidence": "high", "notes": []}})
            spec = {"modules": [{"ten": "M", "chuc_nang": [{
                "ten": "F", "mo_ta": "desc", "dau_vao_mo_ta": "none", "luong_xu_ly": ["step"],
                "dau_ra": {"thanh_cong": "ok", "loi": []}, "phan_quyen": "public",
                "neo": [{"repo": "RepoA", "path": "a.py:1"}], "evidence_refs": [key], "do_tin_cay": "cao", "ghi_chu": ""
            }]}], "api": []}
            errors = validate_spec(spec, {"RepoA": repo}, store, discovered_routes=[{"repo": "RepoA", "method": "GET", "path": "/missing"}])
            self.assertTrue(any("coverage gap" in x for x in errors))


if __name__ == "__main__":
    unittest.main()
