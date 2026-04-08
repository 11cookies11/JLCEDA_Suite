import type { BridgePoint, BridgeResult } from '../bridge/protocol';

export interface OpenDocumentPayload {
  documentUuid: string;
  splitScreenId?: string;
}

export interface OpenLibraryDocumentPayload {
  libraryUuid: string;
  libraryType: 'symbol' | 'footprint';
  uuid: string;
  splitScreenId?: string;
}

export interface CloseDocumentPayload {
  tabId: string;
}

export interface CreateSplitScreenPayload {
  splitScreenType: 'horizontal' | 'vertical';
  tabId: string;
}

export interface MoveDocumentToSplitScreenPayload {
  tabId: string;
  splitScreenId: string;
}

export interface ZoomRegionPayload {
  left: number;
  right: number;
  top: number;
  bottom: number;
  tabId?: string;
}

export interface ZoomToPayload {
  x?: number;
  y?: number;
  scaleRatio?: number;
  tabId?: string;
}

export interface PointPayload extends BridgePoint {}

function summarizePrimitiveLike(primitive: unknown): Record<string, unknown> {
  if (!primitive || typeof primitive !== 'object') {
    return {};
  }

  const candidate = primitive as Record<string, unknown>;
  const read = (
    methodName:
      | 'getState_PrimitiveId'
      | 'getState_PrimitiveType'
      | 'getState_Name'
      | 'getState_Net'
      | 'getState_X'
      | 'getState_Y'
      | 'getState_Line'
      | 'getState_ComponentType'
      | 'getState_SubPartName'
      | 'getState_Rotation'
      | 'getState_Mirror'
      | 'getState_AddIntoBom'
      | 'getState_AddIntoPcb'
      | 'getState_Layer',
  ): unknown => {
    const method = candidate[methodName];

    if (typeof method !== 'function') {
      return undefined;
    }

    return method.call(primitive);
  };

  return {
    primitiveId: read('getState_PrimitiveId'),
    primitiveType: read('getState_PrimitiveType'),
    name: read('getState_Name'),
    net: read('getState_Net'),
    position: {
      x: read('getState_X'),
      y: read('getState_Y'),
    },
    line: read('getState_Line'),
    componentType: read('getState_ComponentType'),
    subPartName: read('getState_SubPartName'),
    rotation: read('getState_Rotation'),
    mirror: read('getState_Mirror'),
    addIntoBom: read('getState_AddIntoBom'),
    addIntoPcb: read('getState_AddIntoPcb'),
    layer: read('getState_Layer'),
  };
}

function summarizeBlob(blob: Blob | undefined): Record<string, unknown> | undefined {
  if (!blob) {
    return undefined;
  }

  return {
    size: blob.size,
    type: blob.type,
  };
}

async function safeCall<T>(operation: () => Promise<T>): Promise<T | undefined> {
  try {
    return await operation();
  }
  catch {
    return undefined;
  }
}

async function getCurrentSchematicUuid(): Promise<string | undefined> {
  const schematicInfo = (await safeCall(() => eda.dmt_Schematic.getCurrentSchematicInfo())) as
    | {
      uuid: string;
    }
    | undefined;
  return schematicInfo?.uuid;
}

async function getCurrentPcbUuid(): Promise<string | undefined> {
  const pcbInfo = (await safeCall(() => eda.dmt_Pcb.getCurrentPcbInfo())) as
    | {
      uuid: string;
    }
    | undefined;
  return pcbInfo?.uuid;
}

export async function getEditorSplitScreenTreeResult(): Promise<BridgeResult> {
  const splitScreenTree = await safeCall(() => eda.dmt_EditorControl.getSplitScreenTree());

  return {
    summary: 'editor split screen tree collected',
    data: {
      splitScreenTree,
    },
  };
}

export async function getEditorSplitScreenIdByTabIdResult(tabId: string): Promise<BridgeResult> {
  const splitScreenId = await eda.dmt_EditorControl.getSplitScreenIdByTabId(tabId);

  return {
    summary: 'editor split screen id collected',
    data: {
      tabId,
      splitScreenId,
    },
  };
}

export async function getEditorTabsBySplitScreenIdResult(splitScreenId: string): Promise<BridgeResult> {
  const tabs = await eda.dmt_EditorControl.getTabsBySplitScreenId(splitScreenId);

  return {
    summary: 'editor tabs collected',
    data: {
      splitScreenId,
      tabs,
      count: tabs.length,
    },
  };
}

