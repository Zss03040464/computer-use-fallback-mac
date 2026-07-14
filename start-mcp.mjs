#!/usr/bin/env node
import { main } from './src/mcp-server.mjs';

main().catch((err) => {
  console.error('[Computer Use MCP] Failed to start:', err);
  process.exit(1);
});
