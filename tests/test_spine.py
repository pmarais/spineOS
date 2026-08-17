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
        self.assertIn("PROMISE.json missing", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