export async function openDocumentResult(payload: OpenDocumentPayload): Promise<BridgeResult> {
  const tabId = await eda.dmt_EditorControl.openDocument(payload.documentUuid, payload.splitScreenId);

  if (!tabId) {
    throw new Error(`Failed to open document: ${payload.documentUuid}`);
  }

  return {
    summary: 'document opened',
    data: {
      documentUuid: payload.documentUuid,
      splitScreenId: payload.splitScreenId,
      tabId,
    },
  };
}

export async function openLibraryDocumentResult(payload: OpenLibraryDocumentPayload): Promise<BridgeResult> {
  const tabId = await eda.dmt_EditorControl.openLibraryDocument(
    payload.libraryUuid,
    (payload.libraryType === 'footprint' ? '4' : '2') as never,
    payload.uuid,
    payload.splitScreenId,
  );

  if (!tabId) {
    throw new Error(`Failed to open library document: ${payload.libraryUuid}/${payload.uuid}`);
  }

  return {
    summary: 'library document opened',
    data: {
      libraryUuid: payload.libraryUuid,
      libraryType: payload.libraryType,
      uuid: payload.uuid,
      splitScreenId: payload.splitScreenId,
      tabId,
    },
  };
}

export async function closeDocumentResult(tabId: string): Promise<BridgeResult> {
  const closed = await eda.dmt_EditorControl.closeDocument(tabId);

  if (!closed) {
    throw new Error(`Failed to close document: ${tabId}`);
  }

  return {
    summary: 'document closed',
    data: {
      tabId,
      closed: true,
    },
  };
}

export async function createSplitScreenResult(payload: CreateSplitScreenPayload): Promise<BridgeResult> {
  const splitScreen = await eda.dmt_EditorControl.createSplitScreen(
    (payload.splitScreenType === 'horizontal' ? 'horizontal' : 'vertical') as never,
    payload.tabId,
  );

  if (!splitScreen) {
    throw new Error(`Failed to create split screen for tab ${payload.tabId}.`);
  }

  return {
    summary: 'split screen created',
    data: {
      tabId: payload.tabId,
      splitScreenType: payload.splitScreenType,
      splitScreen,
    },
  };
}

export async function moveDocumentToSplitScreenResult(payload: MoveDocumentToSplitScreenPayload): Promise<BridgeResult> {
  const moved = await eda.dmt_EditorControl.moveDocumentToSplitScreen(payload.tabId, payload.splitScreenId);

  if (!moved) {
    throw new Error(`Failed to move tab ${payload.tabId} to split screen ${payload.splitScreenId}.`);
  }

  return {
    summary: 'document moved to split screen',
    data: {
      tabId: payload.tabId,
      splitScreenId: payload.splitScreenId,
      moved: true,
    },
  };
}

export async function activateDocumentResult(tabId: string): Promise<BridgeResult> {
  const activated = await eda.dmt_EditorControl.activateDocument(tabId);

  if (!activated) {
    throw new Error(`Failed to activate document: ${tabId}`);
  }

  return {
    summary: 'document activated',
    data: {
      tabId,
      activated: true,
    },
  };
}

export async function activateSplitScreenResult(splitScreenId: string): Promise<BridgeResult> {
  const activated = await eda.dmt_EditorControl.activateSplitScreen(splitScreenId);

  if (!activated) {
    throw new Error(`Failed to activate split screen: ${splitScreenId}`);
  }

  return {
    summary: 'split screen activated',
    data: {
      splitScreenId,
      activated: true,
    },
  };
}

export async function tileAllDocumentsToSplitScreenResult(): Promise<BridgeResult> {
  const tiled = await eda.dmt_EditorControl.tileAllDocumentToSplitScreen();

  if (!tiled) {
    throw new Error('Failed to tile all documents to split screens.');
  }

  return {
    summary: 'all documents tiled to split screen',
    data: {
      tiled: true,
    },
  };
}

export async function mergeAllDocumentsFromSplitScreenResult(): Promise<BridgeResult> {
  const merged = await eda.dmt_EditorControl.mergeAllDocumentFromSplitScreen();

  if (!merged) {
    throw new Error('Failed to merge all documents from split screens.');
  }

  return {
    summary: 'all documents merged from split screen',
    data: {
      merged: true,
    },
  };
}

