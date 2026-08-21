# SpineOS

**LLMs are the processor. Chat is RAM. SpineOS is the disk, and the operating system.**

Durable, append-only operational state for humans and AI agents working together: what you promised, where every case stands, who did what, and the rules of execution. It survives every session, every operator, and every model swap.

- **No API keys. No server. No dependencies.** One Python file (stdlib, 3.9+) operated by the agent CLI you already subscribe to: Claude Code, Grok CLI, Codex CLI, Cursor.
- **Append-only by rule.** Current state is *folded* from the ledger (latest value per field, by timestamp) — it cannot drift, by construction.
- **Gated.** Irreversible actions (send, pay, publish, delete) wait for a recorded, single-use authorisation.
- **Attributed.** Every write carries an author; owner and author are distinct.

## Install (2 minutes, no API keys)

```bash
git clone https://github.com/pmarais/spineOS myspine && cd myspine
```

**Open the folder in your agent CLI** — Claude Code, Grok CLI, Copilot CLI, Codex or Cursor — and make your first command:

> **`/seed`**  (Claude Code) · or just say **"seed"** in any other CLI

The agent boots from the spine and, on a fresh clone, **sets you up in conversation**: your name (for attribution), what a "case" is in your world (clients? matters? projects?), an optional private remote for durability, and your first real case. From then on every session starts with `seed` and runs `worklist → case → append → sitrep`. Per-CLI guides: [docs/adoption/](docs/adoption/README.md). Full walkthrough: [docs/quickstart.md](docs/quickstart.md).

Prefer the raw CLI?

```bash
python3 spine.py seed                 # boot: rules + index + worklist
python3 spine.py new "Acme Ltd"       # open a case
python3 spine.py promise 1 --client "Acme Ltd" --total 120000 --currency ZAR \
    --milestone "deposit:40000:paid" --milestone "final:80000"
python3 spine.py append 1 --stage in_progress --owner you --note "Deposit bank-confirmed; started."
python3 spine.py show 1               # fold: the case's current position
python3 spine.py worklist             # every open case, ranked P1/P2/P3
python3 spine.py doctor               # drift detection
python3 spine.py sitrep 1             # the operator report skeleton
python3 spine.py sync                 # commit ONLY this session's files, merge (never rebase), push
python3 spine.py snapshot delivery-1  # pin the current state as a tag
```

**Multi-agent, multi-machine, zero loss:** ledgers are append-only and union-merged (conflicts are
impossible by construction), every write is journaled locally before it lands (`recover` replays),
sync commits only the files your session touched, and teams can run per-member branches with a
manual admin `reconcile`. The design and its production scar tissue: [docs/sync-design.md](docs/sync-design.md).

## Try the worked example

```bash
cd examples/demo_spine && python3 ../../spine.py seed
```

Three realistic cases: an engagement in progress, a message staged at a gate awaiting authorisation, and a raw lead — with full ledgers, logs and a delivery router to read.

## What is in the box

| Path | What |
|---|---|
| [`spine.py`](spine.py) | The whole CLI. One file, stdlib only |
| [`SPINE.md`](SPINE.md) | The starter rulebook: boot checklist, gates, SITREP protocol, 10 invariants each carrying the incident that created it |
| [`.claude/skills/`](.claude/skills) | Claude Code skills: `/seed`, `/case`, `/sitrep` |
| [`AGENTS.md`](AGENTS.md) | Operating instructions for any agent CLI (CLAUDE.md and GROK.md point here) |
| [`docs/`](docs) | [Quickstart](docs/quickstart.md) · [Concepts](docs/concepts.md) · [Adoption per CLI](docs/adoption/README.md) · [Sync design](docs/sync-design.md) · [Architecture](docs/architecture-v03.md) |
| [`examples/demo_spine/`](examples/demo_spine) | A fully worked spine to learn from |
| [`routers/`](routers) | Your task-specific processes (the Prime Rule: use the registered process, never invent one) |
| [`modules/docs-node/`](modules/docs-node) | Document skills: DOCX · PPTX · XLSX (Node 22, pinned) |
| [`tests/`](tests) | 12 golden tests incl. two-clone convergence with zero loss: `python3 tests/test_spine.py` |
| [`BLUEPRINT.md`](BLUEPRINT.md) | The roadmap: SQLite backend, conformance levels, adapters |

## The five primitives

1. **PROMISE** — the commitment, snapshotted at acceptance. Changes only when the deal changes, and the change is ledgered.
2. **LEDGER** — append-only position record; state is folded, never authored.
3. **LOG** — append-only action record; one verb writes both, so they cannot drift apart.
4. **RULES** — SPINE.md, read at boot; invariants carry their origin incidents, so the spine learns from every failure.
5. **PROJECTIONS** — worklist, summaries, SITREPs: computed, never stored.

Why it is shaped this way: [docs/concepts.md](docs/concepts.md).

## Provenance

Extracted from a production operations spine that has run a real professional-services firm since July 2026: two human operators, concurrent AI agents on multiple machines, real client commitments executed under gates, attribution and audit. The starter invariants are that firm's incidents, generalised.

## Licence

[Apache-2.0](LICENSE).

---

Website: [spineos.dev](https://spineos.dev)
