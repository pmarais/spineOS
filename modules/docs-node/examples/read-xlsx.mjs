#!/usr/bin/env node
// Full read of a workbook → JSON, so the agent can interpret and sense-check it against the spine.
import ExcelJS from "exceljs";

const [src] = process.argv.slice(2);
if (!src) { console.error("usage: read-xlsx.mjs <in.xlsx>"); process.exit(1); }

const wb = new ExcelJS.Workbook();
await wb.xlsx.readFile(src);
const out = {};
wb.eachSheet(ws => {
  const rows = [];
  ws.eachRow((row, n) => rows.push({ n, values: row.values.slice(1).map(v =>
    (v && typeof v === "object" && "formula" in v) ? { formula: v.formula, result: v.result } : v) }));
  out[ws.name] = rows;
});
console.log(JSON.stringify(out, null, 2));
