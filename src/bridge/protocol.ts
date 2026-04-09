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

export interface BridgeBinaryFilePayload {
  fileName?: string;
  mimeType?: string;
  contentBase64?: string;
  contentText?: string;
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
  'schematic.inspect_connectivity': {
    allSchematicPages?: boolean;
    tolerance?: number;
    maxIssues?: number;
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
  'system.get_update_config': Record<string, never>;
  'system.get_update_status': Record<string, never>;
  'system.check_for_updates': {
    force?: boolean;
  };
  'system.save_update_config': {
    repoOwner?: string;
    repoName?: string;
    githubToken?: string;
  };
  'system.api_invoke': {
    path: string;
    args?: Array<unknown>;
  };
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
  'system.shortcut_register': {
    shortcutKey: Array<string>;
    title: string;
    documentType?: Array<number>;
    scene?: Array<number>;
  };
  'system.shortcut_unregister': {
    shortcutKey: Array<string>;
  };
  'system.shortcut_list_registered': {
    includeSystem?: boolean;
  };
  'system.timer_set_interval': {
    id: string;
    timeout: number;
  };
  'system.timer_clear_interval': {
    id: string;
  };
  'system.timer_set_timeout': {
    id: string;
    timeout: number;
  };
  'system.timer_clear_timeout': {
    id: string;
  };
  'system.right_click_change_menu': {
    menuId: string;
    menuItems: Array<Record<string, unknown> | null>;
  };
  'system.callback_events_list': Record<string, never>;
  'system.callback_events_drain': Record<string, never>;
  'system.file_system_get_extension_file': {
    uri: string;
  };
  'system.file_system_save_file': BridgeBinaryFilePayload;
  'system.file_system_save_file_to_file_system': BridgeBinaryFilePayload & {
    uri: string;
    force?: boolean;
  };
  'system.file_system_list_files': {
    folderPath: string;
    recursive?: boolean;
  };
  'system.file_system_delete_file': {
    uri: string;
    force?: boolean;
  };
  'system.file_system_get_eda_path': Record<string, never>;
  'system.file_system_get_documents_path': Record<string, never>;
  'system.file_system_get_libraries_paths': Record<string, never>;
  'system.file_system_get_projects_paths': Record<string, never>;
  'system.file_manager_get_project_file': {
    fileName?: string;
    password?: string;
    fileType?: 'epro' | 'epro2';
  };
  'system.file_manager_get_document_file': {
    fileName?: string;
    password?: string;
    fileType?: 'epro' | 'epro2';
  };
  'system.file_manager_get_document_source': Record<string, never>;
  'system.file_manager_get_document_footprint_sources': Record<string, never>;
  'system.file_manager_set_document_source': {
    source: string;
  };
  'system.file_manager_get_project_file_by_project_uuid': {
    projectUuid: string;
    fileName?: string;
    password?: string;
    fileType?: 'epro' | 'epro2';
  };
  'system.file_manager_get_device_file_by_device_uuid': {
    deviceUuid: string | Array<string>;
    libraryUuid?: string;
    fileType?: 'elibz' | 'elibz2';
  };
  'system.file_manager_get_symbol_file_by_symbol_uuid': {
    symbolUuid: string | Array<string>;
    libraryUuid?: string;
    fileType?: 'elibz' | 'elibz2';
  };
  'system.storage_get_all_user_configs': Record<string, never>;
  'system.storage_set_all_user_configs': {
    configs: Record<string, unknown>;
  };
  'system.storage_clear_all_user_configs': Record<string, never>;
  'system.storage_get_user_config': {
    key: string;
  };
  'system.storage_set_user_config': {
    key: string;
    value: unknown;
  };
  'system.storage_delete_user_config': {
    key: string;
  };
  'system.tool_netlist_comparison': {
    left: string | {
      projectUuid: string;
      documentUuid?: string;
      schematicUuid?: string;
      pcbUuid?: string;
    };
    right: string | {
      projectUuid: string;
      documentUuid?: string;
      schematicUuid?: string;
      pcbUuid?: string;
    };
  };
  'system.tool_schematic_comparison': {
    left: string | {
      projectUuid: string;
      documentUuid?: string;
      schematicUuid?: string;
    };
    right: string | {
      projectUuid: string;
      documentUuid?: string;
      schematicUuid?: string;
    };
  };
  'system.tool_pcb_comparison': {
    left: string | {
      projectUuid: string;
      documentUuid?: string;
      pcbUuid?: string;
    };
    right: string | {
      projectUuid: string;
      documentUuid?: string;
      pcbUuid?: string;
    };
  };
  'system.header_menu_replace': {
    headerMenus: Record<string, unknown>;
  };
  'system.header_menu_insert': {
    headerMenus: Record<string, unknown>;
  };
  'system.header_menu_remove': Record<string, never>;
  'system.header_menu_insert_system_item': {
    env: 'home' | 'blank' | 'sch' | 'symbol' | 'pcb' | 'footprint' | 'pcbView' | 'panel' | 'panelView';
    id: Array<string>;
    props: Record<string, unknown>;
  };
  'system.header_menu_remove_system_item': {
    id: Array<string>;
    props?: {
      removeTheBeforeDivider?: boolean;
      removeTheAfterDivider?: boolean;
    };
  };
  'system.format_conversion_ad_single': {
    files: Array<BridgeBinaryFilePayload> | BridgeBinaryFilePayload;
  };
  'system.format_conversion_ad_multi': {
    files: Array<BridgeBinaryFilePayload> | BridgeBinaryFilePayload;
  };
  'system.format_conversion_disa_single': {
    files: Array<BridgeBinaryFilePayload> | BridgeBinaryFilePayload;
  };
  'system.format_conversion_disa_multi': {
    files: Array<BridgeBinaryFilePayload> | BridgeBinaryFilePayload;
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
