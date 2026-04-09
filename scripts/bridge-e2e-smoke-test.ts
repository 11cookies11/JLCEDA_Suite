import type { BridgeRequest, BridgeResponse } from '../src/bridge/protocol';
import { spawn } from 'node:child_process';
import process from 'node:process';
import WebSocket from 'ws';
import { BRIDGE_PROTOCOL_VERSION } from '../src/bridge/protocol';
import { RemoteBridgeClient } from '../src/remote/client';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitFor(condition: () => boolean, timeoutMs: number, message: string): Promise<void> {
  const startedAt = Date.now();
  while (!condition()) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(message);
    }
    await sleep(25);
  }
}

async function waitForHealth(url: string, token: string): Promise<void> {
  const deadline = Date.now() + 60_000;
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
      // Keep waiting for the Python server to finish booting.
    }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for server health at ${url}.`);
}

async function postJson<TResponse>(url: string, body: unknown, token: string): Promise<TResponse> {
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

async function run(): Promise<void> {
  const bridgePort = Number(process.env.BRIDGE_SERVER_SMOKE_PORT ?? '8794');
  const controlPort = Number(process.env.BRIDGE_SERVER_SMOKE_CONTROL_PORT ?? '8795');
  const host = process.env.BRIDGE_SERVER_SMOKE_HOST ?? '127.0.0.1';
  const token = process.env.BRIDGE_SERVER_SMOKE_TOKEN ?? 'e2e-token';

  const serverProcess = spawn('python3', ['./scripts/python_bridge_server.py'], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      BRIDGE_SERVER_HOST: host,
      BRIDGE_SERVER_PORT: String(bridgePort),
      BRIDGE_SERVER_CONTROL_HOST: host,
      BRIDGE_SERVER_CONTROL_PORT: String(controlPort),
      BRIDGE_SERVER_TOKEN: token,
      BRIDGE_SERVER_CONTROL_TOKEN: token,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  const stdoutChunks: string[] = [];
  const stderrChunks: string[] = [];
  serverProcess.stdout?.on('data', chunk => stdoutChunks.push(String(chunk)));
  serverProcess.stderr?.on('data', chunk => stderrChunks.push(String(chunk)));

  try {
    await waitForHealth(`http://${host}:${controlPort}/health`, token);

    const configs = new Map<string, unknown>();
    let socket: WebSocket | undefined;

    const client = new RemoteBridgeClient({
      registerSocket: (id, serviceUri, receiveMessageCallFn, onConnected) => {
        assert(id === 'jlceda-aiagent-remote-bridge', 'client should use the fixed remote bridge socket id');
        socket = new WebSocket(serviceUri);
        socket.once('open', () => {
          void onConnected?.();
        });
        socket.on('message', (rawData) => {
          void receiveMessageCallFn?.({
            data: rawData.toString(),
          } as MessageEvent<string>);
        });
      },
      sendSocketData: (_id, data) => {
        socket?.send(data);
      },
      closeSocket: () => {
        socket?.close();
      },
      getConfig: key => configs.get(key),
      setConfig: async (key, value) => {
        configs.set(key, value);
        return true;
      },
      executeRequest: async (request: BridgeRequest): Promise<BridgeResponse> => {
        return {
          id: request.id,
          type: 'command.response',
          protocolVersion: request.protocolVersion,
          status: 'success',
          result: {
            summary: 'e2e remote execution complete',
            data: {
              command: `${request.command.domain}.${request.command.action}`,
            },
          },
        };
      },
    });

    await client.saveSettings({
      serverUrl: `ws://${host}:${bridgePort}`,
      authToken: token,
      clientId: 'e2e-client-001',
      autoConnect: true,
    });

    await client.connect();

    await waitFor(() => socket?.readyState === WebSocket.OPEN, 5_000, 'client socket should open');
    await waitForHealth(`http://${host}:${controlPort}/health`, token);

    const sessionsResponse = await fetch(`http://${host}:${controlPort}/sessions`, {
      headers: {
        'x-bridge-control-token': token,
      },
    });
    assert(sessionsResponse.ok, 'sessions endpoint should be available');
    const sessionsPayload = await sessionsResponse.json() as {
      sessions: Array<{ clientId?: string }>;
    };
    assert(sessionsPayload.sessions.some(session => session.clientId === 'e2e-client-001'), 'client should register with the server');
    console.log('PASS e2e registration');

    const requestPromise = postJson<{
      response: BridgeResponse;
    }>(`http://${host}:${controlPort}/request`, {
      clientId: 'e2e-client-001',
      request: {
        id: 'e2e-request-001',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'e2e-session',
        command: {
          domain: 'system',
          action: 'ping',
          payload: {
            echo: 'e2e',
          },
        },
      },
    }, token);

    const response = await requestPromise;
    assert(response.response.status === 'success', 'end-to-end request should succeed');
    if (response.response.status === 'success') {
      const resultData = response.response.result.data as { command?: string };
      assert(resultData.command === 'system.ping', 'response should contain the handled command name');
    }
    console.log('PASS e2e request routing');

    const status = client.getStatus();
    assert(status.connected === true, 'client status should report an active remote connection');
    console.log('PASS e2e client status');

    client.disconnect();
  }
  finally {
    serverProcess.kill('SIGTERM');
    await new Promise<void>((resolve) => {
      if (serverProcess.exitCode !== null || serverProcess.signalCode !== null) {
        resolve();
        return;
      }

      serverProcess.once('exit', () => resolve());
    });

    if (stdoutChunks.length) {
      process.stdout.write(stdoutChunks.join(''));
    }
    if (stderrChunks.length) {
      process.stderr.write(stderrChunks.join(''));
    }
  }
}

run().catch((error) => {
  console.error('Bridge end-to-end smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
