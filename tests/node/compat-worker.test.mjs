import assert from 'node:assert/strict';
import { readdir, readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';

import { CompatWorker } from '../../src/compat-worker.mjs';


const root = path.resolve(import.meta.dirname, '../..');

async function textFilesUnder(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (['__pycache__', '.venv'].includes(entry.name)) continue;
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await textFilesUnder(absolute));
    else if ((await stat(absolute)).size < 2_000_000) files.push(absolute);
  }
  return files;
}

test('compatibility worker is persistent and returns structured unknown-command errors', async (t) => {
  const worker = new CompatWorker();
  t.after(async () => worker.close());

  const first = await worker.call('check_permissions', {});
  const second = await worker.call('check_permissions', {});
  assert.equal(typeof first.accessibility, 'boolean');
  assert.equal(typeof first.screenRecording, 'boolean');
  assert.deepEqual(second, first);
  assert.ok(worker.pid > 0);

  await assert.rejects(
    worker.call('not_a_compat_command', {}),
    (error) => error.code === 'unknown_command' && error.details.command === 'not_a_compat_command',
  );
});

test('clipboard payload is not persisted or emitted by compatibility worker', async (t) => {
  const worker = new CompatWorker();
  const secret = `SENTINEL-compat-${process.pid}-${Date.now()}`;
  let original;
  t.after(async () => {
    if (typeof original === 'string') await worker.call('write_clipboard', { text: original });
    await worker.close();
  });
  original = await worker.call('read_clipboard', {});

  assert.deepEqual(await worker.call('write_clipboard', { text: secret }), { written: true });
  assert.equal(await worker.call('read_clipboard', {}), secret);
  assert.equal(worker.stderr.includes(secret), false);

  for (const file of await textFilesUnder(path.join(root, 'runtime'))) {
    const content = await readFile(file, 'utf8').catch(() => '');
    assert.equal(content.includes(secret), false, `sensitive payload persisted in ${file}`);
  }
});
