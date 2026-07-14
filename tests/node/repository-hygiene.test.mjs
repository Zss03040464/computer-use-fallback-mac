import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { access, readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

function trackedFiles() {
  return execFileSync('git', ['ls-files', '-z'], {
    cwd: projectRoot,
    encoding: 'utf8',
  }).split('\0').filter(Boolean);
}

function isLocalOnly(file) {
  return [
    /^\.agent_state(?:\/|$)/,
    /^AGENT_HANDOFF\.md$/,
    /^NEXT_AGENT_HANDOFF\.md$/,
    /^PROJECT_HISTORY\.md$/,
    /^USER_DIALOGUE\.md$/,
    /^logs\/agent_sessions(?:\/|$)/,
    /^docs\/superpowers(?:\/|$)/,
  ].some((pattern) => pattern.test(file));
}

function isSensitivePath(file) {
  const base = path.basename(file).toLowerCase();
  return base === '.env'
    || base === 'auth.json'
    || /\.(?:key|pem|p12|pfx)$/.test(base);
}

const secretPatterns = [
  /-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/,
  /\bgh[pousr]_[A-Za-z0-9]{36,255}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{40,255}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/,
];

test('tracked publication tree follows repository hygiene contract', async () => {
  const files = trackedFiles();
  const requiredFiles = [
    '.editorconfig',
    '.gitattributes',
    '.github/dependabot.yml',
    '.github/workflows/ci.yml',
    'CHANGELOG.md',
    'CODE_OF_CONDUCT.md',
    'CONTRIBUTING.md',
    'LICENSE',
    'NOTICE',
    'README.md',
    'SECURITY.md',
  ];

  for (const file of requiredFiles) {
    assert.ok(files.includes(file), `required repository file is not tracked: ${file}`);
  }

  const localOnlyFiles = files.filter(isLocalOnly);
  assert.deepEqual(localOnlyFiles, [], `local-only files are tracked:\n${localOnlyFiles.join('\n')}`);

  const sensitiveFiles = files.filter(isSensitivePath);
  assert.deepEqual(sensitiveFiles, [], `credential-bearing path is tracked:\n${sensitiveFiles.join('\n')}`);

  const privateHomePrefix = ['', 'Users', 'vivian', ''].join('/');
  const findings = [];
  for (const file of files) {
    const buffer = await readFile(path.join(projectRoot, file));
    if (buffer.includes(0)) continue;
    const text = buffer.toString('utf8');
    if (text.includes(privateHomePrefix)) findings.push(`${file}: private absolute path`);
    for (const pattern of secretPatterns) {
      if (pattern.test(text)) findings.push(`${file}: credential signature ${pattern.source}`);
    }
  }
  assert.deepEqual(findings, [], `tracked content contains private material:\n${findings.join('\n')}`);

  const packageJson = JSON.parse(await readFile(path.join(projectRoot, 'package.json'), 'utf8'));
  assert.equal(packageJson.private, true, 'package must remain non-publishable to npm');
  assert.equal(packageJson.license, 'MIT');
  assert.equal(packageJson.engines?.node, '>=20');
  assert.equal(
    packageJson.repository?.url,
    'git+https://github.com/Zss03040464/computer-use-fallback-mac.git',
  );
  assert.equal(packageJson.bugs?.url, 'https://github.com/Zss03040464/computer-use-fallback-mac/issues');
  assert.equal(packageJson.homepage, 'https://github.com/Zss03040464/computer-use-fallback-mac#readme');
});

test('tracked Markdown uses valid repository-relative links', async () => {
  const brokenLinks = [];
  for (const file of trackedFiles().filter((candidate) => candidate.endsWith('.md'))) {
    const text = await readFile(path.join(projectRoot, file), 'utf8');
    for (const match of text.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      const target = match[1].trim().replace(/^<|>$/g, '');
      if (/^(?:[a-z]+:|#)/i.test(target)) continue;
      const relativePath = decodeURIComponent(target.split('#', 1)[0]);
      try {
        await access(path.resolve(projectRoot, path.dirname(file), relativePath));
      } catch {
        brokenLinks.push(`${file} -> ${target}`);
      }
    }
  }
  assert.deepEqual(brokenLinks, [], `broken repository-relative links:\n${brokenLinks.join('\n')}`);
});
