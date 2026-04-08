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
