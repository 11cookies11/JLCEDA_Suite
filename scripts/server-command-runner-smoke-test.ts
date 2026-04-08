import type { IncomingMessage, ServerResponse } from 'node:http';
import { Buffer } from 'node:buffer';
import { execFile } from 'node:child_process';
import http from 'node:http';
import process from 'node:process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

interface ControlSessionsResponse {
  sessions: Array<{
    clientId: string;
    pluginVersion: string;
    protocolVersion: string;
    supportedCommands: Array<string>;
    connectedAt: string;
    lastSeenAt: string;
  }>;
}

interface ControlRequestBody {
  clientId: string;
  request: {
    command: {
      domain: string;
      action: string;
    };
  };
}

function readJsonBody(request: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];

    request.on('data', (chunk) => {
      chunks.push(Buffer.from(chunk));
    });

    request.on('end', () => {
      const rawBody = Buffer.concat(chunks).toString('utf8');

      if (!rawBody.trim()) {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(rawBody) as unknown);
      }
      catch (error) {
        reject(error);
      }
    });

    request.on('error', reject);
  });
}

function writeJson(response: ServerResponse, statusCode: number, body: unknown): void {
  response.statusCode = statusCode;
  response.setHeader('content-type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(body));
}

async function run(): Promise<void> {
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', `http://${request.headers.host ?? '127.0.0.1:8791'}`);

    if (request.method === 'GET' && url.pathname === '/sessions') {
      const payload: ControlSessionsResponse = {
        sessions: [
          {
            clientId: 'mock-client',
            pluginVersion: '0.1.0',
            protocolVersion: '0.1.0',
            supportedCommands: ['system.get_bridge_status'],
            connectedAt: new Date().toISOString(),
            lastSeenAt: new Date().toISOString(),
          },
        ],
      };
      writeJson(response, 200, payload);
      return;
    }

    if (request.method === 'POST' && url.pathname === '/request') {
      const body = (await readJsonBody(request)) as ControlRequestBody;
      writeJson(response, 200, {
        response: {
          id: 'mock-response',
          type: 'command.response',
          protocolVersion: '0.1.0',
          status: 'success',
          result: {
            summary: 'mock',
            data: {
              command: `${body.request.command.domain}.${body.request.command.action}`,
            },
          },
        },
      });
      return;
    }

    writeJson(response, 404, { error: 'not_found' });
  });

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(8791, '127.0.0.1', () => resolve());
  });

  const { stdout } = await execFileAsync('npx', [
    'ts-node',
    '--files',
    './scripts/server-command-runner.ts',
  ], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      BRIDGE_CONTROL_URL: 'http://127.0.0.1:8791',
      BRIDGE_COMMANDS_JSON: JSON.stringify({
        clientId: 'mock-client',
        requests: [
          {
            id: 'mock-step-001',
            domain: 'system',
            action: 'get_bridge_status',
            payload: {},
            requiresConfirmation: false,
          },
        ],
      }),
    },
    timeout: 15_000,
    maxBuffer: 1024 * 1024,
  });

  if (!stdout.includes('"command": "system.get_bridge_status"')) {
    throw new Error('Runner smoke test did not execute the expected command.');
  }

  console.log('PASS server command runner');
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

run().catch((error) => {
  console.error('Server command runner smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
