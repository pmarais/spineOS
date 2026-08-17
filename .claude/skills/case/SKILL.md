---
name: case
description: Work one case on the spine. Use for "what's going on with X", "work on case N", "update X", opening new cases, or recording progress. Loads the case, does the work under SPINE.md rules, and appends the outcome so the next session finds it.
---

# case — load, work, append

**Arguments:** a case number or name fragment, e.g. `/case 3` or `/case acme`. If the operator wants a NEW case: `python3 spine.py new "<slug>" --note "<how it arrived>"`.

## The loop (always this order)

1. **Load before acting:**
   ```bash
   python3 spine.py show <case>
   ```
   Read the PROMISE and the position. Reason against the promise: what did we commit to, what do we owe, what are we waiting on, has anything they asked for gone unanswered?

2. **Do the work** the operator asked for, following SPINE.md and any `routers/` process for the task type.

3. **Gate check.** If the work produced something irreversible to execute (a message to send, money to move, something to publish or delete): STOP. Stage it, show the operator, and only execute on their explicit authorisation, recorded first:
   ```bash
   python3 spine.py append <case> --action AUTH_GRANT --note "operator authorised: <exact action>"
   # ...execute...
   python3 spine.py append <case> --action AUTH_CONSUME --note "<what happened, verified how>"
   ```
   One authorisation, one action, consumed on use. Never retry on an old authorisation.

4. **Append the outcome** — position and action in one verb, with a comprehensive note (this is the only memory the next session has):
   ```bash
   python3 spine.py append <case> --stage <stage> --owner <who> \
     --blocked-on <who> --next "<single suggested next action>" \
     --action <CODE> --note "<what happened, what was decided, what it means>"
   ```

5. **Report** in SITREP format (see the sitrep skill). Never report in free-form prose.

## Rules that bind here

- The promise changes only via `spine.py promise --force`, and only when the deal itself changed.
- Never edit or delete ledger lines, log rows, or history of any kind. Corrections are newer lines.
- If it only exists in this conversation, it does not exist: append before you finish.
