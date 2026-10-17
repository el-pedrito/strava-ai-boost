// Fold dist-gate0/assets/*.js into dist-gate0/index.html so the Gate 0 page is
// ONE self-contained file (no external script, stylesheet or manifest), then
// delete the assets and print the SHA-256 of the result.
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const outDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../dist-gate0');
const htmlPath = path.join(outDir, 'index.html');
let html = fs.readFileSync(htmlPath, 'utf8');

const scriptRe = /<script\b[^>]*\bsrc="\.?\/?(assets\/[^"]+\.js)"[^>]*><\/script>/g;
let inlined = 0;
html = html.replace(scriptRe, (_tag, rel) => {
  inlined += 1;
  // Escape any closing tag inside the bundle so it cannot end the inline script early.
  const js = fs.readFileSync(path.join(outDir, rel), 'utf8').replace(/<\/script/gi, '<\\/script');
  // Function replacement: `$` sequences in the bundle are not interpreted.
  return `<script type="module">${js}</script>`;
});
if (inlined === 0) {
  throw new Error('inline.mjs: no bundled script found in dist-gate0/index.html');
}

// Refuse to ship anything that still points at another file.
const external = html.match(/\s(?:src|href)=["'][^"']*["']/gi);
if (external) {
  throw new Error(`inline.mjs: external reference left in HTML: ${external.join(', ')}`);
}

// Refuse any URL anywhere in the output (markup, CSS, or inside the inlined bundle):
// the page must load nothing. Matching the whole file is deliberately blunt: a URL in
// a string literal of the bundle fails too, and none is expected there. `url(` needs a
// non-letter before it so `URL.createObjectURL(` (the blob download) is not a hit.
// Also refused: WebSocket schemes, and a protocol-relative URL opening a string literal
// ("//host" or '//host'). This blunt scan WILL break the build if a future dependency
// embeds any URL (an SVG namespace, an error-page link): that is intended, do not
// loosen the regex, remove the dependency from the Gate 0 page instead.
const urlLike = html.match(/(?:https?|wss?):\/\/|(?<![A-Za-z])url\(|["'`]\/\/[A-Za-z0-9]/gi);
if (urlLike) {
  throw new Error(`inline.mjs: URL left in output: ${[...new Set(urlLike)].join(', ')}`);
}

// The defence-in-depth meta tags must survive the build.
for (const required of ['name="referrer" content="no-referrer"', `http-equiv="Content-Security-Policy"`]) {
  if (!html.includes(required)) {
    throw new Error(`inline.mjs: missing meta tag ${required}`);
  }
}

fs.writeFileSync(htmlPath, html);
fs.rmSync(path.join(outDir, 'assets'), { recursive: true, force: true });
const left = fs.readdirSync(outDir);
if (left.length !== 1 || left[0] !== 'index.html') {
  throw new Error(`inline.mjs: dist-gate0 must hold only index.html, found: ${left.join(', ')}`);
}

const sha = createHash('sha256').update(fs.readFileSync(htmlPath)).digest('hex');
console.log(`gate0: ${htmlPath}`);
console.log(`gate0 sha256: ${sha}`);
