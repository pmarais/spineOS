# AGENTS.md — how any AI agent operates this repository

This repository is a **spine**: durable, append-only operational state for humans and AI working together. You (the agent) are the processor; this repo is the disk and the operating system. You need no API key and no server — just this repo and the CLI you are already running in.

## Boot (do this first, every session)

```bash
python3 spine.py seed
```

Read the output in full. It prints SPINE.md (the rules that bind you), the case index, the ranked worklist, and your contract as the agent.

## The five things you must know

1. **Load one case before acting on it:** `python3 spine.py show <case>`. Reason against its PROMISE (the deal): what do we owe, what do we await, what has gone unanswered?
2. **Append after every substantive step:** `python3 spine.py append <case> --note "..."` (plus any changed fields: `--stage --owner --blocked-on --next --paid --action CODE`). One verb writes both the position ledger and the action log. **If it only exists in the conversation, it does not exist.**
3. **Never edit history.** Ledger lines and log rows are append-only. A mistake is corrected by a newer line.
4. **Gates:** anything irreversible (sending to an outside party, moving money, publishing, deleting) defaults to STAGE FOR REVIEW. Execute only on the operator's explicit authorisation, recorded first (`--action AUTH_GRANT`), consumed by the one action it authorises (`--action AUTH_CONSUME`). Never retry on an old authorisation.
5. **Report in SITREP format only** (`python3 spine.py sitrep <case>` renders the skeleton; you complete DECIDE with options + trade-offs and NEXT in priority order). Controlled language: one idea per sentence, ≤25 words, no idioms.

## Verbs

```
python3 spine.py seed                # boot: rules + index + worklist
python3 spine.py new "<slug>"        # open a case
python3 spine.py promise <case> ...  # write the deal snapshot (--force to change it, ledgered)
python3 spine.py append <case> ...   # position + action, one verb
python3 spine.py show <case>         # fold a case, human/LLM-legible
python3 spine.py fold <case>         # same, JSON
python3 spine.py worklist            # all open cases ranked P1/P2/P3
python3 spine.py doctor              # drift detection
python3 spine.py sitrep <case>       # report skeleton
python3 spine.py sync                # commit ONLY this session's files, merge (never rebase), push
python3 spine.py snapshot [label]    # pin current state as a tag (deliveries, handovers)
python3 spine.py recover             # replay journaled lines missing from ledgers (idempotent)
python3 spine.py reconcile           # ADMIN, MANUAL: merge member branches into main
```

Sync is safe by construction: ledgers merge as unions (conflicts impossible), lines deduplicate by
id, every write is journaled locally before it touches a ledger, and the choreography never rebases
and never stashes. Details: docs/sync-design.md.

## Attribution

Every write is attributed. Ensure `SPINE_OPERATOR` is set (ask the operator if it is not); when you act on their behalf the convention is `agent:<operator>` via `--author`.

## Where the detail lives

- `SPINE.md` — the operating rules and invariants (the rules carry their origin stories; read them).
- `routers/` — task-specific processes, one file per task type. Prime Rule: use the registered process, never invent one.
- `docs/` — quickstart, concepts, example workflows.
- `examples/demo_spine/` — a fully worked spine to learn from: `cd examples/demo_spine && python3 ../../spine.py seed`.
