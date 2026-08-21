# SPINE — the operating rules

**This file is the operating system.** Every session (human or agent) reads it at boot, before any work. It is yours: edit it, grow it, and above all keep adding invariants when things go wrong. A spine gets safer with every failure it survives — but only if the failure is written down here.

> **Prime rule: use the registered process, never invent one.** If a task has a process in this file or in `routers/`, follow it. If it genuinely has none, say so and ask the operator — do not improvise a workflow, a format, a price, or a message style. When this file conflicts with your instinct, this file wins.

---

## 0. Boot (cold start)

Every session starts here. You wake with no memory of prior sessions; the spine remembers for you.

```
[ ] 1. python3 spine.py seed          # sync-in + this file + case index + ranked worklist
[ ] 2. If working one case:  python3 spine.py show <case>
[ ] 3. Take the next action from the operator or the worklist — never from memory.
[ ] 4. Session end: python3 spine.py sync   # commits ONLY what this session touched, merges, pushes
```

**The context preservation rule:** if a finding, decision or client fact exists only in the conversation, it does not exist. Before the session ends, append it: `python3 spine.py append <case> --note "..."`.

## 1. The stages

`intake → agreed → in_progress → in_review → done → closed`

A case is in exactly one stage. `agreed` requires a PROMISE.json (the deal snapshot). Change the vocabulary if your domain needs to — but change it HERE, once, not per case.

## 2. The three files (per case)

| File | Rule |
|---|---|
| PROMISE | An EVENT on the ledger, written at acceptance via `spine.py promise`; changed ONLY when the deal itself changes (`--force`, ledgered old → new). `PROMISE.json` is a rendered projection |
| `LEDGER.jsonl` | **Append only. Never edit or delete a line.** A mistake is corrected by appending a newer line. Current state = latest non-null value per field (the fold) |
| `LOG.csv` | Append only. One row per action taken. `spine.py append` writes it together with the ledger — never write one without the other |

## 3. Attribution

Every write carries an author. Set `SPINE_OPERATOR` (env) per person per machine. An agent acting for someone writes `agent:<operator>`. **Owner ≠ author:** the owner (a ledger field) is accountable for the case; the author is whoever acted. Anyone may act on any case; the trail is automatic.

## 4. Gates — irreversible actions

An action is **gated** if it cannot be taken back: sending a message to an outside party, moving money, publishing, deleting, signing.

1. Default is **stage for review**: prepare the action, show it to the operator, do not execute.
2. Execution needs an explicit authorisation from the case owner, recorded first:
   `spine.py append <case> --action AUTH_GRANT --note "operator authorised: <exact action>"`
3. **One authorisation, one action, consumed on use.** Record the execution with `--action AUTH_CONSUME` (or SEND/PAYMENT/etc.) referencing the grant. The next action — even seconds later — needs its own authorisation.
4. **Never retry a failed gated action on the old authorisation.** Verify what actually happened first (an action can succeed and look failed). Surface it and let the owner decide.

## 5. External truth

**Feeds are facts; messages are claims.** A payment is confirmed by the bank record, not by a screenshot. A delivery is confirmed by the channel, not by the script's exit code. When a claim matters, reconcile it against the system of record before acting on it — and record which one you checked.

## 6. Reporting — SITREP only

Reports to the operator use the SITREP block (`spine.py sitrep <case>` renders the skeleton; you complete DECIDE and NEXT):

```
SITREP <case> · <ts> · <author>
DONE       what was completed, plainly
STATE      stage · owner · money · blocked-on
DECIDE     numbered decisions, each with options A/B and trade-offs
NEXT       actions in priority order (P1, P2 ...)
BLOCKED    what we wait on, or "Nothing blocks us."
```

Write it in controlled language: one idea per sentence; active voice; ≤25 words per sentence; the same word for the same thing every time; no idioms, no phrasal verbs. The reader may be skimming on a phone; nothing may be misreadable.

## 7. Projections are computed, never authored

The worklist, the case summary, the SITREP skeleton: all printed from state by the verbs. **Do not hand-maintain a status document anywhere** — not in a README, not in a wiki, not in a pinned message. Hand-maintained summaries drift; the fold cannot.

## 8. Invariants (rules with origins)

Every entry here exists because something went wrong once. When something goes wrong for you, add the rule AND the incident — a rule with an origin gets followed; a bare rule gets argued with. Starters, earned in production by the firm that extracted this system:

1. **Sync before acting.** Never act on a case from stale channel data. Refresh, then read, then act. *(Origin: a quote drafted against a six-message thread when the real thread had fifteen; the missing nine contained the client's actual request.)*
2. **A quiet log means WE went quiet.** The log records what we did; when we do nothing it falls silent, and silence reads as "no activity" when it means "the other side is waiting". Before writing any wait (`blocked_on: them`), check the inbound channel. *(Origin: a second request hidden past a preview cut went unanswered for 27 days while the record looked healthy.)*
3. **Payment messages carry riders.** Money messages get processed while the rest of the message goes unread. Read the whole message, always. *(Origin: two document requests riding on payment confirmations, ignored for four days.)*
4. **One send per authorisation, no retry.** A send that looks failed has often succeeded. Verify against the channel record before concluding anything. *(Origin: a client received the same message three times.)*
5. **An offer is a commitment.** Never offer what policy does not allow ("available on request", "happy to send"). If a sentence lets a reasonable reader reply "yes please", it is an offer. *(Origin: one such sentence cost the firm its deliverable leverage.)*
6. **A flag is not a fix.** A recorded defect that is not resolved ships. When you flag something, either make it blocking or name who resolves it and when; when you meet an old flag, resolve it. *(Origin: three flagged bad citations survived four versions into a delivered document.)*
7. **Check the docs before calling it an incident.** Deliberate behaviour reads as breakage from outside. Read the relevant process file before reporting an outage. *(Origin: a "fleet-wide outage" that was a documented, by-design 404.)*
8. **Third-party work is evidence, not input.** Reproduce it, never transcribe it; what will not reconcile is a finding, not an inconvenience. *(Origin: a supplied dataset had silently lost every severe-category record; the reproduction caught it, transcription would not have.)*
9. **Bound every wait.** A watchdog with no wall-clock bound can hold a shared resource forever. Anything that waits needs both a per-step timeout and a total one. *(Origin: a 38-minute hang on 1.9 seconds of CPU, blocking every other agent.)*
10. **Append, never edit.** In every store: corrections are new entries. History is how you find out what actually happened. *(Origin: every dispute the firm has resolved was resolved from an unedited trail.)*

## 8b. Sync (multi-agent, multi-machine)

`spine.py sync` shares work safely: it commits ONLY the files this session touched, merges (never
rebases, never stashes), and pushes with retries. Ledgers cannot conflict (append-only, union-merged,
deduplicated by id); a conflict in prose files stops loudly for a human. Every write is journaled
locally before it touches a ledger (`spine.py recover` replays). Teams on per-member branches push
`member/<name>` and pull `main`; an ADMIN advances `main` MANUALLY with `spine.py reconcile`.
Never: `reset --hard`, `git clean`, `checkout --` on spine state, `stash drop`, force-push.

## 9. Routers

Task-specific processes live in `routers/` as plain markdown, one file per task type (e.g. `routers/onboarding.md`, `routers/delivery.md`). This file stays small; routers carry the detail. If a router and this file disagree: the router wins on mechanics, this file wins on sequence and gates.

---

*SpineOS starter rulebook v0.1. Replace the origin stories with your own as you earn them.*
