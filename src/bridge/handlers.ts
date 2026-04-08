import type {
  BridgeCommandName,
  BridgeCommandPayloadMap,
  BridgeConfirmation,
  BridgeError,
  BridgeRequest,
  BridgeResponse,
  BridgeResult,
} from './protocol';
import {
  changeRightClickMenuResult,
  clearIntervalTimerResult,
  clearTimeoutTimerResult,
  drainCallbackEventsResult,
  listCallbackEventsResult,
  listShortcutKeysResult,
  registerShortcutKeyResult,
  setIntervalTimerResult,
  setTimeoutTimerResult,
  unregisterShortcutKeyResult,
} from '../adapters/callback-control';
import {
  activateDocumentResult,
  activateSplitScreenResult,
  autoLayoutSchematicResult,
  autoRouteSchematicResult,
  checkSchematicDrcResult,
  clearPcbRoutingResult,
  closeDocumentResult,
  convertCanvasOriginToDataOriginResult,
  convertDataOriginToCanvasOriginResult,
  createSplitScreenResult,
  getCurrentRenderedAreaImageResult,
  getEditorSplitScreenIdByTabIdResult,
  getEditorSplitScreenTreeResult,
  getEditorTabsBySplitScreenIdResult,
  getPcbCalculatingRatlineStatusResult,
  getPcbCanvasOriginResult,
  getPcbFilterConfigurationResult,
  getPcbPrimitiveAtPointResult,
  getPcbPrimitivesInRegionResult,
  getSchematicFilterConfigurationResult,
  getSchematicPrimitiveAtPointResult,
  getSchematicPrimitivesInRegionResult,
  importPcbChangesResult,
  importSchematicChangesResult,
  mergeAllDocumentsFromSplitScreenResult,
  moveDocumentToSplitScreenResult,
  navigatePcbToCoordinatesResult,
  navigatePcbToRegionResult,
  navigateSchematicToCoordinatesResult,
  navigateSchematicToRegionResult,
  openDocumentResult,
  openLibraryDocumentResult,
  savePanelResult,
  savePcbResult,
  saveSchematicResult,
  setPcbCanvasOriginResult,
  startPcbCalculatingRatlineResult,
  stopPcbCalculatingRatlineResult,
  tileAllDocumentsToSplitScreenResult,
  zoomPcbToBoardOutlineResult,
  zoomToAllPrimitivesResult,
  zoomToRegionResult,
  zoomToResult,
  zoomToSelectedPrimitivesResult,
} from '../adapters/document-control';
import {
  createBoardResult,
  createPcbResult,
  createProjectResult,
  createSchematicPageResult,
  createSchematicResult,
  getBoardSummaryResult,
  getCurrentPcbInfoResult,
  getCurrentSchematicInfoResult,
  getProjectInfoResult,
  getProjectInventoryResult,
  getSystemEnvironmentResult,
  listBoardsResult,
  listPcbsResult,
  listProjectsResult,
  listSchematicPagesResult,
  listSchematicsResult,
  listTeamsResult,
  listWorkspacesResult,
  openProjectResult,
} from '../adapters/document-tree';
import {
  exportProjectBom,
} from '../adapters/export';
import {
  getBridgeStatusResult,
  getDocumentSummaryResult,
  getSelectionSnapshotResult,
  pingBridgeResult,
} from '../adapters/read-only';
import {
  annotateSchematicNet,
  createSchematicNetFlag,
  createSchematicNetPort,
  createSchematicShortCircuitFlag,
  createSchematicWire,
  placePcbFootprint,
  placeSchematicComponent,
} from '../adapters/schematic-write';
import {
  addSystemLogResult,
  clearSystemLogResult,
  closeBottomPanelResult,
  closeLeftPanelResult,
  closeRightPanelResult,
  exportSystemLogResult,
  findSystemLogResult,
  getCurrentThemeResult,
  getShortcutKeysResult,
  getUrlAnchorResult,
  getUrlParamResult,
  isBottomPanelLockedResult,
  isLeftPanelLockedResult,
  isRightPanelLockedResult,
  openBottomPanelResult,
  openLeftPanelResult,
  openRightPanelResult,
  openUiWindowResult,
  openWindowResult,
  removeFollowMouseTipResult,
  showConfirmationMessageResult,
  showFollowMouseTipResult,
  showInformationMessageResult,
  showToastMessageResult,
  sortSystemLogResult,
  toggleBottomPanelLockResult,
  toggleLeftPanelLockResult,
  toggleRightPanelLockResult,
} from '../adapters/system-control';
import {
  clearExtensionAllUserConfigsResult,
  convertAltiumDesignerLibrariesToEasyEDAMultiFilesResult,
  convertAltiumDesignerLibrariesToEasyEDASingleFileResult,
  convertDisaLibrariesToEasyEDAMultiFilesResult,
  convertDisaLibrariesToEasyEDASingleFileResult,
  deleteExtensionUserConfigResult,
  deleteFileInFileSystemResult,
  getDeviceFileByDeviceUuidResult,
  getDocumentFileResult,
  getDocumentFootprintSourcesResult,
  getDocumentSourceResult,
  getDocumentsPathResult,
  getEdaPathResult,
  getExtensionAllUserConfigsResult,
  getExtensionFileResult,
  getExtensionUserConfigResult,
  getLibrariesPathsResult,
  getProjectFileByProjectUuidResult,
  getProjectFileResult,
  getProjectsPathsResult,
  getSymbolFileBySymbolUuidResult,
  insertHeaderMenusResult,
  insertSystemHeaderMenuItemResult,
  listFilesOfFileSystemResult,
  netlistComparisonResult,
  pcbComparisonResult,
  removeHeaderMenusResult,
  removeSystemHeaderMenuItemResult,
  replaceHeaderMenusResult,
  saveFileResult,
  saveFileToFileSystemResult,
  schematicComparisonResult,
  setDocumentSourceResult,
  setExtensionAllUserConfigsResult,
  setExtensionUserConfigResult,
} from '../adapters/utility-control';
import { BRIDGE_PROTOCOL_VERSION } from './protocol';
import { getCommandDescriptor, isCommandImplemented } from './registry';

