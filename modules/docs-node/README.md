# docs-node — the document skills (DOCX · PPTX · XLSX)

Node 22 (pinned by `.nvmrc`), three libraries pinned in `package.json`. Install once:

```bash
cd modules/docs-node && npm ci   # or npm install on first ever run to create the lockfile
```

## The one rule

**Rendered files are build artifacts.** You never hand-edit a DOCX/PPTX/XLSX output; you edit the
source (markdown, data, config) and re-render. A tracked-changes redline is computed from two source
versions; "Accept All" must equal the clean render of the new source.

## Examples

| Script | Demonstrates |
|---|---|
| `examples/md-to-docx.mjs` | markdown → DOCX via docx-js (headings, paragraphs, bold/italics) |
| `examples/data-to-pptx.mjs` | a deck rendered from a JSON outline via pptxgenjs |
| `examples/read-xlsx.mjs` | full read of a workbook (sheets, cells, formulas) → JSON for the agent to interpret |

Run: `node examples/md-to-docx.mjs input.md output.docx` etc. These are deliberately small: they are
the pattern, not the product. Grow them into your own translators inside your spine, and treat every
output as disposable: regenerate, never patch.

Team spreadsheets that join the workspace are read through `read-xlsx.mjs`, interpreted by the agent,
and sense-checked against the spine before any number from them is trusted.