export async function getCurrentRenderedAreaImageResult(tabId?: string): Promise<BridgeResult> {
  const image = await safeCall(() => eda.dmt_EditorControl.getCurrentRenderedAreaImage(tabId)) as Blob | undefined;

  return {
    summary: 'current rendered area image collected',
    data: {
      tabId,
      image: summarizeBlob(image),
    },
  };
}

export async function zoomToRegionResult(payload: ZoomRegionPayload): Promise<BridgeResult> {
  const zoomed = await eda.dmt_EditorControl.zoomToRegion(
    payload.left,
    payload.right,
    payload.top,
    payload.bottom,
    payload.tabId,
  );

  if (!zoomed) {
    throw new Error('Failed to zoom to the requested region.');
  }

  return {
    summary: 'zoomed to region',
    data: {
      ...payload,
      zoomed,
    },
  };
}

export async function zoomToResult(payload: ZoomToPayload): Promise<BridgeResult> {
  const zoomed = await eda.dmt_EditorControl.zoomTo(payload.x, payload.y, payload.scaleRatio, payload.tabId);

  if (!zoomed) {
    throw new Error('Failed to zoom to the requested area.');
  }

  return {
    summary: 'zoomed to area',
    data: {
      ...payload,
      zoomed,
    },
  };
}

export async function zoomToAllPrimitivesResult(tabId?: string): Promise<BridgeResult> {
  const zoomed = await eda.dmt_EditorControl.zoomToAllPrimitives(tabId);

  if (!zoomed) {
    throw new Error('Failed to zoom to all primitives.');
  }

  return {
    summary: 'zoomed to all primitives',
    data: {
      tabId,
      zoomed,
    },
  };
}

export async function zoomToSelectedPrimitivesResult(tabId?: string): Promise<BridgeResult> {
  const zoomed = await eda.dmt_EditorControl.zoomToSelectedPrimitives(tabId);

  if (!zoomed) {
    throw new Error('Failed to zoom to selected primitives.');
  }

  return {
    summary: 'zoomed to selected primitives',
    data: {
      tabId,
      zoomed,
    },
  };
}

export async function importSchematicChangesResult(): Promise<BridgeResult> {
  const imported = await eda.sch_Document.importChanges();

  if (!imported) {
    throw new Error('Failed to import schematic changes.');
  }

  return {
    summary: 'schematic changes imported',
    data: {
      imported: true,
    },
  };
}

export async function saveSchematicResult(): Promise<BridgeResult> {
  const saved = await eda.sch_Document.save();

  if (!saved) {
    throw new Error('Failed to save schematic.');
  }

  return {
    summary: 'schematic saved',
    data: {
      saved: true,
    },
  };
}

export async function navigateSchematicToCoordinatesResult(payload: PointPayload): Promise<BridgeResult> {
  const navigated = await eda.sch_Document.navigateToCoordinates(payload.x, payload.y);

  if (!navigated) {
    throw new Error('Failed to navigate schematic to coordinates.');
  }

  return {
    summary: 'schematic navigated to coordinates',
    data: {
      ...payload,
      navigated,
    },
  };
}

export async function navigateSchematicToRegionResult(payload: ZoomRegionPayload): Promise<BridgeResult> {
  const navigated = await eda.sch_Document.navigateToRegion(
    payload.left,
    payload.right,
    payload.top,
    payload.bottom,
  );

  if (!navigated) {
    throw new Error('Failed to navigate schematic to region.');
  }

  return {
    summary: 'schematic navigated to region',
    data: {
      ...payload,
      navigated,
    },
  };
}

export async function getSchematicPrimitiveAtPointResult(payload: PointPayload): Promise<BridgeResult> {
  const primitive = await safeCall(() => Promise.resolve(eda.sch_Document.getPrimitiveAtPoint(payload.x, payload.y)));

  return {
    summary: 'schematic primitive lookup completed',
    data: {
      point: payload,
      primitive: summarizePrimitiveLike(primitive),
    },
  };
}

export async function getSchematicPrimitivesInRegionResult(payload: ZoomRegionPayload): Promise<BridgeResult> {
  const primitives = eda.sch_Document.getPrimitivesInRegion(
    payload.left,
    payload.right,
    payload.top,
    payload.bottom,
  );

  return {
    summary: 'schematic primitives collected',
    data: {
      region: payload,
      primitives: primitives.map(summarizePrimitiveLike),
      count: primitives.length,
    },
  };
}

