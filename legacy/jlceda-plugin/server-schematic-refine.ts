import type { BridgeRequest, BridgeResponse } from '../src/bridge/protocol';
import process from 'node:process';

interface SchematicEditStep {
  kind: 'place_component' | 'create_wire' | 'annotate_net' | 'create_net_flag' | 'create_net_port' | 'save';
  payload?: Record<string, unknown>;
  note?: string;
}

interface EditDecision {
  title: string;
  rationale: string;
  verification?: string;
}

function env(name: string, fallback = ''): string {
  const value = process.env[name];
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

function parseJson<T>(name: string, fallback: T): T {
  const value = env(name);
  return value ? JSON.parse(value) as T : fallback;
}

function buildRequest(id: string, action: BridgeRequest['command']['action'], payload: Record<string, unknown> = {}): BridgeRequest {
  return {
    id,
    type: 'command.request',
    protocolVersion: '0.1.0',
    sessionId: 'server-schematic-refine',
    command: {
      domain: action.startsWith('project.') ? 'project' : 'schematic',
      action,
      requiresConfirmation: false,
      payload,
    },
  } as BridgeRequest;
}

async function getJson<T>(url: string, token?: string): Promise<T> {
  const response = await fetch(url, {
    headers: token ? { 'x-bridge-control-token': token } : undefined,
  });
  if (!response.ok) {
    throw new Error(`Control query failed: ${response.status} ${response.statusText}`);
  }
  return await response.json() as T;
}

async function send(controlUrl: string, clientId: string, request: BridgeRequest, token?: string) {
  try {
    const response = await fetch(`${controlUrl}/request`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        ...(token ? { 'x-bridge-control-token': token } : {}),
      },
      body: JSON.stringify({ clientId, request }),
    });
    if (!response.ok) {
      throw new Error(`Control request failed: ${response.status} ${response.statusText}`);
    }
    const payload = await response.json() as { response: BridgeResponse };
    const bridge = payload.response;
    const result = bridge.status === 'success' ? bridge.result : undefined;
    const error = 'error' in bridge ? bridge.error?.message : undefined;
    return {
      command: `${request.command.domain}.${request.command.action}`,
      ok: bridge.status === 'success',
      summary: result?.summary,
      data: result?.data,
      error: bridge.status === 'success' ? undefined : error ?? bridge.status,
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

async function run() {
  const controlUrl = env('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788');
  const controlToken = env('BRIDGE_CONTROL_TOKEN');
  const editPlan = parseJson<SchematicEditStep[]>('BRIDGE_SCHEMATIC_EDIT_PLAN_JSON', []);
  const decisions = parseJson<EditDecision[]>('BRIDGE_SCHEMATIC_DECISIONS_JSON', []);
  const sessionsPayload = await getJson<{ sessions: Array<{ clientId: string; pluginVersion: string; protocolVersion: string }> }>(`${controlUrl}/sessions`, controlToken);
  const clientId = env('BRIDGE_TARGET_CLIENT_ID') || sessionsPayload.sessions[0]?.clientId;
  if (!clientId) {
    throw new Error('No bridge clientId available.');
  }

  const beforeDocument = await send(controlUrl, clientId, buildRequest('schematic-edit-001', 'get_document_summary'), controlToken);
  const beforeSchematic = await send(controlUrl, clientId, buildRequest('schematic-edit-002', 'get_current_schematic_info'), controlToken);

  const actionMap: Record<SchematicEditStep['kind'], BridgeRequest['command']['action']> = {
    place_component: 'place_component',
    create_wire: 'create_wire',
    annotate_net: 'annotate_net',
    create_net_flag: 'create_net_flag',
    create_net_port: 'create_net_port',
    save: 'save',
  };

  const steps = [] as Array<Record<string, unknown>>;
  for (let index = 0; index < editPlan.length; index += 1) {
    const step = editPlan[index];
    const action = actionMap[step.kind];
    const result = await send(controlUrl, clientId, buildRequest(`schematic-edit-${String(index + 3).padStart(3, '0')}`, action, step.payload ?? {}), controlToken);
    steps.push({
      kind: step.kind,
      note: step.note ?? '',
      result,
    });
  }

  const afterDocument = await send(controlUrl, clientId, buildRequest('schematic-edit-900', 'get_document_summary'), controlToken);
  const afterSchematic = await send(controlUrl, clientId, buildRequest('schematic-edit-901', 'get_current_schematic_info'), controlToken);
  const failedSteps = steps.filter(step => (step.result as { ok?: boolean }).ok === false).length;

  console.log(JSON.stringify({
    client: {
      clientId,
      pluginVersion: sessionsPayload.sessions[0]?.pluginVersion,
      protocolVersion: sessionsPayload.sessions[0]?.protocolVersion,
    },
    decisions,
    before: {
      documentSummary: beforeDocument,
      currentSchematic: beforeSchematic,
    },
    steps,
    after: {
      documentSummary: afterDocument,
      currentSchematic: afterSchematic,
    },
    validation: {
      failedSteps,
      ok: failedSteps === 0,
      nextChecks: [
        'Review the edited function block in the current schematic.',
        'Verify critical nets and labels after the change batch.',
        'Save and continue only after the post-edit context looks correct.',
      ],
    },
  }, null, 2));
}

run().catch((error) => {
  console.error('Server schematic refine failed.');
  console.error(error);
  process.exitCode = 1;
});
