import type { BridgePoint, BridgeResult } from '../bridge/protocol';
import { getDefaultRuleProfileSnapshot, getRuleProfileSnapshot } from '../remote/rule-profile';
import { collectCurrentSchematicPinLocations, snapPointsToNearbyPins } from './schematic-diagnostics';
import { type Point2D, type SourceRecord, parseSourceRecord, normalizeNumber, distanceSquaredBetweenPoints, distanceSquaredPointToSegment } from './shared-utils';

export interface PlaceComponentPayload {
  libraryUuid: string;
  uuid: string;
  position: BridgePoint;
  subPartName?: string;
  rotation?: number;
  mirror?: boolean;
  addIntoBom?: boolean;
  addIntoPcb?: boolean;
}

export interface CreateWirePayload {
  points: Array<BridgePoint>;
  netName?: string;
}

function getPrimitiveStateValue(
  primitive: unknown,
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
): string | number | Array<number> | Array<Array<number>> | undefined {
  if (!primitive || typeof primitive !== 'object') {
    return undefined;
  }

  const candidate = primitive as Record<string, unknown>;
  const method = candidate[methodName];

  if (typeof method !== 'function') {
    return undefined;
  }

  return method.call(primitive) as string | number | Array<number> | Array<Array<number>> | undefined;
}

function normalizeWirePoints(points: Array<BridgePoint>): Array<number> {
  return points.flatMap(point => [point.x, point.y]);
}

interface PcbFootprintPlacementTransform {
  offsetX: number;
  offsetY: number;
  mirrorX: boolean;
  layer: 'top' | 'bottom';
  groupId: number;
  componentKey: string;
}

interface SchematicPlacementPoint {
  x: number;
  y: number;
}

interface SchematicPlacementGeometry {
  components: Array<SchematicPlacementPoint>;
  segments: Array<{
    start: SchematicPlacementPoint;
    end: SchematicPlacementPoint;
  }>;
}

function stringifySourceRecord(record: SourceRecord): string {
  return `${JSON.stringify(record.header)}||${JSON.stringify(record.body)}|`;
}

function parseCurrentSchematicPlacementGeometry(source: string): SchematicPlacementGeometry {
  const components: Array<SchematicPlacementPoint> = [];
  const segments: Array<{
    start: SchematicPlacementPoint;
    end: SchematicPlacementPoint;
  }> = [];

  const wireSegments = new Map<string, {
    start?: SchematicPlacementPoint;
    end?: SchematicPlacementPoint;
  }>();

  for (const line of source.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    const record = parseSourceRecord(trimmed);
    if (!record) {
      continue;
    }

    const type = String(record.header.type ?? '');

    if (type === 'COMPONENT') {
      const x = normalizeNumber(record.body.x);
      const y = normalizeNumber(record.body.y);
      if (x !== undefined && y !== undefined) {
        components.push({ x, y });
      }
      continue;
    }

    if (type === 'LINE') {
      const lineGroup = String(record.body.lineGroup ?? '');
      const startX = normalizeNumber(record.body.startX);
      const startY = normalizeNumber(record.body.startY);
      const endX = normalizeNumber(record.body.endX);
      const endY = normalizeNumber(record.body.endY);

      if (!lineGroup || startX === undefined || startY === undefined || endX === undefined || endY === undefined) {
        continue;
      }

      const entry = wireSegments.get(lineGroup) ?? {};
      entry.start = entry.start ?? { x: startX, y: startY };
      entry.end = { x: endX, y: endY };
      wireSegments.set(lineGroup, entry);
    }
  }

  for (const segment of wireSegments.values()) {
    if (segment.start && segment.end) {
      segments.push({
        start: segment.start,
        end: segment.end,
      });
    }
  }

  return {
    components,
    segments,
  };
}

function generatePlacementOffsets(step: number, maxRing: number): Array<SchematicPlacementPoint> {
  const candidateOffsets: Array<SchematicPlacementPoint> = [{ x: 0, y: 0 }];

  for (let ring = 1; ring <= maxRing; ring += 1) {
    const distance = ring * step;
    const coordinates = [
      [distance, 0],
      [-distance, 0],
      [0, distance],
      [0, -distance],
      [distance, distance],
      [distance, -distance],
      [-distance, distance],
      [-distance, -distance],
    ] as const;

    for (const [x, y] of coordinates) {
      candidateOffsets.push({ x, y });
    }
  }

  // Sort by distance from origin so closer positions are tried first
  candidateOffsets.sort((a, b) => (a.x * a.x + a.y * a.y) - (b.x * b.x + b.y * b.y));

  return candidateOffsets;
}