export async function getSchematicFilterConfigurationResult(): Promise<BridgeResult> {
  const filterConfiguration = await eda.sch_Document.getCurrentFilterConfiguration();

  return {
    summary: 'schematic filter configuration collected',
    data: {
      filterConfiguration,
    },
  };
}

export async function autoRouteSchematicResult(payload?: {
  uuids?: Array<string>;
  netlist?: {
    component: {
      [uniqueId: string]: {
        pinInfoMap: {
          [key: string]: {
            name: string;
            number: string;
            net: string;
            props: {
              'Pin Number': string;
            };
          };
        };
      };
    };
  };
  designatorDeviceTypeMap?: {
    [designator: string]: 'resistor' | 'capacitor' | 'inductive' | 'diode' | 'triode' | 'oscillator' | 'chip' | 'otherDevice';
  };
}): Promise<BridgeResult> {
  const result = await eda.sch_Document.autoRouting(payload);

  return {
    summary: 'schematic auto-routing executed',
    data: result,
  };
}

export async function autoLayoutSchematicResult(payload?: {
  uuids?: Array<string>;
  netlist?: {
    component: {
      [uniqueId: string]: {
        pinInfoMap: {
          [key: string]: {
            name: string;
            number: string;
            net: string;
            props: {
              'Pin Number': string;
            };
          };
        };
      };
    };
  };
  designatorDeviceTypeMap?: {
    [designator: string]: 'resistor' | 'capacitor' | 'inductive' | 'diode' | 'triode' | 'oscillator' | 'chip' | 'otherDevice';
  };
}): Promise<BridgeResult> {
  const result = await eda.sch_Document.autoLayout(payload);

  return {
    summary: 'schematic auto-layout executed',
    data: result,
  };
}

export async function checkSchematicDrcResult(payload?: {
  strict?: boolean;
  userInterface?: boolean;
  includeVerboseError?: boolean;
}): Promise<BridgeResult> {
  const strict = payload?.strict ?? true;
  const userInterface = payload?.userInterface ?? false;
  const includeVerboseError = payload?.includeVerboseError ?? false;
  const result = await eda.sch_Drc.check(strict, userInterface, includeVerboseError as never);

  return {
    summary: 'schematic DRC checked',
    data: {
      strict,
      userInterface,
      includeVerboseError,
      result,
    },
  };
}

export async function importPcbChangesResult(payload?: { schematicUuid?: string }): Promise<BridgeResult> {
  const sourceSchematicUuid = payload?.schematicUuid ?? await getCurrentSchematicUuid();
  const imported = await eda.pcb_Document.importChanges(sourceSchematicUuid);

  if (!imported) {
    throw new Error('Failed to import PCB changes.');
  }

  return {
    summary: 'PCB changes imported',
    data: {
      imported: true,
      schematicUuid: sourceSchematicUuid,
    },
  };
}

export async function savePcbResult(payload?: { pcbUuid?: string }): Promise<BridgeResult> {
  const pcbUuid = payload?.pcbUuid ?? await getCurrentPcbUuid();

  if (!pcbUuid) {
    throw new Error('No current PCB is available for saving.');
  }

  const saved = await eda.pcb_Document.save(pcbUuid);

  if (!saved) {
    throw new Error('Failed to save PCB.');
  }

  return {
    summary: 'PCB saved',
    data: {
      saved: true,
      pcbUuid,
    },
  };
}

export async function getPcbCalculatingRatlineStatusResult(): Promise<BridgeResult> {
  const status = await eda.pcb_Document.getCalculatingRatlineStatus();

  return {
    summary: 'PCB ratline status collected',
    data: {
      status,
    },
  };
}

export async function startPcbCalculatingRatlineResult(): Promise<BridgeResult> {
  const started = await eda.pcb_Document.startCalculatingRatline();

  if (!started) {
    throw new Error('Failed to start PCB ratline calculation.');
  }

  return {
    summary: 'PCB ratline calculation started',
    data: {
      started: true,
    },
  };
}

export async function stopPcbCalculatingRatlineResult(): Promise<BridgeResult> {
  const stopped = await eda.pcb_Document.stopCalculatingRatline();

  if (!stopped) {
    throw new Error('Failed to stop PCB ratline calculation.');
  }

  return {
    summary: 'PCB ratline calculation stopped',
    data: {
      stopped: true,
    },
  };
}

