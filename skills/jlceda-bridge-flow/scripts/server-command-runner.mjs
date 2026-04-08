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

function buildRequest(step, index) {
  return {
    id: step.id ?? `runner-${String(index + 1).padStart(3, '0')}`,
    type: 'command.request',
    protocolVersion: BRIDGE_PROTOCOL_VERSION,
    sessionId: 'server-command-runner',
    command: {
      domain: step.domain,
      action: step.action,
      payload: step.payload ?? {},
      ...(typeof step.requiresConfirmation === 'boolean' ? { requiresConfirmation: step.requiresConfirmation } : {}),
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

async function loadPlan() {
  const inlinePlan = getEnv('BRIDGE_COMMANDS_JSON');
  if (inlinePlan) {
    return JSON.parse(inlinePlan);
  }

  const planFile = getEnv('BRIDGE_COMMANDS_FILE');
  if (planFile) {
    const fs = await import('node:fs/promises');
    return JSON.parse(await fs.readFile(planFile, 'utf8'));
  }

  const stdinChunks = [];
  if (!process.stdin.isTTY) {
    for await (const chunk of process.stdin) {
      stdinChunks.push(Buffer.from(chunk));
    }
    const raw = Buffer.concat(stdinChunks).toString('utf8').trim();
    if (raw) {
      return JSON.parse(raw);
    }
  }

  throw new Error('No command plan provided. Set BRIDGE_COMMANDS_JSON, BRIDGE_COMMANDS_FILE, or pipe JSON on stdin.');
}

async function run() {
  const controlUrl = getEnv('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788');
  const controlToken = getEnv('BRIDGE_CONTROL_TOKEN');
  const targetClientId = getEnv('BRIDGE_TARGET_CLIENT_ID');
  const autoApprove = getEnv('BRIDGE_AUTO_APPROVE', 'false') === 'true';
  const plan = await loadPlan();

  const sessionPayload = await getJson(`${controlUrl}/sessions`, controlToken);
  const sessions = Array.isArray(sessionPayload?.sessions) ? sessionPayload.sessions : [];
  assert(sessions.length > 0, 'No connected bridge sessions were found.');

  const clientId = targetClientId || plan.clientId || sessions[0]?.clientId;
  assert(clientId, 'No bridge clientId available.');

  console.log(`Target client: ${clientId}`);

  for (let index = 0; index < plan.requests.length; index += 1) {
    const step = plan.requests[index];
    const request = buildRequest(step, index);
    const commandName = `${request.command.domain}.${request.command.action}`;

    const response = await sendBridgeRequest(controlUrl, clientId, request, controlToken);
    if (response.status === 'confirmation_required' && autoApprove) {
      console.log(`AUTO-APPROVE ${commandName} -> ${response.confirmation.token}`);
      const approvedResponse = await sendBridgeRequest(
        controlUrl,
        clientId,
        {
          ...request,
          command: {
            ...request.command,
            requiresConfirmation: false,
          },
        },
        controlToken,
      );
      console.log(JSON.stringify({
        command: commandName,
        status: approvedResponse.status,
        response: approvedResponse,
      }, null, 2));
      continue;
    }

    console.log(JSON.stringify({
      command: commandName,
      status: response.status,
      response,
    }, null, 2));
  }
}

run().catch((error) => {
  console.error('Server command runner failed.');
  console.error(error);
  process.exitCode = 1;
});
