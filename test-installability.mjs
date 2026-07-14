import fs from 'node:fs';
import path from 'node:path';

const root = path.dirname(new URL(import.meta.url).pathname);

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), 'utf8');
}

function exists(relativePath) {
  return fs.existsSync(path.join(root, relativePath));
}

for (const file of [
  'package.json',
  'start-mcp.mjs',
  'src/bridge.mjs',
  'src/mcp-server.mjs',
  'src/runtime-worker.mjs',
  'src/compat-worker.mjs',
  'runtime/worker.py',
  'runtime/compat_worker.py',
  'runtime/compat_services/service.py',
  'runtime/cu_runtime/service.py',
  'runtime/cu_runtime/actions.py',
  'runtime/cu_runtime/cursor_feedback.py',
  'runtime/virtual_cursor_overlay.py',
  'runtime/requirements.txt',
  'runtime/requirements.in',
  'tests/packaging/clean-copy-smoke.mjs',
  'tests/packaging/bootstrap-client.mjs',
  'docs/COMPUTER_USE_OPERATION_GUIDE.md',
  'README.md',
  'MCP_INSTALL.md',
]) {
  if (!exists(file)) {
    throw new Error(`Missing installable artifact: ${file}`);
  }
}

const pkg = JSON.parse(read('package.json'));
if (pkg.scripts?.start !== 'node start-mcp.mjs') {
  throw new Error('package.json must expose npm start as node start-mcp.mjs');
}
if (pkg.scripts?.test !== 'npm run test:ci' || !pkg.scripts?.['test:live'] || !pkg.scripts?.['test:clean-install']) {
  throw new Error('package.json must keep real-app live tests explicit and expose the clean-install smoke');
}

const bridge = read('src/bridge.mjs');
if (!bridge.includes('ensureBootstrapped') || !bridge.includes('requirements.txt') || !bridge.includes('venv')) {
  throw new Error('Bridge must bootstrap Python dependencies from runtime/requirements.txt');
}

const requirements = read('runtime/requirements.txt').toLowerCase();
for (const dependency of ['pyobjc-framework-applicationservices', 'pyobjc-framework-cocoa', 'pyobjc-framework-quartz', 'pyobjc-framework-screencapturekit', 'pyobjc-framework-vision', 'pillow']) {
  if (!requirements.includes(dependency)) {
    throw new Error(`runtime/requirements.txt missing ${dependency}`);
  }
}
if (requirements.includes('pyautogui') || requirements.includes('mss')) {
  throw new Error('runtime/requirements.txt must not include global-input or unused desktop-capture dependencies');
}
if (!requirements.includes('--hash=sha256:') || !bridge.includes("'--require-hashes'")) {
  throw new Error('Python bootstrap must install the hash-verified dependency lock');
}
if (bridge.includes("'--upgrade', 'pip'")) {
  throw new Error('Bootstrap must not replace pip with an unpinned network version');
}

const installDoc = read('MCP_INSTALL.md');
for (const phrase of [
  'Generic MCP stdio configuration',
  'Verify the tool surface',
  'virtual_cursor_overlay',
  'test:unit',
  'test:integration',
  'test:live',
  'test:overlay-style',
  'test:all',
]) {
  if (!installDoc.includes(phrase)) {
    throw new Error(`MCP_INSTALL.md missing required phrase: ${phrase}`);
  }
}

const readme = read('README.md');
if (!readme.includes('MCP_INSTALL.md') || !readme.includes('cursorFeedback')) {
  throw new Error('README.md must document installation and virtual cursor feedback');
}

const operationGuide = read('docs/COMPUTER_USE_OPERATION_GUIDE.md');
for (const phrase of ['Coordinate Pitfalls', 'App-targeted control model', 'Virtual mouse']) {
  if (!operationGuide.includes(phrase)) {
    throw new Error(`Operation guide missing required phrase: ${phrase}`);
  }
}

console.log('Installability guard: PASS');
