#!/usr/bin/env python3
"""
spine.py — SpineOS v0: durable, append-only operational state for humans and
AI agents working together.

Single file, standard library only, Python 3.9+. No API keys, no server,
no dependencies. Designed to be operated BY an agent CLI you already
subscribe to (Claude Code, Grok CLI, Codex CLI, Cursor) — the agent is the
interpreter, the spine is the state.

The five primitives (per case, in cases/NNNN_slug/):
  PROMISE.json   the commitment, snapshotted at acceptance (rewritten only
                 when the deal itself changes, and the change is ledgered)
  LEDGER.jsonl   append-only position record; current state is FOLDED:
                 latest non-null value per field wins, by timestamp
  LOG.csv        append-only action record: what was done, by whom, when
Repo level:
  SPINE.md       the operating rules the agent reads at boot
  projections    printed by show/worklist/sitrep — computed, never stored

Verbs:
  init · new · promise · append · show · fold · worklist · doctor · sitrep · seed

Hard rules implemented here:
  - append only: this tool never edits or deletes a ledger line or log row
  - one verb writes both ledgers: append writes LEDGER + LOG together
  - attribution: every write carries an author (SPINE_OPERATOR env,
    .spine/config.json, or --author)
"""

import argparse
import csv
import io
import json
import os
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

# ---------------------------------------------------------------- constants

LEDGER_FIELDS = [
    "stage", "owner", "paid", "blocked_on", "deadline",
    "asks_them", "asks_us", "next", "complexity",
]
LIST_FIELDS = {"blocked_on", "asks_them", "asks_us"}
STAGES = ["intake", "agreed", "in_progress", "in_review", "done", "closed"]
LOG_COLUMNS = ["ts", "author", "action", "ref", "note"]
STALE_DAYS = 7
DEADLINE_SOON_DAYS = 7


# ---------------------------------------------------------------- utilities

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> date:
    return date.today()


def die(msg: str, code: int = 1):
    print(f"spine: {msg}", file=sys.stderr)
    sys.exit(code)


def find_root(start: Path = None) -> Path:
    """The spine root is the nearest ancestor directory containing SPINE.md."""
    p = (start or Path.cwd()).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "SPINE.md").is_file():
            return candidate
    die("no SPINE.md found here or above. Run 'spine.py init' to start a spine.")


def get_author(cli_author: str = None, root: Path = None) -> str:
    if cli_author:
        return cli_author
    env = os.environ.get("SPINE_OPERATOR")
    if env:
        return env
    if root:
        cfg = root / ".spine" / "config.json"
        if cfg.is_file():
            try:
                op = json.loads(cfg.read_text()).get("operator")
                if op:
                    return op
            except (json.JSONDecodeError, OSError):
                pass
    return "unattributed"


def case_dirs(root: Path):
    cdir = root / "cases"
    if not cdir.is_dir():
        return []
    return sorted(d for d in cdir.iterdir()
                  if d.is_dir() and re.match(r"^\d{4}_", d.name))


def resolve_case(root: Path, ident: str) -> Path:
    """Match a case by number, exact name, or unique substring."""
    dirs = case_dirs(root)
    num = ident.zfill(4) if ident.isdigit() else None
    exact = [d for d in dirs if d.name == ident or (num and d.name.startswith(num + "_"))]
    if len(exact) == 1:
        return exact[0]
    subs = [d for d in dirs if ident.lower() in d.name.lower()]
    if len(subs) == 1:
        return subs[0]
    if not subs:
        die(f"no case matches '{ident}'. Existing: " + (", ".join(d.name for d in dirs) or "(none)"))
    die(f"'{ident}' is ambiguous: " + ", ".join(d.name for d in subs))


def read_ledger(cdir: Path):
    """Return (lines:list[dict], errors:list[str]). Never raises on bad lines."""
    path = cdir / "LEDGER.jsonl"
    lines, errors = [], []
    if not path.is_file():
        return lines, errors
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError("not an object")
            lines.append(obj)
        except (json.JSONDecodeError, ValueError) as e:
            errors.append(f"LEDGER.jsonl line {i}: {e}")
    lines.sort(key=lambda o: o.get("ts", ""))
    return lines, errors


