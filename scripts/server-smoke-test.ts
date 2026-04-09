import type { ClientToServerMessage, ServerToClientMessage } from '../src/server/protocol';
import { spawn } from 'node:child_process';
import process from 'node:process';
import WebSocket from 'ws';
import { BRIDGE_PROTOCOL_VERSION } from '../src/bridge/protocol';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function waitForMessage<TMessage>(
  socket: WebSocket,
  predicate: (message: TMessage) => boolean,
): Promise<TMessage> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('Timed out waiting for server message.'));
    }, 5_000);

    const handleMessage = (rawData: WebSocket.RawData) => {
      const message = JSON.parse(rawData.toString()) as TMessage;

      if (!predicate(message)) {
        return;
      }

      clearTimeout(timeout);
      socket.off('message', handleMessage);
      resolve(message);
    };

    socket.on('message', handleMessage);
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
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
      // Retry until the server is ready.
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
  const bridgePort = Number(process.env.BRIDGE_SERVER_SMOKE_PORT ?? '8792');
  const controlPort = Number(process.env.BRIDGE_SERVER_SMOKE_CONTROL_PORT ?? '8793');
  const host = process.env.BRIDGE_SERVER_SMOKE_HOST ?? '127.0.0.1';
  const token = process.env.BRIDGE_SERVER_SMOKE_TOKEN ?? 'smoke-token';

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

  const serverExitPromise = new Promise<number>((resolve, reject) => {
    serverProcess.once('exit', (code) => {
      if (code === null) {
        reject(new Error('Python server exited unexpectedly.'));
        return;
      }

      resolve(code);
    });
    serverProcess.once('error', reject);
  });

  try {
    await waitForHealth(`http://${host}:${controlPort}/health`, token);

    const socket = new WebSocket(`ws://${host}:${bridgePort}`);
    await new Promise<void>((resolve, reject) => {
      socket.once('open', resolve);
      socket.once('error', reject);
    });

    const registerMessage: ClientToServerMessage = {
      type: 'agent.register',
      token,
      client: {
        clientId: 'client-smoke-001',
        pluginVersion: '0.1.0',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        supportedCommands: ['system.ping', 'system.get_bridge_status'],
      },
    };

    socket.send(JSON.stringify(registerMessage));

    const registeredMessage = await waitForMessage<ServerToClientMessage>(
      socket,
      message => message.type === 'server.registered',
    );
    assert(registeredMessage.type === 'server.registered', 'register ack should be returned');
    console.log('PASS server register');

    const sessionsResponse = await fetch(`http://${host}:${controlPort}/sessions`, {
      headers: {
        'x-bridge-control-token': token,
      },
    });
    assert(sessionsResponse.ok, 'sessions endpoint should be available');
    const sessionsPayload = await sessionsResponse.json() as {
      sessions: Array<{ clientId?: string }>;
    };
    assert(sessionsPayload.sessions.length === 1, 'server should track one connected session');
    assert(sessionsPayload.sessions[0]?.clientId === 'client-smoke-001', 'server should store the expected client id');
    console.log('PASS session tracking');

    const heartbeatMessage: ClientToServerMessage = {
      type: 'agent.heartbeat',
      clientId: 'client-smoke-001',
      timestamp: new Date().toISOString(),
    };
    socket.send(JSON.stringify(heartbeatMessage));

    const heartbeatAck = await waitForMessage<ServerToClientMessage>(
      socket,
      message => message.type === 'server.heartbeat_ack',
    );
    assert(heartbeatAck.type === 'server.heartbeat_ack', 'heartbeat ack should be returned');
    console.log('PASS heartbeat ack');

    const requestPromise = postJson<{ response: { id: string; status: string; result: { data?: { ok?: boolean; echo?: string } } } }>(
      `http://${host}:${controlPort}/request`,
      {
        clientId: 'client-smoke-001',
        request: {
          id: 'smoke-request-001',
          type: 'command.request',
          protocolVersion: BRIDGE_PROTOCOL_VERSION,
          sessionId: 'server-smoke-session',
          command: {
            domain: 'system',
            action: 'ping',
            payload: {
              echo: 'from-server',
            },
          },
        },
      },
      token,
    );

    const bridgeRequest = await waitForMessage<ServerToClientMessage>(
      socket,
      message => message.type === 'bridge.request',
    );
    assert(bridgeRequest.type === 'bridge.request', 'server should forward a bridge request');
    console.log('PASS bridge request dispatch');

    const bridgeResponse: ClientToServerMessage = {
      type: 'bridge.response',
      clientId: 'client-smoke-001',
      response: {
        id: bridgeRequest.request.id,
        type: 'command.response',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        status: 'success',
        result: {
          summary: 'pong',
          data: {
            ok: true,
            echo: 'from-server',
          },
        },
      },
    };

    socket.send(JSON.stringify(bridgeResponse));

    const requestResult = await requestPromise;
    assert(requestResult.response.status === 'success', 'server should resolve with the client response');
    console.log('PASS bridge response routing');

    socket.close();
  }
  finally {
    serverProcess.kill('SIGTERM');
    await serverExitPromise.catch(() => undefined);

    if (stdoutChunks.length) {
      process.stdout.write(stdoutChunks.join(''));
    }
    if (stderrChunks.length) {
      process.stderr.write(stderrChunks.join(''));
    }
  }
}

run().catch((error) => {
  console.error('Server smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
