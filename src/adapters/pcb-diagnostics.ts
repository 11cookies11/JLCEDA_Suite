import type { BridgeResult } from '../bridge/protocol';
import { getDefaultRuleProfileSnapshot, getRuleProfileSnapshot } from '../remote/rule-profile';
import { type Point2D, parseSourceRecord, normalizeNumber, distanceSquaredBetweenPoints, distanceSquaredPointToSegment } from './shared-utils';

interface Point {
  x: number;
  y: number;
}

interface PcbComponentSource {
  primitiveId: string;
  x: number;
  y: number;
  designator?: string;
  name?: string;
}

interface PcbTrackSegment {
  trackId: string;
  net?: string;
  start: Point;
  end: Point;
}

interface PcbLayoutIssue {
  type: 'component_component_proximity' | 'component_track_proximity' | 'component_label_component_proximity' | 'component_label_track_proximity' | 'board_edge_component_proximity';
  severity: 'warning' | 'info';
  message: string;
  componentId?: string;
  designator?: string;
  relatedComponentId?: string;
  relatedDesignator?: string;
  trackId?: string;
  trackNet?: string;
  distance?: number;
  suggestedPosition?: Point;
}

interface InspectPcbLayoutHygienePayload {
  allPcbPages?: boolean;
  componentClearance?: number;
  trackClearance?: number;
  labelClearance?: number;
  boardEdgeClearance?: number;
  maxIssues?: number;
}

interface PcbBoardBounds {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

function parsePcbComponents(source: string): Array<PcbComponentSource> {
  const components: Array<PcbComponentSource> = [];

  for (const line of source.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    const record = parseSourceRecord(trimmed);
    if (!record || String(record.header.type ?? '') !== 'COMPONENT') {
      continue;
    }

    const body = record.body;
    const x = normalizeNumber(body.x);
    const y = normalizeNumber(body.y);

    if (x === undefined || y === undefined) {
      continue;
    }

    components.push({
      primitiveId: String(record.header.id ?? ''),
      x,
      y,
      designator: typeof body.designator === 'string' ? body.designator : undefined,
      name: typeof body.name === 'string' ? body.name : undefined,
    });
  }

  return components;
}

function parsePcbTracks(source: string): Array<PcbTrackSegment> {
  const groups = new Map<string, { trackId: string; net?: string; segments: Array<PcbTrackSegment> }>();

  for (const line of source.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    const record = parseSourceRecord(trimmed);
    if (!record) {
      continue;
    }

    const headerType = String(record.header.type ?? '');
    const recordId = String(record.header.id ?? '');
    const body = record.body;

    if (headerType === 'LINE' || headerType === 'TRACK') {
      const trackGroup = String(body.trackGroup ?? body.lineGroup ?? recordId);
      const startX = normalizeNumber(body.startX ?? body.x1);
      const startY = normalizeNumber(body.startY ?? body.y1);
      const endX = normalizeNumber(body.endX ?? body.x2);
      const endY = normalizeNumber(body.endY ?? body.y2);

      if (!trackGroup || startX === undefined || startY === undefined || endX === undefined || endY === undefined) {
        continue;
      }

      const group = groups.get(trackGroup) ?? {
        trackId: trackGroup,
        segments: [],
      };
      group.segments.push({
        trackId: trackGroup,
        start: { x: startX, y: startY },
        end: { x: endX, y: endY },
      });
      groups.set(trackGroup, group);
      continue;
    }

    if (headerType === 'ATTR' && String(body.key ?? '') === 'NET') {
      const parentId = String(body.parentId ?? '');
      if (!parentId) {
        continue;
      }

      const group = groups.get(parentId) ?? {
        trackId: parentId,
        segments: [],
      };
      group.net = typeof body.value === 'string' ? body.value : undefined;
      groups.set(parentId, group);
    }
  }

  const segments: Array<PcbTrackSegment> = [];
  for (const group of groups.values()) {
    for (const segment of group.segments) {
      segments.push({
        trackId: group.trackId,
        net: group.net,
        start: segment.start,
        end: segment.end,
      });
    }
  }

  return segments;
}

function parsePcbBoardBounds(source: string): Array<PcbBoardBounds> {
  const boards: Array<PcbBoardBounds> = [];

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
    if (type !== 'BOARD' && type !== 'BOARD_OUTLINE' && type !== 'OUTLINE') {
      continue;
    }

    const body = record.body;
    const left = normalizeNumber(body.left ?? body.minX ?? body.x1);
    const right = normalizeNumber(body.right ?? body.maxX ?? body.x2);
    const top = normalizeNumber(body.top ?? body.maxY ?? body.y1);
    const bottom = normalizeNumber(body.bottom ?? body.minY ?? body.y2);

    if (left !== undefined && right !== undefined && top !== undefined && bottom !== undefined) {
      boards.push({ left, right, top, bottom });
      continue;
    }

    const x = normalizeNumber(body.x);
    const y = normalizeNumber(body.y);
    const width = normalizeNumber(body.width);
    const height = normalizeNumber(body.height);

    if (x !== undefined && y !== undefined && width !== undefined && height !== undefined) {
      boards.push({
        left: x,
        right: x + width,
        top: y,
        bottom: y + height,
      });
    }
  }

  return boards;
}

function estimateLabelAnchor(
  component: PcbComponentSource,
  profile: Awaited<ReturnType<typeof getRuleProfileSnapshot>>,
): Point {
  const nameLength = (component.designator ?? component.name ?? '').length;
  const horizontalOffset = Math.min(
    profile.pcb.labelHorizontalOffsetMax,
    profile.pcb.labelHorizontalOffsetBase + nameLength * 2,
  );
  const verticalOffset = Math.min(
    profile.pcb.labelVerticalOffsetMax,
    profile.pcb.labelVerticalOffsetBase + Math.ceil(nameLength / 6) * 4,
  );

  return {
    x: component.x + horizontalOffset,
    y: component.y - verticalOffset,
  };
}

