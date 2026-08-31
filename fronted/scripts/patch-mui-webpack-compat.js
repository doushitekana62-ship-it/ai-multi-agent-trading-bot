const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', 'node_modules', '@mui');
const TARGETS = ['elementAcceptingRef', 'chainPropTypes'];
const IMPORT_RE = /import\s*\{([\s\S]*?)\}\s*from\s*['"]@mui\/utils['"];?/g;
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

function patchImport(match, body) {
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
    replacement.push(`import ${item.source} from '@mui/utils/${item.source}';` + (item.local !== item.source ? `\nconst ${item.local} = ${item.source};` : ''));
  }
  return replacement.join('\n');
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
  for (const name of direct) lines.push(`const ${name} = require('@mui/utils/${name}').default;`);
  return lines.join('\n');
}

let changed = 0;
for (const file of walk(ROOT)) {
  const before = fs.readFileSync(file, 'utf8');
  const after = before.replace(IMPORT_RE, patchImport).replace(REQUIRE_RE, patchRequire);
  if (after !== before) {
    fs.writeFileSync(file, after);
    changed += 1;
  }
}

console.log(`[CLOUDFLARE-MUI-PATCH] Patched ${changed} installed MUI JS files for CRA/Webpack compatibility.`);
