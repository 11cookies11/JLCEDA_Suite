import JSZip from 'jszip';
import type { BridgeResult } from '../bridge/protocol';

interface SourceRecord {
  header: Record<string, unknown>;
  body: Record<string, unknown>;
}

interface Point {
  x: number;
  y: number;
}

interface PlacementTransform {
  x: number;
  y: number;
  rotation: number;
  mirror: boolean;
}

interface SchematicComponentSource {
  primitiveId: string;
  x: number;
  y: number;
  rotation: number;
  mirror: boolean;
  componentType?: string;
  designator?: string;
  name?: string;
  uniqueId?: string;
  symbol?: {
    libraryUuid: string;
    uuid: string;
  };
}

interface SymbolPinSource {
  pinNumber: string;
  pinName?: string;
  x: number;
  y: number;
  rotation: number;
  pinLength: number;
}

interface ConnectivityPointRef {
  x: number;
  y: number;
  componentId?: string;
  designator?: string;
  componentType?: string;
  pinNumber?: string;
  pinName?: string;
  pinPrimitiveId?: string;
  noConnected?: boolean;
}

interface ConnectivitySegment {
  wireId: string;
  net?: string;
  start: Point;
  end: Point;
}

interface ConnectivityIssue {
  type: 'dangling_wire_endpoint' | 'unconnected_pin' | 'zero_length_segment';
  severity: 'warning' | 'info';
  message: string;
  point?: Point;
  wireId?: string;
  wireNet?: string;
  componentId?: string;
  designator?: string;
  pinNumber?: string;
  pinName?: string;
}

interface InspectConnectivityPayload {
  allSchematicPages?: boolean;
  tolerance?: number;
  maxIssues?: number;
}

function parseSourceRecord(line: string): SourceRecord | undefined {
  const separatorIndex = line.indexOf('||');

  if (separatorIndex < 0) {
    return undefined;
  }

  const headerText = line.slice(0, separatorIndex);
  const bodyText = line.slice(separatorIndex + 2).replace(/\|$/, '');

  try {
    return {
      header: JSON.parse(headerText) as Record<string, unknown>,
      body: JSON.parse(bodyText) as Record<string, unknown>,
    };
  }
  catch {
    return undefined;
  }
}

function normalizeNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  return undefined;
}

function normalizeBoolean(value: unknown): boolean {
  if (typeof value === 'boolean') {
    return value;
  }

  if (typeof value === 'string') {
    return value === 'true' || value === '1' || value.toLowerCase() === 'yes';
  }

  return false;
}

function transformPoint(point: Point, placement: PlacementTransform): Point {
  const mirrored = placement.mirror
    ? { x: -point.x, y: point.y }
    : point;

  const rotation = ((placement.rotation % 360) + 360) % 360;

  switch (rotation) {
    case 90:
      return {
        x: placement.x - mirrored.y,
        y: placement.y + mirrored.x,
      };
    case 180:
      return {
        x: placement.x - mirrored.x,
        y: placement.y - mirrored.y,
      };
    case 270:
      return {
        x: placement.x + mirrored.y,
        y: placement.y - mirrored.x,
      };
    default:
      return {
        x: placement.x + mirrored.x,
        y: placement.y + mirrored.y,
      };
  }
}

function approxEqual(a: number, b: number, tolerance: number): boolean {
  return Math.abs(a - b) <= tolerance;
}

function pointsEqual(left: Point, right: Point, tolerance: number): boolean {
  return approxEqual(left.x, right.x, tolerance) && approxEqual(left.y, right.y, tolerance);
}

function pointOnSegment(point: Point, start: Point, end: Point, tolerance: number): boolean {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const lengthSquared = dx * dx + dy * dy;

  if (lengthSquared === 0) {
    return pointsEqual(point, start, tolerance);
  }

  const cross = (point.y - start.y) * dx - (point.x - start.x) * dy;
  if (Math.abs(cross) > tolerance * Math.sqrt(lengthSquared)) {
    return false;
  }

  const dot = (point.x - start.x) * dx + (point.y - start.y) * dy;
  if (dot < -tolerance) {
    return false;
  }

  if (dot > lengthSquared + tolerance) {
    return false;
  }

  return true;
}

function getRecordNumber(record: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = normalizeNumber(record[key]);
    if (value !== undefined) {
      return value;
    }
  }

  return undefined;
}