export async function inspectPcbLayoutHygieneResult(
  payload?: InspectPcbLayoutHygienePayload,
): Promise<BridgeResult> {
  const profile = await getRuleProfileSnapshot();
  const defaultProfile = getDefaultRuleProfileSnapshot();
  const componentClearance = payload?.componentClearance ?? profile.pcb.componentClearance ?? defaultProfile.pcb.componentClearance;
  const trackClearance = payload?.trackClearance ?? profile.pcb.trackClearance ?? defaultProfile.pcb.trackClearance;
  const labelClearance = payload?.labelClearance ?? profile.pcb.labelClearance ?? defaultProfile.pcb.labelClearance;
  const boardEdgeClearance = payload?.boardEdgeClearance ?? profile.pcb.boardEdgeClearance ?? defaultProfile.pcb.boardEdgeClearance;
  const maxIssues = payload?.maxIssues ?? 100;
  const source = await eda.sys_FileManager.getDocumentSource();

  if (!source) {
    throw new Error('Unable to read the current PCB source.');
  }

  const components = parsePcbComponents(source);
  const tracks = parsePcbTracks(source);
  const boardBounds = parsePcbBoardBounds(source);
  const issues: Array<PcbLayoutIssue> = [];

  for (let i = 0; i < components.length; i += 1) {
    const component = components[i];
    const componentPoint = { x: component.x, y: component.y };

    for (let j = i + 1; j < components.length; j += 1) {
      const other = components[j];
      const distance = Math.sqrt(distanceSquaredBetweenPoints(componentPoint, { x: other.x, y: other.y }));

      if (distance > componentClearance) {
        continue;
      }

      issues.push({
        type: 'component_component_proximity',
        severity: 'warning',
        message: `PCB component ${component.designator ?? component.primitiveId ?? 'unknown'} is too close to ${other.designator ?? other.primitiveId ?? 'another component'} (${distance.toFixed(1)} < ${componentClearance}).`,
        componentId: component.primitiveId,
        designator: component.designator,
        relatedComponentId: other.primitiveId,
        relatedDesignator: other.designator,
        distance,
      });

      if (issues.length >= maxIssues) {
        break;
      }
    }

    if (issues.length >= maxIssues) {
      break;
    }

    const labelAnchor = estimateLabelAnchor(component, profile);

    for (const other of components) {
      if (other.primitiveId === component.primitiveId) {
        continue;
      }

      const distance = Math.sqrt(distanceSquaredBetweenPoints(labelAnchor, { x: other.x, y: other.y }));
      if (distance > labelClearance) {
        continue;
      }

      issues.push({
        type: 'component_label_component_proximity',
        severity: 'warning',
        message: `PCB label for ${component.designator ?? component.primitiveId ?? 'unknown'} is crowded by ${other.designator ?? other.primitiveId ?? 'another component'} (${distance.toFixed(1)} < ${labelClearance}).`,
        componentId: component.primitiveId,
        designator: component.designator,
        relatedComponentId: other.primitiveId,
        relatedDesignator: other.designator,
        distance,
        suggestedPosition: labelAnchor,
      });

      if (issues.length >= maxIssues) {
        break;
      }
    }

    if (issues.length >= maxIssues) {
      break;
    }

    for (const track of tracks) {
      const distance = Math.sqrt(distanceSquaredPointToSegment(labelAnchor, track.start, track.end));
      if (distance > trackClearance) {
        continue;
      }

      issues.push({
        type: 'component_label_track_proximity',
        severity: 'warning',
        message: `PCB label for ${component.designator ?? component.primitiveId ?? 'unknown'} is too close to track ${track.trackId}${track.net ? ` (${track.net})` : ''} (${distance.toFixed(1)} < ${trackClearance}).`,
        componentId: component.primitiveId,
        designator: component.designator,
        trackId: track.trackId,
        trackNet: track.net,
        distance,
        suggestedPosition: labelAnchor,
      });

      if (issues.length >= maxIssues) {
        break;
      }
    }

    if (issues.length >= maxIssues) {
      break;
    }

    for (const board of boardBounds) {
      const leftDistance = componentPoint.x - board.left;
      const rightDistance = board.right - componentPoint.x;
      const topDistance = board.top - componentPoint.y;
      const bottomDistance = componentPoint.y - board.bottom;

      const nearestEdgeDistance = Math.min(leftDistance, rightDistance, topDistance, bottomDistance);
      if (nearestEdgeDistance > boardEdgeClearance) {
        continue;
      }

      issues.push({
        type: 'board_edge_component_proximity',
        severity: 'warning',
        message: `PCB component ${component.designator ?? component.primitiveId ?? 'unknown'} is too close to the board edge (${nearestEdgeDistance.toFixed(1)} < ${boardEdgeClearance}).`,
        componentId: component.primitiveId,
        designator: component.designator,
        distance: nearestEdgeDistance,
      });

      if (issues.length >= maxIssues) {
        break;
      }
    }

    if (issues.length >= maxIssues) {
      break;
    }
  }

  return {
    summary: 'PCB layout hygiene inspected',
    data: {
      componentCount: components.length,
      trackCount: tracks.length,
      boardCount: boardBounds.length,
      componentClearance,
      trackClearance,
      labelClearance,
      boardEdgeClearance,
      issueCount: issues.length,
      issues,
    },
  };
}
