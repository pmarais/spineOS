# research — the generic Central Dogma for numbers, stats and analysis

```
DATA (immutable) → ANALYSIS (pinned Python) → NUMBERS LEDGER → PROSE → RENDERS
```

- **DATA**: client/source inputs live in `data/`, verbatim, never edited. A re-supplied dataset is
  reconciled against the held version on a stable key before any analysis runs off it.
- **ANALYSIS**: deterministic scripts in `analysis/`, pinned Python (`.python-version` +
  `requirements.txt`, enforced by `spine.py doctor --env`). Every reported difference carries an
  effect size and a p-value; sample sizes are shown as calculations; non-significant findings stay in.
- **NUMBERS LEDGER** (`numbers.py`): every computed quantity is recorded with its script and input
  hashes. Prose cites `{{num:key}}`; `check` fails any document citing an unledgered number; `render`
  substitutes. **No number enters prose by hand** — no transcribed figures, no orphaned numbers,
  everything re-derivable.
- **RENDERS**: DOCX/PPTX via `modules/docs-node` — build artifacts, regenerated, never patched.

Third-party analyses (a statistician's output, a co-author's table) are **evidence, not input**:
archive them verbatim, reproduce their specification on YOUR data, record YOUR computed values, and
report the concordance count. What will not reconcile is a finding — named, never silently adopted
or dropped. (Production origin: a reproduced analysis agreed on 38 of 38 checkable quantities and
thereby exposed that the "better" re-supplied dataset had silently lost every severe-category record.)

```bash
python3 modules/research/numbers.py record --key mortality_over40 --value 0.82 \
    --script analysis/03_outcomes.py --inputs data/cohort.csv --unit "proportion"
python3 modules/research/numbers.py check docs/report.md
python3 modules/research/numbers.py render docs/report.md out/report.md
```
