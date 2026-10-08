import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const REQUIRED_VERSION = '4.0.4';

/** CVE-2026-33671 / CVE-2026-33672 and related patched ranges per advisory */
const VULNERABLE_VERSIONS = new Set([
  '1.0.0',
  '1.0.1',
  '1.0.2',
  '1.1.0',
  '1.1.1',
  '1.1.2',
  '1.1.3',
  '2.0.0',
  '2.0.1',
  '2.0.2',
  '2.0.3',
  '2.0.4',
  '2.0.5',
  '2.0.6',
  '2.0.7',
  '2.0.8',
  '2.0.9',
  '2.0.10',
  '2.1.0',
  '2.1.1',
  '2.2.0',
  '2.2.1',
  '2.2.2',
  '2.2.3',
  '2.3.0',
  '3.0.0',
  '3.0.1',
  '4.0.0',
  '4.0.1',
  '4.0.2',
  '4.0.3',
]);

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');

function findPicomatchInstalls(baseDir) {
  const installs = [];
  const nm = path.join(baseDir, 'node_modules');
  if (!fs.existsSync(nm)) return installs;

  const walk = (dir) => {
    const pkgPath = path.join(dir, 'package.json');
    if (fs.existsSync(pkgPath)) {
      try {
        const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
        if (pkg.name === 'picomatch') {
          installs.push({ dir, version: pkg.version });
        }
      } catch {
        /* skip */
      }
    }
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const ent of entries) {
      if (!ent.isDirectory() || ent.name === '.bin') continue;
      if (ent.name.startsWith('@')) {
        walk(path.join(dir, ent.name));
      } else if (ent.name === 'node_modules' || ent.name === 'picomatch') {
        walk(path.join(dir, ent.name));
      }
    }
  };

  walk(nm);
  return installs;
}

const installs = findPicomatchInstalls(root);

let hoistedVersion = null;
try {
  const hoistedPkg = path.join(root, 'node_modules', 'picomatch', 'package.json');
  hoistedVersion = JSON.parse(fs.readFileSync(hoistedPkg, 'utf8')).version;
} catch {
  hoistedVersion = null;
}

const vulnerable = installs.filter((i) => VULNERABLE_VERSIONS.has(i.version));
const wrongVersion = installs.filter((i) => i.version !== REQUIRED_VERSION);

if (vulnerable.length) {
  console.error('VULNERABLE picomatch installs:', vulnerable);
  process.exit(1);
}

if (wrongVersion.length) {
  console.error(
    `Expected all picomatch installs to be ${REQUIRED_VERSION}, found:`,
    wrongVersion
  );
  process.exit(1);
}

if (hoistedVersion !== REQUIRED_VERSION) {
  console.error(
    `Hoisted picomatch must be ${REQUIRED_VERSION}, got: ${hoistedVersion}`
  );
  process.exit(1);
}

console.log(
  JSON.stringify({
    ok: true,
    hoistedVersion,
    installCount: installs.length,
    requiredVersion: REQUIRED_VERSION,
  })
);
