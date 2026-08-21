# SpineOS blueprint

> **Design docs:** [docs/sync-design.md](docs/sync-design.md) (v0.2: multi-agent git pipeline) · [docs/architecture-v03.md](docs/architecture-v03.md) (v0.3: ingest modules, document skills, research dogma, roles/branches, server kit).

# SpineOS — open-source repo concept (NOT built — blueprint only)

Target: `github.com/<org>/spineos` (org TBD; `spine-os` fallback). Licence: Apache-2.0. Language: Python 3.12+ stdlib-only core (sqlite3 built in, zero hard dependencies — the install story is `pipx install spineos`). TypeScript adapter package later, not at launch.

---

## Repo layout

```
spineos/
├── README.md                  # the manifesto: processor/RAM/disk/OS in 60 lines + quickstart
├── LICENSE                    # Apache-2.0
├── SPEC.md                    # the normative spec: formats, fold semantics, verbs (versioned)
├── docs/
│   ├── concepts.md            # the analogy, the five primitives, the no-drift theorem
│   ├── quickstart.md          # zero → running spine in 5 minutes, single user + Claude Code
│   ├── multi-operator.md      # operators, owners, gates, git or SQLite modes
│   ├── sitrep.md              # the operator report protocol (STE rules included)
│   ├── backends.md            # files vs sqlite; export/import wire format
│   ├── adapters.md            # Claude Code / Cursor / MCP / plain-prompt integration
│   └── case-studies/mmedlab.md# the origin story, anonymised
├── spine/                     # the package
│   ├── cli.py                 # verbs: init seed new promise append show fold worklist doctor sitrep export import
│   ├── model.py               # Case, Promise, LedgerLine, LogRow, Operator (+ fold())
│   ├── backend_files.py       # v0: markdown + JSONL + CSV in git
│   ├── backend_sqlite.py      # v1: WAL, append-only triggers, transactional dual-write
│   ├── doctor.py              # drift checks (pluggable rule interface)
│   ├── sitrep.py              # SITREP renderer + parser
│   └── gates.py               # authorisation records: request → grant → consume, one action each
├── templates/
│   ├── SPINE.md               # starter OS: boot checklist, routing table, ~15 generic invariants WITH origin slots
│   ├── routers/               # example process files (intake, delivery, settlement, handover)
│   └── verticals/             # skeletal packs: consulting/, legal/, agency/ (community-fillable)
├── adapters/
│   ├── claude-code/           # .claude/skills/spine/ — seed, update, sitrep skills
│   ├── mcp/                   # MCP server exposing the verbs (read + gated write)
│   └── AGENTS.md.example      # how any agent is told to use the spine
└── tests/                     # fold semantics golden tests; append-only enforcement; doctor cases
```

## The spec's normative core (SPEC.md, v0.1)

1. **Formats.** `PROMISE.json` schema; `LEDGER.jsonl` line schema (required `ts`,`author`; controlled field vocabulary + `x_` extension namespace; `note` free text); `LOG.csv` columns; `SPINE.md` structural conventions (invariant = rule + origin).
2. **Fold semantics.** Latest-non-null-wins per field by `ts`; deterministic; reference implementation + golden test vectors so third-party implementations can verify.
3. **The verbs** and their contracts (append writes ledger+log atomically; show never reads raw storage in prose form...).
4. **Gate protocol.** Authorisation objects: scope, grantor, single-use consumption, expiry.
5. **Wire format.** Files ⇄ SQLite export/import, byte-deterministic, git-diffable.
6. **Conformance levels.** L0 read (can fold a spine), L1 write (append correctly), L2 gated (honours authorisations). Lets other tools claim compatibility precisely.

## Launch content (with the repo, not after)

- The essay: *"RAM-only computing"* — why context windows are not memory, with the incident receipts.
- *"Brains and spines"* — the gbrain-complement piece (respectful, technical, comparison table from 02_MARKET).
- A 3-minute demo: fresh clone → seed → agent handles a case end-to-end → SITREP → second agent (different vendor) picks it up cold.

## Deliberate non-goals at launch

No web UI. No embeddings/search. No hosted anything. No workflow DSL (routers are prose process files — the LLM is the interpreter). Each of these is either the paid tier or a trap.

## Anti-scope-creep rule for maintainers

Every proposed feature answers one question: *does it make promised-state more durable, more attributable, or more safely actionable?* If it makes the spine smarter instead (retrieval, ranking, extraction) it belongs in the brain layer — point the PR at gbrain/mem0 with love.
