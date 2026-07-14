import test from 'node:test';
import assert from 'node:assert/strict';

import {
  commandMatchesOwnership,
  selectOwnedProcessIds,
} from '../fixtures/process-ownership.mjs';


test('unique launch token excludes a user process created after the snapshot', () => {
  const executable = '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge';
  const token = '--user-data-dir=/tmp/cu-owned-profile';
  const rows = [
    { pid: 100, command: `${executable} --user-data-dir=/Users/me/Library/Edge` },
    { pid: 101, command: `${executable} ${token} --guest` },
  ];

  assert.deepEqual(selectOwnedProcessIds(rows, executable, new Set(), token), [101]);
  assert.equal(commandMatchesOwnership(rows[0].command, executable, token), false);
  assert.equal(commandMatchesOwnership(rows[1].command, executable, token), true);
  assert.equal(
    commandMatchesOwnership(`${executable} ${token}-different`, executable, token),
    false,
  );
});


test('preexisting matching pid is never claimed', () => {
  const executable = '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge';
  const token = '--user-data-dir=/tmp/cu-owned-profile';
  const rows = [{ pid: 101, command: `${executable} ${token} --guest` }];

  assert.deepEqual(selectOwnedProcessIds(rows, executable, new Set([101]), token), []);
});
