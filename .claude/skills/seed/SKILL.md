---
name: seed
description: Boot the session from the spine. Use at the start of any working session, or when asked to "seed", "cold start", "load context", or "read the spine". Prints the rules, the case index and the ranked worklist, then waits for the operator's instruction.
---

# seed — cold-start the session from the spine

Run the boot sequence NOW and read its output in full:

```bash
python3 spine.py seed
```

If the output contains a **[FIRST RUN]** block, this spine is not set up yet: interview the operator exactly as that block instructs — one question at a time (name → attribution, what a case is for them, team/branch mode, optional private remote, first real case) — and complete the setup before anything else.

Then:

1. **Follow SPINE.md exactly as printed** — it is the operating system for this repo. Its Prime Rule, gates, and reporting format bind you for the whole session.
2. If the operator named a case (`/seed 0003`), load it: `python3 spine.py show <case>`.
3. Report readiness in a few lines: operator attribution status, number of open cases, top of the worklist, anything the doctor would flag (`python3 spine.py doctor` if the seed output suggests drift).
4. **Stop.** The next action comes from the operator or the worklist — never from your own initiative on gated actions.

Never skip the seed because you "remember" the spine from earlier: you have no memory between sessions. The spine remembers for you.
