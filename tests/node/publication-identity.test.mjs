import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve(import.meta.dirname, '../..');

function trackedFiles() {
  return execFileSync('git', ['ls-files', '-z'], {
    cwd: root,
    encoding: 'utf8',
  }).split('\0').filter((file) => file && existsSync(path.join(root, file)));
}

test('publication presents one independently developed repository identity', async () => {
  const read = (file) => readFile(path.join(root, file), 'utf8');
  const [readme, notice, provenance] = await Promise.all([
    read('README.md'),
    read('NOTICE'),
    read('PROVENANCE.md'),
  ]);

  assert.match(readme, /由本仓库独立设计并实现/);
  assert.match(
    notice,
    /Project-specific source code, tests, documentation and cursor artwork are independently developed/,
  );
  assert.match(provenance, /^# Source Ownership/m);
  assert.match(provenance, /All project-specific production source code/);
});

test('publication contains stable product knowledge instead of internal process records', () => {
  const requiredKnowledge = [
    'knowledge/architecture/app-targeted-runtime.md',
    'knowledge/architecture/compatibility-runtime.md',
    'knowledge/features/virtual-cursor-feedback.md',
    'knowledge/quality/background-control-verification.md',
  ];
  for (const file of requiredKnowledge) {
    assert.equal(existsSync(path.join(root, file)), true, `stable knowledge is missing: ${file}`);
  }

  const historicalProcessFiles = trackedFiles().filter((file) => (
    file.startsWith('knowledge/tasks/')
    || file.startsWith('knowledge/plans/')
    || file.startsWith('knowledge/incidents/')
  ));
  assert.deepEqual(
    historicalProcessFiles,
    [],
    'internal task, plan, or incident records remain in the publication tree',
  );
});
