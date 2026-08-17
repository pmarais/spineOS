# SpineOS

**LLMs are the processor. Chat is RAM. SpineOS is the disk, and the operating system.**

Durable, append-only operational state for humans and AI agents working together: what you promised, where every case stands, who did what, and the rules of execution. It survives every session, every operator, and every model swap.

- **No API keys. No server. No dependencies.** One Python file (stdlib, 3.9+) operated by the agent CLI you already subscribe to: Claude Code, Grok CLI, Codex CLI, Cursor.
- **Append-only by rule.** Current state is *folded* from the ledger (latest value per field, by timestamp) — it cannot drift, by construction.
- **Gated.** Irreversible actions (send, pay, publish, delete) wait for a recorded, single-use authorisation.
- **Attributed.** Every write carries an author; owner and author are distinct.

## Quickstart (60 seconds)

```bash
git clone <this-repo> myspine && cd myspine
export SPINE_OPERATOR=yourname
```

Open Claude Code (or your agent CLI) in the folder and say **"seed"**. The agent boots from the spine — rules, case index, ranked worklist — and waits for your instruction. Full walkthrough: [docs/quickstart.md](docs/quickstart.md).

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
```

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
| [`docs/`](docs) | [Quickstart](docs/quickstart.md) · [Concepts](docs/concepts.md) · [Example workflows](docs/workflows.md) |
| [`examples/demo_spine/`](examples/demo_spine) | A fully worked spine to learn from |
| [`routers/`](routers) | Your task-specific processes (the Prime Rule: use the registered process, never invent one) |
| [`tests/`](tests) | Golden tests for the fold semantics and CLI: `python3 tests/test_spine.py` |
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