export async function convertCanvasOriginToDataOriginResult(payload: PointPayload): Promise<BridgeResult> {
  const point = await eda.pcb_Document.convertCanvasOriginToDataOrigin(payload.x, payload.y);

  return {
    summary: 'canvas origin converted to data origin',
    data: {
      canvas: payload,
      dataOrigin: point,
    },
  };
}

export async function convertDataOriginToCanvasOriginResult(payload: PointPayload): Promise<BridgeResult> {
  const point = await eda.pcb_Document.convertDataOriginToCanvasOrigin(payload.x, payload.y);

  return {
    summary: 'data origin converted to canvas origin',
    data: {
      data: payload,
      canvasOrigin: point,
    },
  };
}

export async function getPcbCanvasOriginResult(): Promise<BridgeResult> {
  const origin = await eda.pcb_Document.getCanvasOrigin();

  return {
    summary: 'PCB canvas origin collected',
    data: origin,
  };
}

export async function setPcbCanvasOriginResult(payload: { offsetX: number; offsetY: number }): Promise<BridgeResult> {
  const updated = await eda.pcb_Document.setCanvasOrigin(payload.offsetX, payload.offsetY);

  if (!updated) {
    throw new Error('Failed to set PCB canvas origin.');
  }

  return {
    summary: 'PCB canvas origin updated',
    data: {
      updated: true,
      ...payload,
    },
  };
}

export async function navigatePcbToCoordinatesResult(payload: PointPayload): Promise<BridgeResult> {
  const navigated = await eda.pcb_Document.navigateToCoordinates(payload.x, payload.y);

  if (!navigated) {
    throw new Error('Failed to navigate PCB to coordinates.');
  }

  return {
    summary: 'PCB navigated to coordinates',
    data: {
      ...payload,
      navigated,
    },
  };
}

export async function navigatePcbToRegionResult(payload: ZoomRegionPayload): Promise<BridgeResult> {
  const navigated = await eda.pcb_Document.navigateToRegion(
    payload.left,
    payload.right,
    payload.top,
    payload.bottom,
  );

  if (!navigated) {
    throw new Error('Failed to navigate PCB to region.');
  }

  return {
    summary: 'PCB navigated to region',
    data: {
      ...payload,
      navigated,
    },
  };
}

export async function getPcbPrimitiveAtPointResult(payload: PointPayload): Promise<BridgeResult> {
  const primitive = await safeCall(() => eda.pcb_Document.getPrimitiveAtPoint(payload.x, payload.y));

  return {
    summary: 'PCB primitive lookup completed',
    data: {
      point: payload,
      primitive: summarizePrimitiveLike(primitive),
    },
  };
}

export async function getPcbPrimitivesInRegionResult(payload: ZoomRegionPayload): Promise<BridgeResult> {
  const primitives = await eda.pcb_Document.getPrimitivesInRegion(
    payload.left,
    payload.right,
    payload.top,
    payload.bottom,
  );

  return {
    summary: 'PCB primitives collected',
    data: {
      region: payload,
      primitives: primitives.map(summarizePrimitiveLike),
      count: primitives.length,
    },
  };
}

export async function zoomPcbToBoardOutlineResult(): Promise<BridgeResult> {
  const zoomed = await eda.pcb_Document.zoomToBoardOutline();

  if (!zoomed) {
    throw new Error('Failed to zoom PCB to board outline.');
  }

  return {
    summary: 'PCB zoomed to board outline',
    data: {
      zoomed: true,
    },
  };
}

export async function getPcbFilterConfigurationResult(): Promise<BridgeResult> {
  const filterConfiguration = await eda.pcb_Document.getCurrentFilterConfiguration();

  return {
    summary: 'PCB filter configuration collected',
    data: {
      filterConfiguration,
    },
  };
}

export async function clearPcbRoutingResult(payload?: { type?: 'all' | 'net' | 'connection' }): Promise<BridgeResult> {
  const cleared = await eda.pcb_Document.clearRouting(payload?.type);

  if (!cleared) {
    throw new Error('Failed to clear PCB routing.');
  }

  return {
    summary: 'PCB routing cleared',
    data: {
      cleared: true,
      type: payload?.type ?? 'all',
    },
  };
}

export async function savePanelResult(): Promise<BridgeResult> {
  const saved = await eda.pnl_Document.save();

  if (!saved) {
    throw new Error('Failed to save panel document.');
  }

  return {
    summary: 'panel document saved',
    data: {
      saved: true,
    },
  };
}