function parseSchematicComponents(source: string): Array<SchematicComponentSource> {
  const components: Array<SchematicComponentSource> = [];

  for (const line of source.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    const record = parseSourceRecord(trimmed);
    if (!record || String(record.header.type ?? '') !== 'COMPONENT') {
      continue;
    }

    const primitiveId = String(record.header.id ?? '');
    const body = record.body;
    const symbol = body.symbol && typeof body.symbol === 'object'
      ? {
          libraryUuid: String((body.symbol as Record<string, unknown>).libraryUuid ?? ''),
          uuid: String((body.symbol as Record<string, unknown>).uuid ?? ''),
        }
      : undefined;

    components.push({
      primitiveId,
      x: normalizeNumber(body.x) ?? 0,
      y: normalizeNumber(body.y) ?? 0,
      rotation: normalizeNumber(body.rotation) ?? 0,
      mirror: normalizeBoolean(body.isMirror),
      componentType: typeof body.componentType === 'string' ? body.componentType : undefined,
      designator: typeof body.designator === 'string' ? body.designator : undefined,
      name: typeof body.name === 'string' ? body.name : undefined,
      uniqueId: typeof body.uniqueId === 'string' ? body.uniqueId : undefined,
      symbol,
    });
  }

  return components;
}

function parseSourceWires(source: string): Array<{ wireId: string; net?: string; segments: Array<ConnectivitySegment> }> {
  const wireGroups = new Map<string, { wireId: string; net?: string; segments: Array<ConnectivitySegment> }>();

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
    const id = String(record.header.id ?? '');

    if (type === 'LINE') {
      const lineGroup = String(record.body.lineGroup ?? '');
      if (!lineGroup) {
        continue;
      }

      const startX = normalizeNumber(record.body.startX);
      const startY = normalizeNumber(record.body.startY);
      const endX = normalizeNumber(record.body.endX);
      const endY = normalizeNumber(record.body.endY);

      if (startX === undefined || startY === undefined || endX === undefined || endY === undefined) {
        continue;
      }

      const group = wireGroups.get(lineGroup) ?? {
        wireId: lineGroup,
        segments: [],
      };

      group.segments.push({
        wireId: lineGroup,
        start: { x: startX, y: startY },
        end: { x: endX, y: endY },
      });

      wireGroups.set(lineGroup, group);
      continue;
    }

    if (type === 'ATTR' && String(record.body.key ?? '') === 'NET') {
      const parentId = String(record.body.parentId ?? '');
      if (!parentId) {
        continue;
      }

      const group = wireGroups.get(parentId) ?? {
        wireId: parentId,
        segments: [],
      };

      const netValue = typeof record.body.value === 'string' ? record.body.value : undefined;
      group.net = netValue;
      wireGroups.set(parentId, group);
      continue;
    }

    if (type === 'WIRE') {
      wireGroups.set(id, wireGroups.get(id) ?? {
        wireId: id,
        segments: [],
      });
    }
  }

  return [...wireGroups.values()];
}

async function extractSymbolSourceText(symbolFile: File | Blob): Promise<string | undefined> {
  const zip = await JSZip.loadAsync(await symbolFile.arrayBuffer());
  const candidateEntries = Object.values(zip.files).filter(entry => !entry.dir);
  let bestSource: string | undefined;
  let bestPinCount = -1;

  for (const entry of candidateEntries) {
    let text: string;
    try {
      text = await entry.async('string');
    }
    catch {
      continue;
    }

    const pinCount = text.split('\n').filter(line => {
      const record = parseSourceRecord(line.trim());
      if (!record) {
        return false;
      }

      const type = String(record.header.type ?? '');
      if (type === 'PIN') {
        return true;
      }

      const pinNumber = record.body.pinNumber ?? record.body.pinNo ?? record.body.number;
      const pinName = record.body.pinName ?? record.body.name;
      return pinNumber !== undefined || pinName !== undefined;
    }).length;

    if (pinCount > bestPinCount || (pinCount === bestPinCount && text.includes('DOCHEAD'))) {
      bestPinCount = pinCount;
      bestSource = text;
    }
  }

  return bestSource;
}

async function parseSymbolPins(
  symbolFile: File | Blob | undefined,
): Promise<Array<SymbolPinSource>> {
  if (!symbolFile) {
    return [];
  }

  const source = await extractSymbolSourceText(symbolFile);
  if (!source) {
    return [];
  }

  const pins: Array<SymbolPinSource> = [];

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
    const body = record.body;
    const pinNumber = typeof body.pinNumber === 'string'
      ? body.pinNumber
      : typeof body.pinNo === 'string'
        ? body.pinNo
        : typeof body.number === 'string'
          ? body.number
          : undefined;
    const pinName = typeof body.pinName === 'string'
      ? body.pinName
      : typeof body.name === 'string'
        ? body.name
        : undefined;

    if (type !== 'PIN' && pinNumber === undefined && pinName === undefined) {
      continue;
    }

    const x = getRecordNumber(body, ['x', 'centerX']) ?? 0;
    const y = getRecordNumber(body, ['y', 'centerY']) ?? 0;

    pins.push({
      pinNumber: pinNumber ?? String(pins.length + 1),
      pinName,
      x,
      y,
      rotation: getRecordNumber(body, ['rotation']) ?? 0,
      pinLength: getRecordNumber(body, ['pinLength', 'length']) ?? 0,
    });
  }

  return pins;
}

