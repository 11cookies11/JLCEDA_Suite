import type { BridgeRequest, BridgeResponse } from '../src/bridge/protocol';
import process from 'node:process';

interface Req {
  role: string;
  functionBlock?: string;
  keywords?: string[];
  minVoltage?: number;
  minCurrentMa?: number;
  tolerancePercent?: number;
  preferredPackage?: string;
  requiredPackage?: string;
  maxUnitPrice?: number;
  preferredManufacturer?: string;
  availabilityPriority?: 'low' | 'medium' | 'high';
}

interface Candidate {
  name: string;
  manufacturer?: string;
  mfrPartNumber?: string;
  package?: string;
  voltage?: number;
  currentMa?: number;
  tolerancePercent?: number;
  unitPrice?: number;
  availability?: 'unknown' | 'low' | 'medium' | 'high';
  lifecycle?: 'unknown' | 'active' | 'not_recommended' | 'obsolete';
  pinInfo?: {
    available: boolean;
    pinCount?: number;
    source?: string;
    note?: string;
  };
}

function env(name: string, fallback = ''): string {
  const value = process.env[name];
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

function parseJson<T>(name: string, fallback: T): T {
  const value = env(name);
  return value ? JSON.parse(value) as T : fallback;
}

const normalize = (value?: string) => (value ?? '').trim().toLowerCase();
const requestOf = (id: string, domain: BridgeRequest['command']['domain'], action: BridgeRequest['command']['action']): BridgeRequest => ({ id, type: 'command.request', protocolVersion: '0.1.0', sessionId: 'server-part-selector', command: { domain, action, requiresConfirmation: false, payload: {} } } as BridgeRequest);
async function getJson<T>(url: string, token?: string): Promise<T> {
  const response = await fetch(url, {
    headers: token ? { 'x-bridge-control-token': token } : undefined,
  });
  if (!response.ok) {
    throw new Error(`Control query failed: ${response.status} ${response.statusText}`);
  }
  return await response.json() as T;
}

async function post(url: string, clientId: string, request: BridgeRequest, token?: string) {
  try {
    const response = await fetch(`${url}/request`, {
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
function score(requirements: Req, candidate: Candidate) {
  let total = 0;
  const reasons: string[] = [];
  const risks: string[] = [];
  const pinInfo = candidate.pinInfo;
  const preferredPackage = normalize(requirements.preferredPackage || requirements.requiredPackage);
  const candidatePackage = normalize(candidate.package);

  if (!pinInfo?.available) {
    total -= 100;
    risks.push('pin geometry is not verified');
  }
  else {
    total += 18;
    const pinSummary = typeof pinInfo.pinCount === 'number' ? `${pinInfo.pinCount} pins` : 'pin geometry verified';
    reasons.push(pinSummary + (pinInfo.source ? ` via ${pinInfo.source}` : ''));
  }

  if (preferredPackage && candidatePackage) {
    if (candidatePackage.includes(preferredPackage) || preferredPackage.includes(candidatePackage)) {
      total += 20;
      reasons.push(`package matches preference: ${candidate.package}`);
    }
    else {
      risks.push(`package mismatch: ${candidate.package}`);
    }
  }

  if (typeof requirements.minVoltage === 'number' && typeof candidate.voltage === 'number') {
    if (candidate.voltage >= requirements.minVoltage) {
      total += 12;
      reasons.push(`voltage headroom ok: ${candidate.voltage}V`);
    }
    else {
      risks.push(`voltage too low: ${candidate.voltage}V < ${requirements.minVoltage}V`);
    }
  }

  if (typeof requirements.minCurrentMa === 'number' && typeof candidate.currentMa === 'number') {
    if (candidate.currentMa >= requirements.minCurrentMa) {
      total += 12;
      reasons.push(`current capability ok: ${candidate.currentMa}mA`);
    }
    else {
      risks.push(`current too low: ${candidate.currentMa}mA < ${requirements.minCurrentMa}mA`);
    }
  }

  if (typeof requirements.maxUnitPrice === 'number' && typeof candidate.unitPrice === 'number') {
    if (candidate.unitPrice <= requirements.maxUnitPrice) {
      total += 10;
      reasons.push(`price within budget: ${candidate.unitPrice}`);
    }
    else {
      risks.push(`price above budget: ${candidate.unitPrice} > ${requirements.maxUnitPrice}`);
    }
  }

  if (requirements.preferredManufacturer && candidate.manufacturer && normalize(candidate.manufacturer) === normalize(requirements.preferredManufacturer)) {
    total += 8;
    reasons.push(`preferred manufacturer: ${candidate.manufacturer}`);
  }

  if (candidate.availability === 'high') {
    total += requirements.availabilityPriority === 'high' ? 18 : 10;
    reasons.push('availability is strong');
  }
  else if (candidate.availability === 'low') {
    risks.push('availability risk is high');
  }

  if (candidate.lifecycle === 'active') {
    total += 8;
    reasons.push('lifecycle is active');
  }
  else if (candidate.lifecycle === 'not_recommended' || candidate.lifecycle === 'obsolete') {
    risks.push(`lifecycle risk: ${candidate.lifecycle}`);
  }

  if (typeof requirements.tolerancePercent === 'number' && typeof candidate.tolerancePercent === 'number') {
    if (candidate.tolerancePercent <= requirements.tolerancePercent) {
      total += 6;
      reasons.push(`tolerance ok: +/-${candidate.tolerancePercent}%`);
    }
    else {
      risks.push(`tolerance may be too wide: +/-${candidate.tolerancePercent}%`);
    }
  }

  return { candidate, score: total, reasons, risks };
}

function searchPlan(requirements: Req) {
  return {
    keywords: Array.from(new Set([
      requirements.role,
      requirements.functionBlock ?? '',
      ...(requirements.keywords ?? []),
      requirements.preferredPackage ?? '',
      requirements.preferredManufacturer ?? '',
    ].map(item => item.trim()).filter(Boolean))),
    informationGaps: [
      'pin geometry confirmation for the candidate library symbol',
      typeof requirements.minVoltage === 'number' ? '' : 'missing voltage constraint',
      typeof requirements.minCurrentMa === 'number' ? '' : 'missing current constraint',
      requirements.preferredPackage || requirements.requiredPackage ? '' : 'missing package constraint',
      typeof requirements.maxUnitPrice === 'number' ? '' : 'missing cost ceiling',
    ].filter(Boolean),
  };
}
async function run() {
  const controlUrl = env('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788');
  const controlToken = env('BRIDGE_CONTROL_TOKEN');
  const requirements = parseJson<Req>('BRIDGE_SELECTION_REQUIREMENTS_JSON', { role: 'unspecified-component' });
  const candidates = parseJson<Candidate[]>('BRIDGE_SELECTION_CANDIDATES_JSON', []);
  if (!requirements.role) {
    throw new Error('BRIDGE_SELECTION_REQUIREMENTS_JSON.role is required.');
  }

  const sessionsPayload = await getJson<{ sessions: Array<{ clientId: string; pluginVersion: string; protocolVersion: string }> }>(`${controlUrl}/sessions`, controlToken);
  const clientId = env('BRIDGE_TARGET_CLIENT_ID') || sessionsPayload.sessions[0]?.clientId;
  if (!clientId) {
    throw new Error('No bridge clientId available.');
  }

  const [documentSummary, selectionSnapshot, currentSchematic, inventory] = await Promise.all([
    post(controlUrl, clientId, requestOf('selection-001', 'project', 'get_document_summary'), controlToken),
    post(controlUrl, clientId, requestOf('selection-002', 'project', 'get_selection_snapshot'), controlToken),
    post(controlUrl, clientId, requestOf('selection-003', 'schematic', 'get_current_schematic_info'), controlToken),
    post(controlUrl, clientId, requestOf('selection-004', 'project', 'get_inventory'), controlToken),
  ]);

  const ranked = candidates.map(candidate => score(requirements, candidate)).sort((a, b) => b.score - a.score);
  const winner = ranked[0]?.candidate;
  const recommendation = winner
    ? {
        candidate: winner,
        reasons: ranked[0]?.reasons ?? [],
        risks: ranked[0]?.risks ?? [],
        bomNote: [
          `role=${requirements.role}`,
          winner.manufacturer ? `manufacturer=${winner.manufacturer}` : '',
          winner.mfrPartNumber ? `mpn=${winner.mfrPartNumber}` : '',
          winner.package ? `package=${winner.package}` : '',
        ].filter(Boolean).join(' | '),
        verificationChecklist: [
          'Confirm the symbol pinout is available and matches the intended device.',
          'Confirm key electrical limits fit the target block.',
          'Confirm package and PCB manufacturability constraints still fit.',
        ],
      }
    : undefined;

  console.log(JSON.stringify({
    client: { clientId, pluginVersion: sessionsPayload.sessions[0]?.pluginVersion, protocolVersion: sessionsPayload.sessions[0]?.protocolVersion },
    requirements,
    context: { documentSummary, selectionSnapshot, currentSchematic, inventory },
    candidateComparison: ranked,
    recommendation,
    searchPlan: ranked.length === 0 ? searchPlan(requirements) : undefined,
  }, null, 2));
}

run().catch((error) => {
  console.error('Server part selector failed.');
  console.error(error);
  process.exitCode = 1;
});
