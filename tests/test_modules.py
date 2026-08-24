#!/usr/bin/env python3
"""Tests for the ingest + research modules. Run: python3 tests/test_modules.py"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import spine  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


email_mod = load("email_ingest", REPO / "modules" / "email-imap" / "ingest.py")
wa_mod = load("wa_ingest", REPO / "modules" / "whatsapp-local" / "ingest.py")
NUMBERS = str(REPO / "modules" / "research" / "numbers.py")
FETCH = str(REPO / "modules" / "api" / "fetch.py")


class SpineTmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {**os.environ, "SPINE_OPERATOR": "tester", "SPINE_SESSION": "s-test"}
        subprocess.run([sys.executable, str(REPO / "spine.py"), "init", "--operator", "tester"],
                       cwd=self.root, capture_output=True, text=True, env=self.env)
        subprocess.run([sys.executable, str(REPO / "spine.py"), "new", "Acme"],
                       cwd=self.root, capture_output=True, text=True, env=self.env)

    def tearDown(self):
        self.tmp.cleanup()

    def run_py(self, script, *args, check=True, cwd=None):
        r = subprocess.run([sys.executable, script, *args], cwd=cwd or self.root,
                           capture_output=True, text=True, env=self.env)
        if check and r.returncode != 0:
            self.fail(f"{script} {' '.join(args)} failed:\n{r.stderr}\n{r.stdout}")
        return r


class TestEmailRouting(SpineTmp):
    def rec(self, key, frm, to=(), subject="s", body="b"):
        return {"key": key, "account": "a", "mailbox": "INBOX", "uid": key.split("/")[-1],
                "message_id": key, "date": "", "from": [frm], "to": list(to), "cc": [],
                "subject": subject, "body": body, "fetched_at": "t"}

    def test_multi_address_routing_and_unrouted(self):
        routes = {"addresses": {"client@x.com": "0001", "client.second@y.org": "0001"}}
        records = [
            self.rec("a/INBOX/1", "client@x.com"),                       # primary address
            self.rec("a/INBOX/2", "client.second@y.org"),                # SECOND address, same case
            self.rec("a/Sent/3", "us@firm.com", to=["client@x.com"]),    # our outbound, routed by to:
            self.rec("a/INBOX/4", "stranger@nowhere.com"),               # unroutable
        ]
        routed, unrouted = email_mod.route_records(self.root, routes, records)
        self.assertEqual((routed, unrouted), (3, 1))
        case_file = next((self.root / "cases").glob("*/EMAIL.jsonl"))
        lines = [json.loads(l) for l in case_file.read_text().splitlines()]
        self.assertEqual(len(lines), 3)
        unr = (self.root / "channels" / "email" / "unrouted.jsonl").read_text()
        self.assertIn("stranger@nowhere.com", unr)

    def test_full_body_never_truncated(self):
        import email as email_lib
        long_tail = "the buried second request: please also quote the presentation"
        raw = ("From: c@x.com\r\nTo: us@firm.com\r\nSubject: hi\r\n"
               "Content-Type: text/plain\r\n\r\n" + ("filler " * 500) + long_tail)
        msg = email_lib.message_from_string(raw)
        rec = email_mod.message_record("a", "INBOX", "9", msg)
        self.assertIn(long_tail, rec["body"])   # the 27-day scar: nothing past any cut


class TestApiFetch(SpineTmp):
    def test_dedupe_by_content_hash(self):
        payload = self.root / "feed.json"
        payload.write_text(json.dumps({"transactions": [{"amount": 100}]}))
        cfg = self.root / "sources.json"
        cfg.write_text(json.dumps({"sources": [
            {"name": "test-feed", "url": payload.as_uri(), "authoritative_for": "test"}]}))
        self.run_py(FETCH, "--config", str(cfg))
        self.run_py(FETCH, "--config", str(cfg))     # identical content → no new record
        store = self.root / "channels" / "api" / "test-feed" / "records.jsonl"
        self.assertEqual(len(store.read_text().strip().splitlines()), 1)
        payload.write_text(json.dumps({"transactions": [{"amount": 100}, {"amount": 250}]}))
        self.run_py(FETCH, "--config", str(cfg))     # changed content → appended, never rewritten
        lines = store.read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("100", lines[0])               # history intact


class TestWhatsAppExtract(SpineTmp):
    def fake_chatstorage(self, path, messages):
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE IF NOT EXISTS ZWACHATSESSION (Z_PK INTEGER PRIMARY KEY, ZPARTNERNAME TEXT, ZCONTACTJID TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS ZWAMESSAGE (Z_PK INTEGER PRIMARY KEY, ZCHATSESSION INTEGER, ZMESSAGEDATE REAL, ZISFROMME INTEGER, ZTEXT TEXT)")
        conn.execute("INSERT OR IGNORE INTO ZWACHATSESSION VALUES (1, 'Dr Okafor', '12345@lid')")
        for i, (t, fm, txt) in enumerate(messages, 100):
            conn.execute("INSERT OR REPLACE INTO ZWAMESSAGE VALUES (?,?,?,?,?)", (i, 1, t, fm, txt))
        conn.commit(); conn.close()

    def test_union_extract_lid_chat(self):
        snap = self.root / "channels" / "whatsapp" / "snapshot"
        snap.mkdir(parents=True)
        db = snap / "ChatStorage.sqlite"
        self.fake_chatstorage(db, [(800000000, 0, "hello"), (800000060, 1, "hi back")])
        wa_mod.cmd_extract(self.root)
        store = self.root / "channels" / "whatsapp" / "chats" / "Dr_Okafor.jsonl"
        self.assertEqual(len(store.read_text().strip().splitlines()), 2)
        # deeper extract ADDS the new message and never deletes the old ones
        self.fake_chatstorage(db, [(800000000, 0, "hello"), (800000060, 1, "hi back"),
                                   (800000120, 0, "one more thing")])
        wa_mod.cmd_extract(self.root)
        lines = store.read_text().strip().splitlines()
        self.assertEqual(len(lines), 3)
        wa_mod.cmd_extract(self.root)                 # idempotent: nothing duplicated
        self.assertEqual(len(store.read_text().strip().splitlines()), 3)
        self.assertIn("@lid", lines[0])               # jid preserved, keyed by NAME


class TestNumbersLedger(SpineTmp):
    def test_record_check_render(self):
        data = self.root / "data.csv"
        data.write_text("a,b\n1,2\n")
        self.run_py(NUMBERS, "record", "--key", "mortality_over40", "--value", "0.82",
                    "--script", "analysis/03.py", "--inputs", str(data), "--unit", "proportion")
        doc = self.root / "report.md"
        doc.write_text("Mortality above 40% TBSA was {{num:mortality_over40}}, versus {{num:mortality_under40}} below.")
        r = self.run_py(NUMBERS, "check", str(doc), check=False)
        self.assertEqual(r.returncode, 2)                       # unledgered number → publish refused
        self.assertIn("mortality_under40", r.stdout)
        r = self.run_py(NUMBERS, "render", str(doc), str(self.root / "out.md"), check=False)
        self.assertNotEqual(r.returncode, 0)                    # render refuses too
        self.run_py(NUMBERS, "record", "--key", "mortality_under40", "--value", "0.21",
                    "--script", "analysis/03.py", "--inputs", str(data))
        r = self.run_py(NUMBERS, "check", str(doc))
        self.assertIn("all ledgered", r.stdout)
        self.run_py(NUMBERS, "render", str(doc), str(self.root / "out.md"))
        out = (self.root / "out.md").read_text()
        self.assertIn("0.82 proportion", out)
        self.assertIn("0.21", out)
        self.assertNotIn("{{num:", out)
        # latest wins: re-record after a corrected analysis
        self.run_py(NUMBERS, "record", "--key", "mortality_over40", "--value", "0.79",
                    "--script", "analysis/03.py", "--inputs", str(data))
        r = self.run_py(NUMBERS, "get", "mortality_over40")
        self.assertIn("0.79", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
