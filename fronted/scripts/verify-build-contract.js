const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const PACKAGE_JSON = path.join(ROOT, 'package.json');
const pkg = JSON.parse(fs.readFileSync(PACKAGE_JSON, 'utf8'));

function installedVersion(packageName) {
  const packageJson = path.join(ROOT, 'node_modules', ...packageName.split('/'), 'package.json');
  if (!fs.existsSync(packageJson)) {
    throw new Error(`[CLOUDFLARE-BUILD-CONTRACT] Missing installed package: ${packageName}`);
  }
  return JSON.parse(fs.readFileSync(packageJson, 'utf8')).version;
}

const nodeMajor = Number(process.versions.node.split('.')[0]);
if (nodeMajor !== 20) {
  throw new Error(
    `[CLOUDFLARE-BUILD-CONTRACT] Node 20 is required for the frozen CRA 5 deployment baseline; detected Node ${process.versions.node}. Set Cloudflare NODE_VERSION=20.`
  );
}

// MUI 5.17.1 is the frozen public baseline for this CRA 5 / React 18 deployment.
// Do not patch files under node_modules: MUI's published package exports must be
// consumed as-is. Patching individual utility exports caused a repeating cycle of
// chainPropTypes -> elementAcceptingRef -> refType -> HTMLElementType failures.
const expectedMui = {
  '@mui/material': '5.17.1',
  '@mui/icons-material': '5.17.1',
};

for (const [name, expected] of Object.entries(expectedMui)) {
  const actual = installedVersion(name);
  if (actual !== expected) {
    throw new Error(`[CLOUDFLARE-BUILD-CONTRACT] ${name} must be exactly ${expected}; detected ${actual}.`);
  }
}

const patchScript = path.join(__dirname, 'patch-mui-webpack-compat.js');
if (fs.existsSync(patchScript)) {
  throw new Error('[CLOUDFLARE-BUILD-CONTRACT] Forbidden MUI node_modules patch script still exists. Remove it before building.');
}

const verifyScript = path.join(__dirname, 'verify-cloudflare-deps.js');
if (fs.existsSync(verifyScript)) {
  throw new Error('[CLOUDFLARE-BUILD-CONTRACT] Obsolete MUI version-specific verifier still exists. Remove it before building.');
}

if (pkg.scripts && /patch-mui|verify-cloudflare-deps/.test(pkg.scripts.prebuild || '')) {
  throw new Error('[CLOUDFLARE-BUILD-CONTRACT] package.json still invokes the obsolete MUI patch/preflight scripts.');
}

console.log('[CLOUDFLARE-BUILD-CONTRACT] Node 20 verified.');
console.log('[CLOUDFLARE-BUILD-CONTRACT] MUI public baseline 5.17.1 verified.');
console.log('[CLOUDFLARE-BUILD-CONTRACT] No MUI node_modules patching is configured.');