function isPlacementClear(
  candidate: SchematicPlacementPoint,
  geometry: SchematicPlacementGeometry,
  componentClearance: number,
  wireClearance: number,
): boolean {
  const componentClearanceSquared = componentClearance * componentClearance;
  const wireClearanceSquared = wireClearance * wireClearance;

  for (const component of geometry.components) {
    if (distanceSquaredBetweenPoints(candidate, component) < componentClearanceSquared) {
      return false;
    }
  }

  for (const segment of geometry.segments) {
    if (distanceSquaredPointToSegment(candidate, segment.start, segment.end) < wireClearanceSquared) {
      return false;
    }
  }

  return true;
}

async function hasPrimitiveAtPoint(candidate: SchematicPlacementPoint): Promise<boolean> {
  try {
    const primitive = await Promise.resolve(eda.sch_Document.getPrimitiveAtPoint(candidate.x, candidate.y));
    return Boolean(primitive);
  }
  catch {
    return false;
  }
}

async function resolveSchematicComponentPlacement(
  requestedPosition: BridgePoint,
): Promise<{
  adjusted: boolean;
  position: BridgePoint;
  originalPosition: BridgePoint;
}> {
  const source = await eda.sys_FileManager.getDocumentSource();

  if (!source) {
    return {
      adjusted: false,
      position: {
        x: requestedPosition.x,
        y: requestedPosition.y,
      },
      originalPosition: {
        x: requestedPosition.x,
        y: requestedPosition.y,
      },
    };
  }

  const geometry = parseCurrentSchematicPlacementGeometry(source);
  if (!geometry.components.length && !geometry.segments.length) {
    return {
      adjusted: false,
      position: {
        x: requestedPosition.x,
        y: requestedPosition.y,
      },
      originalPosition: {
        x: requestedPosition.x,
        y: requestedPosition.y,
      },
    };
  }

  const profile = await getRuleProfileSnapshot();
  const defaultProfile = getDefaultRuleProfileSnapshot();
  const step = profile.schematic.placementStep ?? defaultProfile.schematic.placementStep;
  const maxRing = profile.schematic.placementMaxRing ?? defaultProfile.schematic.placementMaxRing;
  const componentClearance = profile.schematic.placementComponentClearance
    ?? defaultProfile.schematic.placementComponentClearance;
  const wireClearance = profile.schematic.placementWireClearance
    ?? defaultProfile.schematic.placementWireClearance;
  const offsets = generatePlacementOffsets(step, maxRing);

  for (const offset of offsets) {
    const candidate = {
      x: requestedPosition.x + offset.x,
      y: requestedPosition.y + offset.y,
    };

    if (!isPlacementClear(candidate, geometry, componentClearance, wireClearance)) {
      continue;
    }
    // Runtime occupancy check: source snapshots can be stale between rapid placements.
    if (await hasPrimitiveAtPoint(candidate)) {
      continue;
    }

    return {
      adjusted: offset.x !== 0 || offset.y !== 0,
      position: candidate,
      originalPosition: {
        x: requestedPosition.x,
        y: requestedPosition.y,
      },
    };
  }

  return {
    adjusted: false,
    position: {
      x: requestedPosition.x,
      y: requestedPosition.y,
    },
    originalPosition: {
      x: requestedPosition.x,
      y: requestedPosition.y,
    },
  };
}

function transformLayerId(layerId: unknown, placement: PcbFootprintPlacementTransform): unknown {
  if (typeof layerId !== 'number') {
    return layerId;
  }

  if (placement.layer !== 'bottom') {
    return layerId;
  }

  const layerMap = new Map<number, number>([
    [1, 2],
    [2, 1],
    [3, 4],
    [4, 3],
    [5, 6],
    [6, 5],
    [7, 8],
    [8, 7],
    [9, 10],
    [10, 9],
  ]);

  return layerMap.get(layerId) ?? layerId;
}

function transformXCoordinate(x: number, placement: PcbFootprintPlacementTransform): number {
  return placement.mirrorX
    ? placement.offsetX - x
    : placement.offsetX + x;
}

function transformYCoordinate(y: number, placement: PcbFootprintPlacementTransform): number {
  return placement.offsetY + y;
}

