#!/usr/bin/env python3
"""email-imap — generic IMAP ingest for a spine. Stdlib only (imaplib/email).

Works against any IMAP host (privateemail.com, Gmail app passwords, self-hosted).
The contract (docs/architecture-v03.md §2), each rule earned in production:

  - FULL BODIES, always. A request hidden past a preview cut once went unanswered
    for 27 days. `body` is complete; previews are display-only.
  - UNION, never replace. The window (--days) controls what we LOOK at, never what
    we KEEP: messages are keyed (account/mailbox/uid) and only ever added.
  - ROUTE to cases via routes.json; one case may have MANY addresses (a client's
    second address once routed nowhere for 30 of her 33 sends). Unroutable mail
    lands in unrouted.jsonl — silence is never "no mail".
  - PARTIAL FAILURE IS VISIBLE. A timed-out account cannot stamp freshness for a
    window it did not cover; the run exits non-zero if any account failed.
  - REPORT-ONLY. This module never sends, never commits; `spine.py sync` owns
    transport. Written paths are added to the session manifest.

Config (modules/email-imap/config.json — copy config.example.json):
  {"accounts": [{"name": "main", "host": "mail.privateemail.com", "port": 993,
                 "user": "you@yourfirm.com", "password_env": "SPINE_IMAP_MAIN",
                 "mailboxes": ["INBOX", "Sent"]}]}
Routing (modules/email-imap/routes.json):
  {"addresses": {"client@x.com": "0001", "client.second@y.com": "0001"}}

Run:  python3 modules/email-imap/ingest.py --days 7 [--account main]
"""
import argparse
import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR.parent.parent))
import spine  # noqa: E402  (manifest + root discovery + now_iso)

IMAP_TIMEOUT = 60  # per-operation; the run loop is also bounded per account


# ------------------------------------------------------------------ helpers

def decode_header(raw):
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out).strip()


def addresses(msg, *headers):
    found = []
    for h in headers:
        for _, addr in email.utils.getaddresses(msg.get_all(h, [])):
            if addr:
                found.append(addr.lower())
    return found


def full_body(msg):
    """FULL text body: prefer text/plain, fall back to de-tagged HTML. Never truncated."""
    plains, htmls = [], []
    for part in msg.walk():
        ct = part.get_content_type()
        if ct not in ("text/plain", "text/html") or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        (plains if ct == "text/plain" else htmls).append(text)
    if plains:
        return "\n".join(plains)
    if htmls:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", "\n".join(htmls), flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"[ \t]+", " ", text).strip()
    return ""


def message_record(account, mailbox, uid, msg):
    return {
        "key": f"{account}/{mailbox}/{uid}",
        "account": account, "mailbox": mailbox, "uid": uid,
        "message_id": decode_header(msg.get("Message-ID", "")),
        "date": decode_header(msg.get("Date", "")),
        "from": addresses(msg, "From"),
        "to": addresses(msg, "To"),
        "cc": addresses(msg, "Cc"),
        "subject": decode_header(msg.get("Subject", "")),
        "body": full_body(msg),           # FULL, by law
        "fetched_at": spine.now_iso(),
    }


# ------------------------------------------------------- store (union, append)

def channel_dir(root):
    d = root / "channels" / "email"
    d.mkdir(parents=True, exist_ok=True)
    return d


def existing_keys(path):
    keys = set()
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                keys.add(json.loads(raw).get("key"))
            except json.JSONDecodeError:
                continue
    return keys


def append_records(root, path, records):
    if not records:
        return
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    spine.manifest_add(root, path)


def route_records(root, routes, records):
    """Route each new message to its case's EMAIL.jsonl by ANY matching address
    (from for inbound, to/cc for our outbound). Unmatched → unrouted.jsonl.
    Returns (routed_count, unrouted_count)."""
    amap = {k.lower(): v for k, v in (routes.get("addresses") or {}).items()}
    by_case_dir = {}
    for d in spine.case_dirs(root):
        by_case_dir[d.name[:4]] = d
    routed, unrouted = 0, []
    for r in records:
        case_no = None
        for addr in r["from"] + r["to"] + r["cc"]:
            if addr in amap:
                case_no = str(amap[addr]).zfill(4)
                break
        cdir = by_case_dir.get(case_no) if case_no else None
        if cdir:
            append_records(root, cdir / "EMAIL.jsonl", [r])
            routed += 1
        else:
            unrouted.append(r)
    append_records(root, channel_dir(root) / "unrouted.jsonl", unrouted)
    return routed, len(unrouted)


