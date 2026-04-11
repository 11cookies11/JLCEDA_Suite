import { Buffer } from 'node:buffer';
import { execFile } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

async function readJson(request: http.IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.from(chunk));
  }
  const raw = Buffer.concat(chunks).toString('utf8').trim();
  return raw ? JSON.parse(raw) as unknown : {};
}

function writeJson(response: http.ServerResponse, statusCode: number, body: unknown): void {
  response.statusCode = statusCode;
  response.setHeader('content-type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(body));
}

async function run(): Promise<void> {
  const port = 8796;
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', `http://${request.headers.host ?? '127.0.0.1:8796'}`);
    if (request.method === 'GET' && url.pathname === '/sessions') {
      writeJson(response, 200, {
        sessions: [{
          clientId: 'mock-client',
          pluginVersion: '0.1.26',
          protocolVersion: '0.1.0',
          supportedCommands: [],
          connectedAt: new Date().toISOString(),
          lastSeenAt: new Date().toISOString(),
        }],
      });
      return;
    }

    if (request.method === 'POST' && url.pathname === '/request') {
      const body = await readJson(request) as { request?: { command?: { action?: string } } };
      const action = body.request?.command?.action;
      const results: Record<string, unknown> = {
        get_document_summary: { summary: 'document summary collected', data: { document: { kind: 'schematic' }, project: { name: 'Mock Project' } } },
        get_current_schematic_info: { summary: 'current schematic info collected', data: { name: 'Power Sheet', pageCount: 1 } },
        place_component: { summary: 'schematic component placed', data: { primitiveId: 'cmp-001' } },
        create_wire: { summary: 'schematic wire created', data: { primitiveId: 'wire-001' } },
        annotate_net: { summary: 'schematic net annotated', data: { primitiveId: 'net-001' } },
        save: { summary: 'schematic saved', data: { saved: true } },
      };
      writeJson(response, 200, {
        response: {
          id: 'mock-response',
          type: 'command.response',
          protocolVersion: '0.1.0',
          status: 'success',
          result: results[action || 'save'],
        },
      });
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
    const { stdout } = await execFileAsync(process.execPath, [tsNodeCli, '--files', './scripts/server-schematic-refine.ts'], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        BRIDGE_CONTROL_URL: `http://127.0.0.1:${port}`,
        BRIDGE_TARGET_CLIENT_ID: 'mock-client',
        BRIDGE_SCHEMATIC_EDIT_PLAN_JSON: JSON.stringify([
          { kind: 'place_component', payload: { libraryUuid: 'lib-001', uuid: 'sym-001', position: { x: 100, y: 100 } }, note: 'place regulator' },
          { kind: 'create_wire', payload: { points: [{ x: 100, y: 100 }, { x: 200, y: 100 }], netName: 'VIN' }, note: 'connect input rail' },
          { kind: 'annotate_net', payload: { netName: 'VIN', position: { x: 150, y: 80 } }, note: 'label the net' },
          { kind: 'save' },
        ]),
        BRIDGE_SCHEMATIC_DECISIONS_JSON: JSON.stringify([
          { title: 'power-input', rationale: 'Place the regulator block first', verification: 'Check VIN label and symbol position' },
        ]),
      },
      timeout: 15000,
      maxBuffer: 1024 * 1024,
    });

    if (!stdout.includes('"steps"')) {
      throw new Error('schematic refine should include executed steps');
    }
    if (!stdout.includes('schematic component placed')) {
      throw new Error('schematic refine should execute placement');
    }
    if (!stdout.includes('"validation"')) {
      throw new Error('schematic refine should include validation summary');
    }

    console.log('PASS server schematic refine');
  }
  finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }
}

run().catch((error) => {
  console.error('Server schematic refine smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
