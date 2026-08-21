# SpineOS + Grok CLI

```bash
git clone https://github.com/pmarais/spineOS myspine && cd myspine
grok            # open Grok CLI in the folder
```

Grok reads `GROK.md`, which points it at `AGENTS.md` (the agent contract). Then say:

> **seed**

Always the first instruction. Grok runs `python3 spine.py seed`, reads your rules and worklist, and
on a fresh clone interviews you: name, what a case is in your business, optional private remote,
first case. After that the working loop is plain language:

- "what should I work on?" → Grok reads the ranked worklist
- "what's going on with Acme?" → `show`, reasoned against the promise
- "record that the deposit landed and we started" → `append` (attributed, journaled, synced)
- "report" → the SITREP block

The contract Grok is bound to (from AGENTS.md): load one case before acting on it; append after
every substantive step; never edit history; irreversible actions wait for your recorded, single-use
authorisation; reports in SITREP format only.
