#!/usr/bin/env python3
"""
spine.py — SpineOS v0.2: durable, append-only operational state for humans and
AI agents working together.

Single file, standard library only, Python 3.9+. No API keys, no server,
no dependencies. Operated by the agent CLI you already subscribe to
(Claude Code, Grok CLI, Copilot CLI, Codex, Cursor): the agent is the
processor, the spine is the state.

The five primitives (per case, in cases/NNNN_slug/):
  PROMISE        the commitment — an EVENT on the ledger (PROMISE.json is a
                 rendered projection of the latest promise event)
  LEDGER.jsonl   append-only position record; every line carries a unique id;
                 current state is FOLDED: latest non-null per field by (ts, id)
  LOG.csv        append-only action record, written together with the ledger
Repo level:
  SPINE.md       the operating rules the agent reads at boot
  projections    printed by show/worklist/sitrep — computed, never stored

Sync (design: docs/sync-design.md):
  - ledgers are grow-only sets; git merges them with the union driver; lines
    deduplicate by id, so double-merges are harmless — conflicts are impossible
  - every write is journaled to .spine/journal/ BEFORE touching the ledger
  - every mutating verb records its path in a per-session manifest; `sync`
    commits exactly those paths — never another agent's work
  - choreography is MERGE, never rebase, never stash
  - branch modes: "shared" (all on one branch) or "member" (push member/<name>,
    pull main; an admin advances main MANUALLY with `spine.py reconcile`)

Verbs: init · new · promise · append · show · fold · worklist · doctor ·
       sitrep · seed · sync · reconcile · snapshot · recover
"""

import argparse
import csv
import io
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: proceed without the advisory lock
    fcntl = None

# ---------------------------------------------------------------- constants

LIST_FIELDS = {"blocked_on", "asks_them", "asks_us"}
STAGES = ["intake", "agreed", "in_progress", "in_review", "done", "closed"]
LOG_COLUMNS = ["ts", "author", "action", "ref", "note"]
STALE_DAYS = 7
DEADLINE_SOON_DAYS = 7
PUSH_MAX_AGE_MIN = 10   # append triggers a sync when the last push is older
GITATTRIBUTES = (
    "cases/**/LEDGER.jsonl merge=union\n"
    "cases/**/LOG.csv merge=union\n"
)

ASOF = None  # set by --as-of: fold only lines with ts <= ASOF


# ---------------------------------------------------------------- utilities

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> date:
    return date.today()


def new_id() -> str:
    """Time-ordered unique line id (ULID-style: ms timestamp + random)."""
    return f"{int(time.time() * 1000):013d}-{random.getrandbits(40):010x}"


def die(msg: str, code: int = 1):
    print(f"spine: {msg}", file=sys.stderr)
    sys.exit(code)


def find_root(start: Path = None) -> Path:
    p = (start or Path.cwd()).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "SPINE.md").is_file():
            return candidate
    die("no SPINE.md found here or above. Run 'spine.py init' to start a spine.")