# ---------------------------------------------------------------- imap fetch

def fetch_account(root, acct, days):
    """Fetch one account. Returns (new_records, stats) or raises on failure."""
    password = os.environ.get(acct.get("password_env", ""), "")
    if not password:
        raise RuntimeError(f"password env {acct.get('password_env')} is not set (credentials never live in the repo)")
    socket.setdefaulttimeout(IMAP_TIMEOUT)
    conn = imaplib.IMAP4_SSL(acct["host"], int(acct.get("port", 993)))
    conn.login(acct["user"], password)
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    store = channel_dir(root) / "threads.jsonl"
    known = existing_keys(store)
    new, seen = [], 0
    try:
        for mailbox in acct.get("mailboxes", ["INBOX"]):
            if conn.select(f'"{mailbox}"', readonly=True)[0] != "OK":
                continue
            ok, data = conn.uid("search", None, f"(SINCE {since})")
            if ok != "OK":
                continue
            uids = data[0].split()
            seen += len(uids)
            for uid in uids:
                key = f"{acct['name']}/{mailbox}/{uid.decode()}"
                if key in known:
                    continue                      # union: look again, keep once
                ok, msgdata = conn.uid("fetch", uid, "(RFC822)")
                if ok != "OK" or not msgdata or msgdata[0] is None:
                    continue
                msg = email.message_from_bytes(msgdata[0][1])
                new.append(message_record(acct["name"], mailbox, uid.decode(), msg))
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    append_records(root, store, new)
    return new, {"seen_in_window": seen, "new": len(new)}


def stamp_freshness(root, account, days):
    """Depth-aware freshness stamp, written ONLY for accounts that fully succeeded."""
    path = channel_dir(root) / "state.json"
    state = {}
    if path.is_file():
        try:
            state = json.loads(path.read_text())
        except json.JSONDecodeError:
            state = {}
    state[account] = {"last_sync": spine.now_iso(), "days": days}
    path.write_text(json.dumps(state, indent=2) + "\n")
    spine.manifest_add(root, path)


# ----------------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description="IMAP ingest: union, full bodies, routed to cases, report-only")
    ap.add_argument("--days", type=int, default=7, help="window to LOOK at (never controls what is kept)")
    ap.add_argument("--account", help="only this account")
    ap.add_argument("--config", default=str(MODULE_DIR / "config.json"))
    ap.add_argument("--routes", default=str(MODULE_DIR / "routes.json"))
    args = ap.parse_args()

    root = spine.find_root()
    cfgp = Path(args.config)
    if not cfgp.is_file():
        sys.exit(f"email-imap: no {cfgp}. Copy config.example.json and edit (passwords via env, never in the repo).")
    accounts = json.loads(cfgp.read_text()).get("accounts", [])
    if args.account:
        accounts = [a for a in accounts if a["name"] == args.account]
    routes = {}
    rp = Path(args.routes)
    if rp.is_file():
        routes = json.loads(rp.read_text())

    failures = []
    all_new = []
    for acct in accounts:
        try:
            new, stats = fetch_account(root, acct, args.days)
            all_new += new
            stamp_freshness(root, acct["name"], args.days)
            print(f"✓ {acct['name']}: {stats['seen_in_window']} in window · {stats['new']} new")
        except Exception as e:  # partial failure must be visible, never silent
            failures.append((acct.get("name", "?"), str(e)))
            print(f"⚠ {acct.get('name','?')}: FAILED — {e} (freshness NOT stamped for this account)")
    routed, unrouted = route_records(root, routes, all_new)
    print(f"routed {routed} to cases · {unrouted} unrouted"
          + (" (review channels/email/unrouted.jsonl — an unrouted message is a waiting client)" if unrouted else ""))
    print("note: nothing was sent, nothing was committed — share with: python3 spine.py sync")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
