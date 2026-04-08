import type { BridgePoint, BridgeResult } from '../bridge/protocol';

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
  const created = await eda.sch_PrimitiveComponent.create(
    {
      libraryUuid: payload.libraryUuid,
      uuid: payload.uuid,
    },
    payload.position.x,
    payload.position.y,
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
    },
  };
}

export async function createSchematicWire(payload: CreateWirePayload): Promise<BridgeResult> {
  if (payload.points.length < 2) {
    throw new Error('At least two points are required to create a schematic wire.');
  }

  const created = await eda.sch_PrimitiveWire.create(normalizeWirePoints(payload.points), payload.netName);

  if (!created) {
    throw new Error('JLCEDA did not create the schematic wire.');
  }

  return {
    summary: 'schematic wire created',
    data: {
      ...summarizeSchematicPrimitive(created),
      points: payload.points,
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
  const created = await eda.pcb_PrimitiveComponent.create(
    {
      libraryType: '4',
      libraryUuid: payload.libraryUuid,
      uuid: payload.uuid,
    },
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
    },
  };
}
