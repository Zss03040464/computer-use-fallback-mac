import { spawn } from 'node:child_process';

console.log('--- STARTING MCP CONNECTION HANDSHAKE TEST ---');

const mcp = spawn('node', ['start-mcp.mjs']);

let receivedData = '';
let testTimeout = setTimeout(() => {
  console.error('Test failed: Timeout waiting for MCP handshake response.');
  mcp.kill();
  process.exit(1);
}, 5000);

mcp.stdout.on('data', (data) => {
  receivedData += data.toString();
  console.log(`[MCP Out]: ${data.toString().trim()}`);

  if (receivedData.includes('jsonrpc') && receivedData.includes('result')) {
    console.log('\nSUCCESS: MCP Handshake Completed successfully!');
    clearTimeout(testTimeout);
    mcp.kill();
    process.exit(0);
  }
});

mcp.stderr.on('data', (data) => {
  console.log(`[MCP Err/Log]: ${data.toString().trim()}`);
});

mcp.on('close', (code) => {
  console.log(`MCP Server exited with code: ${code}`);
});

// Write standard MCP initialize request
const initRequest = {
  jsonrpc: '2.0',
  id: 1,
  method: 'initialize',
  params: {
    protocolVersion: '2024-11-05',
    capabilities: {},
    clientInfo: { name: 'mcp-test-client', version: '1.0.0' }
  }
};

console.log(`[MCP In]: Sending initialize request...`);
mcp.stdin.write(JSON.stringify(initRequest) + '\n');