async function buildPinLocationsFromSource(
  components: Array<SchematicComponentSource>,
  allPinsByComponentId: Map<string, Array<SymbolPinSource>>,
): Promise<Array<ConnectivityPointRef>> {
  const pins: Array<ConnectivityPointRef> = [];

  for (const component of components) {
    const symbolPins = allPinsByComponentId.get(component.primitiveId) ?? [];
    for (const pin of symbolPins) {
      const transformed = transformPoint(
        { x: pin.x, y: pin.y },
        {
          x: component.x,
          y: component.y,
          rotation: component.rotation,
          mirror: component.mirror,
        },
      );

      pins.push({
        x: transformed.x,
        y: transformed.y,
        componentId: component.primitiveId,
        designator: component.designator,
        componentType: component.componentType,
        pinNumber: pin.pinNumber,
        pinName: pin.pinName,
        noConnected: false,
      });
    }
  }

  return pins;
}

async function collectSchematicPinLocations(
  allSchematicPages: boolean,
): Promise<{
  absolutePins: Array<ConnectivityPointRef>;
  componentCount: number;
}> {
  const [source, runtimeComponents] = await Promise.all([
    eda.sys_FileManager.getDocumentSource(),
    eda.sch_PrimitiveComponent.getAll(undefined, allSchematicPages),
  ]);

  if (!source) {
    throw new Error('Unable to read the current schematic source.');
  }

  const components = parseSchematicComponents(source);
  const sourceComponentMap = new Map(components.map(component => [component.primitiveId, component] as const));

  const allPinsByComponentId = new Map<string, Array<SymbolPinSource>>();
  for (const runtimeComponent of runtimeComponents) {
    const primitiveId = typeof runtimeComponent.getState_PrimitiveId === 'function'
      ? runtimeComponent.getState_PrimitiveId()
      : undefined;
    const symbol = typeof runtimeComponent.getState_Symbol === 'function'
      ? runtimeComponent.getState_Symbol()
      : undefined;

    if (!primitiveId || !symbol?.uuid || !symbol?.libraryUuid) {
      continue;
    }

    try {
      const symbolFile = await eda.sys_FileManager.getSymbolFileBySymbolUuid(symbol.uuid, symbol.libraryUuid);
      const symbolPins = await parseSymbolPins(symbolFile);
      allPinsByComponentId.set(primitiveId, symbolPins);
    }
    catch {
      allPinsByComponentId.set(primitiveId, []);
    }
  }

  const absolutePins = await buildPinLocationsFromSource(
    components.filter(component => sourceComponentMap.has(component.primitiveId)),
    allPinsByComponentId,
  );

  return {
    absolutePins,
    componentCount: components.length,
  };
}

export async function collectCurrentSchematicPinLocations(
  allSchematicPages = true,
): Promise<Array<ConnectivityPointRef>> {
  const { absolutePins } = await collectSchematicPinLocations(allSchematicPages);
  return absolutePins;
}

export function snapPointsToNearbyPins(
  points: Array<Point>,
  pins: Array<ConnectivityPointRef>,
  tolerance = 1.5,
): Array<Point> {
  if (!points.length || !pins.length) {
    return points.map(point => ({ ...point }));
  }

  const toleranceSquared = tolerance * tolerance;

  return points.map((point, index) => {
    if (index !== 0 && index !== points.length - 1) {
      return { ...point };
    }

    let bestPin: ConnectivityPointRef | undefined;
    let bestDistance = Number.POSITIVE_INFINITY;

    for (const pin of pins) {
      const dx = pin.x - point.x;
      const dy = pin.y - point.y;
      const distance = dx * dx + dy * dy;

      if (distance <= toleranceSquared && distance < bestDistance) {
        bestPin = pin;
        bestDistance = distance;
      }
    }

    if (!bestPin) {
      return { ...point };
    }

    return {
      x: bestPin.x,
      y: bestPin.y,
    };
  });
}

function flattenWireSegments(
  wires: Array<{ wireId: string; net?: string; segments: Array<ConnectivitySegment> }>,
): Array<ConnectivitySegment> {
  const segments: Array<ConnectivitySegment> = [];
  for (const wire of wires) {
    for (const segment of wire.segments) {
      segments.push({
        wireId: wire.wireId,
        net: wire.net,
        start: segment.start,
        end: segment.end,
      });
    }
  }

  return segments;
}

