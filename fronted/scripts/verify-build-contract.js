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

// CRA 5 + React 18 must use the pre-module-conversion MUI 5.14 dependency graph.
// MUI 5.15.7 introduced utility module/export changes; later MUI 5.x versions
// repeatedly triggered CRA/Webpack default-export failures for chainPropTypes,
// elementAcceptingRef, refType and HTMLElementType in this deployment.
const expectedMui = {
  '@mui/material': '5.14.0',
  '@mui/icons-material': '5.14.0',
  '@mui/system': '5.14.0',
  '@mui/utils': '5.13.7',
  '@mui/private-theming': '5.13.7',
  '@mui/styled-engine': '5.13.2',
  '@mui/core-downloads-tracker': '5.14.0',
  '@mui/types': '7.2.4',
  '@mui/base': '5.0.0-beta.7',
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
console.log('[CLOUDFLARE-BUILD-CONTRACT] Frozen MUI 5.14 CRA compatibility graph verified.');
console.log('[CLOUDFLARE-BUILD-CONTRACT] No MUI node_modules patching is configured.');
