from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from documentkit.config import Config, Repository
from documentkit.core import pull_and_update


def sh(cwd: Path, *args: str) -> str:
    cp = subprocess.run(list(args), cwd=cwd, text=True, capture_output=True, check=True)
    return cp.stdout.strip()

class PullTriggerPolicyTests(unittest.TestCase):
    def setup_repo(self, root: Path, branch: str):
        bare=root/'remote.git'; sh(root,'git','init','--bare',str(bare))
        seed=root/'seed'; sh(root,'git','clone',str(bare),str(seed)); sh(seed,'git','config','user.email','t@x'); sh(seed,'git','config','user.name','T')
        (seed/'app.py').write_text('x=1\n'); sh(seed,'git','add','.'); sh(seed,'git','commit','-m','init'); sh(seed,'git','branch','-M',branch); sh(seed,'git','push','-u','origin',branch)
        work=root/'RepoA'; sh(root,'git','clone','-b',branch,str(bare),str(work))
        return seed, work

    def cfg(self, root: Path, work: Path):
        return Config(
            config_path=root/'document-kit.toml', project_name='P', workspace=root,
            state_dir=root/'.document-kit', cache_dir=root/'.document-kit/cache',
            spec_json=root/'docs/spec.json', markdown=root/'docs/SPEC.md', xlsx=None, changelog=root/'docs/CHANGELOG.md',
            allowed_branches=['develop','dev','staging','stg','production','prod'], auto_update=True,
            require_current_branch_match=True, require_clean_worktree=True,
            cbm_enabled=False, repositories=[Repository('RepoA',work,'RepoA')]
        )

    def test_disallowed_branch_pulls_but_never_triggers_docs(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); seed,work=self.setup_repo(root,'feature-x'); cfg=self.cfg(root,work)
            (seed/'app.py').write_text('x=2\n'); sh(seed,'git','add','.'); sh(seed,'git','commit','-m','change'); sh(seed,'git','push')
            out=pull_and_update(cfg,cfg.repositories[0],'origin','feature-x',plan_only=False)
            self.assertTrue(out['source_changed']); self.assertFalse(out['docs_triggered'])
            self.assertFalse(cfg.spec_json.exists())

    def test_allowed_branch_change_creates_plan_without_agent_in_plan_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); seed,work=self.setup_repo(root,'develop'); cfg=self.cfg(root,work)
            (seed/'app.py').write_text('x=2\n'); sh(seed,'git','add','.'); sh(seed,'git','commit','-m','change'); sh(seed,'git','push')
            out=pull_and_update(cfg,cfg.repositories[0],'origin','develop',plan_only=True)
            self.assertTrue(out['docs_triggered']); self.assertEqual('planned',out['status']); self.assertTrue(Path(out['context']).is_file())
            self.assertFalse(cfg.spec_json.exists())

if __name__ == '__main__':
    unittest.main()
