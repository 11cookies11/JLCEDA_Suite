import type { BridgeCommandPayloadMap, BridgeRequest, BridgeResponse } from '../src/bridge/protocol';
import process from 'node:process';

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

interface ControlRequestResponse {
  response: BridgeResponse;
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function buildRequest<K extends keyof BridgeCommandPayloadMap>(
  id: string,
  domain: BridgeRequest['command']['domain'],
  action: BridgeRequest['command']['action'],
  payload: BridgeCommandPayloadMap[K],
  requiresConfirmation = false,
): BridgeRequest {
  return {
    id,
    type: 'command.request',
    protocolVersion: '0.1.0',
    sessionId: 'server-project-flow',
    command: {
      domain,
      action,
      requiresConfirmation,
      payload,
    },
  } as unknown as BridgeRequest;
}

async function postJson<TResponse>(url: string, body: unknown, token?: string): Promise<TResponse> {
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

async function getJson<TResponse>(url: string, token?: string): Promise<TResponse> {
  const response = await fetch(url, {
    headers: token ? { 'x-bridge-control-token': token } : undefined,
  });

  if (!response.ok) {
    throw new Error(`Control query failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as TResponse;
}

async function sendBridgeRequest(
  controlUrl: string,
  clientId: string,
  request: BridgeRequest,
  token?: string,
): Promise<BridgeResponse> {
  const result = await postJson<ControlRequestResponse>(`${controlUrl}/request`, {
    clientId,
    request,
  }, token);

  return result.response;
}

async function run(): Promise<void> {
  const controlUrl = process.env.BRIDGE_CONTROL_URL ?? 'http://127.0.0.1:8788';
  const controlToken = process.env.BRIDGE_CONTROL_TOKEN ?? '';
  const targetClientId = process.env.BRIDGE_TARGET_CLIENT_ID;
  const projectFriendlyName = process.env.BRIDGE_PROJECT_NAME ?? 'Codex Test Project';
  const projectName = process.env.BRIDGE_PROJECT_CODE ?? 'codex-test-project';

  const sessions = await getJson<ControlSessionsResponse>(`${controlUrl}/sessions`, controlToken);
  assert(sessions.sessions.length > 0, 'No connected bridge sessions were found.');

  const clientId = targetClientId ?? sessions.sessions[0]?.clientId;
  assert(clientId, 'No bridge clientId available.');

  const createProjectResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest(
      'server-flow-001',
      'project',
      'create_project',
      {
        projectFriendlyName,
        projectName,
        description: 'Created by server-side Codex flow',
      },
      false,
    ),
    controlToken,
  );

  assert(createProjectResponse.status === 'success', 'Project creation should succeed.');
  if (createProjectResponse.status !== 'success') {
    throw new Error('Project creation did not succeed.');
  }

  const projectUuid = (createProjectResponse.result.data as { projectUuid?: string }).projectUuid;
  assert(projectUuid, 'Project creation did not return a projectUuid.');
  console.log(`Created project: ${projectUuid}`);

  const openProjectResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest(
      'server-flow-002',
      'project',
      'open_project',
      {
        projectUuid,
      },
      false,
    ),
    controlToken,
  );
  assert(openProjectResponse.status === 'success', 'Project open should succeed.');
  console.log('PASS open project');

  const projectInfoResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest(
      'server-flow-003',
      'project',
      'get_project_info',
      {
        projectUuid,
      },
      false,
    ),
    controlToken,
  );
  assert(projectInfoResponse.status === 'success', 'Project info should succeed.');
  console.log('PASS project info');

  const inventoryResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('server-flow-004', 'project', 'get_inventory', {}, false),
    controlToken,
  );
  assert(inventoryResponse.status === 'success', 'Project inventory should succeed.');
  console.log('PASS project inventory');

  const schematicResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest(
      'server-flow-005',
      'schematic',
      'create_schematic',
      {
        boardName: 'Main Board',
      },
      false,
    ),
    controlToken,
  );
  assert(schematicResponse.status === 'success', 'Schematic creation should succeed.');
  if (schematicResponse.status !== 'success') {
    throw new Error('Schematic creation did not succeed.');
  }

  const schematicUuid = (schematicResponse.result.data as { schematicUuid?: string }).schematicUuid;
  assert(schematicUuid, 'Schematic creation did not return a schematicUuid.');
  console.log(`Created schematic: ${schematicUuid}`);

  const schematicPageResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest(
      'server-flow-006',
      'schematic',
      'create_schematic_page',
      {
        schematicUuid,
      },
      false,
    ),
    controlToken,
  );
  assert(schematicPageResponse.status === 'success', 'Schematic page creation should succeed.');
  console.log('PASS schematic page');

  const summaryResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('server-flow-007', 'project', 'get_document_summary', {}, false),
    controlToken,
  );
  assert(summaryResponse.status === 'success', 'Document summary should succeed.');
  console.log('PASS document summary');

  const currentSchematicResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('server-flow-008', 'schematic', 'get_current_schematic_info', {}, false),
    controlToken,
  );
  assert(currentSchematicResponse.status === 'success', 'Current schematic info should succeed.');
  console.log('PASS current schematic info');
}

run().catch((error) => {
  console.error('Server project flow failed.');
  console.error(error);
  process.exitCode = 1;
});
