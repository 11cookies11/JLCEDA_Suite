import type { BridgeRequest, BridgeResponse } from '../src/bridge/protocol';
import process from 'node:process';

interface PcbAssistOptions {
  componentClearance?: number;
  trackClearance?: number;
  labelClearance?: number;
  boardEdgeClearance?: number;
  maxIssues?: number;
  focusAreas?: string[];
  goals?: string[];
}

interface PcbIssueLike {
  type?: string;
  severity?: string;
  message?: string;
  designator?: string;
  relatedDesignator?: string;
  trackNet?: string;
}

function env(name: string, fallback = ''): string {
  const value = process.env[name];
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

function parseJson<T>(name: string, fallback: T): T {
  const value = env(name);
  return value ? JSON.parse(value) as T : fallback;
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
    sessionId: 'server-pcb-assist',
    command: {
      domain,
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

function extractIssues(payload: unknown): PcbIssueLike[] {
  if (!payload || typeof payload !== 'object') {
    return [];
  }
  const data = payload as { issues?: unknown; diagnostics?: { issues?: unknown } };
  if (Array.isArray(data.issues)) {
    return data.issues as PcbIssueLike[];
  }
  if (data.diagnostics && Array.isArray(data.diagnostics.issues)) {
    return data.diagnostics.issues as PcbIssueLike[];
  }
  return [];
}

function summarizeIssueTypes(issues: PcbIssueLike[]) {
  const counts = new Map<string, number>();
  for (const issue of issues) {
    const key = issue.type ?? 'unknown_issue';
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries()).map(([type, count]) => ({ type, count }));
}

function buildPlacementAdvice(issues: PcbIssueLike[], options: PcbAssistOptions): string[] {
  const advice = new Set<string>();
  const focusAreas = options.focusAreas ?? [];

  for (const issue of issues) {
    switch (issue.type) {
      case 'component_component_proximity':
        advice.add(`Spread ${issue.designator ?? 'the crowded component'} away from ${issue.relatedDesignator ?? 'neighboring parts'} before adding new footprints.`);
        break;
      case 'component_track_proximity':
      case 'component_label_track_proximity':
        advice.add(`Reserve routing channels around ${issue.designator ?? 'the affected component'} and re-check nearby net labels or tracks.`);
        break;
      case 'board_edge_component_proximity':
        advice.add(`Move ${issue.designator ?? 'edge-near components'} inward to recover board-edge clearance before final placement.`);
        break;
      case 'component_label_component_proximity':
        advice.add(`Untangle label density around ${issue.designator ?? 'the active block'} so silkscreen remains readable during PCB review.`);
        break;
      default:
        if (issue.message) {
          advice.add(`Review issue: ${issue.message}`);
        }
        break;
    }
  }

  if (focusAreas.some(area => area.toLowerCase().includes('power'))) {
    advice.add('Keep the power path compact: place regulators, input caps, and output caps as one tight cluster before routing detail nets.');
  }
  if (focusAreas.some(area => area.toLowerCase().includes('interface'))) {
    advice.add('Place interface connectors close to the board edge and preserve a clean fanout path back to the main control block.');
  }
  if (advice.size === 0) {
    advice.add('No immediate hygiene issues were reported. Continue with functional block placement and confirm anchor components before routing.');
  }

  return Array.from(advice).slice(0, 6);
}

function buildNextTasks(issues: PcbIssueLike[], options: PcbAssistOptions, ratlineActive: boolean): string[] {
  const tasks = new Set<string>();

  tasks.add('Review board summary and current PCB metadata before changing placement.');
  tasks.add('Place or regroup one function block at a time, then re-run PCB hygiene inspection.');

  if (issues.length > 0) {
    tasks.add('Resolve the highest-density PCB hygiene warnings before importing another large schematic change batch.');
  }
  else {
    tasks.add('With hygiene currently clear, continue placing the next critical function block and preserve routing channels.');
  }

  if (!ratlineActive) {
    tasks.add('Start or refresh ratline calculation after any meaningful placement change so connectivity guidance stays current.');
  }
  else {
    tasks.add('Use the live ratline result to shorten critical nets and reduce crossovers while the block layout is still flexible.');
  }

  for (const goal of options.goals ?? []) {
    tasks.add(`Keep the next PCB pass aligned with this goal: ${goal}`);
  }

  return Array.from(tasks).slice(0, 6);
}

async function run() {
  const controlUrl = env('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788');
  const controlToken = env('BRIDGE_CONTROL_TOKEN');
  const options = parseJson<PcbAssistOptions>('BRIDGE_PCB_ASSIST_OPTIONS_JSON', {});
  const sessionsPayload = await getJson<{ sessions: Array<{ clientId: string; pluginVersion: string; protocolVersion: string }> }>(`${controlUrl}/sessions`, controlToken);
  const clientId = env('BRIDGE_TARGET_CLIENT_ID') || sessionsPayload.sessions[0]?.clientId;
  if (!clientId) {
    throw new Error('No bridge clientId available.');
  }

  const [documentSummary, currentSchematic, boardSummary, currentPcb, hygiene, ratlineStatus] = await Promise.all([
    send(controlUrl, clientId, buildRequest('pcb-assist-001', 'project', 'get_document_summary'), controlToken),
    send(controlUrl, clientId, buildRequest('pcb-assist-002', 'schematic', 'get_current_schematic_info'), controlToken),
    send(controlUrl, clientId, buildRequest('pcb-assist-003', 'pcb', 'get_board_summary'), controlToken),
    send(controlUrl, clientId, buildRequest('pcb-assist-004', 'pcb', 'get_current_pcb_info'), controlToken),
    send(controlUrl, clientId, buildRequest('pcb-assist-005', 'pcb', 'inspect_layout_hygiene', {
      componentClearance: options.componentClearance,
      trackClearance: options.trackClearance,
      labelClearance: options.labelClearance,
      boardEdgeClearance: options.boardEdgeClearance,
      maxIssues: options.maxIssues,
    }), controlToken),
    send(controlUrl, clientId, buildRequest('pcb-assist-006', 'pcb', 'get_calculating_ratline_status'), controlToken),
  ]);

  const issues = extractIssues(hygiene.data);
  const ratlineData = ratlineStatus.data as { active?: boolean; isCalculating?: boolean } | undefined;
  const ratlineActive = Boolean(ratlineData?.active ?? ratlineData?.isCalculating);

  console.log(JSON.stringify({
    client: {
      clientId,
      pluginVersion: sessionsPayload.sessions[0]?.pluginVersion,
      protocolVersion: sessionsPayload.sessions[0]?.protocolVersion,
    },
    options,
    context: {
      documentSummary,
      currentSchematic,
      boardSummary,
      currentPcb,
      ratlineStatus,
    },
    hygiene: {
      inspection: hygiene,
      issueCount: issues.length,
      issueTypes: summarizeIssueTypes(issues),
      topIssues: issues.slice(0, 5),
    },
    layoutAdvice: buildPlacementAdvice(issues, options),
    nextTasks: buildNextTasks(issues, options, ratlineActive),
  }, null, 2));
}

run().catch((error) => {
  console.error('Server PCB assist failed.');
  console.error(error);
  process.exitCode = 1;
});
