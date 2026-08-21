# Adoption — SpineOS in YOUR agent CLI

SpineOS needs no API keys and no server. It runs inside the agent subscription you already pay for.
The install story is the same everywhere:

```
1. Visit github.com/pmarais/spineOS  →  git clone https://github.com/pmarais/spineOS myspine
2. Open the folder in your agent CLI (Claude Code, Grok CLI, Copilot CLI, Codex, Cursor)
3. Say: seed          (in Claude Code: /seed)   ← always the first command
4. The agent sets you up: your name, what a case is in your world, an optional private remote,
   and your first real case. Then you work: worklist → case → sitrep.
```

From then on, every session starts with `seed` and ends with your findings appended to the spine.

## The canonical first session (any CLI, same transcript)

> **You:** seed
> **Agent:** *(runs `python3 spine.py seed`, reads the rules, sees FIRST RUN)* This spine is not set
> up yet. What is your name, for attribution? …And what do you run here: clients, matters, projects?
> **You:** I'm Sam. Clients — I run a small consultancy.
> **Agent:** *(sets SPINE_OPERATOR=sam, writes config)* Set up. Shall we open your first case — which
> client is most on your mind today?
> **You:** Acme. They accepted a 120k proposal yesterday, deposit of 40k is already in.
> **Agent:** *(runs `new`, `promise` with milestones, `append --paid 40000`)* Acme is on the spine:
> promise ledgered, deposit recorded, stage in_progress. Your worklist has one case. What did you
> promise them first?

Tomorrow, in a fresh session with a blank context window: **"seed"** → the agent knows all of it.

## Per-CLI notes

| CLI | Boot file it reads | Guide |
|---|---|---|
| Claude Code | `CLAUDE.md` + `.claude/skills/` (`/seed`, `/case`, `/sitrep`) | [claude-code.md](claude-code.md) |
| Grok CLI | `GROK.md` → AGENTS.md | [grok-cli.md](grok-cli.md) |
| GitHub Copilot (CLI / coding agent) | `AGENTS.md` + `.github/copilot-instructions.md` | [copilot.md](copilot.md) |
| Codex CLI | `AGENTS.md` (native) | [codex-cursor.md](codex-cursor.md) |
| Cursor | `.cursor/rules/spineos.mdc` → AGENTS.md | [codex-cursor.md](codex-cursor.md) |

Every file above points at the same two sources of truth: `AGENTS.md` (the agent contract) and
`SPINE.md` (your rules). One spine, any processor — switching CLI mid-week changes nothing.
