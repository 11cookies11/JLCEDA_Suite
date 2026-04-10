import type { BridgeRequest, BridgeResponse } from '../src/bridge/protocol';
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
  pendingRequests?: Array<Record<string, unknown>>;
}

interface ControlRequestResponse {
  response: BridgeResponse;
}

interface SessionDebugResponse {
  session: Record<string, unknown>;
  pendingRequests?: Array<Record<string, unknown>>;
  recentRequests?: Array<Record<string, unknown>>;
  activeProfile?: string;
}

interface ContextStepResult {
  command: string;
  ok: boolean;
  summary?: string;
  data?: unknown;
  error?: string;
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function getEnv(name: string, fallback = ''): string {
  const value = process.env[name];
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

function buildRequest(
  id: string,
  domain: BridgeRequest['command']['domain'],
  action: BridgeRequest['command']['action'],
  payload: Record<string, unknown> = {},
): BridgeRequest {
  return {
    id,
    type: 'command.request',
    protocolVersion: '0.1.0',
    sessionId: 'server-context-summary',
    command: {
      domain,
      action,
      requiresConfirmation: false,
      payload,
    },
  } as BridgeRequest;
}

async function getJson<TResponse>(url: string, token?: string): Promise<TResponse> {
  const response = await fetch(url, {
    headers: token ? { 'x-bridge-control-token': token } : undefined,
  });

  if (!response.ok) {
    throw new Error(`Control query failed: ${response.status} ${response.statusText}`);
  }

  return await response.json() as TResponse;
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

  return await response.json() as TResponse;
}

async function sendBridgeRequest(
  controlUrl: string,
  clientId: string,
  request: BridgeRequest,
  token?: string,
): Promise<ContextStepResult> {
  try {
    const result = await postJson<ControlRequestResponse>(`${controlUrl}/request`, {
      clientId,
      request,
    }, token);
    const response = result.response;
    const successResult = response.status === 'success' ? response.result : undefined;
    const responseError = 'error' in response ? response.error?.message : undefined;
    return {
      command: `${request.command.domain}.${request.command.action}`,
      ok: response.status === 'success',
      summary: successResult?.summary,
      data: successResult?.data,
      error: response.status === 'success' ? undefined : responseError ?? response.status,
    };
  }
  catch (error) {
    return {
      command: `${request.command.domain}.${request.command.action}`,
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function buildSuggestedNextSteps(results: {
  documentSummary?: ContextStepResult;
  selectionSnapshot?: ContextStepResult;
  currentSchematic?: ContextStepResult;
}): string[] {
  const steps: string[] = [];
  const documentSummary = results.documentSummary?.data as {
    document?: { kind?: string };
    project?: { name?: string };
    selection?: { count?: number };
  } | undefined;
  const currentSchematic = results.currentSchematic?.data as {
    pageCount?: number;
    name?: string;
  } | undefined;
  const selectionSnapshot = results.selectionSnapshot?.data as {
    count?: number;
    documentKind?: string;
  } | undefined;

  if (!documentSummary?.project?.name) {
    steps.push('?????????????????????????');
  }

  if (documentSummary?.document?.kind !== 'schematic') {
    steps.push('?????????????????????????');
  }

  if (!currentSchematic && documentSummary?.document?.kind === 'schematic') {
    steps.push('????????????????????????? schematic ???');
  }

  if (currentSchematic && (currentSchematic.pageCount ?? 0) === 0) {
    steps.push('?? schematic ?????????????? schematic page?');
  }

  if ((selectionSnapshot?.count ?? 0) > 0) {
    steps.push('??????????????????????????????');
  }
  else {
    steps.push('??????????????????????????????????');
  }

  steps.push('??????????????????????????????????????');
  return steps;
}

async function run(): Promise<void> {
  const controlUrl = getEnv('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788');
  const controlToken = getEnv('BRIDGE_CONTROL_TOKEN');
  const targetClientId = getEnv('BRIDGE_TARGET_CLIENT_ID');

  const sessionsPayload = await getJson<ControlSessionsResponse>(`${controlUrl}/sessions`, controlToken);
  const sessions = sessionsPayload.sessions ?? [];
  assert(sessions.length > 0, 'No connected bridge sessions were found.');

  const clientId = targetClientId || sessions[0]?.clientId;
  assert(clientId, 'No bridge clientId available.');

  const sessionDebug = await getJson<SessionDebugResponse>(`${controlUrl}/debug/session/${encodeURIComponent(clientId)}`, controlToken);

  const bridgeStatus = await sendBridgeRequest(controlUrl, clientId, buildRequest('context-001', 'system', 'get_bridge_status'), controlToken);
  const documentSummary = await sendBridgeRequest(controlUrl, clientId, buildRequest('context-002', 'project', 'get_document_summary'), controlToken);
  const selectionSnapshot = await sendBridgeRequest(controlUrl, clientId, buildRequest('context-003', 'project', 'get_selection_snapshot'), controlToken);
  const currentSchematic = await sendBridgeRequest(controlUrl, clientId, buildRequest('context-004', 'schematic', 'get_current_schematic_info'), controlToken);

  const payload = {
    client: {
      clientId,
      pluginVersion: sessions.find(session => session.clientId === clientId)?.pluginVersion,
      protocolVersion: sessions.find(session => session.clientId === clientId)?.protocolVersion,
      connectedAt: sessions.find(session => session.clientId === clientId)?.connectedAt,
      lastSeenAt: sessions.find(session => session.clientId === clientId)?.lastSeenAt,
    },
    diagnostics: {
      activeProfile: sessionDebug.activeProfile,
      pendingRequests: sessionDebug.pendingRequests ?? [],
      recentRequests: sessionDebug.recentRequests ?? [],
      pendingRequestsFromSessions: sessionsPayload.pendingRequests ?? [],
    },
    context: {
      bridgeStatus,
      documentSummary,
      selectionSnapshot,
      currentSchematic,
    },
    suggestedNextSteps: buildSuggestedNextSteps({
      documentSummary,
      selectionSnapshot,
      currentSchematic: currentSchematic.ok ? currentSchematic : undefined,
    }),
  };

  console.log(JSON.stringify(payload, null, 2));
}

run().catch((error) => {
  console.error('Server context summary failed.');
  console.error(error);
  process.exitCode = 1;
});
