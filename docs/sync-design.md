# SYNC — the multi-agent git pipeline (design, v0.2 proposal)

*Status: design for review. Nothing here is implemented yet. The guarantees are stated first, the reasoning second, the implementation plan last.*

---

## 1. The guarantees we are designing for

| # | Guarantee | Meaning, precisely |
|---|---|---|
| G1 | **Never overrides** | No sync operation may replace one writer's data with another's. Convergence, not conflict resolution |
| G2 | **Zero data loss, ever** | An appended line survives machine crash, git misuse, race conditions, and malicious-looking accidents. "Recoverable with effort" counts only as a last resort; the design target is "never needs recovering" |
| G3 | **Touched-files-only commits** | An agent's commit contains exactly the files that agent wrote, never a concurrent agent's half-written work |
| G4 | **Sync-in before work** | Boot = fetch + integrate + resolve, in seconds, then work on fresh state |
| G5 | **Work → commit → push, continuously** | Durable state reaches the remote within minutes of being written, not at end-of-day |
| G6 | **Snapshots** | Any historical position reconstructible; deliverable states pinned |

## 2. The scar tissue (why every piece of this design exists)

These are real incidents from the production spine this system is extracted from. Each one maps to a structural counter below — a rule that makes the failure *impossible*, not a warning that asks people to be careful.

| Incident | What happened | Structural counter (section) |
|---|---|---|
| Autostash parking | `--autostash` on a shared tree lifted another agent's only copy of 37 reference rows into `stash@{0}`, exited 0 | Never rebase, never stash: merge-only choreography (§5), commit-before-integrate |
| Fork-point drop | `git pull --rebase` computed a fork point from a stale tracking reflog and silently dropped 13 commits, no conflict, no warning | No rebase anywhere in the pipeline (§5); remote refuses history rewrites (§7) |
| `git add -A` sweep | A bare sync committed every concurrent agent's half-written files under one agent's name | Session manifest: the CLI records what it wrote; sync stages exactly that (§4) |
| Tracked projections | Generated views guaranteed conflicts whose only correct resolution was "regenerate" | Projections are never stored, already v0 law (§3) |
| Shallow window clobber | A 2-day sync overwrote history a 30-day sync had captured (5 messages deleted invisibly) | Union semantics at the data layer: a write can add, never subtract (§3) |
| `checkout -- dir/` revert | Reverting "churn" also reverted source edits in the same directory | Destructive-command deny-list + append-only remote (§7) |
| Concurrent same-file writers | Two syncs interleaved writes on one JSON file | Single-flight lock for the git choreography (§5); atomic writes (already v0) |
| Staged-not-committed loss | Work left in the git index was eaten by a concurrent operation | Staging is an *instant* inside `spine sync`, never a resting state (§5) |
| WAL-less snapshot | Copying a SQLite file without its WAL produced a confident, incomplete copy | Journal-before-write gives a second independent copy of every line (§6) |

## 3. The core insight: make conflicts impossible, then git is just transport

The spine's data model already contains the solution. A ledger line is an immutable fact with a required timestamp and author. Position is a **fold** (latest non-null per field, by timestamp). File order is irrelevant. Therefore:

> **A case ledger is a grow-only set of lines (a G-Set CRDT) serialised as JSONL. The union of any two copies is the only correct merge, union is commutative and associative, so every sync order converges to the same state and a merge conflict is not something to resolve — it is something the data model makes impossible.**

Git's `merge=union` driver implements exactly this at line level. What v0.2 must add to make it bulletproof:

1. **A unique `id` per line** (ULID: time-ordered, collision-free). Git's union driver keeps both copies when both sides carry the same line; replays and double-merges can duplicate. With ids, `read_ledger()` deduplicates exactly, so **duplicates are harmless forever and compaction is never needed** (compaction would be a rewrite, which we forbid).
2. **`.gitattributes` shipped by `spine init`**, not documented as advice: `cases/**/LEDGER.jsonl merge=union`, `cases/**/LOG.csv merge=union`. (Union-driver caveat: it can interleave when a file lacks a trailing newline — `spine.py` always writes newline-terminated lines, and `doctor` verifies it.)
3. **PROMISE becomes an event, not a file-overwrite.** Today PROMISE.json is the one authored file with replace semantics — the only place two writers can genuinely collide. v0.2: `spine promise` appends the full promise object as a `promise` field on a ledger line; **PROMISE.json becomes a projection** (rendered for convenience, gitignored or overwrite-safe). The deal's history lives in the ledger like everything else; concurrent re-promises become two ledger lines, surfaced by `doctor` as "promise changed twice in one window — owner must confirm which stands", appended as a third line. Nothing is ever lost or auto-picked.
4. **Prose files (SPINE.md, routers/) keep normal git merge.** They are human-owned, low-frequency, and a textual conflict there is *meaningful* — it means two humans edited the constitution simultaneously, which deserves eyes. This is the one place "resolve" is a real step, and it is rare by construction.

