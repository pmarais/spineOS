#!/usr/bin/env node
// Minimal markdown → DOCX. Pattern demo: source in, artifact out, never hand-edit the output.
import { Document, Packer, Paragraph, TextRun, HeadingLevel } from "docx";
import { readFileSync, writeFileSync } from "node:fs";

const [src, dst] = process.argv.slice(2);
if (!src || !dst) { console.error("usage: md-to-docx.mjs <in.md> <out.docx>"); process.exit(1); }

const runs = (text) => {
  // **bold** and *italic* inline handling
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean);
  return parts.map(p =>
    p.startsWith("**") ? new TextRun({ text: p.slice(2, -2), bold: true }) :
    p.startsWith("*")  ? new TextRun({ text: p.slice(1, -1), italics: true }) :
    new TextRun(p));
};

const children = [];
for (const line of readFileSync(src, "utf8").split("\n")) {
  if (line.startsWith("# "))       children.push(new Paragraph({ text: line.slice(2), heading: HeadingLevel.HEADING_1 }));
  else if (line.startsWith("## ")) children.push(new Paragraph({ text: line.slice(3), heading: HeadingLevel.HEADING_2 }));
  else if (line.trim())            children.push(new Paragraph({ children: runs(line) }));
}
const doc = new Document({ sections: [{ children }] });
writeFileSync(dst, await Packer.toBuffer(doc));
console.log(`✓ ${dst} rendered from ${src} — edit the source, re-render; never patch the output`);
