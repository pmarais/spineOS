#!/usr/bin/env python3
"""whatsapp-local — ingest the local WhatsApp database (macOS) into a spine.

EXPERIMENTAL · macOS only · read-only. Sending stays entirely outside this
module: an outbound WhatsApp message is a gated action under SPINE.md.

The two laws, both paid for in production:

  1. COPY ALL THREE FILES. WhatsApp runs SQLite in WAL mode: a just-received
     message lives in ChatStorage.sqlite-wal until checkpointed. Copy the
     .sqlite alone and you get a file that opens cleanly, looks fresh, and is
     missing exactly the newest messages — the ones you are looking for.
  2. UNION, never replace. A shallower extract must never delete what a deeper
     one captured. Messages are keyed (ts, from_me, text) and only ever added.

Caveat carried from production: some chats use linked-identity JIDs
("...@lid") that contain NO phone number — never probe by number; this module
keys chats on the partner NAME and stores the JID alongside.

Run:
  python3 modules/whatsapp-local/ingest.py snapshot     # copy live DB (3 files) into the spine
  python3 modules/whatsapp-local/ingest.py extract      # snapshot -> per-chat jsonl (union)
  python3 modules/whatsapp-local/ingest.py sync         # both
Routing (optional routes.json): {"chats": {"Partner Name": "0001"}}
"""
import argparse
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR.parent.parent))
import spine  # noqa: E402

LIVE = Path.home() / "Library" / "Group Containers" / "group.net.whatsapp.WhatsApp.shared" / "ChatStorage.sqlite"
APPLE_EPOCH = 978307200  # 2001-01-01, WhatsApp's ZMESSAGEDATE base


def chan(root):
    d = root / "channels" / "whatsapp"
    (d / "snapshot").mkdir(parents=True, exist_ok=True)
    (d / "chats").mkdir(parents=True, exist_ok=True)
    return d


def cmd_snapshot(root, live=LIVE):
    if not live.is_file():
        sys.exit("whatsapp-local: live ChatStorage.sqlite not found (is WhatsApp Desktop installed? macOS only)")
    dest = chan(root) / "snapshot"
    copied = []
    for suffix in ("", "-wal", "-shm"):        # ALL THREE FILES, always
        src = Path(str(live) + suffix)
        if src.is_file():
            shutil.copy2(src, dest / src.name)
            copied.append(src.name)
    print(f"✓ snapshot: {', '.join(copied)} → {dest.relative_to(root)}")
    if "ChatStorage.sqlite-wal" not in copied:
        print("note: no -wal file present (checkpointed); nothing missing.")
    return dest / "ChatStorage.sqlite"


def read_snapshot(db_path):
    """Yield (partner_name, jid, messages[{ts, from_me, text}]) per chat session."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        sessions = conn.execute(
            "SELECT Z_PK, COALESCE(ZPARTNERNAME,''), COALESCE(ZCONTACTJID,'') FROM ZWACHATSESSION").fetchall()
        for pk, name, jid in sessions:
            rows = conn.execute(
                "SELECT ZMESSAGEDATE, ZISFROMME, ZTEXT FROM ZWAMESSAGE "
                "WHERE ZCHATSESSION=? AND ZTEXT IS NOT NULL ORDER BY ZMESSAGEDATE", (pk,)).fetchall()
            msgs = [{"ts": spine.datetime.fromtimestamp(t + APPLE_EPOCH).astimezone().isoformat(timespec="seconds"),
                     "from_me": bool(fm), "text": txt}
                    for t, fm, txt in rows if t is not None]
            if msgs:
                yield (name or jid or f"session-{pk}"), jid, msgs
    finally:
        conn.close()


def cmd_extract(root):
    db = chan(root) / "snapshot" / "ChatStorage.sqlite"
    if not db.is_file():
        sys.exit("whatsapp-local: no snapshot yet — run: ingest.py snapshot")
    routes = {}
    rp = MODULE_DIR / "routes.json"
    if rp.is_file():
        routes = (json.loads(rp.read_text()).get("chats") or {})
    by_case = {d.name[:4]: d for d in spine.case_dirs(root)}
    total_new = 0
    for name, jid, msgs in read_snapshot(db):
        slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "unknown"
        store = chan(root) / "chats" / f"{slug}.jsonl"
        known = set()
        if store.is_file():
            for raw in store.read_text(encoding="utf-8").splitlines():
                try:
                    o = json.loads(raw)
                    known.add((o.get("ts"), o.get("from_me"), o.get("text")))
                except json.JSONDecodeError:
                    continue
        new = [m for m in msgs if (m["ts"], m["from_me"], m["text"]) not in known]
        if not new:
            continue
        with open(store, "a", encoding="utf-8") as f:  # UNION: only ever added
            for m in new:
                f.write(json.dumps({**m, "chat": name, "jid": jid}, ensure_ascii=False) + "\n")
        spine.manifest_add(root, store)
        total_new += len(new)
        case_no = routes.get(name)
        cdir = by_case.get(str(case_no).zfill(4)) if case_no else None
        if cdir:
            with open(cdir / "WHATSAPP.jsonl", "a", encoding="utf-8") as f:
                for m in new:
                    f.write(json.dumps({**m, "chat": name}, ensure_ascii=False) + "\n")
            spine.manifest_add(root, cdir / "WHATSAPP.jsonl")
        print(f"✓ {name}: +{len(new)}" + (f" → routed to {cdir.name}" if cdir else ""))
    print(f"extract: {total_new} new message(s). Nothing sent, nothing committed — share with: python3 spine.py sync")


def main():
    ap = argparse.ArgumentParser(description="local WhatsApp ingest (macOS, read-only, union)")
    ap.add_argument("cmd", choices=["snapshot", "extract", "sync"])
    args = ap.parse_args()
    root = spine.find_root()
    if args.cmd in ("snapshot", "sync"):
        cmd_snapshot(root)
    if args.cmd in ("extract", "sync"):
        cmd_extract(root)


if __name__ == "__main__":
    main()
