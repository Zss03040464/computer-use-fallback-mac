import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { isDeepStrictEqual } from 'node:util';
import path from 'node:path';


const root = path.resolve(import.meta.dirname, '../..');
const python = path.join(root, '.venv', 'bin', 'python3');
const snapshotScript = path.join(import.meta.dirname, 'input_activity_snapshot.py');


export async function startInputActivityMonitor() {
  const child = spawn(python, [snapshotScript], {
    cwd: root,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  let stdoutBuffer = '';
  let stderr = '';
  let summary;
  let resetResolve;
  let resetReject;
  let readyResolve;
  let readyReject;
  const ready = new Promise((resolve, reject) => {
    readyResolve = resolve;
    readyReject = reject;
  });
  const timeout = setTimeout(() => readyReject(new Error('Input activity monitor did not become ready')), 3000);

  child.stderr.on('data', (chunk) => { stderr += chunk; });
  child.stdout.on('data', (chunk) => {
    stdoutBuffer += chunk;
    const lines = stdoutBuffer.split('\n');
    stdoutBuffer = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      const message = JSON.parse(line);
      if (message.ready) readyResolve();
      if (message.reset && resetResolve) {
        resetResolve();
        resetResolve = undefined;
        resetReject = undefined;
      }
      if (message.summary) summary = message.summary;
    }
  });
  child.once('exit', (code, signal) => {
    if (!summary) {
      readyReject(new Error(`Input activity monitor exited before reporting: code=${code}, signal=${signal}, stderr=${stderr}`));
    }
  });

  try {
    await ready;
  } catch (error) {
    child.kill('SIGTERM');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
  let stopPromise;
  return {
    reset() {
      if (stopPromise) return Promise.reject(new Error('Input activity monitor is already stopping'));
      if (resetResolve) return Promise.reject(new Error('Input activity monitor reset is already pending'));
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          resetResolve = undefined;
          resetReject = undefined;
          reject(new Error('Input activity monitor reset timed out'));
        }, 1000);
        resetResolve = () => {
          clearTimeout(timeout);
          resolve();
        };
        resetReject = reject;
        if (!child.kill('SIGUSR1')) {
          clearTimeout(timeout);
          resetResolve = undefined;
          resetReject = undefined;
          reject(new Error('Input activity monitor reset signal failed'));
        }
      });
    },
    stop() {
      if (stopPromise) return stopPromise;
      stopPromise = new Promise((resolve, reject) => {
        if (child.exitCode !== null) {
          reject(new Error(`Input activity monitor exited early: code=${child.exitCode}, stderr=${stderr}`));
          return;
        }
        child.once('exit', (code, signal) => {
          if (resetReject) resetReject(new Error('Input activity monitor exited during reset'));
          if (code !== 0 || !summary) {
            reject(new Error(`Input activity monitor failed: code=${code}, signal=${signal}, stderr=${stderr}`));
            return;
          }
          resolve(summary);
        });
        child.kill('SIGTERM');
      });
      return stopPromise;
    },
  };
}


export function assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity) {
  assert.equal(
    activity.nonHidMouseMoves,
    0,
    `non-HID mouse movement was observed: ${activity.nonHidMouseMoves}`,
  );
  if (!isDeepStrictEqual(pointerAfter, pointerBefore)) {
    assert.ok(
      activity.hidMouseMoves > 0,
      `physical pointer changed without HID movement: before=${JSON.stringify(pointerBefore)}, after=${JSON.stringify(pointerAfter)}`,
    );
  }
}


export function assertFocusIsolation(
  frontmostBefore,
  frontmostAfter,
  activity,
  protectedPids = [],
) {
  const transitions = Array.isArray(activity.focusTransitions)
    ? activity.focusTransitions
    : [];
  const protectedTransition = transitions.find((item) => protectedPids.includes(item?.pid));
  assert.equal(
    protectedTransition,
    undefined,
    `protected application became frontmost: ${JSON.stringify(protectedTransition)}`,
  );
  assert.equal(
    protectedPids.includes(frontmostAfter?.pid),
    false,
    `protected application became frontmost: ${JSON.stringify(frontmostAfter)}`,
  );
  const unattributed = transitions.filter((item) => !item?.hidAttributed);
  assert.deepEqual(
    unattributed,
    [],
    `unattributed focus transition: ${JSON.stringify(unattributed)}`,
  );
  if (isDeepStrictEqual(frontmostAfter, frontmostBefore)) return;
  assert.ok(
    activity.hidActivationEvents > 0,
    `frontmost changed without physical activation: before=${JSON.stringify(frontmostBefore)}, after=${JSON.stringify(frontmostAfter)}`,
  );
}