function transformPathArray(path: Array<unknown>, placement: PcbFootprintPlacementTransform): Array<unknown> {
  if (!path.length) {
    return [];
  }

  if (path[0] === 'CIRCLE' && path.length >= 4) {
    const [command, x, y, radius, ...rest] = path;

    return [
      command,
      typeof x === 'number' ? transformXCoordinate(x, placement) : x,
      typeof y === 'number' ? transformYCoordinate(y, placement) : y,
      radius,
      ...rest.map(item => (Array.isArray(item) ? transformPathArray(item, placement) : item)),
    ];
  }

  let coordinateIndex = 0;

  return path.map((item) => {
    if (Array.isArray(item)) {
      return transformPathArray(item, placement);
    }

    if (typeof item === 'string') {
      coordinateIndex = 0;
      return item;
    }

    if (typeof item === 'number') {
      const transformed = coordinateIndex % 2 === 0
        ? transformXCoordinate(item, placement)
        : transformYCoordinate(item, placement);

      coordinateIndex += 1;
      return transformed;
    }

    return item;
  });
}

function transformSourceValue(value: unknown, placement: PcbFootprintPlacementTransform, currentKey?: string): unknown {
  if (Array.isArray(value)) {
    return transformPathArray(value, placement);
  }

  if (!value || typeof value !== 'object') {
    return value;
  }

  const source = value as Record<string, unknown>;
  const transformed: Record<string, unknown> = {};

  for (const [key, entry] of Object.entries(source)) {
    if (key === 'layerId') {
      transformed[key] = transformLayerId(entry, placement);
      continue;
    }

    if (key === 'groupId' || key === 'groupID') {
      transformed[key] = placement.groupId;
      continue;
    }

    if (key === 'centerX' || key === 'x') {
      transformed[key] = typeof entry === 'number' ? transformXCoordinate(entry, placement) : entry;
      continue;
    }

    if (key === 'centerY' || key === 'y') {
      transformed[key] = typeof entry === 'number' ? transformYCoordinate(entry, placement) : entry;
      continue;
    }

    if (key === 'path' && Array.isArray(entry)) {
      transformed[key] = transformPathArray(entry, placement);
      continue;
    }

    transformed[key] = transformSourceValue(entry, placement, currentKey ?? key);
  }

  return transformed;
}

function buildPlacedFootprintSource(
  boardSource: string,
  footprintSource: string,
  placement: PcbFootprintPlacementTransform,
): string {
  const boardLines = boardSource.split('\n').filter(line => line.trim().length > 0);
  const footprintRecords = footprintSource
    .split('\n')
    .map(line => line.trim())
    .filter(line => line.length > 0)
    .map(parseSourceRecord)
    .filter((record): record is SourceRecord => Boolean(record))
    .filter((record) => {
      const recordType = String(record.header.type ?? '');
      return ['PAD', 'POLY', 'FILL', 'ATTR'].includes(recordType);
    })
    .map((record, index) => {
      const transformedBody = transformSourceValue(record.body, placement);

      return {
        header: {
          ...record.header,
          ticket: typeof record.header.ticket === 'number' ? record.header.ticket : index + 1,
          id: `${placement.componentKey}_${String(record.header.id ?? index + 1)}`,
        },
        body: transformedBody as Record<string, unknown>,
      };
    });

  const footprintLines = footprintRecords.map(stringifySourceRecord);

  return [...boardLines, ...footprintLines].join('\n');
}

async function getCurrentPcbUuid(): Promise<string | undefined> {
  try {
    const pcbInfo = await eda.dmt_Pcb.getCurrentPcbInfo();
    return pcbInfo?.uuid;
  }
  catch {
    return undefined;
  }
}

async function getCurrentSchematicUuid(): Promise<string | undefined> {
  try {
    const schematicInfo = await eda.dmt_Schematic.getCurrentSchematicInfo();
    return schematicInfo?.uuid;
  }
  catch {
    return undefined;
  }
}

function summarizeSchematicPrimitive(created: unknown): Record<string, unknown> {
  return {
    primitiveId: getPrimitiveStateValue(created, 'getState_PrimitiveId'),
    primitiveType: getPrimitiveStateValue(created, 'getState_PrimitiveType'),
    componentType: getPrimitiveStateValue(created, 'getState_ComponentType'),
    name: getPrimitiveStateValue(created, 'getState_Name'),
    net: getPrimitiveStateValue(created, 'getState_Net'),
    line: getPrimitiveStateValue(created, 'getState_Line'),
    position: {
      x: getPrimitiveStateValue(created, 'getState_X'),
      y: getPrimitiveStateValue(created, 'getState_Y'),
    },
    subPartName: getPrimitiveStateValue(created, 'getState_SubPartName'),
    rotation: getPrimitiveStateValue(created, 'getState_Rotation'),
    mirror: getPrimitiveStateValue(created, 'getState_Mirror'),
    addIntoBom: getPrimitiveStateValue(created, 'getState_AddIntoBom'),
    addIntoPcb: getPrimitiveStateValue(created, 'getState_AddIntoPcb'),
  };
}

