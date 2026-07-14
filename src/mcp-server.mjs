import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

import {
  callCompat,
  callRuntime,
  closeRuntime,
} from './bridge.mjs';
import { tools } from './tool-definitions.mjs';
import { createToolHandler } from './tool-handlers.mjs';


const runtime = { call: callRuntime };
const handleTool = createToolHandler({ runtime, compatCall: callCompat });

const server = new Server(
  {
    name: 'computer-use-fallback-mac',
    version: '0.2.0',
  },
  {
    capabilities: { tools: {} },
  },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;
  return handleTool(name, args);
});

let cleanupStarted = false;

async function cleanup() {
  if (cleanupStarted) return;
  cleanupStarted = true;
  await closeRuntime();
}

function exitAfterCleanup(code) {
  cleanup()
    .catch((error) => console.error('[Computer Use MCP] Cleanup failed:', error))
    .finally(() => process.exit(code));
}

process.on('SIGINT', () => exitAfterCleanup(0));
process.on('SIGTERM', () => exitAfterCleanup(0));
process.on('uncaughtException', (error) => {
  console.error('[Computer Use MCP] Uncaught exception:', error);
  exitAfterCleanup(1);
});
process.on('unhandledRejection', (reason) => {
  console.error('[Computer Use MCP] Unhandled rejection:', reason);
  exitAfterCleanup(1);
});

export async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('[Computer Use MCP] Server connected via stdio');
}
