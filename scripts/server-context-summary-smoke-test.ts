import type { IncomingMessage, ServerResponse } from 'node:http';
import { Buffer } from 'node:buffer';
import { execFile } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

function writeJson(response: ServerResponse, statusCode: number, body: unknown): void {
  response.statusCode = statusCode;
  response.setHeader('content-type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(body));
}

async function readJsonBody(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.from(chunk));
  }
  const raw = Buffer.concat(chunks).toString('utf8').trim();
  return raw ? JSON.parse(raw) as unknown : {};
}

async function run(): Promise<void> {
  const port = 8794;
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', `http://${request.headers.host ?? '127.0.0.1:8794'}`);

    if (request.method === 'GET' && url.pathname === '/sessions') {
      writeJson(response, 200, {
        sessions: [
          {
            clientId: 'mock-client',
            pluginVersion: '0.1.26',
            protocolVersion: '0.1.0',
            supportedCommands: ['system.get_bridge_status', 'project.get_document_summary'],
            connectedAt: new Date().toISOString(),
            lastSeenAt: new Date().toISOString(),
          },
        ],
        pendingRequests: [],
      });
      return;
    }

    if (request.method === 'GET' && url.pathname === '/debug/session/mock-client') {
      writeJson(response, 200, {
        session: {
          clientId: 'mock-client',
        },
        pendingRequests: [],
        recentRequests: [],
        activeProfile: 'default',
      });
      return;
    }

    if (request.method === 'POST' && url.pathname === '/request') {
      const body = await readJsonBody(request) as {
        request?: { command?: { domain?: string; action?: string } };
      };
      const command = `${body.request?.command?.domain}.${body.request?.command?.action}`;
      const responses: Record<string, unknown> = {
        'system.get_bridge_status': {
          summary: 'bridge status collected',
          data: {
            runtime: {
              isClient: true,
              language: 'zh-CN',
            },
          },
        },
        'project.get_document_summary': {
          summary: 'document summary collected',
          data: {
            document: {
              kind: 'schematic',
            },
            project: {
              name: 'Mock Project',
            },
            selection: {
              count: 0,
            },
          },
        },
        'project.get_selection_snapshot': {
          summary: 'selection snapshot collected',
          data: {
            documentKind: 'schematic',
            count: 0,
            primitives: [],
          },
        },
        'schematic.get_current_schematic_info': {
          summary: 'current schematic info collected',
          data: {
            name: 'Power Sheet',
            pageCount: 1,
          },
        },
      };

      writeJson(response, 200, {
        response: {
          id: 'mock-response',
          type: 'command.response',
          protocolVersion: '0.1.0',
          status: 'success',
          result: responses[command],
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
    const { stdout } = await execFileAsync(process.execPath, [
      tsNodeCli,
      '--files',
      './scripts/server-context-summary.ts',
    ], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        BRIDGE_CONTROL_URL: `http://127.0.0.1:${port}`,
        BRIDGE_TARGET_CLIENT_ID: 'mock-client',
      },
      timeout: 15_000,
      maxBuffer: 1024 * 1024,
    });

    if (!stdout.includes('"clientId": "mock-client"')) {
      throw new Error('Context summary should include the target client id.');
    }
    if (!stdout.includes('"command": "project.get_document_summary"')) {
      throw new Error('Context summary should include the document summary command result.');
    }
    if (!stdout.includes('"suggestedNextSteps"')) {
      throw new Error('Context summary should include suggested next steps.');
    }

    console.log('PASS server context summary');
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
  console.error('Server context summary smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
