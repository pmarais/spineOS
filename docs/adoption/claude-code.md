# SpineOS + Claude Code

```bash
git clone https://github.com/pmarais/spineOS myspine && cd myspine
claude          # open Claude Code in the folder
```

Then type **`/seed`** — always the first command. The bundled skills do the rest:

- **`/seed`** — boots the session: sync-in (if a remote is set), rules, case index, ranked worklist.
  On a fresh clone it walks you through setup: your name (attribution), what a case is for you,
  an optional private remote, your first case.
- **`/case <n|name>`** — load one case, work it under the rules, append the outcome. Gated actions
  (sends, payments, releases) stop for your explicit authorisation, recorded and single-use.
- **`/sitrep <case>`** — the fixed report block: DONE · STATE · DECIDE (options with trade-offs) ·
  NEXT (prioritised) · BLOCKED.

Daily shape: `/seed` → "what should I work on?" (the agent reads the worklist) → work → the agent
appends and syncs → `/sitrep` on anything you need to decide.

Notes: `CLAUDE.md` points Claude at `AGENTS.md`; the skills live in `.claude/skills/`. Set
`SPINE_OPERATOR` in your shell profile so attribution survives new terminals (`/seed` sets this up
for you on first run).
