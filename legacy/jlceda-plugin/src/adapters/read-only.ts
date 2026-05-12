import type { BridgeCommandPayloadMap, BridgeResult } from '../bridge/protocol';
import { BRIDGE_PROTOCOL_VERSION } from '../bridge/protocol';
import { SUPPORTED_COMMANDS } from '../bridge/registry';

interface PrimitiveSnapshot {
  id: string;
  type: string;
}

interface SelectionSnapshot {
  documentKind: 'schematic' | 'pcb' | 'unknown';
  count: number;
  bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  primitives: PrimitiveSnapshot[];
}

function normalizeDocumentKind(documentType?: number): 'schematic' | 'pcb' | 'unknown' {
  if (documentType === 1) {
    return 'schematic';
  }

  if (documentType === 3) {
    return 'pcb';
  }

  return 'unknown';
}

function getPrimitiveStateValue(
  primitive: unknown,
  methodName: 'getState_PrimitiveId' | 'getState_PrimitiveType',
): string | undefined {
  if (!primitive || typeof primitive !== 'object') {
    return undefined;
  }

  const candidate = primitive as Record<string, unknown>;
  const method = candidate[methodName];

  if (typeof method !== 'function') {
    return undefined;
  }

  const value = method.call(primitive);
  return value === undefined || value === null ? undefined : String(value);
}

function serializePrimitiveSelection(primitives: unknown[]): PrimitiveSnapshot[] {
  return primitives.map((primitive, index) => ({
    id: getPrimitiveStateValue(primitive, 'getState_PrimitiveId') ?? `selection_${index + 1}`,
    type: getPrimitiveStateValue(primitive, 'getState_PrimitiveType') ?? 'unknown',
  }));
}

async function getSelectionSnapshot(): Promise<SelectionSnapshot> {
  const currentDocumentInfo = await eda.dmt_SelectControl.getCurrentDocumentInfo();
  const documentKind = normalizeDocumentKind(currentDocumentInfo?.documentType);

  if (documentKind === 'schematic') {
    const primitives = await eda.sch_SelectControl.getAllSelectedPrimitives();
    const bbox = primitives.length > 0
      ? await eda.sch_SelectControl.getPrimitivesBBox(primitives)
      : undefined;

    return {
      documentKind,
      count: primitives.length,
      bbox: bbox ? { x: bbox.x, y: bbox.y, width: bbox.width, height: bbox.height } : undefined,
      primitives: serializePrimitiveSelection(primitives),
    };
  }

  if (documentKind === 'pcb') {
    const primitives = await eda.pcb_SelectControl.getAllSelectedPrimitives();
    const bbox = primitives.length > 0
      ? await eda.pcb_SelectControl.getPrimitivesBBox(primitives)
      : undefined;

    return {
      documentKind,
      count: primitives.length,
      bbox: bbox ? { x: bbox.x, y: bbox.y, width: bbox.width, height: bbox.height } : undefined,
      primitives: serializePrimitiveSelection(primitives),
    };
  }

  return {
    documentKind,
    count: 0,
    primitives: [],
  };
}

export async function getBridgeStatusResult(): Promise<BridgeResult> {
  const language = await eda.sys_I18n.getCurrentLanguage();
  const frontendUnit = await eda.sys_Unit.getFrontendDataUnit();
  const getCurrentTheme = (eda.sys_Environment as {
    getCurrentTheme?: () => Promise<unknown>;
  }).getCurrentTheme;
  const theme = typeof getCurrentTheme === 'function'
    ? await getCurrentTheme.call(eda.sys_Environment)
    : 'unknown';

  return {
    summary: 'bridge status collected',
    data: {
      protocolVersion: BRIDGE_PROTOCOL_VERSION,
      runtime: {
        isClient: eda.sys_Environment.isClient(),
        isWeb: eda.sys_Environment.isWeb(),
        language,
        theme,
        frontendUnit,
      },
      supportedCommands: SUPPORTED_COMMANDS,
    },
  };
}

export async function pingBridgeResult(
  payload: BridgeCommandPayloadMap['system.ping'],
): Promise<BridgeResult> {
  const language = await eda.sys_I18n.getCurrentLanguage();

  return {
    summary: 'bridge ping acknowledged',
    data: {
      ok: true,
      protocolVersion: BRIDGE_PROTOCOL_VERSION,
      echo: payload.echo ?? null,
      runtime: {
        isClient: eda.sys_Environment.isClient(),
        isWeb: eda.sys_Environment.isWeb(),
        language,
      },
      timestamp: new Date().toISOString(),
    },
  };
}

export async function getDocumentSummaryResult(): Promise<BridgeResult> {
  const [
    currentDocumentInfo,
    currentProjectInfo,
    currentWorkspaceInfo,
    currentSchematicInfo,
    currentSchematicPageInfo,
    currentBoardInfo,
  ] = await Promise.all([
    eda.dmt_SelectControl.getCurrentDocumentInfo(),
    eda.dmt_Project.getCurrentProjectInfo(),
    eda.dmt_Workspace.getCurrentWorkspaceInfo(),
    eda.dmt_Schematic.getCurrentSchematicInfo(),
    eda.dmt_Schematic.getCurrentSchematicPageInfo(),
    eda.dmt_Board.getCurrentBoardInfo(),
  ]);

  const documentKind = normalizeDocumentKind(currentDocumentInfo?.documentType);
  const selectionSnapshot = await getSelectionSnapshot();

  return {
    summary: 'document summary collected',
    data: {
      document: currentDocumentInfo
        ? {
            kind: documentKind,
            type: currentDocumentInfo.documentType,
            uuid: currentDocumentInfo.uuid,
            tabId: currentDocumentInfo.tabId,
            parentProjectUuid: currentDocumentInfo.parentProjectUuid,
            parentLibraryUuid: currentDocumentInfo.parentLibraryUuid,
          }
        : undefined,
      workspace: currentWorkspaceInfo,
      project: currentProjectInfo
        ? {
            uuid: currentProjectInfo.uuid,
            name: currentProjectInfo.name,
            description: currentProjectInfo.description,
            dataCount: currentProjectInfo.data.length,
          }
        : undefined,
      schematic: currentSchematicInfo
        ? {
            uuid: currentSchematicInfo.uuid,
            name: currentSchematicInfo.name,
            pageCount: currentSchematicInfo.page.length,
          }
        : undefined,
      schematicPage: currentSchematicPageInfo
        ? {
            uuid: currentSchematicPageInfo.uuid,
            name: currentSchematicPageInfo.name,
          }
        : undefined,
      board: currentBoardInfo
        ? {
            name: currentBoardInfo.name,
            parentPcbUuid: currentBoardInfo.parentPcbUuid,
            parentSchematicUuid: currentBoardInfo.parentSchematicUuid,
          }
        : undefined,
      selection: {
        documentKind: selectionSnapshot.documentKind,
        count: selectionSnapshot.count,
      },
    },
  };
}

export async function getSelectionSnapshotResult(): Promise<BridgeResult> {
  const selectionSnapshot = await getSelectionSnapshot();

  return {
    summary: 'selection snapshot collected',
    data: selectionSnapshot,
    warnings: selectionSnapshot.documentKind === 'unknown'
      ? ['Current document is neither schematic nor PCB, selection support is limited.']
      : [],
  };
}
