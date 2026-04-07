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
    | 'getState_Line',
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
      primitiveId: getPrimitiveStateValue(created, 'getState_PrimitiveId'),
      primitiveType: getPrimitiveStateValue(created, 'getState_PrimitiveType'),
      name: getPrimitiveStateValue(created, 'getState_Name'),
      net: getPrimitiveStateValue(created, 'getState_Net'),
      position: {
        x: getPrimitiveStateValue(created, 'getState_X'),
        y: getPrimitiveStateValue(created, 'getState_Y'),
      },
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
      primitiveId: getPrimitiveStateValue(created, 'getState_PrimitiveId'),
      primitiveType: getPrimitiveStateValue(created, 'getState_PrimitiveType'),
      net: getPrimitiveStateValue(created, 'getState_Net'),
      line: getPrimitiveStateValue(created, 'getState_Line'),
      points: payload.points,
    },
  };
}
