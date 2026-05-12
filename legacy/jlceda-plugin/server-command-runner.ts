import type { BridgeCommandPayloadMap, BridgeRequest, BridgeResponse } from '../src/bridge/protocol';
import { Buffer } from 'node:buffer';
import fs from 'node:fs/promises';
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

interface RunnerStep {
  id?: string;
  domain: BridgeRequest['command']['domain'];
  action: BridgeRequest['command']['action'];
  payload?: BridgeCommandPayloadMap[keyof BridgeCommandPayloadMap] | Record<string, unknown>;
  requiresConfirmation?: boolean;
}

interface RunnerPlan {
  clientId?: string;
  requests: RunnerStep[];
}

type RunnerTemplateName = 'inspect' | 'select' | 'design' | 'pcb' | 'export';

interface RunnerTemplateInput {
  includeComponents?: boolean;
  includeNets?: boolean;
  allSchematicPages?: boolean;
  allPcbPages?: boolean;
  maxIssues?: number;
  componentClearance?: number;
  wireClearance?: number;
  trackClearance?: number;
  labelClearance?: number;
  boardEdgeClearance?: number;
  strict?: boolean;
  exportFormat?: 'json' | 'csv';
  fileName?: string;
  saveToLocal?: boolean;
}

interface RunnerResolvedPlan {
  mode: 'custom' | 'template';
  template?: RunnerTemplateName;
  plan: RunnerPlan;
}

