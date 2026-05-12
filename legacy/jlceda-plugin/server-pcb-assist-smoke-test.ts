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
  const port = 8797;
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', `http://${request.headers.host ?? '127.0.0.1:8797'}`);
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
        get_document_summary: { summary: 'document summary collected', data: { document: { kind: 'pcb' }, project: { name: 'Mock Project' } } },
        get_current_schematic_info: { summary: 'current schematic info collected', data: { name: 'Power Sheet', pageCount: 2 } },
        get_board_summary: { summary: 'board summary collected', data: { boardCount: 1, boards: [{ name: 'Main Board', outline: { width: 48, height: 32 } }] } },
        get_current_pcb_info: { summary: 'current pcb info collected', data: { name: 'Main Board', layerCount: 2, activeLayer: 'TopLayer' } },
        inspect_layout_hygiene: {
          summary: 'pcb hygiene collected',
          data: {
            diagnostics: {
              issueCount: 2,
              issues: [
                { type: 'component_component_proximity', severity: 'warning', designator: 'U1', relatedDesignator: 'C3', message: 'U1 is too close to C3' },
                { type: 'board_edge_component_proximity', severity: 'warning', designator: 'J1', message: 'J1 is too close to the board edge' },
              ],
            },
          },
        },
        get_calculating_ratline_status: { summary: 'ratline status collected', data: { active: false } },
      };
      writeJson(response, 200, {
        response: {
          id: 'mock-response',
          type: 'command.response',
          protocolVersion: '0.1.0',
          status: 'success',
          result: results[action || 'get_document_summary'],
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
    const { stdout } = await execFileAsync(process.execPath, [tsNodeCli, '--files', './scripts/server-pcb-assist.ts'], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        BRIDGE_CONTROL_URL: `http://127.0.0.1:${port}`,
        BRIDGE_TARGET_CLIENT_ID: 'mock-client',
        BRIDGE_PCB_ASSIST_OPTIONS_JSON: JSON.stringify({
          focusAreas: ['power-input', 'interface-edge'],
          goals: ['keep analog and switching loops compact'],
          componentClearance: 120,
          trackClearance: 70,
          boardEdgeClearance: 60,
          maxIssues: 8,
        }),
      },
      timeout: 15000,
      maxBuffer: 1024 * 1024,
    });

    if (!stdout.includes('"layoutAdvice"')) {
      throw new Error('pcb assist should include layout advice');
    }
    if (!stdout.includes('"nextTasks"')) {
      throw new Error('pcb assist should include next tasks');
    }
    if (!stdout.includes('component_component_proximity')) {
      throw new Error('pcb assist should include hygiene issue types');
    }

    console.log('PASS server pcb assist');
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
  console.error('Server pcb assist smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
