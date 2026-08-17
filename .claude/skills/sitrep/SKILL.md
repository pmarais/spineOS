---
name: sitrep
description: Report a case's position to the operator in the fixed SITREP block. Use when asked for status, an update, "where are we on X", or at the end of any substantive piece of work on a case.
---

# sitrep — the operator report

Render the skeleton from state, then complete it with judgement:

```bash
python3 spine.py sitrep <case>
```

The skeleton prefills DONE (from the log) and STATE (from the fold). You complete **DECIDE** and **NEXT**:

- **DECIDE** — every open decision as a numbered item with lettered options and their trade-offs. Mark a recommended option and say why in one clause. If nothing needs deciding, write `- None.`
- **NEXT** — actions in priority order, P1 first. Each is one concrete action, not a theme.

## Language rules (binding)

Controlled language, always: one idea per sentence; active voice; 25 words maximum per sentence; the same word for the same thing every time; no idioms, no phrasal verbs; numerals for numbers. The reader may be a non-first-language English speaker skimming on a phone; no sentence may be misreadable.

Never pad the block with commentary, apologies or enthusiasm. The block is the whole report.
