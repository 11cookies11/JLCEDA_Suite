import type { ChildProcess } from 'node:child_process';
import { spawn } from 'node:child_process';
import process from 'node:process';

export interface PythonBridgeServerRuntime {
  process: ChildProcess;
  stdoutChunks: string[];
  stderrChunks: string[];
  exitPromise: Promise<number>;
}

export interface PythonBridgeServerOptions {
  bridgePort: number;
  controlPort: number;
  host: string;
  token: string;
  controlToken?: string;
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export function spawnPythonBridgeServer(options: PythonBridgeServerOptions): PythonBridgeServerRuntime {
  const serverProcess = spawn('python3', ['./scripts/python_bridge_server.py'], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      BRIDGE_SERVER_HOST: options.host,
      BRIDGE_SERVER_PORT: String(options.bridgePort),
      BRIDGE_SERVER_CONTROL_HOST: options.host,
      BRIDGE_SERVER_CONTROL_PORT: String(options.controlPort),
      BRIDGE_SERVER_TOKEN: options.token,
      BRIDGE_SERVER_CONTROL_TOKEN: options.controlToken ?? options.token,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  const stdoutChunks: string[] = [];
  const stderrChunks: string[] = [];
  serverProcess.stdout?.on('data', chunk => stdoutChunks.push(String(chunk)));
  serverProcess.stderr?.on('data', chunk => stderrChunks.push(String(chunk)));

  const exitPromise = new Promise<number>((resolve, reject) => {
    serverProcess.once('exit', (code) => {
      if (code === null) {
        reject(new Error('Python server exited unexpectedly.'));
        return;
      }

      resolve(code);
    });
    serverProcess.once('error', reject);
  });

  return {
    process: serverProcess,
    stdoutChunks,
    stderrChunks,
    exitPromise,
  };
}

export async function waitForHealth(url: string, token: string, timeoutMs = 60_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, {
        headers: {
          ...(token ? { 'x-bridge-control-token': token } : {}),
        },
      });
      if (response.ok) {
        return;
      }
    }
    catch {
      // Retry until the server is ready.
    }
    await sleep(250);
  }

  throw new Error(`Timed out waiting for server health at ${url}.`);
}

export async function postJson<TResponse>(url: string, body: unknown, token: string): Promise<TResponse> {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(token ? { 'x-bridge-control-token': token } : {}),
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`Control request failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as TResponse;
}

export async function stopPythonBridgeServer(server: PythonBridgeServerRuntime): Promise<void> {
  try {
    server.process.kill('SIGTERM');
  }
  catch {
    // Ignore shutdown races.
  }

  await server.exitPromise.catch(() => undefined);
}

export function flushPythonBridgeServerOutput(server: PythonBridgeServerRuntime): void {
  if (server.stdoutChunks.length) {
    process.stdout.write(server.stdoutChunks.join(''));
  }
  if (server.stderrChunks.length) {
    process.stderr.write(server.stderrChunks.join(''));
  }
}