interface RunnerResultRow {
  command: string;
  status: BridgeResponse['status'];
  response: BridgeResponse;
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

function parseJson<T>(raw: string, fallback: T): T {
  return raw ? JSON.parse(raw) as T : fallback;
}

function buildRequest(step: RunnerStep, index: number): BridgeRequest {
  return {
    id: step.id ?? `runner-${String(index + 1).padStart(3, '0')}`,
    type: 'command.request',
    protocolVersion: '0.1.0',
    sessionId: 'server-command-runner',
    command: {
      domain: step.domain,
      action: step.action,
      payload: (step.payload ?? {}) as BridgeCommandPayloadMap[keyof BridgeCommandPayloadMap],
      ...(typeof step.requiresConfirmation === 'boolean' ? { requiresConfirmation: step.requiresConfirmation } : {}),
    },
  } as BridgeRequest;
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

function makeStep(
  id: string,
  domain: BridgeRequest['command']['domain'],
  action: BridgeRequest['command']['action'],
  payload: Record<string, unknown> = {},
  requiresConfirmation = false,
): RunnerStep {
  return { id, domain, action, payload, requiresConfirmation };
}

function buildTemplatePlan(template: RunnerTemplateName, input: RunnerTemplateInput): RunnerPlan {
  switch (template) {
    case 'inspect':
      return {
        requests: [
          makeStep('template-001', 'system', 'get_bridge_status'),
          makeStep('template-002', 'project', 'get_document_summary'),
          makeStep('template-003', 'project', 'get_selection_snapshot', {
            includeComponents: input.includeComponents ?? true,
            includeNets: input.includeNets ?? true,
          }),
          makeStep('template-004', 'schematic', 'get_current_schematic_info'),
        ],
      };
    case 'select':
      return {
        requests: [
          makeStep('template-001', 'project', 'get_document_summary'),
          makeStep('template-002', 'project', 'get_selection_snapshot', {
            includeComponents: input.includeComponents ?? true,
            includeNets: input.includeNets ?? true,
          }),
          makeStep('template-003', 'schematic', 'get_current_schematic_info'),
          makeStep('template-004', 'project', 'get_inventory'),
        ],
      };
    case 'design':
      return {
        requests: [
          makeStep('template-001', 'project', 'get_document_summary'),
          makeStep('template-002', 'schematic', 'get_current_schematic_info'),
          makeStep('template-003', 'project', 'get_selection_snapshot', {
            includeComponents: input.includeComponents ?? true,
            includeNets: input.includeNets ?? true,
          }),
          makeStep('template-004', 'schematic', 'inspect_connectivity', {
            allSchematicPages: input.allSchematicPages ?? false,
            maxIssues: input.maxIssues ?? 12,
          }),
          makeStep('template-005', 'schematic', 'inspect_layout_hygiene', {
            allSchematicPages: input.allSchematicPages ?? false,
            componentClearance: input.componentClearance,
            wireClearance: input.wireClearance,
            maxIssues: input.maxIssues ?? 12,
          }),
        ],
      };
    case 'pcb':
      return {
        requests: [
          makeStep('template-001', 'project', 'get_document_summary'),
          makeStep('template-002', 'schematic', 'get_current_schematic_info'),
          makeStep('template-003', 'pcb', 'get_board_summary'),
          makeStep('template-004', 'pcb', 'get_current_pcb_info'),
          makeStep('template-005', 'pcb', 'inspect_layout_hygiene', {
            allPcbPages: input.allPcbPages ?? false,
            componentClearance: input.componentClearance,
            trackClearance: input.trackClearance,
            labelClearance: input.labelClearance,
            boardEdgeClearance: input.boardEdgeClearance,
            maxIssues: input.maxIssues ?? 12,
          }),
          makeStep('template-006', 'pcb', 'get_calculating_ratline_status'),
        ],
      };
    case 'export':
      return {
        requests: [
          makeStep('template-001', 'project', 'get_document_summary'),
          makeStep('template-002', 'project', 'export_bom', {
            format: input.exportFormat ?? 'json',
            fileName: input.fileName,
            saveToLocal: input.saveToLocal ?? false,
          }, true),
        ],
      };
    default:
      throw new Error(`Unsupported runner template: ${template}`);
  }
}

async function loadPlan(): Promise<RunnerResolvedPlan> {
  const template = getEnv('BRIDGE_RUNNER_TEMPLATE') as RunnerTemplateName;
  if (template) {
    const templateInput = parseJson<RunnerTemplateInput>(getEnv('BRIDGE_RUNNER_TEMPLATE_INPUT_JSON'), {});
    return {
      mode: 'template',
      template,
      plan: buildTemplatePlan(template, templateInput),
    };
  }

  const inlinePlan = getEnv('BRIDGE_COMMANDS_JSON');
  if (inlinePlan) {
    return {
      mode: 'custom',
      plan: JSON.parse(inlinePlan) as RunnerPlan,
    };
  }

  const planFile = getEnv('BRIDGE_COMMANDS_FILE');
  if (planFile) {
    return {
      mode: 'custom',
      plan: JSON.parse(await fs.readFile(planFile, 'utf8')) as RunnerPlan,
    };
  }

  const stdinChunks: Array<Buffer> = [];
  if (!process.stdin.isTTY) {
    for await (const chunk of process.stdin) {
      stdinChunks.push(Buffer.from(chunk));
    }
    const raw = Buffer.concat(stdinChunks).toString('utf8').trim();
    if (raw) {
      return {
        mode: 'custom',
        plan: JSON.parse(raw) as RunnerPlan,
      };
    }
  }

  throw new Error('No command plan provided. Set BRIDGE_RUNNER_TEMPLATE, BRIDGE_COMMANDS_JSON, BRIDGE_COMMANDS_FILE, or pipe JSON on stdin.');
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

function summarizeResults(results: RunnerResultRow[]) {
  const failureCount = results.filter(result => result.status !== 'success').length;
  return {
    totalCommands: results.length,
    successCount: results.length - failureCount,
    failureCount,
    commands: results.map(result => ({
      command: result.command,
      status: result.status,
      summary: result.response.status === 'success' ? result.response.result.summary : result.response.status,
    })),
  };
}

async function run(): Promise<void> {
  const controlUrl = getEnv('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788');
  const controlToken = getEnv('BRIDGE_CONTROL_TOKEN');
  const targetClientId = getEnv('BRIDGE_TARGET_CLIENT_ID');
  const autoApprove = getEnv('BRIDGE_AUTO_APPROVE', 'false') === 'true';
  const resolved = await loadPlan();
  const plan = resolved.plan;

  const sessionPayload = await getJson<ControlSessionsResponse>(`${controlUrl}/sessions`, controlToken);
  assert(sessionPayload.sessions.length > 0, 'No connected bridge sessions were found.');

  const clientId = targetClientId || plan.clientId || sessionPayload.sessions[0]?.clientId;
  assert(clientId, 'No bridge clientId available.');

  const results: RunnerResultRow[] = [];

  for (let index = 0; index < plan.requests.length; index += 1) {
    const step = plan.requests[index];
    const request = buildRequest(step, index);
    const commandName = `${request.command.domain}.${request.command.action}`;

    let response = await sendBridgeRequest(controlUrl, clientId, request, controlToken);
    if (response.status === 'confirmation_required' && autoApprove) {
      response = await sendBridgeRequest(
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
    }

    results.push({
      command: commandName,
      status: response.status,
      response,
    });
  }

  console.log(JSON.stringify({
    mode: resolved.mode,
    template: resolved.template,
    client: {
      clientId,
      pluginVersion: sessionPayload.sessions.find(session => session.clientId === clientId)?.pluginVersion,
      protocolVersion: sessionPayload.sessions.find(session => session.clientId === clientId)?.protocolVersion,
    },
    summary: summarizeResults(results),
    results,
  }, null, 2));
}

run().catch((error) => {
  console.error('Server command runner failed.');
  console.error(error);
  process.exitCode = 1;
});