function summarizePcbPrimitive(created: unknown): Record<string, unknown> {
  return {
    primitiveId: getPrimitiveStateValue(created, 'getState_PrimitiveId'),
    primitiveType: getPrimitiveStateValue(created, 'getState_PrimitiveType'),
    layer: getPrimitiveStateValue(created, 'getState_Layer'),
    name: getPrimitiveStateValue(created, 'getState_Name'),
    net: getPrimitiveStateValue(created, 'getState_Net'),
    position: {
      x: getPrimitiveStateValue(created, 'getState_X'),
      y: getPrimitiveStateValue(created, 'getState_Y'),
    },
    rotation: getPrimitiveStateValue(created, 'getState_Rotation'),
  };
}

export async function placeSchematicComponent(payload: PlaceComponentPayload): Promise<BridgeResult> {
  const placement = await resolveSchematicComponentPlacement(payload.position);
  const created = await eda.sch_PrimitiveComponent.create(
    {
      libraryUuid: payload.libraryUuid,
      uuid: payload.uuid,
    },
    placement.position.x,
    placement.position.y,
    payload.subPartName,
    payload.rotation,
    payload.mirror,
    payload.addIntoBom,
    payload.addIntoPcb,
  );

  if (!created) {
    throw new Error('JLCEDA did not create the schematic component.');
  }

  return {
    summary: 'schematic component placed',
    data: {
      ...summarizeSchematicPrimitive(created),
      component: {
        libraryUuid: payload.libraryUuid,
        uuid: payload.uuid,
        subPartName: payload.subPartName,
      },
      requestedPosition: placement.originalPosition,
      placementAdjusted: placement.adjusted,
      placementMode: placement.adjusted ? 'avoid_overlap' : 'direct',
    },
  };
}

export async function createSchematicWire(payload: CreateWirePayload): Promise<BridgeResult> {
  if (payload.points.length < 2) {
    throw new Error('At least two points are required to create a schematic wire.');
  }

  let wirePoints = payload.points;

  try {
    const pins = await collectCurrentSchematicPinLocations();
    wirePoints = snapPointsToNearbyPins(payload.points, pins);
  }
  catch {
    wirePoints = payload.points;
  }

  const created = await eda.sch_PrimitiveWire.create(normalizeWirePoints(wirePoints), payload.netName);

  if (!created) {
    throw new Error('JLCEDA did not create the schematic wire.');
  }

  return {
    summary: 'schematic wire created',
    data: {
      ...summarizeSchematicPrimitive(created),
      points: wirePoints,
    },
  };
}

export async function annotateSchematicNet(payload: { netName: string; position: BridgePoint }): Promise<BridgeResult> {
  const created = await eda.sch_PrimitiveAttribute.createNetLabel(
    payload.position.x,
    payload.position.y,
    payload.netName,
  );

  if (!created) {
    throw new Error('JLCEDA did not create the schematic net label.');
  }

  return {
    summary: 'schematic net label created',
    data: {
      ...summarizeSchematicPrimitive(created),
      netName: payload.netName,
      position: payload.position,
    },
  };
}

export async function createSchematicNetFlag(payload: {
  identification: 'Power' | 'Ground' | 'AnalogGround' | 'ProtectGround';
  net: string;
  position: BridgePoint;
  rotation?: number;
  mirror?: boolean;
}): Promise<BridgeResult> {
  const created = await eda.sch_PrimitiveComponent.createNetFlag(
    payload.identification,
    payload.net,
    payload.position.x,
    payload.position.y,
    payload.rotation,
    payload.mirror,
  );

  if (!created) {
    throw new Error('JLCEDA did not create the schematic net flag.');
  }

  return {
    summary: 'schematic net flag created',
    data: {
      ...summarizeSchematicPrimitive(created),
      identification: payload.identification,
      net: payload.net,
      position: payload.position,
    },
  };
}

export async function createSchematicNetPort(payload: {
  direction: 'IN' | 'OUT' | 'BI';
  net: string;
  position: BridgePoint;
  rotation?: number;
  mirror?: boolean;
}): Promise<BridgeResult> {
  const created = await eda.sch_PrimitiveComponent.createNetPort(
    payload.direction,
    payload.net,
    payload.position.x,
    payload.position.y,
    payload.rotation,
    payload.mirror,
  );

  if (!created) {
    throw new Error('JLCEDA did not create the schematic net port.');
  }

  return {
    summary: 'schematic net port created',
    data: {
      ...summarizeSchematicPrimitive(created),
      direction: payload.direction,
      net: payload.net,
      position: payload.position,
    },
  };
}

