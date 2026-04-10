import { Buffer } from 'node:buffer';
import { execFile } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

async function readJson(request: http.IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  const raw = Buffer.concat(chunks).toString('utf8').trim();
  return raw ? JSON.parse(raw) as unknown : {};
}

function writeJson(response: http.ServerResponse, statusCode: number, body: unknown): void {
  response.statusCode = statusCode;
  response.setHeader('content-type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(body));
}

async function run(): Promise<void> {
  const port = 8795;
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', `http://${request.headers.host ?? '127.0.0.1:8795'}`);
    if (request.method === 'GET' && url.pathname === '/sessions') {
      writeJson(response, 200, { sessions: [{ clientId: 'mock-client', pluginVersion: '0.1.25', protocolVersion: '0.1.0', supportedCommands: [], connectedAt: new Date().toISOString(), lastSeenAt: new Date().toISOString() }] });
      return;
    }
    if (request.method === 'POST' && url.pathname === '/request') {
      const body = await readJson(request) as { request?: { command?: { domain?: string; action?: string } } };
      const command = `${body.request?.command?.domain}.${body.request?.command?.action}`;
      const results: Record<string, unknown> = {
        'project.get_document_summary': { summary: 'document summary collected', data: { document: { kind: 'schematic' }, project: { name: 'Mock Project' } } },
        'project.get_selection_snapshot': { summary: 'selection snapshot collected', data: { documentKind: 'schematic', count: 0, primitives: [] } },
        'schematic.get_current_schematic_info': { summary: 'current schematic info collected', data: { name: 'Power Sheet', pageCount: 1 } },
        'project.get_inventory': { summary: 'inventory collected', data: { count: 12 } },
      };
      writeJson(response, 200, { response: { id: 'mock-response', type: 'command.response', protocolVersion: '0.1.0', status: 'success', result: results[command] } });
      return;
    }
    writeJson(response, 404, { error: 'not_found' });
  });

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve());
  });
  try {
    const tsNodeCli = path.join(process.cwd(), 'node_modules', 'ts-node', 'dist', 'bin.js');
    const { stdout } = await execFileAsync(process.execPath, [tsNodeCli, '--files', './scripts/server-part-selector.ts'], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        BRIDGE_CONTROL_URL: `http://127.0.0.1:${port}`,
        BRIDGE_TARGET_CLIENT_ID: 'mock-client',
        BRIDGE_SELECTION_REQUIREMENTS_JSON: JSON.stringify({ role: 'voltage-regulator', minVoltage: 12, minCurrentMa: 500, preferredPackage: 'SOT-223', maxUnitPrice: 1.5, availabilityPriority: 'high' }),
        BRIDGE_SELECTION_CANDIDATES_JSON: JSON.stringify([
          { name: 'AMS1117-5.0', manufacturer: 'Advanced Monolithic Systems', mfrPartNumber: 'AMS1117-5.0', package: 'SOT-223', voltage: 15, currentMa: 800, unitPrice: 0.12, availability: 'high', lifecycle: 'active' },
          { name: 'LM7805', manufacturer: 'TI', mfrPartNumber: 'LM7805', package: 'TO-220', voltage: 35, currentMa: 1000, unitPrice: 0.8, availability: 'medium', lifecycle: 'active' },
        ]),
      },
      timeout: 15000,
      maxBuffer: 1024 * 1024,
    });

    if (!stdout.includes('"recommendation"'))
      throw new Error('part selector should produce a recommendation');
    if (!stdout.includes('AMS1117-5.0'))
      throw new Error('part selector should rank the matching candidate');
    if (!stdout.includes('"bomNote"'))
      throw new Error('part selector should include a BOM note');
    console.log('PASS server part selector');
  }
  finally {
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
}

run().catch((error) => {
  console.error('Server part selector smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
