// Offline protocol fixture: no real device, network, credentials or shell access.
import readline from 'node:readline';
import { writeFileSync } from 'node:fs';

const marker = process.argv[2];
const tools = [
  { name: 'mobile_list_available_devices', description: 'List the offline fixture device.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'mobile_launch_app', description: 'Simulated app launch. Does not control a real phone.', inputSchema: { type: 'object', properties: { device: { type: 'string' }, packageName: { type: 'string' } }, required: ['device', 'packageName'], additionalProperties: false } },
];

for await (const line of readline.createInterface({ input: process.stdin })) {
  const request = JSON.parse(line);
  if (request.id === undefined) continue;
  let result = {};
  if (request.method === 'initialize') {
    result = { protocolVersion: request.params.protocolVersion, capabilities: { tools: {} }, serverInfo: { name: 'offline-phone-fixture', version: '1' }, instructions: 'These are offline test tools. List available devices, then use only fixture-phone. No real device or paid fleet is available.' };
  } else if (request.method === 'tools/list') result = { tools };
  else if (request.method === 'tools/call') {
    if (request.params.name === 'mobile_list_available_devices') {
      result = { content: [{ type: 'text', text: JSON.stringify({ devices: [{ id: 'fixture-phone', name: 'Offline test phone', platform: 'ios', type: 'simulator', state: 'online' }] }) }] };
    } else if (request.params.name === 'mobile_launch_app') {
      writeFileSync(marker, 'simulated-launch-executed');
      result = { content: [{ type: 'text', text: 'Simulated app launch completed.' }] };
    }
  }
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: request.id, result }) + '\n');
}
