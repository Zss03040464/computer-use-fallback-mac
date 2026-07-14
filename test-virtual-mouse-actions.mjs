import { callHelper } from './src/bridge.mjs';

function samePoint(a, b) {
  return a.x === b.x && a.y === b.y;
}

const TEST_POINTS = {
  move: { x: 810, y: 520 },
  click: { x: 820, y: 530 },
  scroll: { x: 828, y: 538 },
  dragFrom: { x: 836, y: 546 },
  dragTo: { x: 846, y: 556 },
  downUp: { x: 854, y: 564 },
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function stablePhysicalSample() {
  const first = await callHelper('physical_cursor_position');
  await sleep(80);
  const second = await callHelper('physical_cursor_position');
  return { stable: samePoint(first, second), point: second, first, second };
}

async function assertPhysicalStable(label, action) {
  const failures = [];
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const sample = await stablePhysicalSample();
    if (!sample.stable) {
      failures.push(`attempt ${attempt}: ambient movement before action (${sample.first.x}, ${sample.first.y}) -> (${sample.second.x}, ${sample.second.y})`);
      continue;
    }

    const before = sample.point;
    await action();
    await sleep(80);
    const after = await callHelper('physical_cursor_position');
    console.log(`${label} attempt ${attempt}: before=(${before.x}, ${before.y}) after=(${after.x}, ${after.y})`);
    if (samePoint(before, after)) {
      return;
    }
    failures.push(`attempt ${attempt}: after action (${before.x}, ${before.y}) -> (${after.x}, ${after.y})`);
  }

  throw new Error(`${label} moved physical cursor or the physical pointer was not stable:\n${failures.join('\n')}`);
}

async function main() {
  console.log('--- STARTING VIRTUAL MOUSE ACTION TEST ---');

  await assertPhysicalStable('move_mouse', async () => {
    await callHelper('move_mouse', TEST_POINTS.move);
    const virtualPos = await callHelper('cursor_position');
    if (virtualPos.x !== TEST_POINTS.move.x || virtualPos.y !== TEST_POINTS.move.y) {
      throw new Error(`move_mouse did not update virtual cursor: ${JSON.stringify(virtualPos)}`);
    }
  });

  await assertPhysicalStable('click', async () => {
    await callHelper('click', {
      x: TEST_POINTS.click.x,
      y: TEST_POINTS.click.y,
      button: 'left',
      count: 1,
      verify: false,
    });
  });

  await assertPhysicalStable('scroll', async () => {
    await callHelper('scroll', {
      x: TEST_POINTS.scroll.x,
      y: TEST_POINTS.scroll.y,
      deltaX: 0,
      deltaY: -1,
    });
  });

  await assertPhysicalStable('drag', async () => {
    await callHelper('drag', {
      from: TEST_POINTS.dragFrom,
      to: TEST_POINTS.dragTo,
      button: 'left',
    });
  });

  await assertPhysicalStable('mouse_down_up', async () => {
    await callHelper('mouse_down', {
      x: TEST_POINTS.downUp.x,
      y: TEST_POINTS.downUp.y,
      button: 'left',
    });
    await callHelper('mouse_up', {
      x: TEST_POINTS.downUp.x,
      y: TEST_POINTS.downUp.y,
      button: 'left',
    });
  });

  console.log('--- VIRTUAL MOUSE ACTION TEST COMPLETED ---');
}

main().catch((err) => {
  console.error('Virtual mouse action test failed:', err);
  process.exit(1);
});
