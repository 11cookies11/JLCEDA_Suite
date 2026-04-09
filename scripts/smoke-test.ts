import type { BridgeRequest } from '../src/bridge/protocol';
import process from 'node:process';
import JSZip from 'jszip';
import { executeBridgeRequest } from '../src/bridge/handlers';
import { BRIDGE_PROTOCOL_VERSION } from '../src/bridge/protocol';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function createMockFile(name: string, type: string, size: number): File {
  const bytes = new Uint8Array(size).map((_, index) => index % 256);

  return {
    name,
    type,
    size,
    arrayBuffer: async () => bytes.buffer.slice(0),
  } as File;
}

async function createMockZipFile(entries: Record<string, string>): Promise<File | Blob> {
  const zip = new JSZip();

  for (const [name, content] of Object.entries(entries)) {
    zip.file(name, content);
  }

  const bytes = await zip.generateAsync({ type: 'uint8array', compression: 'DEFLATE' });
  const buffer = bytes.buffer.slice(0) as ArrayBuffer;

  if (typeof File !== 'undefined') {
    return new File([buffer], 'symbol.zip', { type: 'zip' });
  }

  return new Blob([buffer], { type: 'zip' });
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
    getState_Symbol: () => state.symbol,
  };
}

function installMockEda(): void {
  const extensionUserConfigs = new Map<string, unknown>([
    ['updateCheck.repoOwner', '11cookies11'],
    ['updateCheck.repoName', 'JLCEDA_AIAgent'],
  ]);
  const boardSource = [
    '{"type":"DOCHEAD"}||{"docType":"PCB","client":"smoke-board","uuid":"pcb-001","updateTime":1,"version":"1"}|',
    '{"type":"CANVAS","ticket":1,"id":"CANVAS"}||{"originX":0,"originY":0,"unit":"mm","gridXSize":5,"gridYSize":5,"snapXSize":5,"snapYSize":5,"altSnapXSize":0.0254,"altSnapYSize":0.0254,"gridType":"OUTLETS","multiGridType":"NONE","multiGridRatio":5,"highlightValue":0.5}|',
    '{"type":"ACTIVE_LAYER","ticket":2,"id":"ACTIVE_LAYER"}||{"layerId":1}|',
  ].join('\n');
  const schematicSource = [
    '{"type":"DOCHEAD"}||{"docType":"SCH_PAGE","client":"smoke-schematic","uuid":"schematic-001","updateTime":1,"version":"1"}|',
    '{"type":"CANVAS","ticket":1,"id":"CANVAS"}||{"originX":0,"originY":0}|',
    '{"type":"COMPONENT","ticket":2,"id":"cmp-001"}||{"partId":"smoke-part","x":100,"y":100,"rotation":0,"isMirror":false,"attrs":{},"componentType":"part","designator":"R1","name":"Demo Part","uniqueId":"u-001"}|',
    '{"type":"WIRE","ticket":3,"id":"wire-001"}||{"zIndex":1}|',
    '{"type":"LINE","ticket":4,"id":"line-001"}||{"startX":100,"startY":100,"endX":110,"endY":100,"lineGroup":"wire-001"}|',
    '{"type":"ATTR","ticket":5,"id":"net-001"}||{"parentId":"wire-001","key":"NET","value":"NET_A"}|',
  ].join('\n');
  const footprintSource = [
    '{"type":"DOCHEAD"}||{"docType":"PCB","client":"smoke-footprint","uuid":"fp-001","updateTime":1,"version":"1"}|',
    '{"type":"CANVAS","ticket":1,"id":"CANVAS"}||{"originX":0,"originY":0,"unit":"mm","gridXSize":5,"gridYSize":5,"snapXSize":5,"snapYSize":5,"altSnapXSize":0.0254,"altSnapYSize":0.0254,"gridType":"OUTLETS","multiGridType":"NONE","multiGridRatio":5,"highlightValue":0.5}|',
    '{"type":"PAD","ticket":2,"id":"p1"}||{"groupId":0,"netName":"","layerId":1,"num":"1","centerX":1,"centerY":-1,"padAngle":0,"hole":null,"defaultPad":{"padType":"RECT","width":1,"height":2,"radius":0},"specialPad":[],"padOffsetX":0,"padOffsetY":0,"relativeAngle":null,"plated":true,"padType":"NORMAL","topSolderExpansion":null,"bottomSolderExpansion":null,"topPasteExpansion":null,"bottomPasteExpansion":null,"locked":false,"zIndex":8,"connectMode":null,"spokeSpace":null,"spokeWidth":null,"spokeAngle":null,"unusedInnerLayers":[],"padLen":0,"attrsMap":{}}|',
    '{"type":"POLY","ticket":3,"id":"poly1"}||{"groupId":0,"netName":"","layerId":13,"width":1,"path":[["CIRCLE",0,0,1]],"locked":false,"zIndex":3,"polyType":"NORMAL"}|',
    '{"type":"ATTR","ticket":4,"id":"attr1"}||{"groupID":0,"parentId":"","layerId":3,"x":0,"y":0,"key":"Footprint","value":"FP-DEMO","keyVisible":false,"valueVisible":false,"fontFamily":"default","fontSize":10,"strokeWidth":1,"bold":0,"italic":0,"origin":"LEFT_BOTTOM","angle":0,"reverse":false,"expansion":0,"mirror":false,"locked":false,"zIndex":20,"specialColor":null}|',
  ].join('\n');
  let currentDocumentSource = boardSource;
  let lastFetchRequest: {
    url: string;
    authorization?: string;
  } | undefined;

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
    sys_Log: {
      add: () => undefined,
      clear: () => undefined,
      export: () => undefined,
      sort: async () => [
        {
          timestamp: 1,
          type: 'info',
          message: 'log line',
        },
      ],
      find: async () => [
        {
          timestamp: 2,
          type: 'warn',
          message: 'found line',
        },
      ],
    },
    sys_PanelControl: {
      openLeftPanel: () => undefined,
      closeLeftPanel: () => undefined,
      toggleLeftPanelLockState: () => undefined,
      isLeftPanelLocked: async () => false,
      openRightPanel: () => undefined,
      closeRightPanel: () => undefined,
      toggleRightPanelLockState: () => undefined,
      isRightPanelLocked: async () => false,
      openBottomPanel: () => undefined,
      closeBottomPanel: () => undefined,
      toggleBottomPanelLockState: () => undefined,
      isBottomPanelLocked: async () => true,
    },
    sys_Message: {
      showToastMessage: () => undefined,
      showFollowMouseTip: async () => undefined,
      removeFollowMouseTip: async () => undefined,
    },
    sys_Dialog: {
      showInformationMessage: () => undefined,
      showConfirmationMessage: () => undefined,
    },
    sys_Window: {
      open: () => undefined,
      openUI: async () => undefined,
      getCurrentTheme: async () => 'light',
      getUrlParam: (key: string) => (key === 'mode' ? 'demo' : null),
      getUrlAnchor: () => 'anchor-demo',
    },
    sys_ShortcutKey: {
      registerShortcutKey: async (
        shortcutKey: Array<string>,
        _title: string,
        callback: (shortcutKey: Array<string>) => Promise<void> | void,
        _documentType?: Array<number>,
        _scene?: Array<number>,
      ) => {
        await callback(shortcutKey);
        return true;
      },
      unregisterShortcutKey: async () => true,
      getShortcutKeys: async () => [
        {
          shortcutKey: ['CONTROL', 'S'],
          title: 'Save',
          documentType: [2],
          scene: [1],
        },
      ],
    },
    sys_Timer: {
      setIntervalTimer: (id: string, timeout: number, callback: () => Promise<void> | void) => {
        void callback();
        return true;
      },
      clearIntervalTimer: () => true,
      setTimeoutTimer: (id: string, timeout: number, callback: () => Promise<void> | void) => {
        void callback();
        return true;
      },
      clearTimeoutTimer: () => true,
    },
    sys_RightClickMenu: {
      changeMenu: async () => undefined,
    },
    sys_FileSystem: {
      saveFile: async () => undefined,
      getExtensionFile: async () => createMockFile('extension.bin', 'application/octet-stream', 16),
      saveFileToFileSystem: async () => true,
      listFilesOfFileSystem: async () => [
        {
          fileName: 'demo.txt',
          isDirectory: false,
          fullPath: '/tmp/demo.txt',
        },
      ],
      deleteFileInFileSystem: async () => true,
      getEdaPath: async () => '/opt/eda',
      getDocumentsPath: async () => '/home/user/Documents/JLCEDA',
      getLibrariesPaths: async () => ['/home/user/Libraries'],
      getProjectsPaths: async () => ['/home/user/Projects'],
    },
    sys_FileManager: {
      getProjectFile: async () => createMockFile('project.epro', 'application/octet-stream', 32),
      getDocumentFile: async () => createMockFile('document.epro', 'application/octet-stream', 24),
      getDocumentSource: async () => currentDocumentSource,
      getDocumentFootprintSources: async () => [
        {
          footprintUuid: 'footprint-001',
          documentSource: footprintSource,
        },
      ],
      setDocumentSource: async (source: string) => {
        currentDocumentSource = source;
        return true;
      },
      getSymbolFileBySymbolUuid: async () => createMockZipFile({
        'symbol-source.txt': [
          '{"type":"DOCHEAD"}||{"docType":"SCH_SYMBOL","client":"smoke-symbol","uuid":"sym-001","updateTime":1,"version":"1"}|',
          '{"type":"PIN","ticket":1,"id":"p1"}||{"x":0,"y":0,"pinNumber":"1","pinName":"A","rotation":0,"pinLength":10}|',
          '{"type":"PIN","ticket":2,"id":"p2"}||{"x":10,"y":0,"pinNumber":"2","pinName":"B","rotation":0,"pinLength":10}|',
        ].join('\n'),
      }),
      getProjectFileByProjectUuid: async () => createMockFile('project-by-uuid.epro', 'application/octet-stream', 32),
      getDeviceFileByDeviceUuid: async () => createMockFile('device.elibz', 'application/octet-stream', 32),
    },
    sys_Storage: {
      getExtensionAllUserConfigs: () => ({
        sample: true,
      }),
      setExtensionAllUserConfigs: async () => true,
      clearExtensionAllUserConfigs: async () => true,
      getExtensionUserConfig: (key: string) => extensionUserConfigs.get(key),
      setExtensionUserConfig: async (key: string, value: unknown) => {
        extensionUserConfigs.set(key, value);
        return true;
      },
      deleteExtensionUserConfig: async (key: string) => {
        extensionUserConfigs.delete(key);
        return true;
      },
    },
    sys_Tool: {
      netlistComparison: async () => [
        {
          type: 'Net',
          object: 'VCC',
          netlist1Name: ['A'],
          netlist2Name: ['B'],
        },
      ],
      schematicComparison: async () => ({ result: 'schematic-compare' }),
      pcbComparison: async () => ({ result: 'pcb-compare' }),
    },
    sys_HeaderMenu: {
      insertHeaderMenus: async () => undefined,
      removeHeaderMenus: () => undefined,
      replaceHeaderMenus: async () => undefined,
      insertSystemHeaderMenuItem: async () => ['system', 'help'],
      removeSystemHeaderMenuItem: async () => true,
    },
    sys_FormatConversion: {
      convertAltiumDesignerLibrariesToEasyEDASingleFile: async () =>
        createMockFile('converted.elibz', 'application/octet-stream', 40),
      convertAltiumDesignerLibrariesToEasyEDAMultiFiles: async () => [
        createMockFile('converted-1.elibz', 'application/octet-stream', 20),
        createMockFile('converted-2.elibz', 'application/octet-stream', 20),
      ],
      convertDisaLibrariesToEasyEDASingleFile: async () =>
        createMockFile('converted-disa.elibz', 'application/octet-stream', 40),
      convertDisaLibrariesToEasyEDAMultiFiles: async () => [
        createMockFile('converted-disa-1.elibz', 'application/octet-stream', 20),
      ],
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
    lib_Footprint: {
      get: async (footprintUuid: string, libraryUuid?: string) => ({
        libraryType: '4',
        uuid: footprintUuid,
        libraryUuid: libraryUuid ?? 'footprint-library-uuid',
        name: 'R0603',
        classification: ['RES-SMD'],
        description: 'Smoke test footprint',
      }),
      search: async () => [],
    },
    dmt_EditorControl: {
      openDocument: async (documentUuid: string) => {
        if (documentUuid === 'schematic-001' || documentUuid === '4c6b94fa004d00f4') {
          currentDocumentSource = schematicSource;
        }

        if (documentUuid === 'pcb-001' || documentUuid === '9d915095c87b8761') {
          currentDocumentSource = boardSource;
        }

        return `tab-${documentUuid}`;
      },
      openLibraryDocument: async (_libraryUuid: string, _libraryType: string, uuid: string) => {
        currentDocumentSource = footprintSource;
        return `tab-${uuid}`;
      },
      closeDocument: async () => true,
      getSplitScreenTree: async () => ({
        id: 'split-root',
        direction: 'horizontal',
        children: [],
      }),
      getSplitScreenIdByTabId: async (tabId: string) => `split-${tabId}`,
      getTabsBySplitScreenId: async (splitScreenId: string) => [
        {
          tabId: `${splitScreenId}-tab`,
          title: 'Demo Tab',
          draggable: true,
          isAbleDelete: true,
        },
      ],
      createSplitScreen: async (splitScreenType: string, tabId: string) => ({
        sourceSplitScreenId: `source-${splitScreenType}`,
        newSplitScreenId: `new-${tabId}`,
      }),
      moveDocumentToSplitScreen: async () => true,
      activateDocument: async () => true,
      activateSplitScreen: async () => true,
      tileAllDocumentToSplitScreen: async () => true,
      mergeAllDocumentFromSplitScreen: async () => true,
      getCurrentRenderedAreaImage: async () => new Blob(['fake-image'], { type: 'image/png' }),
      zoomToRegion: async () => ({ left: 0, right: 100, top: 100, bottom: 0 }),
      zoomTo: async () => ({ left: 0, right: 100, top: 100, bottom: 0 }),
      zoomToAllPrimitives: async () => ({ left: 0, right: 100, top: 100, bottom: 0 }),
      zoomToSelectedPrimitives: async () => ({ left: 10, right: 20, top: 20, bottom: 10 }),
    },
    sch_Document: {
      importChanges: async () => true,
      save: async () => true,
      navigateToCoordinates: async () => true,
      navigateToRegion: async () => true,
      getPrimitiveAtPoint: async (x: number, y: number) => createPrimitiveState({
        primitiveId: 'sch-point-001',
        primitiveType: 'part',
        name: 'point-hit',
        x,
        y,
      }),
      getPrimitivesInRegion: () => [
        createPrimitiveState({
          primitiveId: 'sch-region-001',
          primitiveType: 'wire',
          name: 'region-wire',
          line: [0, 0, 10, 10],
        }),
      ],
      getCurrentFilterConfiguration: async () => ({ parts: true, wires: true }),
      autoRouting: async () => ({ routed: true }),
      autoLayout: async () => ({ laidOut: true }),
    },
    sch_Drc: {
      check: async (_strict: boolean, _userInterface: boolean, includeVerboseError: boolean) =>
        (includeVerboseError ? [{ message: 'ok' }] : true),
    },
    pcb_Document: {
      importChanges: async () => true,
      save: async (_uuid: string) => true,
      getCalculatingRatlineStatus: async () => 'idle',
      startCalculatingRatline: async () => true,
      stopCalculatingRatline: async () => true,
      convertCanvasOriginToDataOrigin: async (x: number, y: number) => ({ x: x + 10, y: y + 20 }),
      convertDataOriginToCanvasOrigin: async (x: number, y: number) => ({ x: x - 10, y: y - 20 }),
      getCanvasOrigin: async () => ({ offsetX: 0, offsetY: 0 }),
      setCanvasOrigin: async () => true,
      navigateToCoordinates: async () => true,
      navigateToRegion: async () => true,
      getPrimitiveAtPoint: async (x: number, y: number) => createPrimitiveState({
        primitiveId: 'pcb-point-001',
        primitiveType: 'component',
        name: 'pcb-hit',
        x,
        y,
      }),
      getPrimitivesInRegion: async () => [
        createPrimitiveState({
          primitiveId: 'pcb-region-001',
          primitiveType: 'component',
          name: 'pcb-region',
        }),
      ],
      zoomToBoardOutline: async () => true,
      getCurrentFilterConfiguration: async () => ({ components: true, tracks: true }),
      clearRouting: async () => true,
    },
    pcb_Drc: {
      check: async (_strict: boolean, _userInterface: boolean, includeVerboseError: boolean) =>
        (includeVerboseError ? [{ message: 'pcb-ok' }] : true),
    },
    pnl_Document: {
      save: async () => true,
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
      getAll: async () => [
        createPrimitiveState({
          primitiveId: 'cmp-001',
          primitiveType: 'Component',
          componentType: 'part',
          designator: 'R1',
          name: 'Demo Part',
          x: 100,
          y: 100,
          rotation: 0,
          mirror: false,
          symbol: {
            libraryUuid: 'lib-001',
            uuid: 'sym-001',
          },
        }),
      ],
      getAllPinsByPrimitiveId: async () => [
        createPrimitiveState({
          primitiveId: 'cmp-001-p1',
          primitiveType: 'ComponentPin',
          x: 100,
          y: 100,
          pinNumber: '1',
          pinName: 'A',
          noConnected: false,
        }),
        createPrimitiveState({
          primitiveId: 'cmp-001-p2',
          primitiveType: 'ComponentPin',
          x: 110,
          y: 100,
          pinNumber: '2',
          pinName: 'B',
          noConnected: false,
        }),
      ],
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
      getAll: async () => [
        createPrimitiveState({
          primitiveId: 'wire-001',
          primitiveType: 'Wire',
          net: 'NET_A',
          line: [100, 100, 110, 100],
        }),
      ],
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
      ) => {
        if (component.uuid === 'fp-fallback-001') {
          throw new Error('Cannot convert undefined or null to object');
        }

        return createPrimitiveState({
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
        });
      },
    },
    sch_ManufactureData: {
      getBomFile: async (fileName?: string, fileType?: 'xlsx' | 'csv') =>
        createMockFile(fileName ?? `demo.${fileType ?? 'xlsx'}`, 'text/csv', 128),
    },
  };

  (globalThis as { eda?: unknown }).eda = edaMock;
  (globalThis as { fetch?: typeof fetch; __lastUpdateFetchRequest?: typeof lastFetchRequest }).fetch = async (input, init) => {
    const requestUrl = typeof input === 'string'
      ? input
      : input instanceof Request
        ? input.url
        : input && typeof input === 'object' && 'url' in input
          ? String((input as { url: string }).url)
          : String(input);

    const headers = new Headers(input instanceof Request ? input.headers : init?.headers);

    lastFetchRequest = {
      url: requestUrl,
      authorization: headers.get('authorization') ?? undefined,
    };

    (globalThis as { __lastUpdateFetchRequest?: typeof lastFetchRequest }).__lastUpdateFetchRequest = lastFetchRequest;

    return new Response(JSON.stringify({
      tag_name: 'v0.1.21',
      html_url: 'https://github.com/11cookies11/JLCEDA_AIAgent/releases/tag/v0.1.21',
      assets: [
        {
          name: 'jlceda-aiagent_v0.1.21.eext',
          browser_download_url: 'https://github.com/11cookies11/JLCEDA_AIAgent/releases/download/v0.1.21/jlceda-aiagent_v0.1.21.eext',
        },
      ],
    }), {
      status: 200,
      headers: {
        'content-type': 'application/json',
      },
    });
  };
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
      name: 'system update check',
      request: {
        id: 'smoke-002b1a',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'check_for_updates',
          payload: {
            force: true,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'update check should succeed');
        if (response.status === 'success') {
          const data = response.result.data as {
            updateAvailable?: boolean;
            latestVersion?: string;
            latestDownloadUrl?: string;
          };
          assert(data.updateAvailable === true, 'update check should report a newer release');
          assert(data.latestVersion === 'v0.1.21', 'update check should surface the mocked latest version');
          assert(data.latestDownloadUrl?.includes('v0.1.21'), 'update check should surface the mocked download url');
        }
      },
    },
    {
      name: 'system update status',
      request: {
        id: 'smoke-002b1b',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'get_update_status',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'update status should succeed');
        if (response.status === 'success') {
          const data = response.result.data as {
            updateAvailable?: boolean;
            latestVersion?: string;
          };
          assert(data.updateAvailable === true, 'update status should persist the update check result');
          assert(data.latestVersion === 'v0.1.21', 'update status should expose the mocked latest version');
        }
      },
    },
    {
      name: 'save update config',
      request: {
        id: 'smoke-002b1c',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'save_update_config',
          payload: {
            repoOwner: 'private-owner',
            repoName: 'private-repo',
            githubToken: 'ghp_private_token',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'save update config should succeed');
      },
    },
    {
      name: 'get update config',
      request: {
        id: 'smoke-002b1d',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'get_update_config',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'get update config should succeed');
        if (response.status === 'success') {
          const data = response.result.data as {
            repoOwner?: string;
            repoName?: string;
            githubTokenConfigured?: boolean;
          };
          assert(data.repoOwner === 'private-owner', 'update config should store repo owner');
          assert(data.repoName === 'private-repo', 'update config should store repo name');
          assert(data.githubTokenConfigured === true, 'update config should store token state');
        }
      },
    },
    {
      name: 'system private update check',
      request: {
        id: 'smoke-002b1e',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'check_for_updates',
          payload: {
            force: true,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'private update check should succeed');
        if (response.status === 'success') {
          const data = response.result.data as {
            updateAvailable?: boolean;
            latestVersion?: string;
          };
          const fetchRequest = (globalThis as { __lastUpdateFetchRequest?: { url: string; authorization?: string } }).__lastUpdateFetchRequest;
          assert(fetchRequest?.url.includes('/repos/private-owner/private-repo/releases/latest'), 'private update check should target configured repo');
          assert(fetchRequest?.authorization === 'Bearer ghp_private_token', 'private update check should send GitHub auth token');
          assert(data.updateAvailable === true, 'private update check should report a newer release');
          assert(data.latestVersion === 'v0.1.21', 'private update check should surface the mocked latest version');
        }
      },
    },
    {
      name: 'system generic api invoke',
      request: {
        id: 'smoke-002b00',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'api_invoke',
          requiresConfirmation: false,
          payload: {
            path: 'dmt_Project.getCurrentProjectInfo',
            args: [],
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'generic api invoke should succeed');
      },
    },
    {
      name: 'system file system path',
      request: {
        id: 'smoke-002b0',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'file_system_get_eda_path',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'eda path should succeed');
      },
    },
    {
      name: 'system log add',
      request: {
        id: 'smoke-002b1',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'log_add',
          payload: {
            message: 'smoke-log-line',
            type: 'info',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'log add should succeed');
      },
    },
    {
      name: 'system extension file',
      request: {
        id: 'smoke-002b1a',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'file_system_get_extension_file',
          payload: {
            uri: 'demo.bin',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'extension file should succeed');
      },
    },
    {
      name: 'system file manager source',
      request: {
        id: 'smoke-002b1b',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'file_manager_get_document_source',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'document source should succeed');
      },
    },
    {
      name: 'system storage configs',
      request: {
        id: 'smoke-002b1c',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'storage_get_all_user_configs',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'storage should succeed');
      },
    },
    {
      name: 'system tool netlist compare',
      request: {
        id: 'smoke-002b1d',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'tool_netlist_comparison',
          payload: {
            left: 'project-001',
            right: 'project-002',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'tool comparison should succeed');
      },
    },
    {
      name: 'system header menu insert',
      request: {
        id: 'smoke-002b1e',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'header_menu_insert_system_item',
          payload: {
            env: 'home',
            id: ['home', 'demo'],
            props: {
              title: 'Demo Menu',
            },
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'header menu insertion should succeed');
      },
    },
    {
      name: 'system format conversion',
      request: {
        id: 'smoke-002b1f',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'format_conversion_ad_single',
          payload: {
            files: {
              fileName: 'library.lib',
              contentText: 'demo',
            },
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'format conversion should succeed');
      },
    },
    {
      name: 'system panel state',
      request: {
        id: 'smoke-002b2',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'panel_is_left_locked',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'panel state should succeed');
      },
    },
    {
      name: 'system window theme',
      request: {
        id: 'smoke-002b3',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'window_get_current_theme',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'window theme should succeed');
      },
    },
    {
      name: 'system shortcuts',
      request: {
        id: 'smoke-002b4',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'shortcut_get_shortcuts',
          payload: {
            includeSystem: false,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'shortcuts should succeed');
      },
    },
    {
      name: 'system toast message',
      request: {
        id: 'smoke-002b5',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'show_toast_message',
          payload: {
            message: 'hello from smoke test',
            messageType: 'info',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'toast message should succeed');
      },
    },
    {
      name: 'system shortcut register callback',
      request: {
        id: 'smoke-002b6',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'shortcut_register',
          requiresConfirmation: false,
          payload: {
            shortcutKey: ['CONTROL', 'SHIFT', 'S'],
            title: 'Smoke Save Callback',
            documentType: [2],
            scene: [1],
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'shortcut register should succeed');
      },
    },
    {
      name: 'system shortcut list registered',
      request: {
        id: 'smoke-002b7',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'shortcut_list_registered',
          payload: {
            includeSystem: false,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'shortcut list should succeed');
        if (response.status === 'success') {
          const data = response.result.data as { shortcuts?: Array<{ title?: string }>; count?: number };
          assert((data.count ?? 0) >= 1, 'shortcut list should include entries');
        }
      },
    },
    {
      name: 'system timer set interval',
      request: {
        id: 'smoke-002b8',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'timer_set_interval',
          requiresConfirmation: false,
          payload: {
            id: 'interval-smoke',
            timeout: 250,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'timer interval should succeed');
      },
    },
    {
      name: 'system timer clear interval',
      request: {
        id: 'smoke-002b9',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'timer_clear_interval',
          requiresConfirmation: false,
          payload: {
            id: 'interval-smoke',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'timer clear interval should succeed');
      },
    },
    {
      name: 'system timer set timeout',
      request: {
        id: 'smoke-002ba',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'timer_set_timeout',
          requiresConfirmation: false,
          payload: {
            id: 'timeout-smoke',
            timeout: 500,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'timer timeout should succeed');
      },
    },
    {
      name: 'system timer clear timeout',
      request: {
        id: 'smoke-002bb',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'timer_clear_timeout',
          requiresConfirmation: false,
          payload: {
            id: 'timeout-smoke',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'timer clear timeout should succeed');
      },
    },
    {
      name: 'system right click menu change',
      request: {
        id: 'smoke-002bc',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'right_click_change_menu',
          requiresConfirmation: false,
          payload: {
            menuId: 'smoke-menu',
            menuItems: [
              {
                id: 'smoke-menu-item',
                title: 'Smoke Action',
              },
            ],
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'right click menu should succeed');
      },
    },
    {
      name: 'callback events list',
      request: {
        id: 'smoke-002bd',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'callback_events_list',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'callback events list should succeed');
        if (response.status === 'success') {
          const data = response.result.data as {
            events?: Array<{ kind?: string; name?: string }>;
            count?: number;
          };
          assert((data.count ?? 0) >= 3, 'callback events should include shortcut and timer callbacks');
          const eventNames = new Set((data.events ?? []).map(event => event.name));
          assert(eventNames.has('shortcut.registered'), 'callback events should include shortcut registration');
          assert(eventNames.has('timer.interval'), 'callback events should include interval timer');
          assert(eventNames.has('timer.timeout'), 'callback events should include timeout timer');
        }
      },
    },
    {
      name: 'callback events drain',
      request: {
        id: 'smoke-002be',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'callback_events_drain',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'callback drain should succeed');
        if (response.status === 'success') {
          const data = response.result.data as { count?: number };
          assert((data.count ?? 0) >= 3, 'callback drain should return recorded events');
        }
      },
    },
    {
      name: 'callback events list empty',
      request: {
        id: 'smoke-002bf',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'system',
          action: 'callback_events_list',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'callback events list after drain should succeed');
        if (response.status === 'success') {
          const data = response.result.data as { count?: number };
          assert((data.count ?? 0) === 0, 'callback queue should be empty after drain');
        }
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
      name: 'open document tab',
      request: {
        id: 'smoke-002d',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'open_document',
          payload: {
            documentUuid: 'schematic-001',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'open document should succeed');
      },
    },
    {
      name: 'split screen tree',
      request: {
        id: 'smoke-002e',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'get_split_screen_tree',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'split screen tree should succeed');
      },
    },
    {
      name: 'editor zoom to',
      request: {
        id: 'smoke-002f',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'zoom_to',
          payload: {
            x: 10,
            y: 20,
            scaleRatio: 200,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'editor zoom should succeed');
      },
    },
    {
      name: 'schematic import changes',
      request: {
        id: 'smoke-002g',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'import_changes',
          requiresConfirmation: false,
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'schematic import should succeed');
      },
    },
    {
      name: 'schematic save',
      request: {
        id: 'smoke-002h',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'save',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'schematic save should succeed');
      },
    },
    {
      name: 'schematic primitive lookup',
      request: {
        id: 'smoke-002i',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'get_primitive_at_point',
          payload: {
            x: 5,
            y: 6,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'schematic primitive lookup should succeed');
      },
    },
    {
      name: 'schematic region lookup',
      request: {
        id: 'smoke-002j',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'get_primitives_in_region',
          payload: {
            left: 0,
            right: 10,
            top: 10,
            bottom: 0,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'schematic region lookup should succeed');
      },
    },
    {
      name: 'schematic DRC',
      request: {
        id: 'smoke-002k',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'check_drc',
          requiresConfirmation: false,
          payload: {
            strict: true,
            userInterface: false,
            includeVerboseError: true,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'schematic DRC should succeed');
      },
    },
    {
      name: 'schematic connectivity inspection',
      request: {
        id: 'smoke-002ka',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'schematic',
          action: 'inspect_connectivity',
          requiresConfirmation: false,
          payload: {
            tolerance: 0.75,
            maxIssues: 10,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'schematic connectivity inspection should succeed');
        if (response.status === 'success') {
          const data = response.result.data as { issueCount?: number };
          assert(data.issueCount === 0, 'connectivity inspection should report no issues in the smoke fixture');
        }
      },
    },
    {
      name: 'pcb import changes',
      request: {
        id: 'smoke-002l',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'import_changes',
          requiresConfirmation: false,
          payload: {
            schematicUuid: 'schematic-001',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'pcb import should succeed');
      },
    },
    {
      name: 'pcb save',
      request: {
        id: 'smoke-002m',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'save',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'pcb save should succeed');
      },
    },
    {
      name: 'pcb ratline status',
      request: {
        id: 'smoke-002n',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'get_calculating_ratline_status',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'pcb ratline status should succeed');
      },
    },
    {
      name: 'pcb coordinate conversion',
      request: {
        id: 'smoke-002o',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'convert_canvas_origin_to_data_origin',
          payload: {
            x: 10,
            y: 20,
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'pcb coordinate conversion should succeed');
      },
    },
    {
      name: 'pcb canvas origin',
      request: {
        id: 'smoke-002p',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'get_canvas_origin',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'pcb canvas origin should succeed');
      },
    },
    {
      name: 'pcb zoom to outline',
      request: {
        id: 'smoke-002q',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'zoom_to_board_outline',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'pcb zoom to outline should succeed');
      },
    },
    {
      name: 'panel save',
      request: {
        id: 'smoke-002r',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'project',
          action: 'save_panel',
          payload: {},
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'panel save should succeed');
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
              { x: 100.4, y: 99.7 },
              { x: 109.8, y: 100.3 },
            ],
            netName: 'VCC',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'create wire should succeed when confirmation is disabled');
        if (response.status === 'success') {
          const resultData = response.result.data as {
            points?: Array<{ x?: number; y?: number }>;
          } | undefined;
          const points = resultData?.points;
          assert(points?.[0]?.x === 100 && points?.[0]?.y === 100, 'wire start should snap to the nearest pin');
          assert(points?.[1]?.x === 110 && points?.[1]?.y === 100, 'wire end should snap to the nearest pin');
        }
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
      name: 'pcb footprint placement fallback',
      request: {
        id: 'smoke-009a',
        type: 'command.request',
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        sessionId: 'smoke-session',
        command: {
          domain: 'pcb',
          action: 'place_footprint',
          requiresConfirmation: false,
          payload: {
            libraryUuid: 'footprint-lib',
            uuid: 'fp-fallback-001',
            position: { x: 30, y: 30 },
            layer: 'top',
          },
        },
      },
      verify: (response) => {
        assert(response.status === 'success', 'pcb footprint fallback should succeed');
        if (response.status === 'success') {
          const data = response.result.data as { placementMode?: string };
          assert(data.placementMode === 'source_fallback', 'pcb footprint fallback should use source fallback');
        }
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
