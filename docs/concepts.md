# Concepts — why the spine is shaped like this

## The analogy that explains everything

| Computer | LLM-augmented work | Property |
|---|---|---|
| CPU | The LLM (any vendor) | Stateless, executes what is loaded, interchangeable |
| RAM | The chat context | Fast, small, **wiped every session** |
| Disk | The spine | Durable, append-only, survives everything |
| OS | SPINE.md + the verbs | Boot, paging, scheduling, permissions, integrity |

Most AI-assisted work is RAM-only computing: brilliant sessions whose state evaporates on close. The spine is the disk, and the rules are the operating system. **The LLM is replaceable, the RAM is disposable, the disk is the business.**

## The five primitives

1. **PROMISE** — the commitment, snapshotted at acceptance. Memory systems store what happened; the spine also stores what was *supposed* to happen, so drift is computable. Changes only when the deal itself changes, and the change is ledgered.
2. **LEDGER** — append-only position record. Current state is **folded**: the latest non-null value of each field, scanning by timestamp. Contradiction resolves mechanically, never by re-reading prose.
3. **LOG** — append-only action record. The ledger says where things stand; the log says what was done. One verb (`append`) writes both, so they cannot drift apart through forgetfulness.
4. **RULES** — SPINE.md, read at boot. Invariants carry the incident that created them: a rule with an origin gets followed; a bare rule gets argued with.
5. **PROJECTIONS** — worklist, case summary, SITREP skeleton: printed from state by the verbs, never stored, never hand-maintained. The no-drift theorem: anything a human reads to decide is either a ledger entry or a projection of one.

Plus **GATES**: irreversible actions default to stage-for-review; an authorisation is granted explicitly, recorded, and consumed by the single action it authorises.

## Why append-only

- Nothing can be lost, by construction. Corrections are newer lines.
- Two writers never conflict: order is irrelevant because reads fold by timestamp.
- Every dispute is resolvable from an unedited trail.

## Why no vector database

State is structured and keyed. You do not *search* for where a case stands; you *fold* its ledger. Retrieval on the critical path is deterministic — the deadline never loses a relevance contest. Semantic search over narrative is a fine add-on someday; it is never the foundation.

## Why files first

Markdown, JSONL and CSV are maximally in-distribution for every LLM: there is no schema to teach, and an agent dropped cold into a spine can operate it from SPINE.md alone. Files are also zero-infrastructure and git-native. A SQLite backend (same verbs, ACID writes, append-only enforced by triggers) is the planned robustness tier — see BLUEPRINT.md.

## The compounding claim

Every session ends by writing its findings into the disk the next session boots from. The rules file grows an invariant every time something fails. A spined team's floor rises monotonically; a RAM-only team restarts from zero every morning. That is the whole product.
