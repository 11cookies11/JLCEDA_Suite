import type { BridgeRequest, BridgeResponse } from '../src/bridge/protocol';
import type { ServerToClientMessage } from '../src/server/protocol';
import process from 'node:process';
import { RemoteBridgeClient } from '../src/remote/client';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

async function run(): Promise<void> {
  const sentMessages: string[] = [];
  const configs = new Map<string, unknown>();
  let registeredMessageHandler: ((event: MessageEvent<string>) => void | Promise<void>) | undefined;
  let connectedHandler: (() => void | Promise<void>) | undefined;
  let closedSocketId: string | undefined;
  let executedRequestId: string | undefined;

  const client = new RemoteBridgeClient({
    registerSocket: (id, serviceUri, receiveMessageCallFn, onConnected) => {
      assert(id === 'jlceda-suite-remote-bridge', 'socket id should match the fixed bridge socket id');
      assert(serviceUri === 'ws://127.0.0.1:8787', 'server URL should come from saved settings');
      registeredMessageHandler = receiveMessageCallFn;
      connectedHandler = onConnected;
    },
    sendSocketData: (_id, data) => {
      sentMessages.push(data);
    },
    closeSocket: (id) => {
      closedSocketId = id;
    },
    getConfig: key => configs.get(key),
    setConfig: async (key, value) => {
      configs.set(key, value);
      return true;
    },
    executeRequest: async (request: BridgeRequest): Promise<BridgeResponse> => {
      executedRequestId = request.id;
      return {
        id: request.id,
        type: 'command.response',
        protocolVersion: request.protocolVersion,
        status: 'success',
        result: {
          summary: 'remote execution complete',
        },
      };
    },
  });

  await client.saveSettings({
    serverUrl: 'ws://127.0.0.1:8787',
    authToken: 'remote-token',
    clientId: 'remote-client-001',
    autoConnect: true,
  });

  await client.connect();
  assert(typeof connectedHandler === 'function', 'connect should register an onConnected callback');
  await connectedHandler?.();

  const registerMessage = JSON.parse(sentMessages[0] ?? '{}') as { type?: string; client?: { clientId?: string } };
  assert(registerMessage.type === 'agent.register', 'client should send agent.register after connection');
  assert(registerMessage.client?.clientId === 'remote-client-001', 'client should include configured client id');
  console.log('PASS remote client register');

  assert(typeof registeredMessageHandler === 'function', 'connect should register a receiveMessage handler');

  const bridgeRequest: BridgeRequest = {
    id: 'remote-req-001',
    type: 'command.request',
    protocolVersion: '0.1.0',
    sessionId: 'remote-session',
    command: {
      domain: 'system',
      action: 'ping',
      payload: {
        echo: 'remote',
      },
    },
  };

  const serverRequest: ServerToClientMessage = {
    type: 'bridge.request',
    request: bridgeRequest,
  };

  await registeredMessageHandler?.({
    data: JSON.stringify(serverRequest),
  } as MessageEvent<string>);

  assert(executedRequestId === 'remote-req-001', 'remote bridge request should be passed to the executor');

  const responseMessage = JSON.parse(sentMessages.at(-1) ?? '{}') as { type?: string; response?: { id?: string } };
  assert(responseMessage.type === 'bridge.response', 'client should reply with bridge.response');
  assert(responseMessage.response?.id === 'remote-req-001', 'response should preserve request id');
  console.log('PASS remote client request handling');

  client.disconnect();
  assert(closedSocketId === 'jlceda-suite-remote-bridge', 'disconnect should close the bridge socket');
  console.log('PASS remote client disconnect');
}

run().catch((error) => {
  console.error('Remote client smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
