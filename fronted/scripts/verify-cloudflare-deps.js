const fs = require('fs');
const path = require('path');

const REQUIRED_PUBLIC_MUI_VERSION = '5.17.1';
const PUBLIC_MUI_PACKAGES = ['@mui/material', '@mui/icons-material'];
const INTERNAL_MUI_PACKAGES = [
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

const publicVersions = Object.fromEntries(
  PUBLIC_MUI_PACKAGES.map((name) => [name, readInstalledVersion(name)])
);
const internalVersions = Object.fromEntries(
  INTERNAL_MUI_PACKAGES.map((name) => [name, readInstalledVersion(name)])
);

const publicMismatches = Object.entries(publicVersions).filter(
  ([, version]) => version !== REQUIRED_PUBLIC_MUI_VERSION
);
if (publicMismatches.length > 0) {
  console.error('[CLOUDFLARE-DEPS] Public MUI packages must be exactly 5.17.1.');
  for (const [name, version] of Object.entries(publicVersions)) {
    console.error(`  ${name}: ${version} (required ${REQUIRED_PUBLIC_MUI_VERSION})`);
  }
  process.exit(1);
}

const internalMajorMismatches = Object.entries(internalVersions).filter(
  ([, version]) => !/^5\./.test(version)
);
if (internalMajorMismatches.length > 0) {
  console.error('[CLOUDFLARE-DEPS] MUI internal packages must remain on the MUI v5 line.');
  for (const [name, version] of Object.entries(internalVersions)) {
    console.error(`  ${name}: ${version}`);
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

console.log(`[CLOUDFLARE-DEPS] Public MUI packages verified at ${REQUIRED_PUBLIC_MUI_VERSION}.`);
console.log('[CLOUDFLARE-DEPS] Internal MUI packages verified on v5.');
console.log('[CLOUDFLARE-DEPS] CRA/Webpack MUI utility import compatibility check passed.');