def fold_ledger(lines):
    """LATEST WINS: the last non-null value of each field, scanning from the end."""
    state = {}
    for line in lines:
        for k, v in line.items():
            if v is not None and k not in ("note",):
                state[k] = v
    notes = [{"ts": l.get("ts", ""), "author": l.get("author", ""), "note": l["note"]}
             for l in lines if l.get("note")]
    state["_notes"] = notes
    state["_n_lines"] = len(lines)
    if lines:
        state["_last_ts"] = lines[-1].get("ts", "")
        state["_last_author"] = lines[-1].get("author", "")
    return state


def read_promise(cdir: Path):
    path = cdir / "PROMISE.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"_error": f"PROMISE.json invalid: {e}"}


def parse_iso_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def money(n):
    try:
        return f"{float(n):,.0f}"
    except (TypeError, ValueError):
        return str(n)


def promise_outstanding(promise):
    """Sum of milestones not marked paid; falls back to total."""
    if not promise:
        return None
    ms = promise.get("milestones") or []
    if ms:
        return sum(float(m.get("amount", 0)) for m in ms
                   if str(m.get("status", "outstanding")).lower() != "paid")
    return None


def append_log_row(cdir: Path, ts, author, action, ref, note):
    path = cdir / "LOG.csv"
    new = not path.is_file()
    buf = io.StringIO()
    w = csv.writer(buf)
    if new:
        w.writerow(LOG_COLUMNS)
    w.writerow([ts, author, action, ref or "", note or ""])
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())


# ------------------------------------------------------------------- verbs

