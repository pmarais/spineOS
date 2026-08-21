#!/usr/bin/env node
// Minimal JSON outline → PPTX deck. The deck is a projection of approved source, never authored in PowerPoint.
import pptxgen from "pptxgenjs";
import { readFileSync } from "node:fs";

const [src, dst] = process.argv.slice(2);
if (!src || !dst) { console.error("usage: data-to-pptx.mjs <outline.json> <out.pptx>  (outline: [{title, bullets:[]}])"); process.exit(1); }

const slides = JSON.parse(readFileSync(src, "utf8"));
const pptx = new pptxgen();
for (const s of slides) {
  const slide = pptx.addSlide();
  slide.addText(s.title, { x: 0.5, y: 0.4, w: 9, h: 0.8, fontSize: 28, bold: true, color: "1e6b4f" });
  if (s.bullets?.length)
    slide.addText(s.bullets.map(b => ({ text: b, options: { bullet: true } })),
                  { x: 0.7, y: 1.5, w: 8.6, h: 4.5, fontSize: 16, color: "1c1f26" });
}
await pptx.writeFile({ fileName: dst });
console.log(`✓ ${dst} rendered from ${src}`);
