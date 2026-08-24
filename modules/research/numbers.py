#!/usr/bin/env python3
"""numbers — the numbers ledger: every published quantity is computed, recorded,
and re-derivable. No number enters prose by hand.

The generic Central Dogma for research (docs/architecture-v03.md §4):

  DATA (immutable) → ANALYSIS (pinned Python) → NUMBERS LEDGER → PROSE → RENDERS

An analysis script RECORDS what it computed (key, value, script, input hashes).
Prose cites numbers by key: {{num:mortality_over40}}. CHECK fails any document
citing a key the ledger does not hold; RENDER substitutes values. Consequences:
no transcribed figures, no orphaned numbers, every quantity traceable to a
script and the exact inputs it ran on.

The ledger is append-only and folds latest-wins per key — the same law as every
other spine ledger. Third-party numbers are never recorded directly: reproduce
their analysis on your data, record YOUR computed value, and report the
concordance; what will not reconcile is a finding.

  python3 modules/research/numbers.py record --key mortality_over40 --value 0.82 \
      --script analysis/03_outcomes.py --inputs data/cohort.csv [--unit "%"] [--note "..."]
  python3 modules/research/numbers.py get mortality_over40
  python3 modules/research/numbers.py check docs/report.md      # exit 2 on missing keys
  python3 modules/research/numbers.py render docs/report.md out/report.md
  python3 modules/research/numbers.py list
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR.parent.parent))
import spine  # noqa: E402

REF = re.compile(r"\{\{num:([A-Za-z0-9_.-]+)\}\}")


def ledger_path(root):
    d = root / "research"
    d.mkdir(exist_ok=True)
    return d / "numbers.jsonl"


def fold_numbers(root):
    """Latest-wins per key, exactly like a case ledger."""
    out = {}
    path = ledger_path(root)
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if rec.get("key"):
            out[rec["key"]] = rec
    return out


def fmt(rec):
    v = rec.get("value")
    if isinstance(v, float):
        s = f"{v:.6g}"
    else:
        s = str(v)
    return s + (f" {rec['unit']}" if rec.get("unit") else "")


def cmd_record(args):
    root = spine.find_root()
    inputs_sha = None
    if args.inputs:
        h = hashlib.sha256()
        for f in args.inputs:
            p = Path(f)
            if not p.is_file():
                sys.exit(f"numbers: input {f} not found — record only what was actually computed from real inputs")
            h.update(p.read_bytes())
        inputs_sha = h.hexdigest()
    try:
        value = float(args.value)
    except ValueError:
        value = args.value                      # counts, labels, CIs as strings are allowed
    rec = {"ts": spine.now_iso(), "key": args.key, "value": value,
           "script": args.script, "inputs_sha256": inputs_sha,
           "unit": args.unit, "note": args.note, "author": spine.get_author(None, root)}
    with open(ledger_path(root), "a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in rec.items() if v is not None}, ensure_ascii=False) + "\n")
    spine.manifest_add(root, ledger_path(root))
    print(f"✓ recorded {args.key} = {fmt(rec)} (script: {args.script or '?'}, inputs: {inputs_sha[:12] if inputs_sha else 'none'})")


def cmd_get(args):
    root = spine.find_root()
    rec = fold_numbers(root).get(args.key)
    if not rec:
        sys.exit(f"numbers: no key '{args.key}' in the ledger")
    print(f"{args.key} = {fmt(rec)}")
    print(f"  script: {rec.get('script','?')} · inputs: {str(rec.get('inputs_sha256'))[:16]} · {rec.get('ts')} · {rec.get('author','?')}")


def doc_keys(text):
    return [m.group(1) for m in REF.finditer(text)]


def cmd_check(args):
    root = spine.find_root()
    nums = fold_numbers(root)
    failed = False
    for doc in args.docs:
        text = Path(doc).read_text(encoding="utf-8")
        keys = doc_keys(text)
        missing = sorted({k for k in keys if k not in nums})
        if missing:
            failed = True
            print(f"⚠ {doc}: {len(missing)} number reference(s) NOT in the ledger: {', '.join(missing)}")
            print("  a number that was not computed and recorded may not be published — run the analysis, record it, re-check")
        else:
            print(f"✓ {doc}: {len(keys)} number reference(s), all ledgered")
    sys.exit(2 if failed else 0)


def cmd_render(args):
    root = spine.find_root()
    nums = fold_numbers(root)
    text = Path(args.src).read_text(encoding="utf-8")
    missing = sorted({k for k in doc_keys(text) if k not in nums})
    if missing:
        sys.exit(f"numbers: render refused — unledgered references: {', '.join(missing)}")
    out = REF.sub(lambda m: fmt(nums[m.group(1)]), text)
    dst = Path(args.dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding="utf-8")
    spine.manifest_add(root, dst)
    print(f"✓ rendered {args.dst}: every number substituted from the ledger (edit the source, re-render)")


def cmd_list(args):
    root = spine.find_root()
    nums = fold_numbers(root)
    if not nums:
        print("numbers: ledger is empty")
        return
    for k in sorted(nums):
        r = nums[k]
        print(f"{k:<32} {fmt(r):<18} {r.get('script','?')}")


def main():
    ap = argparse.ArgumentParser(description="the numbers ledger: computed, recorded, re-derivable")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record"); p.add_argument("--key", required=True); p.add_argument("--value", required=True)
    p.add_argument("--script"); p.add_argument("--inputs", nargs="*"); p.add_argument("--unit"); p.add_argument("--note")
    p.set_defaults(fn=cmd_record)
    p = sub.add_parser("get"); p.add_argument("key"); p.set_defaults(fn=cmd_get)
    p = sub.add_parser("check"); p.add_argument("docs", nargs="+"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("render"); p.add_argument("src"); p.add_argument("dst"); p.set_defaults(fn=cmd_render)
    p = sub.add_parser("list"); p.set_defaults(fn=cmd_list)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