def spine_dir(root: Path) -> Path:
    d = root / ".spine"
    for sub in ("journal", "sessions"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def read_config(root: Path) -> dict:
    """Tracked repo settings (.spineos.json: branch_mode, main_branch) merged with
    machine-local config (.spine/config.json: operator). Repo settings travel with clones."""
    out = {}
    for path in (root / ".spineos.json", root / ".spine" / "config.json"):
        if path.is_file():
            try:
                out.update(json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
    return out


def get_author(cli_author: str = None, root: Path = None) -> str:
    if cli_author:
        return cli_author
    env = os.environ.get("SPINE_OPERATOR")
    if env:
        return env
    if root:
        op = read_config(root).get("operator")
        if op:
            return op
    return "unattributed"


def session_name(root: Path) -> str:
    s = os.environ.get("SPINE_SESSION")
    if s:
        return re.sub(r"[^A-Za-z0-9_.-]", "_", s)
    return f"{re.sub(r'[^A-Za-z0-9_.-]', '_', get_author(None, root))}-{os.getppid()}"


def manifest_path(root: Path) -> Path:
    return spine_dir(root) / "sessions" / f"{session_name(root)}.manifest"


def manifest_add(root: Path, path: Path):
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    mp = manifest_path(root)
    existing = set(mp.read_text().splitlines()) if mp.is_file() else set()
    if rel not in existing:
        with open(mp, "a", encoding="utf-8") as f:
            f.write(rel + "\n")


def journal_write(root: Path, record: dict):
    """Write-ahead journal: fsync'd, append-only, machine-local, BEFORE the ledger."""
    path = spine_dir(root) / "journal" / f"{today().strftime('%Y-%m')}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def write_ledger_line(root: Path, cdir: Path, entry: dict):
    entry.setdefault("id", new_id())
    journal_write(root, {"type": "ledger", "case": cdir.name, "line": entry})
    with open(cdir / "LEDGER.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    manifest_add(root, cdir / "LEDGER.jsonl")


def append_log_row(root: Path, cdir: Path, ts, author, action, ref, note):
    row = [ts, author, action, ref or "", note or ""]
    journal_write(root, {"type": "log", "case": cdir.name, "row": row})
    path = cdir / "LOG.csv"
    new = not path.is_file()
    buf = io.StringIO()
    w = csv.writer(buf)
    if new:
        w.writerow(LOG_COLUMNS)
    w.writerow(row)
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())
    manifest_add(root, path)


def case_dirs(root: Path):
    cdir = root / "cases"
    if not cdir.is_dir():
        return []
    return sorted(d for d in cdir.iterdir()
                  if d.is_dir() and re.match(r"^\d{4}_", d.name))


def resolve_case(root: Path, ident: str) -> Path:
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
    """Return (lines, errors, n_duplicates). Dedupes by id; sorts by (ts, id)."""
    path = cdir / "LEDGER.jsonl"
    lines, errors, seen, dupes = [], [], set(), 0
    if not path.is_file():
        return lines, errors, dupes
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError("not an object")
        except (json.JSONDecodeError, ValueError) as e:
            errors.append(f"LEDGER.jsonl line {i}: {e}")
            continue
        key = obj.get("id") or (obj.get("ts", ""), obj.get("author", ""), raw)
        if key in seen:
            dupes += 1        # harmless by design (union merges) — folded once
            continue
        seen.add(key)
        lines.append(obj)
    if ASOF:
        lines = [l for l in lines if str(l.get("ts", "")) <= ASOF]
    lines.sort(key=lambda o: (o.get("ts", ""), o.get("id", "")))
    return lines, errors, dupes


def fold_ledger(lines):
    state = {}
    for line in lines:
        for k, v in line.items():
            if v is not None and k not in ("note", "id"):
                state[k] = v
    notes = [{"ts": l.get("ts", ""), "author": l.get("author", ""), "note": l["note"]}
             for l in lines if l.get("note")]
    state["_notes"] = notes
    state["_n_lines"] = len(lines)
    if lines:
        state["_last_ts"] = lines[-1].get("ts", "")
        state["_last_author"] = lines[-1].get("author", "")
    return state


def get_promise(cdir: Path, folded: dict = None):
    """Promise = latest promise EVENT on the ledger; falls back to PROMISE.json (legacy)."""
    if folded is None:
        lines, _, _ = read_ledger(cdir)
        folded = fold_ledger(lines)
    if folded.get("promise"):
        return folded["promise"]
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
    if not promise:
        return None
    ms = promise.get("milestones") or []
    if ms:
        return sum(float(m.get("amount", 0)) for m in ms
                   if str(m.get("status", "outstanding")).lower() != "paid")
    return None


# ------------------------------------------------------------------ git ops

def git(root: Path, *args, check=False):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r


def has_git(root: Path) -> bool:
    return (root / ".git").exists()


def has_origin(root: Path) -> bool:
    return has_git(root) and git(root, "remote", "get-url", "origin").returncode == 0


def current_branch(root: Path) -> str:
    r = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else "main"


class SyncLock:
    """Single-flight lock: concurrent syncs queue instead of interleaving."""
    def __init__(self, root: Path):
        self.path = spine_dir(root) / "sync.lock"
        self.f = None

    def __enter__(self):
        self.f = open(self.path, "w")
        if fcntl:
            fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if fcntl and self.f:
            fcntl.flock(self.f, fcntl.LOCK_UN)
        if self.f:
            self.f.close()


def do_sync(root: Path, message=None, also=(), push=True, light=False, quiet=False):
    """The sync protocol (docs/sync-design.md §5). MERGE, never rebase, never stash.
    light=True: integrate-only (fetch+merge), used by seed. Returns True on success."""
    def say(s):
        if not quiet:
            print(s)

    if not has_git(root):
        say("sync: not a git repo (git init + add an origin to enable sync). Local-only.")
        return False
    cfg = read_config(root)
    mode = cfg.get("branch_mode", "shared")
    main = cfg.get("main_branch", "main")
    with SyncLock(root):
        # 1. commit this session's manifest (never another agent's work)
        if not light:
            mp = manifest_path(root)
            paths = [p for p in (mp.read_text().splitlines() if mp.is_file() else []) if p]
            paths += list(also)
            if paths:
                git(root, "add", "--", *paths)
                staged = git(root, "diff", "--cached", "--name-only").stdout.strip()
                if staged:
                    author = get_author(None, root)
                    msg = message or f"spine: {author} · {len(staged.splitlines())} file(s)"
                    git(root, "commit", "-m", msg, check=True)
                    say(f"✓ committed {len(staged.splitlines())} file(s) [{author}]")
            if mp.is_file():
                mp.unlink()
            others = [p.name for p in (spine_dir(root) / "sessions").glob("*.manifest")]
            if others:
                say(f"note: other sessions have unsynced manifests: {', '.join(others)}")
            status = [l for l in git(root, "status", "--porcelain").stdout.splitlines() if l]
            modified = [l[3:] for l in status if not l.startswith("??")]
            untracked = [l[3:] for l in status if l.startswith("??")]
            if modified:
                say(f"note: {len(modified)} unclaimed MODIFIED file(s) left untouched "
                    f"(claim with: spine.py sync --also <path>): " + ", ".join(modified[:6])
                    + (" …" if len(modified) > 6 else ""))
            if untracked:
                say(f"note: {len(untracked)} UNTRACKED file(s) NOT shared — hand-made work is "
                    f"invisible until claimed (spine.py sync --also <path>): " + ", ".join(untracked[:6])
                    + (" …" if len(untracked) > 6 else ""))
        # 2. integrate
        if not has_origin(root):
            say("sync: no origin remote — committed locally only.")
            return True
        if git(root, "fetch", "origin", "--prune").returncode != 0:
            say("sync: fetch failed (offline?) — work is committed locally; retry later.")
            return False
        target = main if mode == "member" else current_branch(root)
        if git(root, "rev-parse", f"origin/{target}").returncode == 0:
            m = git(root, "merge", "--no-edit", f"origin/{target}")
            if m.returncode != 0:
                conf = git(root, "diff", "--name-only", "--diff-filter=U").stdout.strip()
                if conf:
                    git(root, "merge", "--abort")
                    die("sync: PROSE MERGE CONFLICT (ledgers cannot conflict). "
                        f"Files:\n  {conf}\nMerge aborted; nothing lost. Resolve with a human, "
                        "then re-run sync.", 2)
                die(f"sync: merge refused:\n{m.stderr.strip()}\nNothing was stashed; "
                    "another agent's in-flight work stays where it lies. Re-run when clear.", 2)
            say(f"✓ merged origin/{target}")
        # 3. push
        if light or not push:
            return True
        ref = f"HEAD:refs/heads/member/{re.sub(r'[^A-Za-z0-9_.-]', '_', get_author(None, root))}" \
            if mode == "member" else f"HEAD:{current_branch(root)}"
        last_err = ""
        for attempt in range(3):
            p = git(root, "push", "origin", ref)
            if p.returncode == 0:
                (spine_dir(root) / "last_push").write_text(now_iso())
                say(f"✓ pushed {ref}")
                return True
            last_err = p.stderr
            if "REFUSED" in last_err:
                break                     # a policy refusal will not heal on retry
            time.sleep(0.5 + random.random())
            git(root, "fetch", "origin")
            if mode != "member" and git(root, "rev-parse", f"origin/{target}").returncode == 0:
                if git(root, "merge", "--no-edit", f"origin/{target}").returncode != 0:
                    git(root, "merge", "--abort")
                    die("sync: conflict during push retry — resolve with a human.", 2)
        say("sync: push failed — work is committed locally.")
        for line in last_err.splitlines():
            if "REFUSED" in line or "rejected" in line:
                say("  server: " + line.replace("remote: ", "").strip())
        return False


def maybe_autosync(root: Path):
    """After append: sync if the last push is old. Offline-tolerant, quiet."""
    if not has_origin(root):
        return
    lp = spine_dir(root) / "last_push"
    try:
        age = (datetime.now().astimezone()
               - datetime.fromisoformat(lp.read_text().strip())).total_seconds() / 60
    except (OSError, ValueError):
        age = 1e9
    if age >= PUSH_MAX_AGE_MIN:
        do_sync(root, quiet=True)


# ------------------------------------------------------------------- verbs

def cmd_init(args):
    root = Path.cwd()
    if (root / "SPINE.md").is_file():
        die("SPINE.md already exists here; this is already a spine.")
    src = Path(__file__).resolve().parent / "SPINE.md"
    if src.is_file():
        (root / "SPINE.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        (root / "SPINE.md").write_text("# SPINE — operating rules\n\n(write your rules here)\n", encoding="utf-8")
    (root / "cases").mkdir(exist_ok=True)
    ga = root / ".gitattributes"
    if not ga.is_file() or "merge=union" not in ga.read_text():
        with open(ga, "a", encoding="utf-8") as f:
            f.write(GITATTRIBUTES)
    spine_dir(root)
    gi = root / ".gitignore"
    if not gi.is_file() or ".spine/" not in (gi.read_text() if gi.is_file() else ""):
        with open(gi, "a", encoding="utf-8") as f:
            f.write(".spine/\n")
    operator = args.operator or os.environ.get("SPINE_OPERATOR") or ""
    (root / ".spineos.json").write_text(json.dumps({
        "branch_mode": args.branch_mode,
        "main_branch": "main",
        "created": now_iso(),
    }, indent=2) + "\n", encoding="utf-8")
    (root / ".spine" / "config.json").write_text(json.dumps({
        "operator": operator,
    }, indent=2), encoding="utf-8")
    for f in ("SPINE.md", ".gitattributes", ".gitignore", ".spineos.json"):
        manifest_add(root, root / f)
    print(f"✓ spine initialised at {root}")
    print(f"  operator: {operator or '(unset — set SPINE_OPERATOR or edit .spine/config.json)'}")
    print(f"  branch mode: {args.branch_mode}"
          + (" (push member/<name>, pull main; admin runs 'spine.py reconcile' to advance main)"
             if args.branch_mode == "member" else " (everyone on one branch)"))
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
    write_ledger_line(root, cdir, {"ts": ts, "author": author, "stage": "intake",
                                   "note": args.note or f"Case opened: {args.slug}"})
    append_log_row(root, cdir, ts, author, "CREATE", "spine new", args.note or "case opened")
    print(f"✓ created {cdir.relative_to(root)} (stage: intake, author: {author})")
    print("  next: 'spine.py promise' when a deal is accepted; 'spine.py append' as things move")


def cmd_promise(args):
    root = find_root()
    cdir = resolve_case(root, args.case)
    existing = get_promise(cdir)
    if existing and not args.force:
        die("a promise exists. It changes only when the deal itself changes; "
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
    # the promise is an EVENT on the ledger; PROMISE.json is a projection
    write_ledger_line(root, cdir, {"ts": ts, "author": author, "stage": "agreed",
                                   "promise": promise, "note": note})
    (cdir / "PROMISE.json").write_text(
        json.dumps(promise, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_add(root, cdir / "PROMISE.json")
    append_log_row(root, cdir, ts, author, "PROMISE", "spine promise", note)
    print(f"✓ {cdir.name}: promise ledgered, stage → agreed (PROMISE.json projected)")


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
    # same-case awareness: has anyone else moved this case recently?
    lines_before, _, _ = read_ledger(cdir)
    if lines_before:
        last = lines_before[-1]
        if last.get("author") not in (author, None):
            print(f"note: {last.get('author')} appended to this case at {last.get('ts','?')}")
    write_ledger_line(root, cdir, entry)
    append_log_row(root, cdir, ts, author, args.action or "STATUS",
                   args.ref or "spine append", args.note or "")
    print(f"✓ {cdir.name}: ledger +1 · log +1 · author {author}")
    if not args.no_sync:
        maybe_autosync(root)


def render_show(root: Path, cdir: Path, n_notes: int) -> str:
    lines, errors, dupes = read_ledger(cdir)
    st = fold_ledger(lines)
    promise = get_promise(cdir, st)
    out = []
    head = f"CASE {cdir.name}"
    if promise and promise.get("type"):
        head += f" · type: {promise['type']}"
    head += f" · stage: {st.get('stage','?')} · owner: {st.get('owner','?')}"
    if ASOF:
        head += f" · AS OF {ASOF}"
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
    notes = st["_notes"][-n_notes:] if st["_notes"] else []
    if notes:
        out.append("RECENT NOTES")
        for n in notes:
            out.append(f"  [{n['ts']} {n['author']}] {n['note']}")
    for e in errors:
        out.append(f"⚠ {e}")
    if dupes:
        out.append(f"note: {dupes} duplicate line(s) folded once (harmless; union merges)")
    out.append("RULES: SPINE.md governs. Irreversible actions need a recorded authorisation first (AUTH_GRANT), consumed by the action it authorises.")
    return "\n".join(out)


def cmd_show(args):
    global ASOF
    ASOF = args.as_of
    root = find_root()
    cdir = resolve_case(root, args.case)
    print(render_show(root, cdir, args.notes))


def cmd_fold(args):
    global ASOF
    ASOF = args.as_of
    root = find_root()
    cdir = resolve_case(root, args.case)
    lines, errors, dupes = read_ledger(cdir)
    st = fold_ledger(lines)
    promise = get_promise(cdir, st)
    st.pop("_notes", None)
    st.pop("promise", None)
    print(json.dumps({"case": cdir.name, "state": st, "promise": promise,
                      "errors": errors, "duplicates_folded": dupes},
                     indent=2, ensure_ascii=False))


def rank_case(cdir: Path):
    lines, _, _ = read_ledger(cdir)
    st = fold_ledger(lines)
    promise = get_promise(cdir, st)
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
    global ASOF
    ASOF = getattr(args, "as_of", None)
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


def env_checks(root: Path):
    problems = []
    if sys.version_info < (3, 9):
        problems.append(f"BLOCKING: Python {sys.version.split()[0]} < 3.9")
    pv = root / ".python-version"
    if pv.is_file():
        want = pv.read_text().strip()
        have = f"{sys.version_info.major}.{sys.version_info.minor}"
        if want and not want.startswith(have):
            problems.append(f"BLOCKING: .python-version wants {want}, running {have}")
    nvmrc = root / ".nvmrc"
    docs_node = root / "modules" / "docs-node"
    if nvmrc.is_file() or docs_node.is_dir():
        r = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if r.returncode != 0:
            problems.append("BLOCKING: node not found but node modules are declared")
        elif nvmrc.is_file():
            want = nvmrc.read_text().strip().lstrip("v").split(".")[0]
            have = r.stdout.strip().lstrip("v").split(".")[0]
            if want and want != have:
                problems.append(f"BLOCKING: .nvmrc wants v{want}.x, running v{have}.x")
        if docs_node.is_dir() and not (docs_node / "node_modules").is_dir():
            problems.append("docs-node present but node_modules missing (run: cd modules/docs-node && npm ci)")
    return problems


def journal_missing_lines(root: Path):
    """Journal ↔ ledger reconciliation: every journaled line must be in its ledger."""
    missing = []
    jdir = spine_dir(root) / "journal"
    ids_by_case = {}
    for jf in sorted(jdir.glob("*.jsonl")):
        for raw in jf.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if rec.get("type") == "ledger":
                case = rec.get("case")
                if case not in ids_by_case:
                    cdir = root / "cases" / case
                    lines, _, _ = read_ledger(cdir) if cdir.is_dir() else ([], [], 0)
                    ids_by_case[case] = {l.get("id") for l in lines}
                line = rec.get("line", {})
                if line.get("id") and line["id"] not in ids_by_case.get(case, set()):
                    missing.append((case, line))
    return missing


def cmd_doctor(args):
    root = find_root()
    flags = 0
    if args.env:
        for p in env_checks(root):
            print(f"env: ⚠ {p}")
            flags += 1
        if flags == 0:
            print("env: clean")
    for cdir in case_dirs(root):
        problems = []
        lines, errors, dupes = read_ledger(cdir)
        problems += errors
        st = fold_ledger(lines)
        promise = get_promise(cdir, st)
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
            problems.append(f"stage '{stage}' but no promise: an accepted engagement needs its deal snapshot")
        dl = parse_iso_date(st.get("deadline") or (promise or {}).get("deadline"))
        if dl and stage not in ("done", "closed") and dl < today():
            problems.append(f"DEADLINE PASSED {(today() - dl).days}d ago ({dl})")
        # promise changed more than once in a day by different authors → owner confirms
        pevents = [l for l in lines if l.get("promise")]
        for a, b in zip(pevents, pevents[1:]):
            if a.get("ts", "")[:10] == b.get("ts", "")[:10] and a.get("author") != b.get("author"):
                problems.append("promise changed twice in one day by different authors — owner must append which stands")
        # ledger lines need a same-day log row (dual-logging drift)
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
        # trailing newline (union-driver safety)
        lp = cdir / "LEDGER.jsonl"
        if lp.is_file() and lp.stat().st_size and not lp.read_bytes().endswith(b"\n"):
            problems.append("LEDGER.jsonl lacks trailing newline (union-merge hazard)")
        if problems:
            flags += len(problems)
            print(f"{cdir.name}:")
            for p in problems:
                print(f"  ⚠ {p}")
    missing = journal_missing_lines(root)
    if missing:
        flags += len(missing)
        print(f"journal: ⚠ {len(missing)} journaled line(s) absent from ledgers — run 'spine.py recover'")
    if has_origin(root):
        r = git(root, "rev-list", "--count", "@{u}..HEAD")
        if r.returncode == 0 and r.stdout.strip() not in ("", "0"):
            print(f"git: note — {r.stdout.strip()} local commit(s) not pushed (run 'spine.py sync')")
    n = len(case_dirs(root))
    print(f"doctor: {flags} flag(s) across {n} case(s)." +
          (" All clean." if flags == 0 else " Fix by APPENDING newer lines, never by editing history."))
    sys.exit(0 if flags == 0 else 2)


def cmd_sitrep(args):
    root = find_root()
    cdir = resolve_case(root, args.case)
    author = get_author(args.author, root)
    lines, _, _ = read_ledger(cdir)
    st = fold_ledger(lines)
    promise = get_promise(cdir, st)
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
    if op == "unattributed" or not case_dirs(root):
        print()
        print("[FIRST RUN] AGENT: this spine is not set up yet. Walk the operator through it now:")
        print("  1. Ask their name; then persist it: append 'export SPINE_OPERATOR=<name>' to their shell")
        print("     profile AND write it into .spine/config.json (operator field).")
        print("  2. Ask what they run here (clients? matters? projects? patients?) — that is their 'case'.")
        print("  3. Ask about their team: solo → branch mode 'shared' is already right; a team wanting")
        print("     per-member branches sets branch_mode 'member' in .spine/config.json (see docs).")
        print("  4. Offer to connect a private git remote for durability (their server or a private repo).")
        print("  5. Open their first case: python3 spine.py new '<their first real case>' — then show them")
        print("     the loop: promise → append → worklist → sitrep. Small, real, today's work.")
        print("  Ask ONE question at a time. Do not dump this list on them.")
    if has_origin(root):
        print("[0] SYNC-IN " + "-" * 58)
        do_sync(root, light=True)
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
    cmd_worklist(argparse.Namespace(all=False, as_of=None))
    print()
    print("[4] YOUR CONTRACT AS THE AGENT " + "-" * 39)
    print("  - Load ONE case before acting on it:   python3 spine.py show <case>")
    print("  - After every substantive step, write: python3 spine.py append <case> ... --note '...'")
    print("  - Irreversible actions (send, pay, publish, delete): STOP and get authorisation first.")
    print("  - Report to the human in SITREP format: python3 spine.py sitrep <case> (then complete DECIDE/NEXT).")
    print("  - Share your work:                      python3 spine.py sync   (commits ONLY what you touched)")
    print("  - If it only exists in the conversation, it does not exist. Append before you finish.")


def cmd_sync(args):
    root = find_root()
    ok = do_sync(root, message=args.message, also=args.also or (), push=not args.no_push)
    sys.exit(0 if ok else 1)


def cmd_reconcile(args):
    """MANUAL reconciler (admin verb): merge all origin/member/* into main, push."""
    root = find_root()
    if not has_origin(root):
        die("reconcile needs an origin remote")
    cfg = read_config(root)
    main = cfg.get("main_branch", "main")
    with SyncLock(root):
        git(root, "fetch", "origin", "--prune", check=True)
        if current_branch(root) != main:
            r = git(root, "checkout", main)
            if r.returncode != 0:
                die(f"cannot checkout {main}: {r.stderr.strip()}")
        if git(root, "rev-parse", f"origin/{main}").returncode == 0:
            git(root, "merge", "--no-edit", f"origin/{main}")
        branches = [b.strip() for b in
                    git(root, "branch", "-r", "--list", "origin/member/*").stdout.splitlines()]
        if not branches:
            print("reconcile: no member branches found.")
            return
        merged, parked = [], []
        for b in branches:
            m = git(root, "merge", "--no-edit", b)
            if m.returncode == 0:
                merged.append(b)
            else:
                conf = git(root, "diff", "--name-only", "--diff-filter=U").stdout.strip()
                git(root, "merge", "--abort")
                parked.append((b, conf))
        if not args.no_push:
            git(root, "push", "origin", f"HEAD:{main}", check=True)
        print(f"✓ reconciled {len(merged)}/{len(branches)} member branch(es) into {main}"
              + ("" if args.no_push else " and pushed"))
        for b, conf in parked:
            print(f"⚠ PARKED {b}: prose conflict in:\n    {conf or '(unknown)'}\n"
                  f"  Resolve with a human, then re-run reconcile. Nothing was lost.")
        sys.exit(2 if parked else 0)


def cmd_snapshot(args):
    root = find_root()
    if not has_git(root):
        die("snapshot needs git")
    label = re.sub(r"[^A-Za-z0-9_.-]", "-", args.label) if args.label else ""
    op = re.sub(r"[^A-Za-z0-9_.-]", "_", get_author(None, root))
    tag = f"snap/{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}-{op}" + (f"-{label}" if label else "")
    git(root, "tag", tag, check=True)
    if has_origin(root):
        git(root, "push", "origin", tag)
    print(f"✓ snapshot {tag}")


def cmd_recover(args):
    """Replay journaled lines absent from ledgers. Idempotent (dedupe by id)."""
    root = find_root()
    missing = journal_missing_lines(root)
    if not missing:
        print("recover: nothing to recover — every journaled line is in its ledger.")
        return
    restored = 0
    for case, line in missing:
        cdir = root / "cases" / case
        if not cdir.is_dir():
            if not args.force_missing_case:
                print(f"⚠ case {case} no longer exists; line NOT replayed "
                      f"(re-run with --force-missing-case to recreate): {json.dumps(line)[:100]}")
                continue
            cdir.mkdir(parents=True)
        with open(cdir / "LEDGER.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        manifest_add(root, cdir / "LEDGER.jsonl")
        restored += 1
    print(f"✓ recover: {restored} line(s) replayed from the journal. Run 'spine.py sync' to share.")


# -------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(prog="spine.py", description="SpineOS v0.2 — append-only operational state for human + AI teams")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="start a spine in the current directory")
    p.add_argument("--operator", help="who operates this clone (else SPINE_OPERATOR env)")
    p.add_argument("--branch-mode", choices=["shared", "member"], default="shared",
                   help="shared: one branch for all. member: push member/<name>, pull main (admin reconciles)")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("new", help="open a new case")
    p.add_argument("slug"); p.add_argument("--note"); p.add_argument("--author")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("promise", help="ledger the commitment for a case (PROMISE.json is a projection)")
    p.add_argument("case")
    p.add_argument("--client"); p.add_argument("--type"); p.add_argument("--scope")
    p.add_argument("--deadline"); p.add_argument("--currency"); p.add_argument("--accepted-on", dest="accepted_on")
    p.add_argument("--total", type=float)
    p.add_argument("--milestone", action="append", help="label:amount[:status], repeatable")
    p.add_argument("--json", help="full promise body inline (overrides flags)")
    p.add_argument("--force", action="store_true", help="re-write an existing promise (ledgered old → new)")
    p.add_argument("--author")
    p.set_defaults(fn=cmd_promise)

    p = sub.add_parser("append", help="append position (LEDGER) + action (LOG) in one verb")
    p.add_argument("case")
    p.add_argument("--stage", choices=STAGES)
    p.add_argument("--owner"); p.add_argument("--deadline"); p.add_argument("--next")
    p.add_argument("--complexity", choices=["low", "med", "high"])
    p.add_argument("--blocked-on", dest="blocked_on")
    p.add_argument("--asks-them", dest="asks_them")
    p.add_argument("--asks-us", dest="asks_us")
    p.add_argument("--paid", type=float)
    p.add_argument("--field", action="append", help="extension key=value (prefix x_ advised)")
    p.add_argument("--note")
    p.add_argument("--action", help="LOG action code (default STATUS)")
    p.add_argument("--ref")
    p.add_argument("--author")
    p.add_argument("--no-sync", action="store_true", help="skip the automatic sync-out")
    p.set_defaults(fn=cmd_append)

    p = sub.add_parser("show", help="fold a case and print its position")
    p.add_argument("case"); p.add_argument("--notes", type=int, default=5)
    p.add_argument("--as-of", dest="as_of", help="fold only lines with ts <= this (time travel)")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("fold", help="machine-readable fold (JSON)")
    p.add_argument("case"); p.add_argument("--as-of", dest="as_of")
    p.set_defaults(fn=cmd_fold)

    p = sub.add_parser("worklist", help="all open cases ranked P1/P2/P3")
    p.add_argument("--all", action="store_true"); p.add_argument("--as-of", dest="as_of")
    p.set_defaults(fn=cmd_worklist)

    p = sub.add_parser("doctor", help="drift detection across all cases")
    p.add_argument("--env", action="store_true", help="also verify pinned environments (BLOCKING on mismatch)")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("sitrep", help="render the operator report skeleton for a case")
    p.add_argument("case"); p.add_argument("--author")
    p.set_defaults(fn=cmd_sitrep)

    p = sub.add_parser("seed", help="boot: sync-in + rules + index + worklist + agent contract")
    p.set_defaults(fn=cmd_seed)

    p = sub.add_parser("sync", help="commit ONLY this session's files, merge (never rebase), push")
    p.add_argument("-m", "--message")
    p.add_argument("--also", action="append", help="claim an unclaimed path into this commit")
    p.add_argument("--no-push", action="store_true")
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("reconcile", help="ADMIN, MANUAL: merge all origin/member/* into main and push")
    p.add_argument("--no-push", action="store_true")
    p.set_defaults(fn=cmd_reconcile)

    p = sub.add_parser("snapshot", help="pin the current state as a tag (snap/<ts>-<operator>[-label])")
    p.add_argument("label", nargs="?")
    p.set_defaults(fn=cmd_snapshot)

    p = sub.add_parser("recover", help="replay journaled lines missing from ledgers (idempotent)")
    p.add_argument("--force-missing-case", action="store_true")
    p.set_defaults(fn=cmd_recover)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
