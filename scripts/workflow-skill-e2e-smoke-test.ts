import { Buffer } from 'node:buffer';
import { execFile } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

async function readJson(request: http.IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.from(chunk));
  }
  const raw = Buffer.concat(chunks).toString('utf8').trim();
  return raw ? JSON.parse(raw) as unknown : {};
}

function writeJson(response: http.ServerResponse, statusCode: number, body: unknown): void {
  response.statusCode = statusCode;
  response.setHeader('content-type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(body));
}

function buildResult(action: string) {
  const results: Record<string, unknown> = {
    get_bridge_status: { summary: 'bridge status collected', data: { connected: true, activeDocumentKind: 'schematic' } },
    get_document_summary: { summary: 'document summary collected', data: { document: { kind: 'schematic' }, project: { name: 'Workflow Project' } } },
    get_selection_snapshot: { summary: 'selection snapshot collected', data: { selectedComponents: [{ designator: 'U1' }], selectedNets: ['VIN'] } },
    get_current_schematic_info: { summary: 'current schematic info collected', data: { name: 'Power Sheet', pageCount: 2 } },
    get_inventory: { summary: 'inventory collected', data: { components: [{ designator: 'U1', name: 'Buck Controller' }] } },
    inspect_connectivity: { summary: 'connectivity inspected', data: { issueCount: 0, issues: [] } },
    inspect_layout_hygiene: { summary: 'layout hygiene inspected', data: { diagnostics: { issueCount: 1, issues: [{ type: 'component_component_proximity', designator: 'U1', relatedDesignator: 'C3', message: 'U1 too close to C3' }] } } },
    place_component: { summary: 'component placed', data: { primitiveId: 'cmp-001' } },
    create_wire: { summary: 'wire created', data: { primitiveId: 'wire-001' } },
    annotate_net: { summary: 'net annotated', data: { primitiveId: 'net-001' } },
    save: { summary: 'document saved', data: { saved: true } },
    get_board_summary: { summary: 'board summary collected', data: { boardCount: 1, boards: [{ name: 'Main Board' }] } },
    get_current_pcb_info: { summary: 'current pcb info collected', data: { name: 'Main Board', layerCount: 2 } },
    get_calculating_ratline_status: { summary: 'ratline status collected', data: { active: true } },
  };
  return results[action] ?? { summary: `${action} completed`, data: { action } };
}

async function runNodeScript(scriptPath: string, envOverrides: NodeJS.ProcessEnv): Promise<string> {
  const { stdout } = await execFileAsync(process.execPath, [scriptPath], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      ...envOverrides,
    },
    timeout: 20000,
    maxBuffer: 1024 * 1024,
  });
  return stdout;
}

