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
  'project.open_document': {
    documentUuid: string;
    splitScreenId?: string;
  };
  'project.open_library_document': {
    libraryUuid: string;
    libraryType: 'symbol' | 'footprint';
    uuid: string;
    splitScreenId?: string;
  };
  'project.close_document': {
    tabId: string;
  };
  'project.get_split_screen_tree': Record<string, never>;
  'project.get_split_screen_id_by_tab_id': {
    tabId: string;
  };
  'project.get_tabs_by_split_screen_id': {
    splitScreenId: string;
  };
  'project.create_split_screen': {
    splitScreenType: 'horizontal' | 'vertical';
    tabId: string;
  };
  'project.move_document_to_split_screen': {
    tabId: string;
    splitScreenId: string;
  };
  'project.activate_document': {
    tabId: string;
  };
  'project.activate_split_screen': {
    splitScreenId: string;
  };
  'project.tile_all_documents_to_split_screen': Record<string, never>;
  'project.merge_all_documents_from_split_screen': Record<string, never>;
  'project.get_current_rendered_area_image': {
    tabId?: string;
  };
  'project.zoom_to_region': {
    left: number;
    right: number;
    top: number;
    bottom: number;
    tabId?: string;
  };
  'project.zoom_to': {
    x?: number;
    y?: number;
    scaleRatio?: number;
    tabId?: string;
  };
  'project.zoom_to_all_primitives': {
    tabId?: string;
  };
  'project.zoom_to_selected_primitives': {
    tabId?: string;
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
  'schematic.import_changes': Record<string, never>;
  'schematic.save': Record<string, never>;
  'schematic.navigate_to_coordinates': {
    x: number;
    y: number;
  };
  'schematic.navigate_to_region': {
    left: number;
    right: number;
    top: number;
    bottom: number;
  };
  'schematic.get_primitive_at_point': {
    x: number;
    y: number;
  };
  'schematic.get_primitives_in_region': {
    left: number;
    right: number;
    top: number;
    bottom: number;
  };
  'schematic.get_current_filter_configuration': Record<string, never>;
  'schematic.auto_routing': {
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
  };
  'schematic.auto_layout': {
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
  };
  'schematic.check_drc': {
    strict?: boolean;
    userInterface?: boolean;
    includeVerboseError?: boolean;
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
  'pcb.import_changes': {
    schematicUuid?: string;
  };
  'pcb.save': {
    pcbUuid?: string;
  };
  'pcb.get_calculating_ratline_status': Record<string, never>;
  'pcb.start_calculating_ratline': Record<string, never>;
  'pcb.stop_calculating_ratline': Record<string, never>;
  'pcb.convert_canvas_origin_to_data_origin': {
    x: number;
    y: number;
  };
  'pcb.convert_data_origin_to_canvas_origin': {
    x: number;
    y: number;
  };
  'pcb.get_canvas_origin': Record<string, never>;
  'pcb.set_canvas_origin': {
    offsetX: number;
    offsetY: number;
  };
  'pcb.navigate_to_coordinates': {
    x: number;
    y: number;
  };
  'pcb.navigate_to_region': {
    left: number;
    right: number;
    top: number;
    bottom: number;
  };
  'pcb.get_primitive_at_point': {
    x: number;
    y: number;
  };
  'pcb.get_primitives_in_region': {
    left: number;
    right: number;
    top: number;
    bottom: number;
  };
  'pcb.zoom_to_board_outline': Record<string, never>;
  'pcb.get_current_filter_configuration': Record<string, never>;
  'pcb.clear_routing': {
    type?: 'all' | 'net' | 'connection';
  };
  'project.save_panel': Record<string, never>;
  'system.ping': {
    echo?: string;
  };
  'system.get_bridge_status': Record<string, never>;
  'system.get_environment': Record<string, never>;
  'system.log_add': {
    message: string;
    type?: 'info' | 'warn' | 'error' | 'fatalError' | 'find' | 'replace' | 'openProject';
  };
  'system.log_clear': Record<string, never>;
  'system.log_export': {
    types?: Array<'info' | 'warn' | 'error' | 'fatalError' | 'find' | 'replace' | 'openProject'> | 'info' | 'warn' | 'error' | 'fatalError' | 'find' | 'replace' | 'openProject';
  };
  'system.log_sort': {
    types?: Array<'info' | 'warn' | 'error' | 'fatalError' | 'find' | 'replace' | 'openProject'> | 'info' | 'warn' | 'error' | 'fatalError' | 'find' | 'replace' | 'openProject';
  };
  'system.log_find': {
    message: string | Array<string | {
      text: string;
      attr?: {
        id?: string;
        path?: string;
        sheet?: string;
        pcbid?: string;
        type?: string;
      };
    }>;
    types?: Array<'info' | 'warn' | 'error' | 'fatalError' | 'find' | 'replace' | 'openProject'> | 'info' | 'warn' | 'error' | 'fatalError' | 'find' | 'replace' | 'openProject';
  };
  'system.panel_open_left': {
    tab?: string;
  };
  'system.panel_close_left': Record<string, never>;
  'system.panel_toggle_left_lock': {
    state?: boolean;
  };
  'system.panel_is_left_locked': Record<string, never>;
  'system.panel_open_right': {
    tab?: string;
  };
  'system.panel_close_right': Record<string, never>;
  'system.panel_toggle_right_lock': {
    state?: boolean;
  };
  'system.panel_is_right_locked': Record<string, never>;
  'system.panel_open_bottom': {
    tab?: string;
  };
  'system.panel_close_bottom': Record<string, never>;
  'system.panel_toggle_bottom_lock': {
    state?: boolean;
  };
  'system.panel_is_bottom_locked': Record<string, never>;
  'system.window_open': {
    url: string;
    target?: '_blank' | '_self';
  };
  'system.window_open_ui': {
    uiName: string;
    args?: Record<string, unknown>;
  };
  'system.window_get_current_theme': Record<string, never>;
  'system.window_get_url_param': {
    key: string;
  };
  'system.window_get_url_anchor': Record<string, never>;
  'system.show_toast_message': {
    message: string;
    messageType?: 'error' | 'warn' | 'info' | 'success' | 'question';
    timer?: number;
    bottomPanel?: string;
    buttonTitle?: string;
    buttonCallbackFn?: string;
  };
  'system.show_follow_mouse_tip': {
    tip: string;
    msTimeout?: number;
  };
  'system.remove_follow_mouse_tip': {
    tip?: string;
  };
  'system.show_information_message': {
    content: string;
    title?: string;
    buttonTitle?: string;
  };
  'system.show_confirmation_message': {
    content: string;
    title?: string;
    mainButtonTitle?: string;
    buttonTitle?: string;
  };
  'system.shortcut_get_shortcuts': {
    includeSystem?: boolean;
  };
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