def cmd_init(args):
    root = Path.cwd()
    if (root / "SPINE.md").is_file():
        die("SPINE.md already exists here; this is already a spine.")
    # SPINE.md ships with the repo; if the user inits elsewhere, copy from the
    # repo the script lives in (single source: the file next to spine.py).
    src = Path(__file__).resolve().parent / "SPINE.md"
    if src.is_file():
        (root / "SPINE.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        (root / "SPINE.md").write_text("# SPINE — operating rules\n\n(write your rules here)\n", encoding="utf-8")
    (root / "cases").mkdir(exist_ok=True)
    (root / ".spine").mkdir(exist_ok=True)
    cfg = root / ".spine" / "config.json"
    operator = args.operator or os.environ.get("SPINE_OPERATOR") or ""
    cfg.write_text(json.dumps({"operator": operator, "created": now_iso()}, indent=2), encoding="utf-8")
    print(f"✓ spine initialised at {root}")
    print(f"  operator: {operator or '(unset — set SPINE_OPERATOR or edit .spine/config.json)'}")
    print("  next: read SPINE.md, then 'spine.py new <slug>' to open your first case")


def cmd_new(args):
    root = find_root()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", args.slug).strip("_")
    if not slug:
        die("slug must contain letters or digits")
    dirs = case_dirs(root)
    nxt = max((int(d.name[:4]) for d in dirs), default=0) + 1
    cdir = root / "cases" / f"{nxt:04d}_{slug}"
    cdir.mkdir(parents=True)
    (cdir / "LEDGER.jsonl").touch()
    author = get_author(args.author, root)
    ts = now_iso()
    entry = {"ts": ts, "author": author, "stage": "intake",
             "note": args.note or f"Case opened: {args.slug}"}
    with open(cdir / "LEDGER.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    append_log_row(cdir, ts, author, "CREATE", "spine new", args.note or "case opened")
    print(f"✓ created {cdir.relative_to(root)} (stage: intake, author: {author})")
    print("  next: 'spine.py promise' when a deal is accepted; 'spine.py append' as things move")


def cmd_promise(args):
    root = find_root()
    cdir = resolve_case(root, args.case)
    path = cdir / "PROMISE.json"
    existing = read_promise(cdir)
    if existing and not args.force:
        die("PROMISE.json exists. A promise changes only when the deal itself changes; "
            "re-run with --force and the change is ledgered as old → new.")
    if args.json:
        try:
            promise = json.loads(args.json)
        except json.JSONDecodeError as e:
            die(f"--json is not valid JSON: {e}")
    else:
        promise = {}
        for k in ("client", "type", "scope", "deadline", "currency", "accepted_on"):
            v = getattr(args, k, None)
            if v:
                promise[k] = v
        if args.total is not None:
            promise["total"] = args.total
        promise.setdefault("accepted_on", str(today()))
        promise.setdefault("currency", "USD")
        ms = []
        for spec in (args.milestone or []):
            parts = spec.split(":")
            if len(parts) < 2:
                die(f"--milestone '{spec}' must be label:amount[:status]")
            ms.append({"label": parts[0], "amount": float(parts[1]),
                       "status": parts[2] if len(parts) > 2 else "outstanding"})
        if ms:
            promise["milestones"] = ms
        promise.setdefault("exceptions", [])
    promise["case"] = cdir.name
    author = get_author(args.author, root)
    ts = now_iso()
    note = (f"PROMISE {'re-written' if existing else 'written'}: "
            f"{promise.get('client','?')} · total {promise.get('total','?')} {promise.get('currency','')}"
            + (f" · was: total {existing.get('total','?')}" if existing else ""))
    path.write_text(json.dumps(promise, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    entry = {"ts": ts, "author": author, "stage": "agreed", "note": note}
    with open(cdir / "LEDGER.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    append_log_row(cdir, ts, author, "PROMISE", "spine promise", note)
    print(f"✓ {cdir.name}: promise written, stage → agreed")


def cmd_append(args):
    root = find_root()
    cdir = resolve_case(root, args.case)
    author = get_author(args.author, root)
    ts = now_iso()
    entry = {"ts": ts, "author": author}
    if args.stage:
        if args.stage not in STAGES:
            die(f"stage '{args.stage}' not in vocabulary {STAGES} (edit SPINE.md to change it)")
        entry["stage"] = args.stage
    for flag, key in [("owner", "owner"), ("deadline", "deadline"),
                      ("next", "next"), ("complexity", "complexity")]:
        v = getattr(args, flag)
        if v is not None:
            entry[key] = v
    for flag, key in [("blocked_on", "blocked_on"), ("asks_them", "asks_them"),
                      ("asks_us", "asks_us")]:
        v = getattr(args, flag)
        if v is not None:
            entry[key] = [s.strip() for s in v.split(",") if s.strip()]
    if args.paid is not None:
        entry["paid"] = args.paid
    for kv in (args.field or []):
        if "=" not in kv:
            die(f"--field '{kv}' must be key=value")
        k, v = kv.split("=", 1)
        entry[k] = v
    if args.note:
        entry["note"] = args.note
    if len(entry) == 2:
        die("nothing to append: give at least one field or --note")
    with open(cdir / "LEDGER.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    append_log_row(cdir, ts, author, args.action or "STATUS", args.ref or "spine append",
                   args.note or "")
    print(f"✓ {cdir.name}: ledger +1 · log +1 · author {author}")


def render_show(root: Path, cdir: Path) -> str:
    promise = read_promise(cdir)
    lines, errors = read_ledger(cdir)
    st = fold_ledger(lines)
    out = []
    head = f"CASE {cdir.name}"
    if promise and promise.get("type"):
        head += f" · type: {promise['type']}"
    head += f" · stage: {st.get('stage','?')} · owner: {st.get('owner','?')}"
    out.append(head)
    if promise:
        if "_error" in promise:
            out.append(f"PROMISE  ⚠ {promise['_error']}")
        else:
            p = (f"PROMISE  {promise.get('client','?')} · total "
                 f"{money(promise.get('total','?'))} {promise.get('currency','')}"
                 f" · accepted {promise.get('accepted_on','?')}")
            if promise.get("deadline"):
                p += f" · deadline {promise['deadline']}"
            out.append(p)
            ms = promise.get("milestones") or []
            if ms:
                out.append("  milestones: " + " · ".join(
                    f"{m.get('label')} {money(m.get('amount'))} [{m.get('status','outstanding')}]" for m in ms))
            if promise.get("scope"):
                out.append(f"  scope: {promise['scope']}")
            if promise.get("exceptions"):
                out.append(f"  exceptions: {json.dumps(promise['exceptions'], ensure_ascii=False)}")
    else:
        out.append("PROMISE  (none yet — this case has no accepted deal)")
    pos = f"POSITION folded from {st['_n_lines']} ledger lines"
    if st.get("_last_ts"):
        pos += f", last {st['_last_ts']} by {st.get('_last_author','?')}"
    out.append(pos)
    for k in ("blocked_on", "asks_us", "asks_them", "deadline", "paid", "complexity"):
        if st.get(k) not in (None, [], ""):
            v = st[k]
            if k == "paid":
                v = money(v)
            out.append(f"  {k}: {', '.join(v) if isinstance(v, list) else v}")
    outn = promise_outstanding(promise)
    if outn is not None:
        out.append(f"  outstanding (from promise milestones): {money(outn)} {promise.get('currency','')}")
    if st.get("next"):
        out.append(f"  NEXT: {st['next']}")
    notes = st["_notes"][-args_show_notes:] if st["_notes"] else []
    if notes:
        out.append("RECENT NOTES")
        for n in notes:
            out.append(f"  [{n['ts']} {n['author']}] {n['note']}")
    for e in errors:
        out.append(f"⚠ {e}")
    out.append("RULES: SPINE.md governs. Irreversible actions need a recorded authorisation first (AUTH_GRANT), consumed by the action it authorises.")
    return "\n".join(out)


args_show_notes = 5  # module default; overridden by --notes


def cmd_show(args):
    global args_show_notes
    args_show_notes = args.notes
    root = find_root()
    cdir = resolve_case(root, args.case)
    print(render_show(root, cdir))


def cmd_fold(args):
    root = find_root()
    cdir = resolve_case(root, args.case)
    lines, errors = read_ledger(cdir)
    st = fold_ledger(lines)
    st.pop("_notes", None)
    result = {"case": cdir.name, "state": st, "promise": read_promise(cdir), "errors": errors}
    print(json.dumps(result, indent=2, ensure_ascii=False))


def rank_case(cdir: Path):
    """Return (priority:int 1..3, reasons:list[str], summary:dict)."""
    promise = read_promise(cdir)
    lines, _ = read_ledger(cdir)
    st = fold_ledger(lines)
    stage = st.get("stage", "?")
    reasons = []
    pri = 3
    dl = parse_iso_date(st.get("deadline") or (promise or {}).get("deadline"))
    if dl and stage not in ("done", "closed"):
        days = (dl - today()).days
        if days < 0:
            pri = 1; reasons.append(f"deadline passed {-days}d")
        elif days <= DEADLINE_SOON_DAYS:
            pri = 1; reasons.append(f"deadline in {days}d")
    blocked = st.get("blocked_on") or []
    if any(b in ("us", "we", "owner", "internal") or b == st.get("owner")
           for b in blocked):
        pri = 1; reasons.append("blocked on us")
    outn = promise_outstanding(promise)
    if pri > 1 and outn and outn > 0 and stage not in ("closed",):
        pri = 2; reasons.append(f"money due {money(outn)}")
    if pri > 2 and st.get("asks_us"):
        pri = 2; reasons.append("we owe work")
    return pri, reasons, {
        "case": cdir.name, "stage": stage, "owner": st.get("owner", "?"),
        "deadline": st.get("deadline") or (promise or {}).get("deadline") or "",
        "paid": st.get("paid", ""), "total": (promise or {}).get("total", ""),
        "next": st.get("next", ""), "last": st.get("_last_ts", ""),
    }


def cmd_worklist(args):
    root = find_root()
    rows = []
    for cdir in case_dirs(root):
        pri, reasons, s = rank_case(cdir)
        if s["stage"] in ("done", "closed") and not args.all:
            continue
        rows.append((pri, reasons, s))
    rows.sort(key=lambda r: (r[0], r[2]["deadline"] or "9999", r[2]["case"]))
    if not rows:
        print("worklist: no open cases. 'spine.py new <slug>' opens one.")
        return
    print(f"{'P':<3}{'case':<27}{'stage':<13}{'owner':<10}{'paid/total':<16}{'deadline':<12}next")
    for pri, reasons, s in rows:
        pt = f"{money(s['paid']) if s['paid'] != '' else '-'}/{money(s['total']) if s['total'] != '' else '-'}"
        nxt = (s["next"] or "")[:60] + (" …" if len(s.get("next") or "") > 60 else "")
        name = s["case"][:25] + " " if len(s["case"]) > 26 else s["case"]
        print(f"P{pri:<2}{name:<27}{s['stage']:<13}{str(s['owner']):<10}{pt:<16}{str(s['deadline']):<12}{nxt}")
        if reasons:
            print(f"   {'':<25}↳ {', '.join(reasons)}")


def cmd_doctor(args):
    root = find_root()
    flags = 0
    for cdir in case_dirs(root):
        problems = []
        promise = read_promise(cdir)
        lines, errors = read_ledger(cdir)
        problems += errors
        st = fold_ledger(lines)
        stage = st.get("stage", "?")
        if promise and "_error" in promise:
            problems.append(promise["_error"])
        if not lines:
            problems.append("empty ledger: the case exists but has no recorded position")
        else:
            last = parse_iso_date(st.get("_last_ts", "")[:10])
            if last and stage not in ("done", "closed") and (today() - last).days > STALE_DAYS:
                problems.append(f"stale: last ledger line {(today() - last).days}d old on an open case")
        if stage in ("in_progress", "in_review") and not promise:
            problems.append(f"stage '{stage}' but PROMISE.json missing: an accepted engagement needs its deal snapshot")
        dl = parse_iso_date(st.get("deadline") or (promise or {}).get("deadline"))
        if dl and stage not in ("done", "closed") and dl < today():
            problems.append(f"DEADLINE PASSED {(today() - dl).days}d ago ({dl})")
        # ledger lines should have a same-day log row (dual-logging drift check)
        log_days = set()
        logp = cdir / "LOG.csv"
        if logp.is_file():
            with open(logp, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    log_days.add(str(row.get("ts", ""))[:10])
        for l in lines:
            d = str(l.get("ts", ""))[:10]
            if d and d not in log_days:
                problems.append(f"ledger line {d} has no LOG.csv row that day (dual-logging drift)")
                break
        if problems:
            flags += len(problems)
            print(f"{cdir.name}:")
            for p in problems:
                print(f"  ⚠ {p}")
    n = len(case_dirs(root))
    print(f"doctor: {flags} flag(s) across {n} case(s)." + (" All clean." if flags == 0 else " Fix by APPENDING newer lines, never by editing history."))
    sys.exit(0 if flags == 0 else 2)


def cmd_sitrep(args):
    root = find_root()
    cdir = resolve_case(root, args.case)
    author = get_author(args.author, root)
    promise = read_promise(cdir)
    lines, _ = read_ledger(cdir)
    st = fold_ledger(lines)
    # recent actions from the log
    recent = []
    logp = cdir / "LOG.csv"
    if logp.is_file():
        with open(logp, encoding="utf-8", newline="") as f:
            recent = list(csv.DictReader(f))[-3:]
    out = [f"SITREP {cdir.name} · {now_iso()} · {author}"]
    out.append("DONE")
    if recent:
        for r in recent:
            out.append(f"  - [{str(r.get('ts',''))[:16]}] {r.get('action','')}: {r.get('note','') or r.get('ref','')}")
    else:
        out.append("  - (no actions logged yet)")
    out.append("STATE")
    s = f"  - Stage {st.get('stage','?')} · owner {st.get('owner','?')}"
    if st.get("paid") not in (None, "") and promise and promise.get("total"):
        s += f" · paid {money(st['paid'])} / {money(promise['total'])}"
    if st.get("blocked_on"):
        s += f" · blocked on {', '.join(st['blocked_on'])}"
    out.append(s + ".")
    out.append("DECIDE")
    out.append("  (agent: list open decisions as numbered options A/B with trade-offs; write '- None.' if none)")
    out.append("NEXT")
    out.append(f"  P1 {st.get('next') or '(agent: state the single next action)'}")
    out.append("BLOCKED")
    if st.get("blocked_on"):
        out.append(f"  - Waiting on: {', '.join(st['blocked_on'])}.")
    else:
        out.append("  - Nothing blocks us.")
    print("\n".join(out))


def cmd_seed(args):
    root = find_root()
    print("=" * 72)
    print("SPINE BOOT SEQUENCE — read in order, then take instructions from the operator")
    print("=" * 72)
    print(f"root: {root}")
    op = get_author(None, root)
    print(f"operator: {op}" + ("  ⚠ set SPINE_OPERATOR so writes are attributed" if op == "unattributed" else ""))
    print()
    print("[1] THE RULES (SPINE.md, verbatim) " + "-" * 36)
    print((root / "SPINE.md").read_text(encoding="utf-8"))
    print("[2] CASE INDEX " + "-" * 55)
    dirs = case_dirs(root)
    if not dirs:
        print("(no cases yet — 'spine.py new <slug>' opens the first)")
    for cdir in dirs:
        _, _, s = rank_case(cdir)
        print(f"  {s['case']:<26} stage {s['stage']:<12} owner {s['owner']:<9} next: {(s['next'] or '')[:50]}")
    print()
    print("[3] WORKLIST (ranked) " + "-" * 48)
    cmd_worklist(argparse.Namespace(all=False))
    print()
    print("[4] YOUR CONTRACT AS THE AGENT " + "-" * 39)
    print("  - Load ONE case before acting on it:   python3 spine.py show <case>")
    print("  - After every substantive step, write: python3 spine.py append <case> ... --note '...'")
    print("  - Irreversible actions (send, pay, publish, delete): STOP and get authorisation first.")
    print("  - Report to the human in SITREP format: python3 spine.py sitrep <case> (then complete DECIDE/NEXT).")
    print("  - If it only exists in the conversation, it does not exist. Append before you finish.")


# -------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(prog="spine.py", description="SpineOS v0 — append-only operational state for human + AI teams")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="start a spine in the current directory")
    p.add_argument("--operator", help="who operates this clone (else SPINE_OPERATOR env)")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("new", help="open a new case")
    p.add_argument("slug")
    p.add_argument("--note")
    p.add_argument("--author")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("promise", help="write the commitment snapshot for a case")
    p.add_argument("case")
    p.add_argument("--client"); p.add_argument("--type"); p.add_argument("--scope")
    p.add_argument("--deadline"); p.add_argument("--currency"); p.add_argument("--accepted-on", dest="accepted_on")
    p.add_argument("--total", type=float)
    p.add_argument("--milestone", action="append", help="label:amount[:status], repeatable")
    p.add_argument("--json", help="full PROMISE.json body inline (overrides flags)")
    p.add_argument("--force", action="store_true", help="re-write an existing promise (the change is ledgered)")
    p.add_argument("--author")
    p.set_defaults(fn=cmd_promise)

    p = sub.add_parser("append", help="append position (LEDGER) + action (LOG) in one verb")
    p.add_argument("case")
    p.add_argument("--stage", choices=STAGES)
    p.add_argument("--owner"); p.add_argument("--deadline"); p.add_argument("--next")
    p.add_argument("--complexity", choices=["low", "med", "high"])
    p.add_argument("--blocked-on", dest="blocked_on", help="comma list, e.g. 'client' or 'us,payment'")
    p.add_argument("--asks-them", dest="asks_them", help="comma list: what we await from them")
    p.add_argument("--asks-us", dest="asks_us", help="comma list: what we owe")
    p.add_argument("--paid", type=float, help="cumulative amount confirmed received")
    p.add_argument("--field", action="append", help="extension key=value (prefix x_ advised)")
    p.add_argument("--note", help="long-form narrative; this is the cross-session memory")
    p.add_argument("--action", help="LOG action code (default STATUS): WORK SEND DELIVER INVOICE PAYMENT AUTH_GRANT AUTH_CONSUME HANDOVER NOTE ...")
    p.add_argument("--ref", help="what command/context caused this")
    p.add_argument("--author")
    p.set_defaults(fn=cmd_append)

    p = sub.add_parser("show", help="fold a case and print its position (LLM-legible)")
    p.add_argument("case"); p.add_argument("--notes", type=int, default=5)
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("fold", help="machine-readable fold (JSON)")
    p.add_argument("case")
    p.set_defaults(fn=cmd_fold)

    p = sub.add_parser("worklist", help="all open cases ranked P1/P2/P3")
    p.add_argument("--all", action="store_true", help="include done/closed")
    p.set_defaults(fn=cmd_worklist)

    p = sub.add_parser("doctor", help="drift detection across all cases")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("sitrep", help="render the operator report skeleton for a case")
    p.add_argument("case"); p.add_argument("--author")
    p.set_defaults(fn=cmd_sitrep)

    p = sub.add_parser("seed", help="the boot sequence: rules + index + worklist + agent contract")
    p.set_defaults(fn=cmd_seed)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