function createBaseResponse(id: string): Pick<BridgeResponse, 'id' | 'type' | 'protocolVersion'> {
  return {
    id,
    type: 'command.response',
    protocolVersion: BRIDGE_PROTOCOL_VERSION,
  };
}

function createSuccessResponse(id: string, result: BridgeResult): BridgeResponse {
  return {
    ...createBaseResponse(id),
    status: 'success',
    result,
  };
}

function createErrorResponse(id: string, error: BridgeError): BridgeResponse {
  return {
    ...createBaseResponse(id),
    status: 'error',
    error,
  };
}

function createConfirmationResponse(id: string, confirmation: BridgeConfirmation): BridgeResponse {
  return {
    ...createBaseResponse(id),
    status: 'confirmation_required',
    confirmation,
  };
}

function getCommandKey(request: BridgeRequest): BridgeCommandName | undefined {
  const commandKey = `${request.command.domain}.${request.command.action}`;
  return commandKey as BridgeCommandName;
}

function validateRequest(request: BridgeRequest, commandKey?: BridgeCommandName): BridgeError | undefined {
  if (request.type !== 'command.request') {
    return {
      code: 'INVALID_REQUEST',
      message: `Unsupported request type: ${request.type}`,
      retryable: false,
    };
  }

  if (request.protocolVersion !== BRIDGE_PROTOCOL_VERSION) {
    return {
      code: 'INVALID_REQUEST',
      message: `Unsupported protocol version: ${request.protocolVersion}`,
      retryable: false,
      details: {
        expected: BRIDGE_PROTOCOL_VERSION,
      },
    };
  }

  if (!commandKey) {
    return {
      code: 'UNSUPPORTED_ACTION',
      message: 'Unable to resolve command from request domain and action.',
      retryable: false,
    };
  }

  const descriptor = getCommandDescriptor(commandKey);

  if (!descriptor) {
    return {
      code: 'UNSUPPORTED_ACTION',
      message: `Unsupported bridge command: ${commandKey}`,
      retryable: false,
      details: {
        command: commandKey,
      },
    };
  }

  if (descriptor.domain !== request.command.domain) {
    return {
      code: 'INVALID_REQUEST',
      message: `Command domain mismatch for ${commandKey}`,
      retryable: false,
      details: {
        expectedDomain: descriptor.domain,
        receivedDomain: request.command.domain,
      },
    };
  }

  if (request.command.payload === undefined || request.command.payload === null) {
    return {
      code: 'INVALID_PAYLOAD',
      message: `Missing payload for ${commandKey}`,
      retryable: false,
    };
  }

  return undefined;
}

function getConfirmationResponseIfNeeded(
  request: BridgeRequest,
  commandKey: BridgeCommandName,
): BridgeResponse | undefined {
  const descriptor = getCommandDescriptor(commandKey);

  if (!descriptor) {
    return undefined;
  }

  const requiresConfirmation = request.command.requiresConfirmation ?? descriptor.requiresConfirmationByDefault;

  if (!requiresConfirmation) {
    return undefined;
  }

  return createConfirmationResponse(request.id, {
    reason: `${commandKey} modifies editor state and requires explicit confirmation.`,
    riskLevel: descriptor.domain === 'system' || descriptor.domain === 'project' ? 'medium' : 'high',
    token: `confirm_${request.id}`,
  });
}

