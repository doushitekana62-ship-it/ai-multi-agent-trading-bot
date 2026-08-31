const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', 'node_modules', '@mui');

// Cloudflare CRA/Webpack repeatedly rejects MUI v5 utility exports when a
// utility subpath is resolved as named-only. Do not chase individual names.
// Normalize every static default import from @mui/utils/*.
const ROOT_IMPORT_RE = /import\s*\{([\s\S]*?)\}\s*from\s*['"]@mui\/utils['"];?/g;
const DEFAULT_SUBPATH_RE = /import\s+([A-Za-z_$][\w$]*)\s+from\s*['"]@mui\/utils\/([^'"\s]+)['"];?/g;

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

function patchRootImport(match) {
  // Root named imports are valid MUI APIs. Leave them unchanged; only the
  // problematic default subpath form is normalized below.
  return match;
}

function patchDefaultSubpathImport(match, local, source) {
  return runtimeRequire(local, source);
}

let changed = 0;
for (const file of walk(ROOT)) {
  const before = fs.readFileSync(file, 'utf8');
  const after = before
    .replace(ROOT_IMPORT_RE, patchRootImport)
    .replace(DEFAULT_SUBPATH_RE, patchDefaultSubpathImport);
  if (after !== before) {
    fs.writeFileSync(file, after);
    changed += 1;
  }
}

console.log(`[CLOUDFLARE-MUI-PATCH] Patched ${changed} installed MUI JS files for CRA/Webpack compatibility.`);
