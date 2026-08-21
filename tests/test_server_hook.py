#!/usr/bin/env python3
"""Tests for server/hooks/update — branch ownership + path RBAC.
Local pushes to a bare repo execute its update hook, so this runs with no sshd:
identity is injected via SPINE_MEMBER, exactly as spine-shell does over SSH.
Run: python3 tests/test_server_hook.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "server" / "hooks" / "update"

ROLES = {
    "roles": {
        "admin": {"paths": ["**"]},
        "business-manager": {"paths": ["cases/**", "routers/**", "policies/**"]},
        "member": {"paths": ["cases/**"]},
    },
    "members": {"alice": "admin", "bob": "business-manager", "carol": "member"},
}


class TestUpdateHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.env = {**os.environ,
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        # bare repo with hook + append-only config
        self.bare = self.base / "spine.git"
        self.sh(self.base, "git", "init", "--bare", "-b", "main", str(self.bare))
        self.sh(self.bare, "git", "config", "receive.denyNonFastForwards", "true")
        self.sh(self.bare, "git", "config", "receive.denyDeletes", "true")
        hookdst = self.bare / "hooks" / "update"
        hookdst.write_text(HOOK.read_text())
        hookdst.chmod(0o755)
        # working clone
        self.work = self.base / "work"
        self.sh(self.base, "git", "clone", str(self.bare), str(self.work), check=False)
        self.sh(self.work, "git", "checkout", "-b", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def sh(self, cwd, *cmd, check=True, member=None):
        env = dict(self.env)
        if member is not None:
            env["SPINE_MEMBER"] = member
        r = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, env=env)
        if check and r.returncode != 0:
            self.fail(f"{' '.join(cmd)} failed:\n{r.stderr}\n{r.stdout}")
        return r

    def commit(self, relpath, content="x", msg="c"):
        p = self.work / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        self.sh(self.work, "git", "add", "-A")
        self.sh(self.work, "git", "commit", "-m", msg)

    def push(self, ref, member, check=False):
        return self.sh(self.work, "git", "push", "origin", ref, member=member, check=check)

    def bootstrap_main(self):
        (self.work / "ROLES.json").write_text(json.dumps(ROLES))
        self.commit("SPINE.md", "# rules", "bootstrap")
        self.push("main", member="alice", check=True)

    def test_bootstrap_first_main_push_allowed_then_governed(self):
        self.bootstrap_main()  # first push accepted openly
        # after bootstrap, a non-admin cannot push main
        self.commit("cases/0001_x/LEDGER.jsonl", '{"ts":"t","id":"1","author":"c"}\n')
        r = self.push("main", member="carol")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("manual reconcile", r.stderr)
        # but an admin can
        self.push("main", member="alice", check=True)

    def test_member_branch_ownership(self):
        self.bootstrap_main()
        self.commit("cases/0002_y/LEDGER.jsonl", '{"ts":"t","id":"2","author":"c"}\n')
        r = self.push("HEAD:refs/heads/member/bob", member="carol")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("only their own branch", r.stderr)
        self.push("HEAD:refs/heads/member/carol", member="carol", check=True)

    def test_no_identity_refused(self):
        self.bootstrap_main()
        self.commit("cases/0003_z/LEDGER.jsonl", "{}\n")
        r = self.push("HEAD:refs/heads/member/carol", member="")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no member identity", r.stderr)

    def test_path_rbac(self):
        self.bootstrap_main()
        # carol (member: cases/** only) touches a router → refused, path named
        self.commit("routers/delivery.md", "# nope")
        r = self.push("HEAD:refs/heads/member/carol", member="carol")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("may not touch", r.stderr)
        self.assertIn("routers/delivery.md", r.stderr)
        # bob (business-manager) may touch routers
        self.push("HEAD:refs/heads/member/bob", member="bob", check=True)
        # carol may not touch ROLES.json (privilege escalation attempt)
        self.commit("ROLES.json", json.dumps({"roles": {"admin": {"paths": ["**"]}},
                                              "members": {"carol": "admin"}}), "escalate")
        r = self.push("HEAD:refs/heads/member/carol", member="carol")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ROLES.json", r.stderr)

    def test_unknown_member_refused(self):
        self.bootstrap_main()
        self.commit("cases/0004_w/LEDGER.jsonl", "{}\n")
        r = self.push("HEAD:refs/heads/member/mallory", member="mallory")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not in ROLES.json", r.stderr)

    def test_snap_tags_open_other_refs_closed(self):
        self.bootstrap_main()
        self.sh(self.work, "git", "tag", "snap/20260817T000000Z-carol")
        self.push("snap/20260817T000000Z-carol", member="carol", check=True)
        self.sh(self.work, "git", "tag", "v1.0")
        r = self.push("v1.0", member="carol")
        self.assertNotEqual(r.returncode, 0)
        r = self.push("HEAD:refs/heads/feature-x", member="carol")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown ref", r.stderr)

    def test_deletion_refused_even_for_admin(self):
        self.bootstrap_main()
        self.commit("cases/0005_v/LEDGER.jsonl", "{}\n")
        self.push("HEAD:refs/heads/member/alice", member="alice", check=True)
        r = self.push(":refs/heads/member/alice", member="alice")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