export async function executeBridgeRequest(request: BridgeRequest): Promise<BridgeResponse> {
  const commandKey = getCommandKey(request);
  const validationError = validateRequest(request, commandKey);

  if (validationError) {
    return createErrorResponse(request.id, validationError);
  }

  const resolvedCommandKey = commandKey as BridgeCommandName;

  const confirmationResponse = getConfirmationResponseIfNeeded(request, resolvedCommandKey);

  if (confirmationResponse) {
    return confirmationResponse;
  }

  if (!isCommandImplemented(resolvedCommandKey)) {
    return createErrorResponse(request.id, {
      code: 'UNSUPPORTED_ACTION',
      message: `Command is registered but not implemented yet: ${resolvedCommandKey}`,
      retryable: false,
      details: {
        command: resolvedCommandKey,
      },
    });
  }

  try {
    switch (resolvedCommandKey) {
      case 'system.ping':
        return createSuccessResponse(
          request.id,
          await pingBridgeResult(request.command.payload as BridgeCommandPayloadMap['system.ping']),
        );
      case 'system.get_bridge_status':
        return createSuccessResponse(request.id, await getBridgeStatusResult());
      case 'system.get_environment':
        return createSuccessResponse(request.id, await getSystemEnvironmentResult());
      case 'system.log_add':
        return createSuccessResponse(
          request.id,
          await addSystemLogResult(request.command.payload as BridgeCommandPayloadMap['system.log_add']),
        );
      case 'system.log_clear':
        return createSuccessResponse(request.id, await clearSystemLogResult());
      case 'system.log_export':
        return createSuccessResponse(
          request.id,
          await exportSystemLogResult(request.command.payload as BridgeCommandPayloadMap['system.log_export']),
        );
      case 'system.log_sort':
        return createSuccessResponse(
          request.id,
          await sortSystemLogResult(request.command.payload as BridgeCommandPayloadMap['system.log_sort']),
        );
      case 'system.log_find':
        return createSuccessResponse(
          request.id,
          await findSystemLogResult(request.command.payload as BridgeCommandPayloadMap['system.log_find']),
        );
      case 'system.panel_open_left':
        return createSuccessResponse(
          request.id,
          await openLeftPanelResult(request.command.payload as BridgeCommandPayloadMap['system.panel_open_left']),
        );
      case 'system.panel_close_left':
        return createSuccessResponse(request.id, await closeLeftPanelResult());
      case 'system.panel_toggle_left_lock':
        return createSuccessResponse(
          request.id,
          await toggleLeftPanelLockResult(
            request.command.payload as BridgeCommandPayloadMap['system.panel_toggle_left_lock'],
          ),
        );
      case 'system.panel_is_left_locked':
        return createSuccessResponse(request.id, await isLeftPanelLockedResult());
      case 'system.panel_open_right':
        return createSuccessResponse(
          request.id,
          await openRightPanelResult(request.command.payload as BridgeCommandPayloadMap['system.panel_open_right']),
        );
      case 'system.panel_close_right':
        return createSuccessResponse(request.id, await closeRightPanelResult());
      case 'system.panel_toggle_right_lock':
        return createSuccessResponse(
          request.id,
          await toggleRightPanelLockResult(
            request.command.payload as BridgeCommandPayloadMap['system.panel_toggle_right_lock'],
          ),
        );
      case 'system.panel_is_right_locked':
        return createSuccessResponse(request.id, await isRightPanelLockedResult());
      case 'system.panel_open_bottom':
        return createSuccessResponse(
          request.id,
          await openBottomPanelResult(request.command.payload as BridgeCommandPayloadMap['system.panel_open_bottom']),
        );
      case 'system.panel_close_bottom':
        return createSuccessResponse(request.id, await closeBottomPanelResult());
      case 'system.panel_toggle_bottom_lock':
        return createSuccessResponse(
          request.id,
          await toggleBottomPanelLockResult(
            request.command.payload as BridgeCommandPayloadMap['system.panel_toggle_bottom_lock'],
          ),
        );
      case 'system.panel_is_bottom_locked':
        return createSuccessResponse(request.id, await isBottomPanelLockedResult());
      case 'system.window_open':
        return createSuccessResponse(
          request.id,
          await openWindowResult(request.command.payload as BridgeCommandPayloadMap['system.window_open']),
        );
      case 'system.window_open_ui':
        return createSuccessResponse(
          request.id,
          await openUiWindowResult(request.command.payload as BridgeCommandPayloadMap['system.window_open_ui']),
        );
      case 'system.window_get_current_theme':
        return createSuccessResponse(request.id, await getCurrentThemeResult());
      case 'system.window_get_url_param':
        return createSuccessResponse(
          request.id,
          await getUrlParamResult(
            (request.command.payload as BridgeCommandPayloadMap['system.window_get_url_param']).key,
          ),
        );
      case 'system.window_get_url_anchor':
        return createSuccessResponse(request.id, await getUrlAnchorResult());
      case 'system.show_toast_message':
        return createSuccessResponse(
          request.id,
          await showToastMessageResult(request.command.payload as BridgeCommandPayloadMap['system.show_toast_message']),
        );
      case 'system.show_follow_mouse_tip':
        return createSuccessResponse(
          request.id,
          await showFollowMouseTipResult(
            request.command.payload as BridgeCommandPayloadMap['system.show_follow_mouse_tip'],
          ),
        );
      case 'system.remove_follow_mouse_tip':
        return createSuccessResponse(
          request.id,
          await removeFollowMouseTipResult(
            request.command.payload as BridgeCommandPayloadMap['system.remove_follow_mouse_tip'],
          ),
        );
      case 'system.show_information_message':
        return createSuccessResponse(
          request.id,
          await showInformationMessageResult(
            request.command.payload as BridgeCommandPayloadMap['system.show_information_message'],
          ),
        );
      case 'system.show_confirmation_message':
        return createSuccessResponse(
          request.id,
          await showConfirmationMessageResult(
            request.command.payload as BridgeCommandPayloadMap['system.show_confirmation_message'],
          ),
        );
      case 'system.shortcut_get_shortcuts':
        return createSuccessResponse(
          request.id,
          await getShortcutKeysResult(
            request.command.payload as BridgeCommandPayloadMap['system.shortcut_get_shortcuts'],
          ),
        );
      case 'system.shortcut_register':
        return createSuccessResponse(
          request.id,
          await registerShortcutKeyResult(
            request.command.payload as never,
          ),
        );
      case 'system.shortcut_unregister':
        return createSuccessResponse(
          request.id,
          await unregisterShortcutKeyResult(
            request.command.payload as never,
          ),
        );
      case 'system.shortcut_list_registered':
        return createSuccessResponse(
          request.id,
          await listShortcutKeysResult(
            request.command.payload as BridgeCommandPayloadMap['system.shortcut_list_registered'],
          ),
        );
      case 'system.timer_set_interval':
        return createSuccessResponse(
          request.id,
          await setIntervalTimerResult(request.command.payload as BridgeCommandPayloadMap['system.timer_set_interval']),
        );
      case 'system.timer_clear_interval':
        return createSuccessResponse(
          request.id,
          await clearIntervalTimerResult(request.command.payload as BridgeCommandPayloadMap['system.timer_clear_interval']),
        );
      case 'system.timer_set_timeout':
        return createSuccessResponse(
          request.id,
          await setTimeoutTimerResult(request.command.payload as BridgeCommandPayloadMap['system.timer_set_timeout']),
        );
      case 'system.timer_clear_timeout':
        return createSuccessResponse(
          request.id,
          await clearTimeoutTimerResult(request.command.payload as BridgeCommandPayloadMap['system.timer_clear_timeout']),
        );
      case 'system.right_click_change_menu':
        return createSuccessResponse(
          request.id,
          await changeRightClickMenuResult(
            request.command.payload as BridgeCommandPayloadMap['system.right_click_change_menu'],
          ),
        );
      case 'system.callback_events_list':
        return createSuccessResponse(request.id, await listCallbackEventsResult());
      case 'system.callback_events_drain':
        return createSuccessResponse(request.id, await drainCallbackEventsResult());
      case 'system.file_system_get_extension_file':
        return createSuccessResponse(
          request.id,
          await getExtensionFileResult(
            (request.command.payload as BridgeCommandPayloadMap['system.file_system_get_extension_file']).uri,
          ),
        );
      case 'system.file_system_save_file':
        return createSuccessResponse(
          request.id,
          await saveFileResult(request.command.payload as BridgeCommandPayloadMap['system.file_system_save_file']),
        );
      case 'system.file_system_save_file_to_file_system':
        return createSuccessResponse(
          request.id,
          await saveFileToFileSystemResult(
            request.command.payload as BridgeCommandPayloadMap['system.file_system_save_file_to_file_system'],
          ),
        );
      case 'system.file_system_list_files':
        return createSuccessResponse(
          request.id,
          await listFilesOfFileSystemResult(
            request.command.payload as BridgeCommandPayloadMap['system.file_system_list_files'],
          ),
        );
      case 'system.file_system_delete_file':
        return createSuccessResponse(
          request.id,
          await deleteFileInFileSystemResult(
            request.command.payload as BridgeCommandPayloadMap['system.file_system_delete_file'],
          ),
        );
      case 'system.file_system_get_eda_path':
        return createSuccessResponse(request.id, await getEdaPathResult());
      case 'system.file_system_get_documents_path':
        return createSuccessResponse(request.id, await getDocumentsPathResult());
      case 'system.file_system_get_libraries_paths':
        return createSuccessResponse(request.id, await getLibrariesPathsResult());
      case 'system.file_system_get_projects_paths':
        return createSuccessResponse(request.id, await getProjectsPathsResult());
      case 'system.file_manager_get_project_file':
        return createSuccessResponse(
          request.id,
          await getProjectFileResult(request.command.payload as BridgeCommandPayloadMap['system.file_manager_get_project_file']),
        );
      case 'system.file_manager_get_document_file':
        return createSuccessResponse(
          request.id,
          await getDocumentFileResult(
            request.command.payload as BridgeCommandPayloadMap['system.file_manager_get_document_file'],
          ),
        );
      case 'system.file_manager_get_document_source':
        return createSuccessResponse(request.id, await getDocumentSourceResult());
      case 'system.file_manager_get_document_footprint_sources':
        return createSuccessResponse(request.id, await getDocumentFootprintSourcesResult());
      case 'system.file_manager_set_document_source':
        return createSuccessResponse(
          request.id,
          await setDocumentSourceResult(
            request.command.payload as BridgeCommandPayloadMap['system.file_manager_set_document_source'],
          ),
        );
      case 'system.file_manager_get_project_file_by_project_uuid':
        return createSuccessResponse(
          request.id,
          await getProjectFileByProjectUuidResult(
            request.command.payload as BridgeCommandPayloadMap['system.file_manager_get_project_file_by_project_uuid'],
          ),
        );
      case 'system.file_manager_get_device_file_by_device_uuid':
        return createSuccessResponse(
          request.id,
          await getDeviceFileByDeviceUuidResult(
            request.command.payload as BridgeCommandPayloadMap['system.file_manager_get_device_file_by_device_uuid'],
          ),
        );
      case 'system.file_manager_get_symbol_file_by_symbol_uuid':
        return createSuccessResponse(
          request.id,
          await getSymbolFileBySymbolUuidResult(
            request.command.payload as BridgeCommandPayloadMap['system.file_manager_get_symbol_file_by_symbol_uuid'],
          ),
        );
      case 'system.storage_get_all_user_configs':
        return createSuccessResponse(request.id, await getExtensionAllUserConfigsResult());
      case 'system.storage_set_all_user_configs':
        return createSuccessResponse(
          request.id,
          await setExtensionAllUserConfigsResult(
            request.command.payload as BridgeCommandPayloadMap['system.storage_set_all_user_configs'],
          ),
        );
      case 'system.storage_clear_all_user_configs':
        return createSuccessResponse(request.id, await clearExtensionAllUserConfigsResult());
      case 'system.storage_get_user_config':
        return createSuccessResponse(
          request.id,
          await getExtensionUserConfigResult(
            request.command.payload as BridgeCommandPayloadMap['system.storage_get_user_config'],
          ),
        );
      case 'system.storage_set_user_config':
        return createSuccessResponse(
          request.id,
          await setExtensionUserConfigResult(
            request.command.payload as BridgeCommandPayloadMap['system.storage_set_user_config'],
          ),
        );
      case 'system.storage_delete_user_config':
        return createSuccessResponse(
          request.id,
          await deleteExtensionUserConfigResult(
            request.command.payload as BridgeCommandPayloadMap['system.storage_delete_user_config'],
          ),
        );
      case 'system.tool_netlist_comparison':
        return createSuccessResponse(
          request.id,
          await netlistComparisonResult(
            request.command.payload as BridgeCommandPayloadMap['system.tool_netlist_comparison'],
          ),
        );
      case 'system.tool_schematic_comparison':
        return createSuccessResponse(
          request.id,
          await schematicComparisonResult(
            request.command.payload as BridgeCommandPayloadMap['system.tool_schematic_comparison'],
          ),
        );
      case 'system.tool_pcb_comparison':
        return createSuccessResponse(
          request.id,
          await pcbComparisonResult(request.command.payload as BridgeCommandPayloadMap['system.tool_pcb_comparison']),
        );
      case 'system.header_menu_replace':
        return createSuccessResponse(
          request.id,
          await replaceHeaderMenusResult(request.command.payload as BridgeCommandPayloadMap['system.header_menu_replace']),
        );
      case 'system.header_menu_insert':
        return createSuccessResponse(
          request.id,
          await insertHeaderMenusResult(request.command.payload as BridgeCommandPayloadMap['system.header_menu_insert']),
        );
      case 'system.header_menu_remove':
        return createSuccessResponse(request.id, await removeHeaderMenusResult());
      case 'system.header_menu_insert_system_item':
        return createSuccessResponse(
          request.id,
          await insertSystemHeaderMenuItemResult(
            request.command.payload as BridgeCommandPayloadMap['system.header_menu_insert_system_item'],
          ),
        );
      case 'system.header_menu_remove_system_item':
        return createSuccessResponse(
          request.id,
          await removeSystemHeaderMenuItemResult(
            request.command.payload as BridgeCommandPayloadMap['system.header_menu_remove_system_item'],
          ),
        );
      case 'system.format_conversion_ad_single':
        return createSuccessResponse(
          request.id,
          await convertAltiumDesignerLibrariesToEasyEDASingleFileResult(
            request.command.payload as BridgeCommandPayloadMap['system.format_conversion_ad_single'],
          ),
        );
      case 'system.format_conversion_ad_multi':
        return createSuccessResponse(
          request.id,
          await convertAltiumDesignerLibrariesToEasyEDAMultiFilesResult(
            request.command.payload as BridgeCommandPayloadMap['system.format_conversion_ad_multi'],
          ),
        );
      case 'system.format_conversion_disa_single':
        return createSuccessResponse(
          request.id,
          await convertDisaLibrariesToEasyEDASingleFileResult(
            request.command.payload as BridgeCommandPayloadMap['system.format_conversion_disa_single'],
          ),
        );
      case 'system.format_conversion_disa_multi':
        return createSuccessResponse(
          request.id,
          await convertDisaLibrariesToEasyEDAMultiFilesResult(
            request.command.payload as BridgeCommandPayloadMap['system.format_conversion_disa_multi'],
          ),
        );
      case 'project.get_inventory':
        return createSuccessResponse(request.id, await getProjectInventoryResult());
      case 'project.get_document_summary':
        return createSuccessResponse(request.id, await getDocumentSummaryResult());
      case 'project.get_selection_snapshot':
        return createSuccessResponse(request.id, await getSelectionSnapshotResult());
      case 'project.list_workspaces':
        return createSuccessResponse(request.id, await listWorkspacesResult());
      case 'project.list_teams':
        return createSuccessResponse(request.id, await listTeamsResult(false));
      case 'project.list_involved_teams':
        return createSuccessResponse(request.id, await listTeamsResult(true));
      case 'project.list_projects':
        return createSuccessResponse(
          request.id,
          await listProjectsResult(request.command.payload as BridgeCommandPayloadMap['project.list_projects']),
        );
      case 'project.get_project_info':
        return createSuccessResponse(
          request.id,
          await getProjectInfoResult(
            (request.command.payload as BridgeCommandPayloadMap['project.get_project_info']).projectUuid,
          ),
        );
      case 'project.open_project':
        return createSuccessResponse(
          request.id,
          await openProjectResult(
            (request.command.payload as BridgeCommandPayloadMap['project.open_project']).projectUuid,
          ),
        );
      case 'project.create_project':
        return createSuccessResponse(
          request.id,
          await createProjectResult(request.command.payload as BridgeCommandPayloadMap['project.create_project']),
        );
      case 'project.list_schematics':
        return createSuccessResponse(request.id, await listSchematicsResult());
      case 'project.list_schematic_pages':
        return createSuccessResponse(
          request.id,
          await listSchematicPagesResult(
            (request.command.payload as BridgeCommandPayloadMap['project.list_schematic_pages']).schematicUuid,
          ),
        );
      case 'project.list_boards':
        return createSuccessResponse(request.id, await listBoardsResult());
      case 'project.list_pcbs':
        return createSuccessResponse(request.id, await listPcbsResult());
      case 'project.get_board_summary':
        return createSuccessResponse(request.id, await getBoardSummaryResult());
      case 'project.create_board':
        return createSuccessResponse(
          request.id,
          await createBoardResult(request.command.payload as BridgeCommandPayloadMap['project.create_board']),
        );
      case 'project.open_document':
        return createSuccessResponse(
          request.id,
          await openDocumentResult(request.command.payload as BridgeCommandPayloadMap['project.open_document']),
        );
      case 'project.open_library_document':
        return createSuccessResponse(
          request.id,
          await openLibraryDocumentResult(
            request.command.payload as BridgeCommandPayloadMap['project.open_library_document'],
          ),
        );
      case 'project.close_document':
        return createSuccessResponse(
          request.id,
          await closeDocumentResult((request.command.payload as BridgeCommandPayloadMap['project.close_document']).tabId),
        );
      case 'project.get_split_screen_tree':
        return createSuccessResponse(request.id, await getEditorSplitScreenTreeResult());
      case 'project.get_split_screen_id_by_tab_id':
        return createSuccessResponse(
          request.id,
          await getEditorSplitScreenIdByTabIdResult(
            (request.command.payload as BridgeCommandPayloadMap['project.get_split_screen_id_by_tab_id']).tabId,
          ),
        );
      case 'project.get_tabs_by_split_screen_id':
        return createSuccessResponse(
          request.id,
          await getEditorTabsBySplitScreenIdResult(
            (request.command.payload as BridgeCommandPayloadMap['project.get_tabs_by_split_screen_id']).splitScreenId,
          ),
        );
      case 'project.create_split_screen':
        return createSuccessResponse(
          request.id,
          await createSplitScreenResult(
            request.command.payload as BridgeCommandPayloadMap['project.create_split_screen'],
          ),
        );
      case 'project.move_document_to_split_screen':
        return createSuccessResponse(
          request.id,
          await moveDocumentToSplitScreenResult(
            request.command.payload as BridgeCommandPayloadMap['project.move_document_to_split_screen'],
          ),
        );
      case 'project.activate_document':
        return createSuccessResponse(
          request.id,
          await activateDocumentResult(
            (request.command.payload as BridgeCommandPayloadMap['project.activate_document']).tabId,
          ),
        );
      case 'project.activate_split_screen':
        return createSuccessResponse(
          request.id,
          await activateSplitScreenResult(
            (request.command.payload as BridgeCommandPayloadMap['project.activate_split_screen']).splitScreenId,
          ),
        );
      case 'project.tile_all_documents_to_split_screen':
        return createSuccessResponse(request.id, await tileAllDocumentsToSplitScreenResult());
      case 'project.merge_all_documents_from_split_screen':
        return createSuccessResponse(request.id, await mergeAllDocumentsFromSplitScreenResult());
      case 'project.get_current_rendered_area_image':
        return createSuccessResponse(
          request.id,
          await getCurrentRenderedAreaImageResult(
            (request.command.payload as BridgeCommandPayloadMap['project.get_current_rendered_area_image']).tabId,
          ),
        );
      case 'project.zoom_to_region':
        return createSuccessResponse(
          request.id,
          await zoomToRegionResult(request.command.payload as BridgeCommandPayloadMap['project.zoom_to_region']),
        );
      case 'project.zoom_to':
        return createSuccessResponse(request.id, await zoomToResult(request.command.payload as BridgeCommandPayloadMap['project.zoom_to']));
      case 'project.zoom_to_all_primitives':
        return createSuccessResponse(
          request.id,
          await zoomToAllPrimitivesResult(
            (request.command.payload as BridgeCommandPayloadMap['project.zoom_to_all_primitives']).tabId,
          ),
        );
      case 'project.zoom_to_selected_primitives':
        return createSuccessResponse(
          request.id,
          await zoomToSelectedPrimitivesResult(
            (request.command.payload as BridgeCommandPayloadMap['project.zoom_to_selected_primitives']).tabId,
          ),
        );
      case 'project.export_bom':
        return createSuccessResponse(
          request.id,
          await exportProjectBom(request.command.payload as BridgeCommandPayloadMap['project.export_bom']),
        );
      case 'schematic.get_current_schematic_info':
        return createSuccessResponse(request.id, await getCurrentSchematicInfoResult());
      case 'schematic.create_schematic':
        return createSuccessResponse(
          request.id,
          await createSchematicResult(
            (request.command.payload as BridgeCommandPayloadMap['schematic.create_schematic']).boardName,
          ),
        );
      case 'schematic.create_schematic_page':
        return createSuccessResponse(
          request.id,
          await createSchematicPageResult(
            (request.command.payload as BridgeCommandPayloadMap['schematic.create_schematic_page']).schematicUuid,
          ),
        );
      case 'schematic.place_component':
        return createSuccessResponse(
          request.id,
          await placeSchematicComponent(
            request.command.payload as BridgeCommandPayloadMap['schematic.place_component'],
          ),
        );
      case 'schematic.create_wire':
        return createSuccessResponse(
          request.id,
          await createSchematicWire(request.command.payload as BridgeCommandPayloadMap['schematic.create_wire']),
        );
      case 'schematic.annotate_net':
        return createSuccessResponse(
          request.id,
          await annotateSchematicNet(request.command.payload as BridgeCommandPayloadMap['schematic.annotate_net']),
        );
      case 'schematic.create_net_flag':
        return createSuccessResponse(
          request.id,
          await createSchematicNetFlag(request.command.payload as BridgeCommandPayloadMap['schematic.create_net_flag']),
        );
      case 'schematic.create_net_port':
        return createSuccessResponse(
          request.id,
          await createSchematicNetPort(request.command.payload as BridgeCommandPayloadMap['schematic.create_net_port']),
        );
      case 'schematic.create_short_circuit_flag':
        return createSuccessResponse(
          request.id,
          await createSchematicShortCircuitFlag(
            request.command.payload as BridgeCommandPayloadMap['schematic.create_short_circuit_flag'],
          ),
        );
      case 'schematic.import_changes':
        return createSuccessResponse(request.id, await importSchematicChangesResult());
      case 'schematic.save':
        return createSuccessResponse(request.id, await saveSchematicResult());
      case 'schematic.navigate_to_coordinates':
        return createSuccessResponse(
          request.id,
          await navigateSchematicToCoordinatesResult(
            request.command.payload as BridgeCommandPayloadMap['schematic.navigate_to_coordinates'],
          ),
        );
      case 'schematic.navigate_to_region':
        return createSuccessResponse(
          request.id,
          await navigateSchematicToRegionResult(
            request.command.payload as BridgeCommandPayloadMap['schematic.navigate_to_region'],
          ),
        );
      case 'schematic.get_primitive_at_point':
        return createSuccessResponse(
          request.id,
          await getSchematicPrimitiveAtPointResult(
            request.command.payload as BridgeCommandPayloadMap['schematic.get_primitive_at_point'],
          ),
        );
      case 'schematic.get_primitives_in_region':
        return createSuccessResponse(
          request.id,
          await getSchematicPrimitivesInRegionResult(
            request.command.payload as BridgeCommandPayloadMap['schematic.get_primitives_in_region'],
          ),
        );
      case 'schematic.get_current_filter_configuration':
        return createSuccessResponse(request.id, await getSchematicFilterConfigurationResult());
      case 'schematic.auto_routing':
        return createSuccessResponse(
          request.id,
          await autoRouteSchematicResult(request.command.payload as BridgeCommandPayloadMap['schematic.auto_routing']),
        );
      case 'schematic.auto_layout':
        return createSuccessResponse(
          request.id,
          await autoLayoutSchematicResult(request.command.payload as BridgeCommandPayloadMap['schematic.auto_layout']),
        );
      case 'schematic.check_drc':
        return createSuccessResponse(
          request.id,
          await checkSchematicDrcResult(request.command.payload as BridgeCommandPayloadMap['schematic.check_drc']),
        );
      case 'pcb.get_board_summary':
        return createSuccessResponse(request.id, await getBoardSummaryResult());
      case 'pcb.get_current_pcb_info':
        return createSuccessResponse(request.id, await getCurrentPcbInfoResult());
      case 'pcb.list_pcbs':
        return createSuccessResponse(request.id, await listPcbsResult());
      case 'pcb.create_pcb':
        return createSuccessResponse(
          request.id,
          await createPcbResult(
            (request.command.payload as BridgeCommandPayloadMap['pcb.create_pcb']).boardName,
          ),
        );
      case 'pcb.place_footprint':
        return createSuccessResponse(
          request.id,
          await placePcbFootprint(request.command.payload as BridgeCommandPayloadMap['pcb.place_footprint']),
        );
      case 'pcb.import_changes':
        return createSuccessResponse(
          request.id,
          await importPcbChangesResult(request.command.payload as BridgeCommandPayloadMap['pcb.import_changes']),
        );
      case 'pcb.save':
        return createSuccessResponse(
          request.id,
          await savePcbResult(request.command.payload as BridgeCommandPayloadMap['pcb.save']),
        );
      case 'pcb.get_calculating_ratline_status':
        return createSuccessResponse(request.id, await getPcbCalculatingRatlineStatusResult());
      case 'pcb.start_calculating_ratline':
        return createSuccessResponse(request.id, await startPcbCalculatingRatlineResult());
      case 'pcb.stop_calculating_ratline':
        return createSuccessResponse(request.id, await stopPcbCalculatingRatlineResult());
      case 'pcb.convert_canvas_origin_to_data_origin':
        return createSuccessResponse(
          request.id,
          await convertCanvasOriginToDataOriginResult(
            request.command.payload as BridgeCommandPayloadMap['pcb.convert_canvas_origin_to_data_origin'],
          ),
        );
      case 'pcb.convert_data_origin_to_canvas_origin':
        return createSuccessResponse(
          request.id,
          await convertDataOriginToCanvasOriginResult(
            request.command.payload as BridgeCommandPayloadMap['pcb.convert_data_origin_to_canvas_origin'],
          ),
        );
      case 'pcb.get_canvas_origin':
        return createSuccessResponse(request.id, await getPcbCanvasOriginResult());
      case 'pcb.set_canvas_origin':
        return createSuccessResponse(
          request.id,
          await setPcbCanvasOriginResult(
            request.command.payload as BridgeCommandPayloadMap['pcb.set_canvas_origin'],
          ),
        );
      case 'pcb.navigate_to_coordinates':
        return createSuccessResponse(
          request.id,
          await navigatePcbToCoordinatesResult(
            request.command.payload as BridgeCommandPayloadMap['pcb.navigate_to_coordinates'],
          ),
        );
      case 'pcb.navigate_to_region':
        return createSuccessResponse(
          request.id,
          await navigatePcbToRegionResult(
            request.command.payload as BridgeCommandPayloadMap['pcb.navigate_to_region'],
          ),
        );
      case 'pcb.get_primitive_at_point':
        return createSuccessResponse(
          request.id,
          await getPcbPrimitiveAtPointResult(
            request.command.payload as BridgeCommandPayloadMap['pcb.get_primitive_at_point'],
          ),
        );
      case 'pcb.get_primitives_in_region':
        return createSuccessResponse(
          request.id,
          await getPcbPrimitivesInRegionResult(
            request.command.payload as BridgeCommandPayloadMap['pcb.get_primitives_in_region'],
          ),
        );
      case 'pcb.zoom_to_board_outline':
        return createSuccessResponse(request.id, await zoomPcbToBoardOutlineResult());
      case 'pcb.get_current_filter_configuration':
        return createSuccessResponse(request.id, await getPcbFilterConfigurationResult());
      case 'pcb.clear_routing':
        return createSuccessResponse(
          request.id,
          await clearPcbRoutingResult(request.command.payload as BridgeCommandPayloadMap['pcb.clear_routing']),
        );
      case 'project.save_panel':
        return createSuccessResponse(request.id, await savePanelResult());
      default:
        return createErrorResponse(request.id, {
          code: 'UNSUPPORTED_ACTION',
          message: `No execution branch is available for ${resolvedCommandKey}`,
          retryable: false,
          details: {
            command: resolvedCommandKey,
          },
        });
    }
  }
  catch (error) {
    return createErrorResponse(request.id, {
      code: 'EXECUTION_FAILED',
      message: error instanceof Error ? error.message : 'Unknown bridge execution failure',
      retryable: true,
      details: {
        command: resolvedCommandKey,
      },
    });
  }
}

export async function executeBridgeCommand<K extends BridgeCommandName>(
  command: K,
  payload?: BridgeCommandPayloadMap[K],
): Promise<BridgeResponse> {
  const [domain, action] = command.split('.', 2) as [
    BridgeRequest<K>['command']['domain'],
    BridgeRequest<K>['command']['action'],
  ];

  return executeBridgeRequest({
    id: `local_${command}`,
    type: 'command.request',
    protocolVersion: BRIDGE_PROTOCOL_VERSION,
    sessionId: 'local-extension-session',
    command: {
      domain,
      action,
      payload: (payload ?? {}) as BridgeCommandPayloadMap[K],
    },
  });
}
