#!/usr/bin/env python3
"""api — generic pull adapter: external feeds become append-only facts on the spine.

Feeds are FACTS; messages are CLAIMS (SPINE.md §5). Each source declares what it
is authoritative FOR, and its records land append-only under channels/api/<name>/
with a content hash, so re-fetching identical data adds nothing and history is
never rewritten. Report-only: never commits (spine.py sync owns transport).

Config (modules/api/sources.json — copy sources.example.json):
  {"sources": [{"name": "bank-feed", "url": "https://...", "auth_env": "SPINE_API_BANK",
                "headers": {"Accept": "application/json"},
                "authoritative_for": "payments: a payment exists when it appears here"}]}

Run:  python3 modules/api/fetch.py [--source name]
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR.parent.parent))
import spine  # noqa: E402

import os  # noqa: E402

TIMEOUT = 30


def fetch_source(root, src):
    req = urllib.request.Request(src["url"])
    for k, v in (src.get("headers") or {}).items():
        req.add_header(k, v)
    if src.get("auth_env"):
        token = os.environ.get(src["auth_env"], "")
        if not token:
            raise RuntimeError(f"auth env {src['auth_env']} is not set (credentials never live in the repo)")
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read()
        status = getattr(resp, "status", 200)
    sha = hashlib.sha256(body).hexdigest()
    d = root / "channels" / "api" / src["name"]
    d.mkdir(parents=True, exist_ok=True)
    store = d / "records.jsonl"
    seen = set()
    if store.is_file():
        for raw in store.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(raw).get("sha"))
            except json.JSONDecodeError:
                continue
    if sha in seen:
        return False, sha
    text = body.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = text
    rec = {"ts": spine.now_iso(), "source": src["name"], "status": status, "sha": sha,
           "authoritative_for": src.get("authoritative_for", ""), "payload": payload}
    with open(store, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    spine.manifest_add(root, store)
    return True, sha


def main():
    ap = argparse.ArgumentParser(description="pull external feeds as append-only facts")
    ap.add_argument("--source", help="only this source")
    ap.add_argument("--config", default=str(MODULE_DIR / "sources.json"))
    args = ap.parse_args()
    root = spine.find_root()
    cfgp = Path(args.config)
    if not cfgp.is_file():
        sys.exit(f"api: no {cfgp}. Copy sources.example.json and edit.")
    sources = json.loads(cfgp.read_text()).get("sources", [])
    if args.source:
        sources = [s for s in sources if s["name"] == args.source]
    failures = []
    for src in sources:
        try:
            new, sha = fetch_source(root, src)
            print(f"✓ {src['name']}: {'new record' if new else 'unchanged (same content hash)'} · {sha[:12]}")
        except Exception as e:
            failures.append(src.get("name", "?"))
            print(f"⚠ {src.get('name','?')}: FAILED — {e}")
    print("note: facts recorded, nothing committed — share with: python3 spine.py sync. "
          "Reconcile spine claims against these records before acting on the claims.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
