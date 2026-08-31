const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', 'node_modules', '@mui');
const TARGETS = ['elementAcceptingRef', 'chainPropTypes'];
const IMPORT_RE = /import\s*\{([\s\S]*?)\}\s*from\s*['"]@mui\/utils['"];?/g;
const DIRECT_RE = /import\s+([A-Za-z_$][\w$]*)\s+from\s*['"]@mui\/utils\/(elementAcceptingRef|chainPropTypes)['"];?/g;
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

function patchRootImport(match, body) {
  const parts = body.split(',').map((x) => x.trim()).filter(Boolean);
  const direct = [];
  const remaining = [];

  for (const part of parts) {
    const base = part.split(/\s+as\s+/)[0].trim();
    if (TARGETS.includes(base)) {
      direct.push({ source: base, local: part.includes(' as ') ? part.split(/\s+as\s+/)[1].trim() : base });
    } else {
      remaining.push(part);
    }
  }

  if (!direct.length) return match;

  const replacement = [];
  if (remaining.length) replacement.push(`import { ${remaining.join(', ')} } from '@mui/utils';`);
  for (const item of direct) {
    // Use require instead of an ESM default import. CRA/Webpack in this
    // deployment resolves the MUI utility subpath through an export shape
    // that can be interpreted as named-only, producing the observed
    // "does not contain a default export" failure.
    replacement.push(`const ${item.local} = (() => { const m = require('@mui/utils/${item.source}'); return m && m.default ? m.default : m; })();`);
  }
  return replacement.join('\n');
}

function patchDirectImport(match, local, source) {
  return `const ${local} = (() => { const m = require('@mui/utils/${source}'); return m && m.default ? m.default : m; })();`;
}

function patchRequire(match, body) {
  const parts = body.split(',').map((x) => x.trim()).filter(Boolean);
  const direct = [];
  const remaining = [];
  for (const part of parts) {
    const base = part.split(/\s*:\s*/)[0].trim();
    if (TARGETS.includes(base)) direct.push(base);
    else remaining.push(part);
  }
  if (!direct.length) return match;
  const lines = [];
  if (remaining.length) lines.push(`const { ${remaining.join(', ')} } = require('@mui/utils');`);
  for (const name of direct) {
    lines.push(`const ${name} = (() => { const m = require('@mui/utils/${name}'); return m && m.default ? m.default : m; })();`);
  }
  return lines.join('\n');
}

let changed = 0;
for (const file of walk(ROOT)) {
  const before = fs.readFileSync(file, 'utf8');
  const after = before
    .replace(IMPORT_RE, patchRootImport)
    .replace(DIRECT_RE, patchDirectImport)
    .replace(REQUIRE_RE, patchRequire);
  if (after !== before) {
    fs.writeFileSync(file, after);
    changed += 1;
  }
}

console.log(`[CLOUDFLARE-MUI-PATCH] Patched ${changed} installed MUI JS files for CRA/Webpack compatibility.`);
