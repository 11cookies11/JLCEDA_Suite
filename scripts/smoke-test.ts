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
    getState_ComponentType: () => state.componentType,
    getState_SubPartName: () => state.subPartName,
    getState_Rotation: () => state.rotation,
    getState_Mirror: () => state.mirror,
    getState_AddIntoBom: () => state.addIntoBom,
    getState_AddIntoPcb: () => state.addIntoPcb,
    getState_Layer: () => state.layer,
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
      isEasyEDAProEdition: () => true,
      isJLCEDAProEdition: () => true,
      isProPrivateEdition: () => false,
      isOnlineMode: () => true,
      isHalfOfflineMode: () => false,
      isOfflineMode: () => false,
      getEditorCurrentVersion: () => 'v3.2.1',
      getEditorCompliedDate: () => '2026-04-08',
      getUserInfo: () => ({
        username: 'smoke-user',
        nickname: 'Smoke User',
        uuid: 'user-001',
      }),
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
      getAllProjectsUuid: async () => ['project-001', 'project-002'],
      getProjectInfo: async (projectUuid: string) => ({
        uuid: projectUuid,
        friendlyName: projectUuid === 'project-001' ? 'Demo Project' : 'Secondary Project',
        teamUuid: 'team-001',
        folderUuid: 'folder-001',
      }),
      openProject: async () => true,
      createProject: async () => 'project-002',
      getCurrentProjectInfo: async () => ({
        uuid: 'project-001',
        name: 'Demo Project',
        description: 'Smoke test project',
        teamUuid: 'team-001',
        folderUuid: 'folder-001',
        friendlyName: 'Demo Project',
        data: [
          {
            itemType: 'BOARD',
            name: 'Main Board',
            schematic: {
              itemType: 'SCHEMATIC',
              uuid: 'schematic-001',
              name: 'Main Schematic',
              page: [
                {
                  itemType: 'SCHEMATIC_PAGE',
                  uuid: 'page-001',
                  name: 'Page 1',
                  parentSchematicUuid: 'schematic-001',
                  showTitleBlock: true,
                  titleBlockData: {},
                },
              ],
              parentProjectUuid: 'project-001',
            },
            pcb: {
              itemType: 'PCB',
              uuid: 'pcb-001',
              name: 'Main PCB',
              parentProjectUuid: 'project-001',
              parentBoardName: 'Main Board',
            },
            parentProjectUuid: 'project-001',
          },
        ],
      }),
    },
    dmt_Workspace: {
      getAllWorkspacesInfo: async () => [
        { uuid: 'workspace-001', name: 'Local Workspace' },
        { uuid: 'workspace-002', name: 'Shared Workspace' },
      ],
      getCurrentWorkspaceInfo: async () => ({
        uuid: 'workspace-001',
        name: 'Local Workspace',
      }),
    },
    dmt_Team: {
      getAllTeamsInfo: async () => [
        { uuid: 'team-001', name: 'Personal', identity: 1 },
        { uuid: 'team-002', name: 'Hardware', identity: 2 },
      ],
      getAllInvolvedTeamInfo: async () => [
        { uuid: 'team-001', name: 'Personal', identity: 1 },
      ],
      getCurrentTeamInfo: async () => ({
        uuid: 'team-001',
        name: 'Personal',
        identity: 1,
      }),
    },
    dmt_Schematic: {
      createSchematic: async () => 'schematic-002',
      createSchematicPage: async () => 'page-002',
      getAllSchematicsInfo: async () => [
        {
          uuid: 'schematic-001',
          name: 'Main Schematic',
          page: [
            {
              itemType: 'SCHEMATIC_PAGE',
              uuid: 'page-001',
              name: 'Page 1',
              parentSchematicUuid: 'schematic-001',
              showTitleBlock: true,
              titleBlockData: {},
            },
          ],
          parentProjectUuid: 'project-001',
        },
      ],
      getAllSchematicPagesInfo: async () => [
        {
          itemType: 'SCHEMATIC_PAGE',
          uuid: 'page-001',
          name: 'Page 1',
          parentSchematicUuid: 'schematic-001',
          showTitleBlock: true,
          titleBlockData: {},
        },
      ],
      getCurrentSchematicInfo: async () => ({
        uuid: 'schematic-001',
        name: 'Main Schematic',
        page: [{
          itemType: 'SCHEMATIC_PAGE',
          uuid: 'page-001',
          name: 'Page 1',
          parentSchematicUuid: 'schematic-001',
          showTitleBlock: true,
          titleBlockData: {},
        }],
        parentProjectUuid: 'project-001',
      }),
      getSchematicInfo: async (schematicUuid: string) => ({
        uuid: schematicUuid,
        name: schematicUuid === 'schematic-001' ? 'Main Schematic' : 'Secondary Schematic',
        page: [{
          itemType: 'SCHEMATIC_PAGE',
          uuid: 'page-002',
          name: 'Page 2',
          parentSchematicUuid: schematicUuid,
          showTitleBlock: false,
          titleBlockData: {},
        }],
        parentProjectUuid: 'project-001',
      }),
      getSchematicPageInfo: async (pageUuid: string) => ({
        itemType: 'SCHEMATIC_PAGE',
        uuid: pageUuid,
        name: 'Page 2',
        parentSchematicUuid: 'schematic-002',
        showTitleBlock: false,
        titleBlockData: {},
      }),
      getCurrentSchematicPageInfo: async () => ({
        uuid: 'page-001',
        name: 'Page 1',
      }),
    },
    dmt_Pcb: {
      createPcb: async () => 'pcb-002',
      getAllPcbsInfo: async () => [
        {
          uuid: 'pcb-001',
          name: 'Main PCB',
          parentProjectUuid: 'project-001',
          parentBoardName: 'Main Board',
        },
      ],
      getCurrentPcbInfo: async () => ({
        uuid: 'pcb-001',
        name: 'Main PCB',
        parentProjectUuid: 'project-001',
        parentBoardName: 'Main Board',
      }),
      getPcbInfo: async (pcbUuid: string) => ({
        uuid: pcbUuid,
        name: pcbUuid === 'pcb-001' ? 'Main PCB' : 'Secondary PCB',
        parentProjectUuid: 'project-001',
        parentBoardName: 'Main Board',
      }),
    },
    dmt_Board: {
      createBoard: async () => 'Board-002',
      getAllBoardsInfo: async () => [
        {
          name: 'Main Board',
          parentProjectUuid: 'project-001',
          schematic: {
            uuid: 'schematic-001',
            name: 'Main Schematic',
            page: [],
            parentProjectUuid: 'project-001',
          },
          pcb: {
            uuid: 'pcb-001',
            name: 'Main PCB',
            parentProjectUuid: 'project-001',
            parentBoardName: 'Main Board',
          },
        },
      ],
      getBoardInfo: async (boardName: string) => ({
        name: boardName,
        parentProjectUuid: 'project-001',
        schematic: {
          uuid: 'schematic-001',
          name: 'Main Schematic',
          page: [],
          parentProjectUuid: 'project-001',
        },
        pcb: {
          uuid: 'pcb-001',
          name: 'Main PCB',
          parentProjectUuid: 'project-001',
          parentBoardName: boardName,
        },
      }),
      getCurrentBoardInfo: async () => ({
        name: 'Main Board',
        parentProjectUuid: 'project-001',
        schematic: {
          uuid: 'schematic-001',
          name: 'Main Schematic',
          page: [],
          parentProjectUuid: 'project-001',
        },
        pcb: {
          uuid: 'pcb-001',
          name: 'Main PCB',
          parentProjectUuid: 'project-001',
          parentBoardName: 'Main Board',
        },
      }),
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
        rotation: 0,
        mirror: false,
        addIntoBom: true,
        addIntoPcb: true,
      }),
      createNetFlag: async (
        identification: string,
        net: string,
        x: number,
        y: number,
      ) => createPrimitiveState({
        primitiveId: 'netflag-001',
        primitiveType: 'part',
        name: identification,
        net,
        x,
        y,
      }),
      createNetPort: async (
        direction: string,
        net: string,
        x: number,
        y: number,
      ) => createPrimitiveState({
        primitiveId: 'netport-001',
        primitiveType: 'part',
        name: direction,
        net,
        x,
        y,
      }),
      createShortCircuitFlag: async (x: number, y: number) => createPrimitiveState({
        primitiveId: 'short-001',
        primitiveType: 'part',
        name: 'short',
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
    sch_PrimitiveAttribute: {
      createNetLabel: async (x: number, y: number, net: string) =>
        createPrimitiveState({
          primitiveId: 'netlabel-001',
          primitiveType: 'attribute',
          name: net,
          net,
          x,
          y,
        }),
    },
    pcb_PrimitiveComponent: {
      create: async (
        component: { libraryUuid: string; uuid: string },
        layer: number,
        x: number,
        y: number,
        rotation?: number,
        primitiveLock?: boolean,
      ) => createPrimitiveState({
        primitiveId: 'pcb-cmp-001',
        primitiveType: 'component',
        name: `${component.libraryUuid}:${component.uuid}`,
        layer,
        x,
        y,
        rotation,
        addIntoBom: true,
        addIntoPcb: true,
        primitiveLock,
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
      name: 'ping bridge',
      request: {
        id: 'smoke-000',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'ping',
          payload: {
            echo: 'smoke-test',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'ping should succeed');
        if (response.status === 'success') {
          const resultData = response.result.data as { ok?: boolean; echo?: string | null };
          assert(resultData.ok === true, 'ping should report ok');
          assert(resultData.echo === 'smoke-test', 'ping should echo payload');
        }
      },
    },
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
      name: 'get inventory',
      request: {
        id: 'smoke-002a',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'get_inventory',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'inventory should succeed');
        if (response.status === 'success') {
          const data = response.result.data as { current?: { project?: { uuid?: string } } };
          assert(Boolean(data.current?.project?.uuid), 'inventory should include current project data');
        }
      },
    },
    {
      name: 'system environment',
      request: {
        id: 'smoke-002b',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'get_environment',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'environment should succeed');
      },
    },
    {
      name: 'list projects',
      request: {
        id: 'smoke-002c',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'list_projects',
          payload: {
            teamUuid: 'team-001',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'project list should succeed');
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
      name: 'annotate net without confirmation',
      request: {
        id: 'smoke-006',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'annotate_net',
          requiresConfirmation: false,
          payload: {
            netName: 'VCC',
            position: { x: 300, y: 400 },
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'annotate net should succeed when confirmation is disabled');
      },
    },
    {
      name: 'create net flag',
      request: {
        id: 'smoke-007',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'create_net_flag',
          requiresConfirmation: false,
          payload: {
            identification: 'Power',
            net: '3V3',
            position: { x: 12, y: 10 },
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'create net flag should succeed');
      },
    },
    {
      name: 'create net port',
      request: {
        id: 'smoke-008',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'create_net_port',
          requiresConfirmation: false,
          payload: {
            direction: 'BI',
            net: 'I2C_SCL',
            position: { x: 20, y: 20 },
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'create net port should succeed');
      },
    },
    {
      name: 'pcb footprint placement',
      request: {
        id: 'smoke-009',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'place_footprint',
          requiresConfirmation: false,
          payload: {
            libraryUuid: 'footprint-lib',
            uuid: 'fp-001',
            position: { x: 10, y: 10 },
            layer: 'top',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'pcb footprint placement should succeed');
      },
    },
    {
      name: 'project create/open flow',
      request: {
        id: 'smoke-010',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'create_project',
          requiresConfirmation: false,
          payload: {
            projectFriendlyName: 'Smoke Project',
            projectName: 'smoke-project',
            description: 'created in smoke test',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'project creation should succeed');
      },
    },
    {
      name: 'project info lookup',
      request: {
        id: 'smoke-011',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'get_project_info',
          payload: {
            projectUuid: 'project-001',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'project info should succeed');
      },
    },
    {
      name: 'schematic creation',
      request: {
        id: 'smoke-012',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'create_schematic',
          requiresConfirmation: false,
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'schematic creation should succeed');
      },
    },
    {
      name: 'pcb current info',
      request: {
        id: 'smoke-013',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'get_current_pcb_info',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'current pcb info should succeed');
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