After these four changes, the entire authored surface of a spine is conflict-free except the constitution, and G1 holds *by data model*, not by discipline.

## 4. G3: the session manifest (how "only the files I touched" becomes automatic)

The CLI is the only writer to spine state. So the CLI can *know* what a session touched — no guessing, no `git add -A`, no scope flags to remember:

- Every mutating verb appends the path it wrote to `.spine/sessions/<session>.manifest` (machine-local, untracked). `<session>` comes from `SPINE_SESSION` if set, else one is derived per boot (seed prints it).
- `spine sync` stages **exactly the manifest paths**, commits them with a structured message (`case · actions · author`), and clears the manifest on success.
- Files changed outside the CLI (a hand-edited router, an artifact dropped into a case folder) are listed by sync as *unclaimed* and left alone until someone claims them: `spine sync --also <path>`. Nothing is ever swept silently.

Two agents in one working tree therefore cannot commit each other's work: each stages from its own manifest, and the stage→commit step runs under the sync lock (§5) so the shared git index is never contested. (A later refinement can use `GIT_INDEX_FILE` per session to remove even the lock from the stage step; the lock alone is sufficient and simpler for v0.2.)

## 5. The choreography: merge, never rebase; commit first, always

The sync verb runs the same short protocol in and out:

```
spine sync            # also runs automatically at the top of `spine seed`
  1. flock .spine/sync.lock          — single-flight per repo; concurrent syncs queue
  2. commit-local: stage manifest paths → commit (skip if manifest empty)
  3. fetch origin
  4. integrate: git merge origin/<branch>   ← MERGE. NEVER REBASE. NEVER STASH.
       - ledgers/logs: union driver → cannot conflict
       - prose conflict → stop, print the file list + resolution rule, exit 2
       - dirty unclaimed files that the merge would touch → refuse, name them, exit 2
         (the other agent's in-flight work stays untouched where it lies)
  5. push; on non-fast-forward race: fetch → merge → push again (bounded retries, jittered)
       — always converges, because step 4 cannot conflict on ledgers
  6. report: what came in (new lines per case), what went out, anything refused
```

**Why merge and not rebase.** Rebase exists to keep history linear. An event-log repo does not need linear history — it needs *unlosable* history. Rebase rewrites commits (fork-point incident), requires a clean tree (autostash incident), and its failure modes are silent. Merge rewrites nothing, needs no stash, and its one failure mode (a prose conflict) is loud and legitimate. We trade an aesthetic (linear log) for a guarantee (nothing rewritten, ever). That trade is the whole design.

**Why staging is never a resting state.** Step 2 is atomic from the caller's view: stage+commit under the lock, milliseconds apart. Work exists in exactly three durable states — written to disk (+ journal), committed, pushed — and "staged" is not one of them. (Production scar: git-staged-uncommitted work is where losses happened.)

**Cadence (G4/G5).** Sync-in is folded into `seed` (boot = fresh state). Sync-out runs at the end of `append` when the last push is older than N minutes (default 10, configurable, `--no-sync` to defer), and always at session end. Continuous small pushes, no end-of-day cliff.

## 6. G2, first half: journal-before-write (data survives even git)

