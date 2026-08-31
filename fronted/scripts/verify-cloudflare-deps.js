const fs = require('fs');
const path = require('path');

const REQUIRED_MUI_VERSION = '5.16.6';
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

console.log(`[CLOUDFLARE-DEPS] MUI family verified: all ${MUI_PACKAGES.length} packages are ${REQUIRED_MUI_VERSION}.`);
