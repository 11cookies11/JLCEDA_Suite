import type { ClientToServerMessage, ServerToClientMessage } from '../src/server/protocol';
import process from 'node:process';
import WebSocket from 'ws';
import { BRIDGE_PROTOCOL_VERSION } from '../src/bridge/protocol';
import {
  flushPythonBridgeServerOutput,
  postJson,
  spawnPythonBridgeServer,
  stopPythonBridgeServer,
  waitForHealth,
} from './python-server-test-utils';

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
  const bridgePort = Number(process.env.BRIDGE_SERVER_SMOKE_PORT ?? '8792');
  const controlPort = Number(process.env.BRIDGE_SERVER_SMOKE_CONTROL_PORT ?? '8793');
  const host = process.env.BRIDGE_SERVER_SMOKE_HOST ?? '127.0.0.1';
  const token = process.env.BRIDGE_SERVER_SMOKE_TOKEN ?? 'smoke-token';
  const server = spawnPythonBridgeServer({
    bridgePort,
    controlPort,
    host,
    token,
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

    const profilesResponse = await fetch(`http://${host}:${controlPort}/profiles`, {
      headers: {
        'x-bridge-control-token': token,
      },
    });
    assert(profilesResponse.ok, 'profiles endpoint should be available');
    const profilesPayload = await profilesResponse.json() as {
      activeProfile?: string;
      profiles?: Array<{ name?: string; active?: boolean }>;
    };
    assert(profilesPayload.activeProfile === 'default', 'server should default to the default profile');
    assert((profilesPayload.profiles ?? []).some(profile => profile.name === 'default'), 'profiles should include default');
    console.log('PASS profile list');

    const profileResponse = await fetch(`http://${host}:${controlPort}/profile`, {
      headers: {
        'x-bridge-control-token': token,
      },
    });
    assert(profileResponse.ok, 'profile endpoint should be available');
    const profilePayload = await profileResponse.json() as {
      activeProfile?: string;
      profile?: {
        name?: string;
        schematic?: {
          componentClearance?: number;
          placementComponentClearance?: number;
          placementWireClearance?: number;
          labelPlacementStepFloor?: number;
          labelGapMin?: number;
          labelGapMax?: number;
          powerColumnCount?: number;
          powerRowSpacingFactor?: number;
          labelGapRatio?: number;
          placementStep?: number;
          placementMaxRing?: number;
          powerKeywords?: Array<string>;
          powerRoleKeywords?: {
            inputCapacitor?: Array<string>;
            regulator?: Array<string>;
          };
          powerRoleOffsets?: {
            connector?: { x?: number; y?: number };
            regulator?: { x?: number; y?: number };
          };
        };
        pcb?: {
          labelHorizontalOffsetBase?: number;
          labelHorizontalOffsetMax?: number;
          labelVerticalOffsetBase?: number;
          labelVerticalOffsetMax?: number;
        };
      };
    };
    assert(profilePayload.activeProfile === 'default', 'profile endpoint should report default');
    assert(profilePayload.profile?.schematic?.componentClearance === 80, 'default profile should use balanced schematic clearance');
    assert(profilePayload.profile?.schematic?.placementComponentClearance === 48, 'default profile should expose placement component clearance');
    assert(profilePayload.profile?.schematic?.placementWireClearance === 40, 'default profile should expose placement wire clearance');
    assert(profilePayload.profile?.schematic?.labelPlacementStepFloor === 64, 'default profile should expose label placement floor');
    assert(profilePayload.profile?.schematic?.labelGapMin === 24, 'default profile should expose label gap minimum');
    assert(profilePayload.profile?.schematic?.labelGapMax === 56, 'default profile should expose label gap maximum');
    assert(profilePayload.profile?.schematic?.powerColumnCount === 3, 'default profile should expose power column count');
    assert(profilePayload.profile?.schematic?.powerRowSpacingFactor === 0.7, 'default profile should expose power row spacing factor');
    assert(profilePayload.profile?.schematic?.labelGapRatio === 0.35, 'default profile should expose label gap ratio');
    assert(profilePayload.profile?.schematic?.placementStep === 40, 'default profile should expose placement step');
    assert(profilePayload.profile?.schematic?.placementMaxRing === 8, 'default profile should expose placement max ring');
    assert((profilePayload.profile?.schematic?.powerKeywords ?? []).includes('vin'), 'default profile should expose power keywords');
    assert((profilePayload.profile?.schematic?.powerRoleKeywords?.regulator ?? []).includes('ldo'), 'default profile should expose power role keywords');
    assert(profilePayload.profile?.schematic?.powerRoleOffsets?.connector?.x === -320, 'default profile should expose connector offset');
    assert(profilePayload.profile?.schematic?.powerRoleOffsets?.regulator?.x === 0, 'default profile should expose regulator offset');
    assert(profilePayload.profile?.pcb?.labelHorizontalOffsetBase === 28, 'default profile should expose pcb label horizontal base');
    assert(profilePayload.profile?.pcb?.labelHorizontalOffsetMax === 64, 'default profile should expose pcb label horizontal max');
    assert(profilePayload.profile?.pcb?.labelVerticalOffsetBase === 20, 'default profile should expose pcb label vertical base');
    assert(profilePayload.profile?.pcb?.labelVerticalOffsetMax === 48, 'default profile should expose pcb label vertical max');
    console.log('PASS profile read');

    const profileUpdateResponse = await fetch(`http://${host}:${controlPort}/profile`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-bridge-control-token': token,
      },
      body: JSON.stringify({
        profileName: 'compact',
      }),
    });
    assert(profileUpdateResponse.ok, 'profile update should succeed');
    const profileUpdatePayload = await profileUpdateResponse.json() as {
      activeProfile?: string;
      profile?: { name?: string };
    };
    assert(profileUpdatePayload.activeProfile === 'compact', 'server should switch to the compact profile');
    assert(profileUpdatePayload.profile?.name === 'compact', 'profile update response should return the compact profile');
    console.log('PASS profile update');

    const profileRestoreResponse = await fetch(`http://${host}:${controlPort}/profile`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-bridge-control-token': token,
      },
      body: JSON.stringify({
        profileName: 'default',
      }),
    });
    assert(profileRestoreResponse.ok, 'profile restore should succeed');
    console.log('PASS profile restore');

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
    await stopPythonBridgeServer(server);
    flushPythonBridgeServerOutput(server);
  }
}

run().catch((error) => {
  console.error('Server smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
