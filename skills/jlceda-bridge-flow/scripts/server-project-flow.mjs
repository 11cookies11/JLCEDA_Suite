#!/usr/bin/env node

const BRIDGE_PROTOCOL_VERSION = '0.1.0';

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function getEnv(name, fallback = '') {
  const value = process.env[name];
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

function buildRequest(id, domain, action, payload) {
  return {
    id,
    type: 'command.request',
    protocolVersion: BRIDGE_PROTOCOL_VERSION,
    sessionId: 'jlceda-bridge-flow',
    command: {
      domain,
      action,
      requiresConfirmation: false,
      payload,
    },
  };
}

async function getJson(url, token) {
  const response = await fetch(url, {
    headers: token ? { 'x-bridge-control-token': token } : undefined,
  });

  if (!response.ok) {
    throw new Error(`Control query failed: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

async function postJson(url, body, token) {
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

  return response.json();
}

async function sendBridgeRequest(controlUrl, clientId, request, token) {
  const payload = await postJson(`${controlUrl}/request`, {
    clientId,
    request,
  }, token);

  assert(payload && typeof payload === 'object' && payload.response, 'Missing bridge response from control plane.');
  return payload.response;
}

async function run() {
  const controlUrl = getEnv('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788');
  const controlToken = getEnv('BRIDGE_CONTROL_TOKEN');
  const targetClientId = getEnv('BRIDGE_TARGET_CLIENT_ID');
  const projectFriendlyName = getEnv('BRIDGE_PROJECT_NAME', 'Codex Test Project');
  const projectName = getEnv('BRIDGE_PROJECT_CODE', 'codex-test-project');

  const sessionPayload = await getJson(`${controlUrl}/sessions`, controlToken);
  const sessions = Array.isArray(sessionPayload?.sessions) ? sessionPayload.sessions : [];
  assert(sessions.length > 0, 'No connected bridge sessions were found.');

  const clientId = targetClientId || sessions[0]?.clientId;
  assert(clientId, 'No bridge clientId available.');

  const createProjectResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('skill-flow-001', 'project', 'create_project', {
      projectFriendlyName,
      projectName,
      description: 'Created by jlceda-bridge-flow',
    }),
    controlToken,
  );
  assert(createProjectResponse.status === 'success', 'Project creation should succeed.');

  const projectUuid = createProjectResponse?.result?.data?.projectUuid;
  assert(projectUuid, 'Project creation did not return a projectUuid.');
  console.log(`Created project: ${projectUuid}`);

  const openProjectResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('skill-flow-002', 'project', 'open_project', {
      projectUuid,
    }),
    controlToken,
  );
  assert(openProjectResponse.status === 'success', 'Project open should succeed.');
  console.log('PASS open project');

  const projectInfoResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('skill-flow-003', 'project', 'get_project_info', {
      projectUuid,
    }),
    controlToken,
  );
  assert(projectInfoResponse.status === 'success', 'Project info should succeed.');
  console.log('PASS project info');

  const inventoryResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('skill-flow-004', 'project', 'get_inventory', {}),
    controlToken,
  );
  assert(inventoryResponse.status === 'success', 'Project inventory should succeed.');
  console.log('PASS project inventory');

  const schematicResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('skill-flow-005', 'schematic', 'create_schematic', {
      boardName: 'Main Board',
    }),
    controlToken,
  );
  assert(schematicResponse.status === 'success', 'Schematic creation should succeed.');

  const schematicUuid = schematicResponse?.result?.data?.schematicUuid;
  assert(schematicUuid, 'Schematic creation did not return a schematicUuid.');
  console.log(`Created schematic: ${schematicUuid}`);

  const schematicPageResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('skill-flow-006', 'schematic', 'create_schematic_page', {
      schematicUuid,
    }),
    controlToken,
  );
  assert(schematicPageResponse.status === 'success', 'Schematic page creation should succeed.');
  console.log('PASS schematic page');

  const summaryResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('skill-flow-007', 'project', 'get_document_summary', {}),
    controlToken,
  );
  assert(summaryResponse.status === 'success', 'Document summary should succeed.');
  console.log('PASS document summary');

  const currentSchematicResponse = await sendBridgeRequest(
    controlUrl,
    clientId,
    buildRequest('skill-flow-008', 'schematic', 'get_current_schematic_info', {}),
    controlToken,
  );
  assert(currentSchematicResponse.status === 'success', 'Current schematic info should succeed.');
  console.log('PASS current schematic info');
}

run().catch((error) => {
  console.error('JLCEDA bridge flow failed.');
  console.error(error);
  process.exitCode = 1;
});