export async function createSchematicShortCircuitFlag(payload: {
  position: BridgePoint;
  rotation?: number;
  mirror?: boolean;
}): Promise<BridgeResult> {
  const created = await eda.sch_PrimitiveComponent.createShortCircuitFlag(
    payload.position.x,
    payload.position.y,
    payload.rotation,
    payload.mirror,
  );

  if (!created) {
    throw new Error('JLCEDA did not create the short-circuit flag.');
  }

  return {
    summary: 'schematic short-circuit flag created',
    data: {
      ...summarizeSchematicPrimitive(created),
      position: payload.position,
    },
  };
}

export async function placePcbFootprint(payload: {
  libraryUuid: string;
  uuid: string;
  position: BridgePoint;
  rotation?: number;
  layer?: 'top' | 'bottom';
  primitiveLock?: boolean;
}): Promise<BridgeResult> {
  const footprint = await eda.lib_Footprint.get(payload.uuid, payload.libraryUuid);
  const createInput = footprint ?? {
    libraryType: '4',
    libraryUuid: payload.libraryUuid,
    uuid: payload.uuid,
  };

  try {
    const created = await eda.pcb_PrimitiveComponent.create(
      createInput,
      payload.layer === 'bottom' ? 2 : 1,
      payload.position.x,
      payload.position.y,
      payload.rotation,
      payload.primitiveLock,
    );

    if (!created) {
      throw new Error('JLCEDA did not create the PCB footprint.');
    }

    return {
      summary: 'pcb footprint placed',
      data: {
        ...summarizePcbPrimitive(created),
        footprint: {
          libraryUuid: payload.libraryUuid,
          uuid: payload.uuid,
        },
        position: payload.position,
        layer: payload.layer ?? 'top',
        primitiveLock: Boolean(payload.primitiveLock),
        placementMode: 'api',
      },
    };
  }
  catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    if (!errorMessage.includes('Cannot convert undefined or null to object')) {
      throw error;
    }

    const pcbUuid = await getCurrentPcbUuid();
    const schematicUuid = await getCurrentSchematicUuid();

    if (!pcbUuid) {
      throw new Error('PCB source fallback requires an active PCB document.');
    }

    const boardSource = await eda.sys_FileManager.getDocumentSource();
    const libraryTabId = await eda.dmt_EditorControl.openLibraryDocument(
      payload.libraryUuid,
      '4' as never,
      payload.uuid,
    );

    if (!libraryTabId) {
      throw new Error('Failed to open footprint library document for source fallback.');
    }

    const footprintSource = await eda.sys_FileManager.getDocumentSource();
    await eda.dmt_EditorControl.openDocument(pcbUuid);

    const existingGroupIds: Array<number> = [];
    for (const match of boardSource.matchAll(/"groupId":(\d+)/g)) {
      existingGroupIds.push(Number(match[1] ?? '0'));
    }

    const existingUpperGroupIds: Array<number> = [];
    for (const match of boardSource.matchAll(/"groupID":(\d+)/g)) {
      existingUpperGroupIds.push(Number(match[1] ?? '0'));
    }
    const nextGroupId = Math.max(0, ...existingGroupIds, ...existingUpperGroupIds) + 1;

    const updatedSource = buildPlacedFootprintSource(boardSource, footprintSource, {
      componentKey: `pcbfp_${payload.uuid}`,
      groupId: nextGroupId,
      layer: payload.layer ?? 'top',
      mirrorX: payload.layer === 'bottom',
      offsetX: payload.position.x,
      offsetY: payload.position.y,
    });

    const updated = await eda.sys_FileManager.setDocumentSource(updatedSource);

    if (!updated) {
      throw new Error('Failed to update PCB source with footprint fallback.');
    }

    if (schematicUuid) {
      await eda.pcb_Document.importChanges(schematicUuid);
    }

    await eda.pcb_Document.save(pcbUuid);

    return {
      summary: 'pcb footprint placed via source fallback',
      data: {
        footprint: {
          libraryUuid: payload.libraryUuid,
          uuid: payload.uuid,
        },
        position: payload.position,
        layer: payload.layer ?? 'top',
        primitiveLock: Boolean(payload.primitiveLock),
        placementMode: 'source_fallback',
      },
    };
  }
}
