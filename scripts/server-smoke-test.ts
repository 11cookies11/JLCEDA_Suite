import type { ClientToServerMessage, ServerToClientMessage } from '../src/server/protocol';
import process from 'node:process';
import WebSocket from 'ws';
import { BRIDGE_PROTOCOL_VERSION } from '../src/bridge/protocol';
import { BridgeServer, createBridgeRequestId } from '../src/server/bridge-server';

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

async function run(): Promise<void> {
  const server = new BridgeServer({
    port: 8788,
    host: '127.0.0.1',
    authToken: 'smoke-token',
    requestTimeoutMs: 5_000,
  });

  await server.start();

  const socket = new WebSocket('ws://127.0.0.1:8788');
  await new Promise<void>((resolve, reject) => {
    socket.once('open', resolve);
    socket.once('error', reject);
  });

  const registerMessage: ClientToServerMessage = {
    type: 'agent.register',
    token: 'smoke-token',
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

  const sessions = server.listSessions();
  assert(sessions.length === 1, 'server should track one connected session');
  assert(sessions[0]?.clientId === 'client-smoke-001', 'server should store the expected client id');
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

  const responsePromise = server.sendBridgeRequest('client-smoke-001', {
    id: createBridgeRequestId('smoke'),
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
  });

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

  const response = await responsePromise;
  assert(response.status === 'success', 'server should resolve with the client response');
  console.log('PASS bridge response routing');

  socket.close();
  await server.stop();
}

run().catch((error) => {
  console.error('Server smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
