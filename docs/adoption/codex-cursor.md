# SpineOS + Codex CLI · Cursor

## Codex CLI

Codex reads `AGENTS.md` natively — no extra setup.

```bash
git clone https://github.com/pmarais/spineOS myspine && cd myspine
codex           # then say: seed
```

## Cursor

Cursor loads `.cursor/rules/spineos.mdc` (ships in this repo), which binds the agent to `AGENTS.md`.
Open the folder in Cursor, then in the agent panel say **seed**.

## Both

The flow is identical to every other CLI: `seed` first (setup interview on a fresh clone), then
worklist → case → append → sitrep. The spine does not care which processor you plug in today —
that is the point. State, rules, attribution and gates live in the repo and survive every vendor.
