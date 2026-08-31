const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', 'node_modules', '@mui');
const ROOT_TARGETS = ['elementAcceptingRef', 'chainPropTypes'];

// CRA/Webpack in this deployment can reject MUI utility subpath imports when
// the package exposes a CommonJS/named export shape rather than a static ESM
// default export. Normalize all default imports from @mui/utils/* to a
// runtime require with a default-or-module fallback. This is deliberately
// broader than the two failures already observed so the build stops failing
// one utility at a time.
const ROOT_IMPORT_RE = /import\s*\{([\s\S]*?)\}\s*from\s*['"]@mui\/utils['"];?/g;
const DEFAULT_SUBPATH_RE = /import\s+([A-Za-z_$][\w$]*)\s+from\s*['"]@mui\/utils\/([^'"\s]+)['"];?/g;
const REQUIRE_RE = /const\s*\{([\s\S]*?)\}\s*=\s*require\(['"]@mui\/utils['"]\);?/g;

if (!fs.existsSync(ROOT)) {
  throw new Error('[CLOUDFLARE-MUI-PATCH] @mui is not installed; refusing to continue.');
}

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, files);
    else if (entry.isFile() && full.endsWith('.js') && !full.endsWith('.map')) files.push(full);
  }
  return files;
}

function runtimeRequire(local, source) {
  return `const ${local} = (() => { const m = require('@mui/utils/${source}'); return m && m.default ? m.default : m; })();`;
}

function patchRootImport(match, body) {
  const parts = body.split(',').map((x) => x.trim()).filter(Boolean);
  const direct = [];
  const remaining = [];

  for (const part of parts) {
    const base = part.split(/\s+as\s+/)[0].trim();
    if (ROOT_TARGETS.includes(base)) {
      direct.push({ source: base, local: part.includes(' as ') ? part.split(/\s+as\s+/)[1].trim() : base });
    } else {
      remaining.push(part);
    }
  }

  if (!direct.length) return match;

  const replacement = [];
  if (remaining.length) replacement.push(`import { ${remaining.join(', ')} } from '@mui/utils';`);
  for (const item of direct) replacement.push(runtimeRequire(item.local, item.source));
  return replacement.join('\n');
}

function patchDefaultSubpathImport(match, local, source) {
  return runtimeRequire(local, source);
}

function patchRequire(match, body) {
  const parts = body.split(',').map((x) => x.trim()).filter(Boolean);
  const direct = [];
  const remaining = [];
  for (const part of parts) {
    const base = part.split(/\s*:\s*/)[0].trim();
    if (ROOT_TARGETS.includes(base)) direct.push(base);
    else remaining.push(part);
  }
  if (!direct.length) return match;

  const lines = [];
  if (remaining.length) lines.push(`const { ${remaining.join(', ')} } = require('@mui/utils');`);
  for (const name of direct) lines.push(runtimeRequire(name, name));
  return lines.join('\n');
}

let changed = 0;
for (const file of walk(ROOT)) {
  const before = fs.readFileSync(file, 'utf8');
  const after = before
    .replace(ROOT_IMPORT_RE, patchRootImport)
    .replace(DEFAULT_SUBPATH_RE, patchDefaultSubpathImport)
    .replace(REQUIRE_RE, patchRequire);
  if (after !== before) {
    fs.writeFileSync(file, after);
    changed += 1;
  }
}

console.log(`[CLOUDFLARE-MUI-PATCH] Patched ${changed} installed MUI JS files for CRA/Webpack compatibility.`);