function collectWireEndpoints(segments: Array<ConnectivitySegment>): Array<{ point: Point; wireId: string; net?: string; end: 'start' | 'end'; segmentIndex: number }> {
  const endpoints: Array<{ point: Point; wireId: string; net?: string; end: 'start' | 'end'; segmentIndex: number }> = [];
  for (const [segmentIndex, segment] of segments.entries()) {
    endpoints.push({ point: segment.start, wireId: segment.wireId, net: segment.net, end: 'start', segmentIndex });
    endpoints.push({ point: segment.end, wireId: segment.wireId, net: segment.net, end: 'end', segmentIndex });
  }
  return endpoints;
}

function pointConnected(
  point: Point,
  segments: Array<ConnectivitySegment>,
  pins: Array<ConnectivityPointRef>,
  tolerance: number,
  ignoreSegmentIndex?: number,
): boolean {
  for (const pin of pins) {
    if (pointsEqual(point, pin, tolerance)) {
      return true;
    }
  }

  for (const [segmentIndex, segment] of segments.entries()) {
    if (segmentIndex === ignoreSegmentIndex) {
      continue;
    }

    if (pointOnSegment(point, segment.start, segment.end, tolerance)) {
      return true;
    }
  }

  return false;
}

function summarizeComponent(component: SchematicComponentSource): Record<string, unknown> {
  return {
    primitiveId: component.primitiveId,
    designator: component.designator,
    name: component.name,
    componentType: component.componentType,
    uniqueId: component.uniqueId,
    position: {
      x: component.x,
      y: component.y,
    },
    rotation: component.rotation,
    mirror: component.mirror,
    symbol: component.symbol,
  };
}

export async function inspectSchematicConnectivityResult(
  payload?: InspectConnectivityPayload,
): Promise<BridgeResult> {
  const tolerance = payload?.tolerance ?? 0.75;
  const maxIssues = payload?.maxIssues ?? 100;
  const allSchematicPages = payload?.allSchematicPages ?? true;
  const { absolutePins, componentCount } = await collectSchematicPinLocations(allSchematicPages);
  const source = await eda.sys_FileManager.getDocumentSource();

  if (!source) {
    throw new Error('Unable to read the current schematic source.');
  }

  const components = parseSchematicComponents(source);
  const sourceWires = parseSourceWires(source);

  const segments = flattenWireSegments(sourceWires);

  const wireEndpoints = collectWireEndpoints(segments);
  const issues: Array<ConnectivityIssue> = [];

  for (const endpoint of wireEndpoints) {
    if (pointConnected(endpoint.point, segments, absolutePins, tolerance, endpoint.segmentIndex)) {
      continue;
    }

    issues.push({
      type: 'dangling_wire_endpoint',
      severity: 'warning',
      message: `Wire endpoint at (${endpoint.point.x}, ${endpoint.point.y}) is not connected.`,
      point: endpoint.point,
      wireId: endpoint.wireId,
      wireNet: endpoint.net,
    });

    if (issues.length >= maxIssues) {
      break;
    }
  }

  for (const pin of absolutePins) {
    if (pin.noConnected) {
      continue;
    }

    const connected = segments.some(segment =>
      pointOnSegment(pin, segment.start, segment.end, tolerance),
    );

    if (connected) {
      continue;
    }

    issues.push({
      type: 'unconnected_pin',
      severity: 'warning',
      message: `Pin ${pin.designator ?? pin.componentId ?? 'unknown'}.${pin.pinNumber ?? '?'} (${pin.pinName ?? 'unnamed'}) is not connected.`,
      point: { x: pin.x, y: pin.y },
      componentId: pin.componentId,
      designator: pin.designator,
      pinNumber: pin.pinNumber,
      pinName: pin.pinName,
    });

    if (issues.length >= maxIssues) {
      break;
    }
  }

  const zeroLengthSegments = segments.filter(segment => pointsEqual(segment.start, segment.end, tolerance));
  for (const segment of zeroLengthSegments) {
    issues.push({
      type: 'zero_length_segment',
      severity: 'info',
      message: `Wire ${segment.wireId} contains a zero-length segment at (${segment.start.x}, ${segment.start.y}).`,
      point: segment.start,
      wireId: segment.wireId,
      wireNet: segment.net,
    });

    if (issues.length >= maxIssues) {
      break;
    }
  }

  const connectedPins = absolutePins.filter(pin =>
    segments.some(segment => pointOnSegment(pin, segment.start, segment.end, tolerance)),
  ).length;

  const connectedEndpoints = wireEndpoints.filter(endpoint =>
    pointConnected(endpoint.point, segments, absolutePins, tolerance, endpoint.segmentIndex),
  ).length;

  return {
    summary: 'schematic connectivity diagnostics collected',
    data: {
      tolerance,
      allSchematicPages,
      componentCount,
      pinCount: absolutePins.length,
      wireCount: sourceWires.length,
      segmentCount: segments.length,
      connectedPinCount: connectedPins,
      connectedEndpointCount: connectedEndpoints,
      issueCount: issues.length,
      components: components.map(summarizeComponent),
      issues,
    },
  };
}
