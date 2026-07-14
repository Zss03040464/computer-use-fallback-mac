import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';


const root = path.resolve(import.meta.dirname, '../..');


test('stdio MCP handshake lists and calls the app-targeted tools', { timeout: 120_000 }, async (t) => {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [path.join(root, 'start-mcp.mjs')],
    cwd: root,
    stderr: 'pipe',
  });
  const client = new Client({ name: 'computer-use-transport-test', version: '1.0.0' });
  t.after(async () => {
    await client.close();
  });

  await client.connect(transport);
  const listed = await client.listTools();
  const names = new Set(listed.tools.map((tool) => tool.name));
  for (const required of ['list_apps', 'get_app_state', 'click', 'drag', 'scroll']) {
    assert.equal(names.has(required), true, `missing MCP tool ${required}`);
  }

  const response = await client.callTool({ name: 'list_apps', arguments: {} });
  assert.equal(response.isError, undefined);
  assert.equal(response.content[0].type, 'text');
  const apps = JSON.parse(response.content[0].text);
  assert.equal(Array.isArray(apps), true);
  assert.equal(apps.some((app) => app.bundleId && app.displayName), true);
});