async function run(): Promise<void> {
  const port = 8798;
  const commands: string[] = [];
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', `http://${request.headers.host ?? '127.0.0.1:8798'}`);
    if (request.method === 'GET' && url.pathname === '/sessions') {
      writeJson(response, 200, {
        sessions: [{
          clientId: 'mock-client',
          pluginVersion: '0.1.25',
          protocolVersion: '0.1.0',
          supportedCommands: [],
          connectedAt: new Date().toISOString(),
          lastSeenAt: new Date().toISOString(),
        }],
      });
      return;
    }

    if (request.method === 'GET' && url.pathname === '/debug/session/mock-client') {
      writeJson(response, 200, {
        clientId: 'mock-client',
        pluginVersion: '0.1.25',
        protocolVersion: '0.1.0',
        activeRequestIds: [],
        recentRequests: [],
      });
      return;
    }

    if (request.method === 'POST' && url.pathname === '/request') {
      const body = await readJson(request) as { request?: { command?: { domain?: string; action?: string } } };
      const action = body.request?.command?.action ?? 'unknown';
      const domain = body.request?.command?.domain ?? 'unknown';
      commands.push(`${domain}.${action}`);
      writeJson(response, 200, {
        response: {
          id: 'mock-response',
          type: 'command.response',
          protocolVersion: '0.1.0',
          status: 'success',
          result: buildResult(action),
        },
      });
      return;
    }

    writeJson(response, 404, { error: 'not_found' });
  });

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve());
  });

  try {
    const skillRoot = path.join(process.cwd(), 'skills', 'jlceda-suite-skill', 'scripts');
    const baseEnv = {
      BRIDGE_CONTROL_URL: `http://127.0.0.1:${port}`,
      BRIDGE_TARGET_CLIENT_ID: 'mock-client',
    };

    const contextStdout = await runNodeScript(path.join(skillRoot, 'server-context-summary.mjs'), baseEnv);
    if (!contextStdout.includes('"suggestedNextSteps"')) {
      throw new Error('workflow e2e should include context next steps');
    }

    const selectionStdout = await runNodeScript(path.join(skillRoot, 'server-part-selector.mjs'), {
      ...baseEnv,
      BRIDGE_SELECTION_REQUIREMENTS_JSON: JSON.stringify({
        role: 'buck regulator',
        functionBlock: 'power-input',
        minVoltage: 20,
        minCurrentMa: 1500,
        preferredPackage: 'SOIC-8',
      }),
      BRIDGE_SELECTION_CANDIDATES_JSON: JSON.stringify([
        { name: 'Part A', manufacturer: 'VendorA', mfrPartNumber: 'VA-1', package: 'SOIC-8', voltage: 40, currentMa: 3000, availability: 'high', lifecycle: 'active' },
        { name: 'Part B', manufacturer: 'VendorB', mfrPartNumber: 'VB-2', package: 'SOT-23', voltage: 24, currentMa: 800, availability: 'medium', lifecycle: 'active' },
      ]),
    });
    if (!selectionStdout.includes('"recommendation"')) {
      throw new Error('workflow e2e should include part recommendation');
    }

    const designStdout = await runNodeScript(path.join(skillRoot, 'server-schematic-refine.mjs'), {
      ...baseEnv,
      BRIDGE_SCHEMATIC_EDIT_PLAN_JSON: JSON.stringify([
        { kind: 'place_component', payload: { libraryUuid: 'lib-001', uuid: 'sym-001', position: { x: 120, y: 120 } }, note: 'place regulator' },
        { kind: 'create_wire', payload: { points: [{ x: 120, y: 120 }, { x: 220, y: 120 }], netName: 'VIN' }, note: 'connect input rail' },
        { kind: 'annotate_net', payload: { netName: 'VIN', position: { x: 180, y: 90 } }, note: 'label vin' },
        { kind: 'save' },
      ]),
      BRIDGE_SCHEMATIC_DECISIONS_JSON: JSON.stringify([
        { title: 'power-block', rationale: 'Place the regulator chain before feedback details', verification: 'Check VIN label and regulator placement' },
      ]),
    });
    if (!designStdout.includes('"validation"')) {
      throw new Error('workflow e2e should include schematic validation');
    }

    const pcbStdout = await runNodeScript(path.join(skillRoot, 'server-pcb-assist.mjs'), {
      ...baseEnv,
      BRIDGE_PCB_ASSIST_OPTIONS_JSON: JSON.stringify({
        focusAreas: ['power-input'],
        goals: ['keep switch-node loop short'],
        componentClearance: 120,
        trackClearance: 70,
        boardEdgeClearance: 60,
      }),
    });
    if (!pcbStdout.includes('"layoutAdvice"')) {
      throw new Error('workflow e2e should include pcb layout advice');
    }

    const expectedCommands = [
      'system.get_bridge_status',
      'project.get_document_summary',
      'project.get_selection_snapshot',
      'schematic.get_current_schematic_info',
      'project.get_inventory',
      'schematic.place_component',
      'schematic.create_wire',
      'schematic.annotate_net',
      'schematic.save',
      'pcb.get_board_summary',
      'pcb.get_current_pcb_info',
      'pcb.inspect_layout_hygiene',
      'pcb.get_calculating_ratline_status',
    ];

    for (const command of expectedCommands) {
      if (!commands.includes(command)) {
        throw new Error(`workflow e2e should execute command: ${command}`);
      }
    }

    console.log('PASS workflow skill e2e');
  }
  finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }
}

run().catch((error) => {
  console.error('Workflow skill e2e smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
