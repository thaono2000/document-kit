from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from documentkit.config import load_config
from documentkit.evidence import EvidenceStore
from documentkit.gitops import pull as git_pull
from documentkit.specops import apply_patch, ensure_doc_ids
from documentkit.validation import validate_spec


def sh(cwd: Path, *args: str) -> str:
    cp = subprocess.run(list(args), cwd=cwd, text=True, capture_output=True, check=True)
    return cp.stdout.strip()


class EvidenceTests(unittest.TestCase):
    def test_symbol_cache_hash_invalidation_and_patch_reuse(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "RepoA"; repo.mkdir()
            src = repo / "src"; src.mkdir()
            f = src / "service.py"
            f.write_text("def auth(x):\n    if not x:\n        raise ValueError()\n    return True\n", encoding="utf-8")
            store = EvidenceStore(root / ".document-kit/cache", {"RepoA": repo})
            key = store.put({
                "repo":"RepoA", "path":"src/service.py", "symbol":"auth", "start":1, "end":4,
                "analysis":{"inputs":["x"],"behavior":["reject falsy x"],"outputs":["True"],"errors":["ValueError"],"side_effects":[],"calls":[],"confidence":"high","notes":[]}
            })
            entry = store.get(key)
            self.assertTrue(store.validate(entry)[0])
            f.write_text("def auth(x):\n    if x is None:\n        raise ValueError()\n    return True\n", encoding="utf-8")
            self.assertFalse(store.validate(entry)[0])

    def test_patch_reuses_logical_evidence_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = root / "RepoA"; (repo / "src").mkdir(parents=True)
            (repo / "src/a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            store = EvidenceStore(root / "cache", {"RepoA": repo})
            spec = ensure_doc_ids({"modules":[{"ten":"M","chuc_nang":[{
                "ten":"Old","mo_ta":"x","dau_vao_mo_ta":"none","luong_xu_ly":["old"],
                "dau_ra":{"thanh_cong":"ok","loi":[]},"phan_quyen":"public",
                "neo":[{"repo":"RepoA","path":"src/a.py:1"}],"evidence_refs":[],"do_tin_cay":"cao","ghi_chu":""
            }]}],"api":[]})
            did = spec["modules"][0]["chuc_nang"][0]["doc_id"]
            patch = {
                "evidence_updates":[{"repo":"RepoA","path":"src/a.py","symbol":"f","start":1,"end":2,
                    "analysis":{"inputs":[],"behavior":["return constant"],"outputs":["1"],"errors":[],"side_effects":[],"calls":[],"confidence":"high","notes":[]}}],
                "spec_updates":[{"doc_id":did,"replacement":{
                    "ten":"New","mo_ta":"business text","dau_vao_mo_ta":"Không có","luong_xu_ly":["Hệ thống xử lý"],
                    "dau_ra":{"thanh_cong":"Thành công","loi":[]},"phan_quyen":"Công khai",
                    "neo":[{"repo":"RepoA","path":"src/a.py:1"}],
                    "evidence_refs":[{"repo":"RepoA","path":"src/a.py","symbol":"f"}],"do_tin_cay":"cao","ghi_chu":""}}]
            }
            new = apply_patch(spec, patch, store)
            refs = new["modules"][0]["chuc_nang"][0]["evidence_refs"]
            self.assertEqual(1, len(refs)); self.assertTrue(refs[0].startswith("sym_"))
            self.assertEqual([], validate_spec(new, {"RepoA":repo}, store))


class GitPullTests(unittest.TestCase):
    def _setup_remote(self, root: Path):
        bare = root / "remote.git"
        sh(root, "git", "init", "--bare", str(bare))
        seed = root / "seed"; sh(root, "git", "clone", str(bare), str(seed))
        sh(seed, "git", "config", "user.email", "test@example.com"); sh(seed, "git", "config", "user.name", "Test")
        (seed / "app.py").write_text("x=1\n")
        sh(seed, "git", "add", "."); sh(seed, "git", "commit", "-m", "init")
        sh(seed, "git", "branch", "-M", "develop"); sh(seed, "git", "push", "-u", "origin", "develop")
        work = root / "work"; sh(root, "git", "clone", "-b", "develop", str(bare), str(work))
        sh(work, "git", "config", "user.email", "test@example.com"); sh(work, "git", "config", "user.name", "Test")
        return bare, seed, work

    def test_pull_detects_noop_and_change(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); bare, seed, work = self._setup_remote(root)
            r = git_pull(work, "origin", "develop", require_clean=True)
            self.assertFalse(r.changed)
            (seed / "app.py").write_text("x=2\n")
            sh(seed, "git", "add", "."); sh(seed, "git", "commit", "-m", "change"); sh(seed, "git", "push")
            r = git_pull(work, "origin", "develop", require_clean=True)
            self.assertTrue(r.changed)
            self.assertEqual("M", r.changed_files[0]["status"])


if __name__ == "__main__":
    unittest.main()
