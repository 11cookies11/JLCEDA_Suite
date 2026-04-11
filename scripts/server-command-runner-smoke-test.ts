import type { IncomingMessage, ServerResponse } from 'node:http';
import { Buffer } from 'node:buffer';
import { execFile } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
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
  const commands: string[] = [];
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
      const command = `${body.request.command.domain}.${body.request.command.action}`;
      commands.push(command);
      writeJson(response, 200, {
        response: {
          id: 'mock-response',
          type: 'command.response',
          protocolVersion: '0.1.0',
          status: 'success',
          result: {
            summary: 'mock',
            data: {
              command,
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

  try {
    const tsNodeCli = path.join(process.cwd(), 'node_modules', 'ts-node', 'dist', 'bin.js');
    const { stdout } = await execFileAsync(process.execPath, [
      tsNodeCli,
      '--files',
      './scripts/server-command-runner.ts',
    ], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        BRIDGE_CONTROL_URL: 'http://127.0.0.1:8791',
        BRIDGE_RUNNER_TEMPLATE: 'pcb',
        BRIDGE_RUNNER_TEMPLATE_INPUT_JSON: JSON.stringify({
          componentClearance: 120,
          trackClearance: 70,
          labelClearance: 90,
          boardEdgeClearance: 60,
          maxIssues: 8,
        }),
      },
      timeout: 15_000,
      maxBuffer: 1024 * 1024,
    });

    const expected = [
      'project.get_document_summary',
      'schematic.get_current_schematic_info',
      'pcb.get_board_summary',
      'pcb.get_current_pcb_info',
      'pcb.inspect_layout_hygiene',
      'pcb.get_calculating_ratline_status',
    ];

    for (const command of expected) {
      if (!commands.includes(command)) {
        throw new Error(`Runner template did not execute expected command: ${command}`);
      }
    }

    if (!stdout.includes('"mode": "template"')) {
      throw new Error('Runner template output should include template mode.');
    }
    if (!stdout.includes('"template": "pcb"')) {
      throw new Error('Runner template output should include template name.');
    }
    if (!stdout.includes('"totalCommands": 6')) {
      throw new Error('Runner template output should summarize command count.');
    }

    console.log('PASS server command runner');
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
  console.error('Server command runner smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
