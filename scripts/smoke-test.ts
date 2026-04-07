import type { BridgeRequest } from '../src/bridge/protocol';
import process from 'node:process';
import { executeBridgeRequest } from '../src/bridge/handlers';
import { BRIDGE_PROTOCOL_VERSION } from '../src/bridge/protocol';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function createMockFile(name: string, type: string, size: number): File {
  return {
    name,
    type,
    size,
  } as File;
}

function createPrimitiveState(state: Record<string, unknown>): Record<string, () => unknown> {
  return {
    getState_PrimitiveId: () => state.primitiveId,
    getState_PrimitiveType: () => state.primitiveType,
    getState_Name: () => state.name,
    getState_Net: () => state.net,
    getState_X: () => state.x,
    getState_Y: () => state.y,
    getState_Line: () => state.line,
  };
}

function installMockEda(): void {
  const edaMock = {
    sys_I18n: {
      getCurrentLanguage: async () => 'zh-CN',
    },
    sys_Environment: {
      isClient: () => true,
      isWeb: () => false,
      getCurrentTheme: async () => 'light',
    },
    sys_Unit: {
      getFrontendDataUnit: async () => 'mil',
    },
    sys_FileSystem: {
      saveFile: async () => undefined,
    },
    dmt_SelectControl: {
      getCurrentDocumentInfo: async () => ({
        documentType: 1,
        uuid: 'doc-001',
        tabId: 'tab-001',
        parentProjectUuid: 'project-001',
      }),
    },
    dmt_Project: {
      getCurrentProjectInfo: async () => ({
        uuid: 'project-001',
        name: 'Demo Project',
        description: 'Smoke test project',
        data: [{ uuid: 'sheet-001' }],
      }),
    },
    dmt_Workspace: {
      getCurrentWorkspaceInfo: async () => ({
        uuid: 'workspace-001',
        name: 'Local Workspace',
      }),
    },
    dmt_Schematic: {
      getCurrentSchematicInfo: async () => ({
        uuid: 'schematic-001',
        name: 'Main Schematic',
        page: [{ uuid: 'page-001' }],
      }),
      getCurrentSchematicPageInfo: async () => ({
        uuid: 'page-001',
        name: 'Page 1',
      }),
    },
    dmt_Board: {
      getCurrentBoardInfo: async () => undefined,
    },
    sch_SelectControl: {
      getAllSelectedPrimitives: async () => [
        createPrimitiveState({
          primitiveId: 'sel-001',
          primitiveType: 'part',
        }),
      ],
      getPrimitivesBBox: async () => ({
        x: 10,
        y: 20,
        width: 30,
        height: 40,
      }),
    },
    pcb_SelectControl: {
      getAllSelectedPrimitives: async () => [],
      getPrimitivesBBox: async () => ({
        x: 0,
        y: 0,
        width: 0,
        height: 0,
      }),
    },
    sch_PrimitiveComponent: {
      create: async (
        component: { libraryUuid: string; uuid: string },
        x: number,
        y: number,
      ) => createPrimitiveState({
        primitiveId: 'cmp-001',
        primitiveType: 'part',
        name: `${component.libraryUuid}:${component.uuid}`,
        net: undefined,
        x,
        y,
      }),
    },
    sch_PrimitiveWire: {
      create: async (line: Array<number> | Array<Array<number>>, net?: string) =>
        createPrimitiveState({
          primitiveId: 'wire-001',
          primitiveType: 'wire',
          net: net ?? '',
          line,
        }),
    },
    sch_ManufactureData: {
      getBomFile: async (fileName?: string, fileType?: 'xlsx' | 'csv') =>
        createMockFile(fileName ?? `demo.${fileType ?? 'xlsx'}`, 'text/csv', 128),
    },
  };

  (globalThis as { eda?: unknown }).eda = edaMock;
}

async function run(): Promise<void> {
  installMockEda();

  const cases: Array<{
    name: string;
    request: BridgeRequest;
    verify: (response: Awaited<ReturnType<typeof executeBridgeRequest>>) => void;
  }> = [
    {
      name: 'get bridge status',
      request: {
        id: 'smoke-001',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'get_bridge_status',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'bridge status should succeed');
      },
    },
    {
      name: 'get document summary',
      request: {
        id: 'smoke-002',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'get_document_summary',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'document summary should succeed');
      },
    },
    {
      name: 'confirmation gate for place component',
      request: {
        id: 'smoke-003',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'place_component',
          payload: {
            libraryUuid: 'lib-001',
            uuid: 'cmp-001',
            position: { x: 100, y: 200 },
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'confirmation_required', 'place component should require confirmation');
      },
    },
    {
      name: 'place component without confirmation',
      request: {
        id: 'smoke-004',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'place_component',
          requiresConfirmation: false,
          payload: {
            libraryUuid: 'lib-001',
            uuid: 'cmp-001',
            position: { x: 100, y: 200 },
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'place component should succeed when confirmation is disabled');
      },
    },
    {
      name: 'create wire without confirmation',
      request: {
        id: 'smoke-005',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'create_wire',
          requiresConfirmation: false,
          payload: {
            points: [
              { x: 100, y: 200 },
              { x: 200, y: 200 },
            ],
            netName: 'VCC',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'create wire should succeed when confirmation is disabled');
      },
    },
    {
      name: 'export bom without confirmation',
      request: {
        id: 'smoke-006',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'export_bom',
          requiresConfirmation: false,
          payload: {
            format: 'csv',
            fileName: 'demo-bom.csv',
            saveToLocal: false,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'export bom should succeed when confirmation is disabled');
      },
    },
    {
      name: 'unimplemented pcb command',
      request: {
        id: 'smoke-007',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'place_footprint',
          requiresConfirmation: false,
          payload: {
            footprintId: 'fp-001',
            position: { x: 10, y: 10 },
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'error', 'unimplemented pcb command should fail');
        if (response.status === 'error') {
          assert(response.error.code === 'UNSUPPORTED_ACTION', 'unimplemented pcb command should use UNSUPPORTED_ACTION');
        }
      },
    },
  ];

  for (const testCase of cases) {
    const response = await executeBridgeRequest(testCase.request);
    testCase.verify(response);
    console.log(`PASS ${testCase.name}`);
  }
}

run().catch((error) => {
  console.error('Smoke test failed.');
  console.error(error);
  process.exitCode = 1;
});
