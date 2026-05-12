export interface Point2D {
  x: number;
  y: number;
}

export interface SourceRecord {
  header: Record<string, unknown>;
  body: Record<string, unknown>;
}

export function parseSourceRecord(line: string): SourceRecord | undefined {
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

export function normalizeNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  return undefined;
}

export function distanceSquaredBetweenPoints(left: Point2D, right: Point2D): number {
  const dx = left.x - right.x;
  const dy = left.y - right.y;
  return dx * dx + dy * dy;
}

export function distanceSquaredPointToSegment(point: Point2D, start: Point2D, end: Point2D): number {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const lengthSquared = dx * dx + dy * dy;

  if (lengthSquared === 0) {
    return distanceSquaredBetweenPoints(point, start);
  }

  const rawT = ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared;
  const t = Math.min(1, Math.max(0, rawT));
  const projected = {
    x: start.x + dx * t,
    y: start.y + dy * t,
  };

  return distanceSquaredBetweenPoints(point, projected);
}
