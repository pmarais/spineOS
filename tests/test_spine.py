#!/usr/bin/env python3
"""Golden tests for SpineOS v0 core semantics. Run: python3 tests/test_spine.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import spine  # noqa: E402

SP = str(REPO / "spine.py")


class TestFold(unittest.TestCase):
    def test_latest_wins(self):
        lines = [
            {"ts": "2026-01-01T10:00:00", "author": "a", "stage": "intake", "owner": "jo"},
            {"ts": "2026-01-02T10:00:00", "author": "b", "stage": "agreed", "note": "n1"},
            {"ts": "2026-01-03T10:00:00", "author": "a", "owner": "sam", "note": "n2"},
        ]
        st = spine.fold_ledger(lines)
        self.assertEqual(st["stage"], "agreed")   # untouched by later line
        self.assertEqual(st["owner"], "sam")      # overridden by latest
        self.assertEqual(st["_n_lines"], 3)
        self.assertEqual([n["note"] for n in st["_notes"]], ["n1", "n2"])

    def test_out_of_order_timestamps_fold_by_time(self):
        lines = [
            {"ts": "2026-01-05T10:00:00", "author": "a", "stage": "in_progress"},
            {"ts": "2026-01-01T10:00:00", "author": "a", "stage": "intake"},
        ]
        # read_ledger sorts; fold on sorted input
        lines.sort(key=lambda o: o.get("ts", ""))
        st = spine.fold_ledger(lines)
        self.assertEqual(st["stage"], "in_progress")

    def test_null_never_overwrites(self):
        lines = [
            {"ts": "2026-01-01T10:00:00", "author": "a", "owner": "jo"},
            {"ts": "2026-01-02T10:00:00", "author": "a", "owner": None, "note": "x"},
        ]
        st = spine.fold_ledger(lines)
        self.assertEqual(st["owner"], "jo")

    def test_outstanding_from_milestones(self):
        p = {"milestones": [
            {"label": "d", "amount": 100, "status": "paid"},
            {"label": "f", "amount": 250, "status": "outstanding"},
        ]}
        self.assertEqual(spine.promise_outstanding(p), 250)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {**os.environ, "SPINE_OPERATOR": "tester"}

    def tearDown(self):
        self.tmp.cleanup()

    def run_sp(self, *args, check=True):
        r = subprocess.run([sys.executable, SP, *args], cwd=self.root,
                           capture_output=True, text=True, env=self.env)
        if check and r.returncode != 0:
            self.fail(f"spine {' '.join(args)} failed: {r.stderr}")
        return r

    def test_end_to_end(self):
        self.run_sp("init", "--operator", "tester")
        self.run_sp("new", "Test Case", "--note", "opened")
        self.run_sp("promise", "1", "--client", "T", "--total", "100",
                    "--milestone", "dep:40:paid", "--milestone", "fin:60")
        self.run_sp("append", "1", "--stage", "in_progress", "--owner", "tester",
                    "--paid", "40", "--note", "working")
        # fold is machine-readable and correct
        r = self.run_sp("fold", "1")
        data = json.loads(r.stdout)
        self.assertEqual(data["state"]["stage"], "in_progress")
        self.assertEqual(data["state"]["paid"], 40.0)
        self.assertEqual(data["promise"]["total"], 100.0)
        # append-only: ledger has 3 lines (create, promise, append)
        ledger = (self.root / "cases").glob("*/LEDGER.jsonl")
        lines = next(ledger).read_text().strip().splitlines()
        self.assertEqual(len(lines), 3)
        # log rows pair the ledger lines
        log = next((self.root / "cases").glob("*/LOG.csv")).read_text().strip().splitlines()
        self.assertEqual(len(log), 4)  # header + 3
        # doctor is clean
        r = self.run_sp("doctor")
        self.assertIn("0 flag(s)", r.stdout)

    def test_promise_requires_force_to_change(self):
        self.run_sp("init", "--operator", "tester")
        self.run_sp("new", "X")
        self.run_sp("promise", "1", "--client", "A", "--total", "10")
        r = self.run_sp("promise", "1", "--client", "A", "--total", "20", check=False)
        self.assertNotEqual(r.returncode, 0, "re-promise without --force must fail")
        self.run_sp("promise", "1", "--client", "A", "--total", "20", "--force")
        r = self.run_sp("fold", "1")
        self.assertEqual(json.loads(r.stdout)["promise"]["total"], 20.0)

    def test_doctor_flags_missing_promise(self):
        self.run_sp("init", "--operator", "tester")
        self.run_sp("new", "Y")
        self.run_sp("append", "1", "--stage", "in_progress", "--note", "moved without a deal")
        r = self.run_sp("doctor", check=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no promise", r.stdout)


class TestSyncPipeline(unittest.TestCase):
    """v0.2: convergence, dedupe, journal recovery, as-of, manual reconcile."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.env = {**os.environ, "SPINE_OPERATOR": "tester",
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def tearDown(self):
        self.tmp.cleanup()

    def sh(self, cwd, *cmd, check=True, env_extra=None):
        env = {**self.env, **(env_extra or {})}
        r = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, env=env)
        if check and r.returncode != 0:
            self.fail(f"{' '.join(cmd)} in {cwd} failed:\n{r.stderr}\n{r.stdout}")
        return r

    def sp(self, cwd, *args, check=True, op="tester"):
        return self.sh(cwd, sys.executable, SP, *args, check=check,
                       env_extra={"SPINE_OPERATOR": op, "SPINE_SESSION": f"s-{op}"})

    def make_remote_and_clone(self, name, branch_mode="shared"):
        bare = self.base / "origin.git"
        if not bare.exists():
            self.sh(self.base, "git", "init", "--bare", "-b", "main", str(bare))
        c = self.base / name
        self.sh(self.base, "git", "clone", str(bare), str(c), check=False)
        self.sh(c, "git", "checkout", "-b", "main", check=False)
        return c

    def test_two_clone_convergence_zero_loss(self):
        a = self.make_remote_and_clone("a")
        self.sp(a, "init", "--operator", "alice", op="alice")
        self.sp(a, "new", "Shared Case", op="alice")
        self.sp(a, "sync", op="alice")
        b = self.base / "b"
        self.sh(self.base, "git", "clone", str(self.base / "origin.git"), str(b))
        # both append to the SAME case, then sync in sequence
        self.sp(a, "append", "1", "--note", "line-from-alice", op="alice")
        self.sp(b, "append", "1", "--note", "line-from-bob", "--owner", "bob", op="bob")
        self.sp(a, "sync", op="alice")
        self.sp(b, "sync", op="bob")      # merges alice's push, unions, pushes
        self.sp(a, "sync", op="alice")    # picks up bob's
        fa = json.loads(self.sp(a, "fold", "1", op="alice").stdout)
        fb = json.loads(self.sp(b, "fold", "1", op="bob").stdout)
        self.assertEqual(fa["state"]["_n_lines"], 3)   # create + alice + bob
        self.assertEqual(fb["state"]["_n_lines"], 3)
        self.assertEqual(fa["state"]["owner"], "bob")
        # zero loss: both notes present in both clones
        for c in (a, b):
            text = next((c / "cases").glob("*/LEDGER.jsonl")).read_text()
            self.assertIn("line-from-alice", text)
            self.assertIn("line-from-bob", text)

    def test_duplicate_lines_fold_once(self):
        a = self.base / "solo"; a.mkdir()
        self.sp(a, "init", "--operator", "t")
        self.sp(a, "new", "X")
        led = next((a / "cases").glob("*/LEDGER.jsonl"))
        line = led.read_text().strip().splitlines()[0]
        with open(led, "a") as f:
            f.write(line + "\n")          # simulate a union double-merge
        r = json.loads(self.sp(a, "fold", "1").stdout)
        self.assertEqual(r["duplicates_folded"], 1)
        self.assertEqual(r["state"]["_n_lines"], 1)

    def test_journal_recovers_deleted_ledger(self):
        a = self.base / "jr"; a.mkdir()
        self.sp(a, "init", "--operator", "t")
        self.sp(a, "new", "Y", "--note", "precious")
        self.sp(a, "append", "1", "--note", "also precious")
        led = next((a / "cases").glob("*/LEDGER.jsonl"))
        led.write_text("")                  # catastrophic loss
        self.sp(a, "recover")
        text = led.read_text()
        self.assertIn("precious", text)
        self.assertIn("also precious", text)
        r = json.loads(self.sp(a, "fold", "1").stdout)
        self.assertEqual(r["state"]["_n_lines"], 2)

    def test_as_of_time_travel(self):
        a = self.base / "tt"; a.mkdir()
        self.sp(a, "init", "--operator", "t")
        self.sp(a, "new", "Z")
        led = next((a / "cases").glob("*/LEDGER.jsonl"))
        with open(led, "a") as f:
            f.write(json.dumps({"ts": "2126-01-01T10:00:00", "id": "a1", "author": "t", "stage": "in_progress"}) + "\n")
            f.write(json.dumps({"ts": "2126-03-01T10:00:00", "id": "a2", "author": "t", "stage": "done"}) + "\n")
        now_state = json.loads(self.sp(a, "fold", "1").stdout)["state"]["stage"]
        old_state = json.loads(self.sp(a, "fold", "1", "--as-of", "2126-02-01").stdout)["state"]["stage"]
        self.assertEqual(now_state, "done")
        self.assertEqual(old_state, "in_progress")

    def test_member_mode_manual_reconcile(self):
        a = self.make_remote_and_clone("ma")
        self.sp(a, "init", "--operator", "alice", "--branch-mode", "member", op="alice")
        self.sp(a, "new", "Team Case", op="alice")
        # bootstrap main so member clones have a base
        self.sh(a, "git", "add", "-A"); self.sh(a, "git", "commit", "-m", "seed", check=False)
        self.sh(a, "git", "push", "origin", "HEAD:main")
        b = self.base / "mb"
        self.sh(self.base, "git", "clone", str(self.base / "origin.git"), str(b))
        self.sp(a, "append", "1", "--note", "from-alice", op="alice")
        self.sp(b, "append", "1", "--note", "from-bob", op="bob")
        self.sp(a, "sync", op="alice")   # → member/alice
        self.sp(b, "sync", op="bob")     # → member/bob
        r = self.sh(self.base / "origin.git", "git", "branch")
        self.assertIn("member/alice", r.stdout); self.assertIn("member/bob", r.stdout)
        # admin reconciles manually from clone a
        self.sp(a, "reconcile", op="alice")
        self.sp(b, "sync", op="bob")     # bob pulls reconciled main
        fb = json.loads(self.sp(b, "fold", "1", op="bob").stdout)
        text = next((b / "cases").glob("*/LEDGER.jsonl")).read_text()
        self.assertIn("from-alice", text); self.assertIn("from-bob", text)
        self.assertGreaterEqual(fb["state"]["_n_lines"], 3)


