export const BRIDGE_PROTOCOL_VERSION = '0.1.0';

export const BRIDGE_DOMAINS = ['project', 'schematic', 'pcb', 'system'] as const;

export const BRIDGE_STATUSES = ['success', 'error', 'confirmation_required'] as const;

export const BRIDGE_ERROR_CODES = [
  'INVALID_REQUEST',
  'UNSUPPORTED_DOMAIN',
  'UNSUPPORTED_ACTION',
  'INVALID_PAYLOAD',
  'DOCUMENT_NOT_READY',
  'SELECTION_REQUIRED',
  'CONFIRMATION_REQUIRED',
  'EXECUTION_FAILED',
  'INTERNAL_ERROR',
] as const;

export type BridgeDomain = (typeof BRIDGE_DOMAINS)[number];
export type BridgeStatus = (typeof BRIDGE_STATUSES)[number];
export type BridgeErrorCode = (typeof BRIDGE_ERROR_CODES)[number];

export interface BridgePoint {
  x: number;
  y: number;
}

export interface BridgeCommandPayloadMap {
  'project.get_inventory': Record<string, never>;
  'project.get_document_summary': Record<string, never>;
  'project.get_selection_snapshot': {
    includeComponents?: boolean;
    includeNets?: boolean;
  };
  'project.list_workspaces': Record<string, never>;
  'project.list_teams': Record<string, never>;
  'project.list_involved_teams': Record<string, never>;
  'project.list_projects': {
    teamUuid?: string;
    folderUuid?: string;
    workspaceUuid?: string;
  };
  'project.get_project_info': {
    projectUuid: string;
  };
  'project.open_project': {
    projectUuid: string;
  };
  'project.create_project': {
    projectFriendlyName: string;
    projectName?: string;
    teamUuid?: string;
    folderUuid?: string;
    description?: string;
    collaborationMode?: string;
  };
  'project.list_schematics': Record<string, never>;
  'project.list_schematic_pages': {
    schematicUuid?: string;
  };
  'project.list_boards': Record<string, never>;
  'project.list_pcbs': Record<string, never>;
  'project.get_board_summary': Record<string, never>;
  'project.create_board': {
    schematicUuid?: string;
    pcbUuid?: string;
  };
  'project.export_bom': {
    format?: 'json' | 'csv';
    fileName?: string;
    saveToLocal?: boolean;
  };
  'schematic.get_current_schematic_info': Record<string, never>;
  'schematic.create_schematic': {
    boardName?: string;
  };
  'schematic.create_schematic_page': {
    schematicUuid: string;
  };
  'schematic.place_component': {
    libraryUuid: string;
    uuid: string;
    position: BridgePoint;
    subPartName?: string;
    rotation?: number;
    mirror?: boolean;
    addIntoBom?: boolean;
    addIntoPcb?: boolean;
  };
  'schematic.create_wire': {
    points: Array<BridgePoint>;
    netName?: string;
  };
  'schematic.annotate_net': {
    netName: string;
    position: BridgePoint;
  };
  'schematic.create_net_flag': {
    identification: 'Power' | 'Ground' | 'AnalogGround' | 'ProtectGround';
    net: string;
    position: BridgePoint;
    rotation?: number;
    mirror?: boolean;
  };
  'schematic.create_net_port': {
    direction: 'IN' | 'OUT' | 'BI';
    net: string;
    position: BridgePoint;
    rotation?: number;
    mirror?: boolean;
  };
  'schematic.create_short_circuit_flag': {
    position: BridgePoint;
    rotation?: number;
    mirror?: boolean;
  };
  'pcb.get_board_summary': Record<string, never>;
  'pcb.get_current_pcb_info': Record<string, never>;
  'pcb.list_pcbs': Record<string, never>;
  'pcb.create_pcb': {
    boardName?: string;
  };
  'pcb.place_footprint': {
    libraryUuid: string;
    uuid: string;
    position: BridgePoint;
    rotation?: number;
    layer?: 'top' | 'bottom';
    primitiveLock?: boolean;
  };
  'system.ping': {
    echo?: string;
  };
  'system.get_bridge_status': Record<string, never>;
  'system.get_environment': Record<string, never>;
}

export type BridgeCommandName = keyof BridgeCommandPayloadMap;

type BridgeCommandDomainMap = {
  [K in BridgeCommandName]: K extends `${infer D}.${string}` ? D : never;
};

export type BridgeCommandDomain<K extends BridgeCommandName>
  = BridgeCommandDomainMap[K] extends BridgeDomain ? BridgeCommandDomainMap[K] : never;

export interface BridgeCommand<K extends BridgeCommandName = BridgeCommandName> {
  domain: BridgeCommandDomain<K>;
  action: K extends `${BridgeCommandDomain<K>}.${infer A}` ? A : string;
  requiresConfirmation?: boolean;
  payload: BridgeCommandPayloadMap[K];
}

export interface BridgeRequest<K extends BridgeCommandName = BridgeCommandName> {
  id: string;
  type: 'command.request';
  protocolVersion: typeof BRIDGE_PROTOCOL_VERSION;
  sessionId: string;
  command: BridgeCommand<K>;
}

export interface BridgeResult {
  summary: string;
  data?: unknown;
  artifacts?: Array<{
    kind: 'file' | 'entity' | 'snapshot';
    ref: string;
  }>;
  warnings?: string[];
}

export interface BridgeConfirmation {
  reason: string;
  riskLevel: 'low' | 'medium' | 'high';
  token: string;
}

export interface BridgeError {
  code: BridgeErrorCode;
  message: string;
  retryable: boolean;
  details?: Record<string, unknown>;
}

export interface BridgeResponseBase {
  id: string;
  type: 'command.response';
  protocolVersion: typeof BRIDGE_PROTOCOL_VERSION;
}

export interface BridgeSuccessResponse extends BridgeResponseBase {
  status: 'success';
  result: BridgeResult;
}

export interface BridgeErrorResponse extends BridgeResponseBase {
  status: 'error';
  error: BridgeError;
}

export interface BridgeConfirmationResponse extends BridgeResponseBase {
  status: 'confirmation_required';
  confirmation: BridgeConfirmation;
}

export type BridgeResponse = BridgeSuccessResponse | BridgeErrorResponse | BridgeConfirmationResponse;
