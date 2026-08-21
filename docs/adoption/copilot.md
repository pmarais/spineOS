# SpineOS + GitHub Copilot

Copilot's agent surfaces read `AGENTS.md` and `.github/copilot-instructions.md` — both ship in this
repo and point at the same contract.

```bash
git clone https://github.com/pmarais/spineOS myspine && cd myspine
copilot         # Copilot CLI in the folder (or open the repo in VS Code agent mode)
```

Then say:

> **seed**

Copilot runs `python3 spine.py seed`; on a fresh clone it sets you up (name, what a case is,
optional private remote, first case), then you work through plain language: "worklist",
"show acme", "record the delivery", "sitrep 1".

Because the spine is just files + a stdlib Python CLI, the Copilot coding agent working in a cloud
environment operates it exactly the same way — the repo carries everything it needs. The gates still
hold: nothing irreversible executes without your recorded, single-use authorisation.