Every mutating verb writes the line to `.spine/journal/YYYY-MM.jsonl` (fsync'd, append-only, machine-local, untracked) **before** touching the case file. The journal is a write-ahead log for the whole spine:

- If any git operation, editor accident, or disk event eats a ledger, `spine recover` replays journal lines absent from ledgers (dedupe by id makes replay idempotent and safe to run any time).
- `doctor` reconciles journal ↔ ledgers on every run: a journal line missing from its ledger is a loud flag.
- Cost: one extra append per write. For "zero loss ever", every line exists in two independent local places within milliseconds of creation, three once pushed.

## 7. G2, second half: the remote only ever grows

The strongest zero-loss property is one no client can violate:

- The spine remote is configured **append-only**: `receive.denyNonFastForwards=true`, `receive.denyDeletes=true`. Force-push and branch deletion are refused by the server, for every client, forever. History can only grow.
- Server-side snapshots: a daily `git bundle` of the spine repo rotated on the server (and optionally mirrored off-box) — recovery exists even if the repo itself is damaged.
- Client deny-list, codified in SPINE.md as law and enforced by the skills: never `reset --hard`, `git clean`, `checkout -- <path>` on spine state, `stash drop`, `push --force`, or history rewrites. If work "disappears": `git stash list`, `git reflog`, `git fsck --lost-found`, `spine recover` — in that order, before anyone concludes loss.

## 8. G6: snapshots are (mostly) free — the ledger is the time machine

Because state is a fold over timestamped, immutable lines:

- **`spine show <case> --as-of <ts>`** folds only lines with `ts ≤ T`: any historical position, reconstructed exactly, with no git archaeology at all. Worklist gets the same flag. This is the deep payoff of append-only: *the ledger is the snapshot mechanism; git commits are just transport batches.*
- **Artifacts** (renders, as-sent files) do need git-level pins: `spine snapshot [label]` creates a lightweight tag `snap/<ts>-<operator>[-label]` — used at deliveries, promise changes, and handovers. Tags ride to the append-only remote, so a pinned state is as unlosable as the data.

## 9. Topology: one tree, worktrees, or clones?

| Topology | Freshness of fold | Isolation | Verdict |
|---|---|---|---|
| **One shared tree** (agents on one machine) | Best — every fold sees every agent's uncommitted appends instantly | Weakest — needs manifest + lock (§4/§5) | **Default.** The spine's whole point is one current truth; isolation is what the data model already provides |
| Git worktrees per agent | Fold goes stale between syncs | Strong | Not worth it: it re-introduces "which copy is current?" to solve a conflict problem §3 already dissolved |
| Clones per machine | Stale between syncs (unavoidable across machines) | Strong | Required across machines; the sync cadence (§5) bounds staleness |

## 10. Adversarial review (what can still go wrong, honestly)

1. **Clock skew across machines.** Latest-wins folding trusts `ts`. Two machines updating the *same field* of the *same case* within the skew window can fold in the wrong order. Mitigations: (a) per-case monotonic guard — `append` stamps `ts = max(now, last_ledger_ts + 1s)` so order is always sane within any one clone; (b) NTP keeps real skew sub-second; (c) `doctor` flags same-field updates from different authors within 60s as a coordination smell (it usually is one, regardless of clocks). Residual risk: accepted and documented; the losing line is still *in the ledger*, visible, never gone.
2. **Same-instant appends to one case from two agents.** Not a conflict (union), and fold order is deterministic by (ts, id) tiebreak. But it may be a *semantic* race (two agents working one case unaware). Counter: `append` prints "note: <other-author> appended to this case <n>m ago" when it lands new-to-this-session lines — awareness, not locking.
3. **Push contention under many agents.** The retry loop converges but could thrash with dozens of writers. Acceptable to ~10 writers per spine; beyond that is exactly the Spine Cloud tier's job (§11).
4. **Binary artifacts bloat.** Large files make clones heavy. v0.2 keeps artifacts in git (simplicity, and our production spine proves it works at real scale); LFS is a documented opt-in later, never a default (it reintroduces a server dependency).
5. **A hostile or broken client ignoring all of this.** It can still write garbage lines (append-only accepts them — corrections are newer lines, doctor flags malformed ones) but it *cannot* destroy history: §7 is enforced server-side, beyond any client's reach. That is the floor under everything.

## 11. What the SQLite/server tier changes (and what it doesn't)

The git pipeline is the **serverless tier**: zero infrastructure, offline-capable, every guarantee above. The v1 SQLite backend collapses §4–§5 into WAL transactions on one machine; Spine Cloud collapses cross-machine sync into an authoritative store and makes §10.1–10.3 vanish (server assigns order). The journal (§6), as-of folds (§8), append-only law and the fold semantics are identical in every tier — **the guarantees are properties of the data model, and the data model never changes. Only the transport does.**

## 12. Implementation plan (on GO — not yet built)

| Step | Change | Size |
|---|---|---|
| 1 | Line `id` (ULID) in `append`/`new`/`promise`; dedupe in `read_ledger`; `(ts,id)` fold tiebreak | small |
| 2 | `spine init` writes `.gitattributes` (union drivers) + `.spine/` scaffolding | small |
| 3 | Session manifest in all mutating verbs | small |
| 4 | `spine sync` (§5 protocol: lock, manifest commit, fetch, merge, push-retry, report) + auto sync-in from `seed`, auto sync-out from `append` | medium |
| 5 | Journal-before-write + `spine recover` + doctor reconciliation | medium |
| 6 | `spine snapshot` + `--as-of` on show/worklist | small |
| 7 | Promise-as-event (PROMISE.json → projection) + doctor double-promise flag | medium |
| 8 | Docs: this file → user-facing `docs/collaboration.md`; server setup note (deny flags + bundle cron); golden tests: two-clone merge convergence, duplicate-line dedupe, journal replay, race-retry push | medium |

Tests are the proof: step 8's two-clone convergence test (append on both, sync both ways, assert identical folds and zero lost lines) is the executable form of G1+G2.

---

*Design principle running through all of it: **discipline is what failed; structure is what works.** Every guarantee above holds because a data model or a server flag enforces it — never because an agent remembered a rule.*
