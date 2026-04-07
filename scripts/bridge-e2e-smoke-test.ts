import type { BridgeRequest, BridgeResponse } from '../src/bridge/protocol';
import process from 'node:process';
import WebSocket from 'ws';
import { BRIDGE_PROTOCOL_VERSION } from '../src/bridge/protocol';
import { RemoteBridgeClient } from '../src/remote/client';
import { BridgeServer, createBridgeRequestId } from '../src/server/bridge-server';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

async function waitFor(condition: () => boolean, timeoutMs: number, message: string): Promise<void> {
  const startedAt = Date.now();

  while (!condition()) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(message);
    }

    await new Promise(resolve => setTimeout(resolve, 25));
  }
}

async function run(): Promise<void> {
  const server = new BridgeServer({
    port: 8789,
    host: '127.0.0.1',
    authToken: 'e2e-token',
    requestTimeoutMs: 5_000,
  });

  await server.start();

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
    serverUrl: 'ws://127.0.0.1:8789',
    authToken: 'e2e-token',
    clientId: 'e2e-client-001',
    autoConnect: true,
  });

  await client.connect();

  await waitFor(() => server.listSessions().some(session => session.clientId === 'e2e-client-001'), 5_000, 'client should register with the server');
  console.log('PASS e2e registration');

  const response = await server.sendBridgeRequest('e2e-client-001', {
    id: createBridgeRequestId('e2e'),
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
  });

  assert(response.status === 'success', 'end-to-end request should succeed');
  if (response.status === 'success') {
    const resultData = response.result.data as { command?: string };
    assert(resultData.command === 'system.ping', 'response should contain the handled command name');
  }
  console.log('PASS e2e request routing');

  const status = client.getStatus();
  assert(status.connected === true, 'client status should report an active remote connection');
  console.log('PASS e2e client status');

  client.disconnect();
  await server.stop();
}

run().catch((error) => {
  console.error('Bridge end-to-end smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
