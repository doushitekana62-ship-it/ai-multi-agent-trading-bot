const fs = require('fs');
const path = require('path');

const REQUIRED_MUI_VERSION = '5.17.1';
const MUI_PACKAGES = [
  '@mui/material',
  '@mui/icons-material',
  '@mui/core-downloads-tracker',
  '@mui/private-theming',
  '@mui/styled-engine',
  '@mui/system',
  '@mui/utils',
];

function readInstalledVersion(packageName) {
  const packageJson = path.join(__dirname, '..', 'node_modules', ...packageName.split('/'), 'package.json');
  if (!fs.existsSync(packageJson)) {
    throw new Error(`[CLOUDFLARE-DEPS] Missing installed package: ${packageName}`);
  }
  return JSON.parse(fs.readFileSync(packageJson, 'utf8')).version;
}

const versions = Object.fromEntries(
  MUI_PACKAGES.map((name) => [name, readInstalledVersion(name)])
);

const mismatches = Object.entries(versions).filter(([, version]) => version !== REQUIRED_MUI_VERSION);

if (mismatches.length > 0) {
  console.error('[CLOUDFLARE-DEPS] MUI dependency family mismatch detected.');
  for (const [name, version] of Object.entries(versions)) {
    console.error(`  ${name}: ${version} (required ${REQUIRED_MUI_VERSION})`);
  }
  process.exit(1);
}

const forbiddenRootImports = [];
const muiRoot = path.join(__dirname, '..', 'node_modules', '@mui');

function scan(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) scan(full);
    else if (entry.isFile() && full.endsWith('.js') && !full.endsWith('.map')) {
      const source = fs.readFileSync(full, 'utf8');
      if (/import\s*\{[^}]*\b(elementAcceptingRef|chainPropTypes)\b[^}]*\}\s*from\s*['"]@mui\/utils['"]/.test(source)) {
        forbiddenRootImports.push(full);
      }
    }
  }
}

scan(muiRoot);

if (forbiddenRootImports.length > 0) {
  console.error('[CLOUDFLARE-DEPS] Unpatched MUI root utility imports remain after compatibility patch.');
  for (const file of forbiddenRootImports) console.error(`  ${file}`);
  process.exit(1);
}

console.log(`[CLOUDFLARE-DEPS] MUI family verified: all ${MUI_PACKAGES.length} packages are ${REQUIRED_MUI_VERSION}.`);
console.log('[CLOUDFLARE-DEPS] CRA/Webpack MUI utility import compatibility check passed.');