class TestInstallPath(unittest.TestCase):
    """The stranger's path: clone the product repo, adopt, sync, then give it its own remote."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.env = {**os.environ, "SPINE_OPERATOR": "stranger", "SPINE_SESSION": "s-stranger",
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def tearDown(self):
        self.tmp.cleanup()

    def sh(self, cwd, *cmd, check=True):
        r = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, env=self.env)
        if check and r.returncode != 0:
            self.fail(f"{' '.join(cmd)} failed:\n{r.stderr}\n{r.stdout}")
        return r

    def test_clone_adopt_sync_remote(self):
        # a "product repo" whose remote URL matches the upstream marker
        product = self.base / "github.com" / "pmarais" / "spineOS"
        product.mkdir(parents=True)
        self.sh(product, "git", "init", "-q", "-b", "main")
        (product / "SPINE.md").write_text("# rules\n")
        (product / "spine.py").write_text(Path(SP).read_text())
        (product / "cases").mkdir(); (product / "cases" / ".gitkeep").touch()
        self.sh(product, "git", "add", "-A"); self.sh(product, "git", "commit", "-q", "-m", "product")
        clone = self.base / "myspine"
        self.sh(self.base, "git", "clone", "-q", str(product), str(clone))
        # adopt: init must NOT refuse, must complete the scaffold, must warn about upstream
        r = self.sh(clone, sys.executable, "spine.py", "init", "--operator", "stranger")
        self.assertIn("adopted", r.stdout)
        self.assertIn("public SpineOS repo", r.stdout)
        self.assertTrue((clone / ".spineos.json").is_file())
        self.assertEqual(json.loads((clone / ".spineos.json").read_text())["main_branch"], "main")
        self.assertEqual((clone / "SPINE.md").read_text(), "# rules\n")   # untouched
        # work + sync: must commit locally and refuse to push to upstream, saying so
        self.sh(clone, sys.executable, "spine.py", "new", "First client")
        r = self.sh(clone, sys.executable, "spine.py", "sync")
        self.assertIn("NOT pushing", r.stdout)
        self.assertEqual(self.sh(product, "git", "rev-list", "--count", "main").stdout.strip(), "1")
        # remote: product repo becomes upstream, new origin takes the state
        own = self.base / "own.git"
        self.sh(self.base, "git", "init", "-q", "--bare", "-b", "main", str(own))
        r = self.sh(clone, sys.executable, "spine.py", "remote", str(own))
        self.assertIn("upstream", r.stdout)
        remotes = self.sh(clone, "git", "remote", "-v").stdout
        self.assertIn("upstream", remotes); self.assertIn(str(own), remotes)
        r = self.sh(clone, sys.executable, "spine.py", "sync")
        self.assertIn("pushed", r.stdout)
        self.assertEqual(self.sh(own, "git", "rev-list", "--count", "main").stdout.strip(),
                         self.sh(clone, "git", "rev-list", "--count", "main").stdout.strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
