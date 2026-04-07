import type {
  BridgeCommandName,
  BridgeConfirmation,
  BridgeError,
  BridgeRequest,
  BridgeResponse,
  BridgeResult,
} from './protocol';
import {
  getBridgeStatusResult,
  getDocumentSummaryResult,
  getSelectionSnapshotResult,
} from '../adapters/read-only';
import {
  createSchematicWire,
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

  const confirmationResponse = getConfirmationResponseIfNeeded(request, commandKey);

  if (confirmationResponse) {
    return confirmationResponse;
  }

  if (!isCommandImplemented(commandKey)) {
    return createErrorResponse(request.id, {
      code: 'UNSUPPORTED_ACTION',
      message: `Command is registered but not implemented yet: ${commandKey}`,
      retryable: false,
      details: {
        command: commandKey,
      },
    });
  }

  try {
    switch (commandKey) {
      case 'system.get_bridge_status':
        return createSuccessResponse(request.id, await getBridgeStatusResult());
      case 'project.get_document_summary':
        return createSuccessResponse(request.id, await getDocumentSummaryResult());
      case 'project.get_selection_snapshot':
        return createSuccessResponse(request.id, await getSelectionSnapshotResult());
      case 'schematic.place_component':
        return createSuccessResponse(
          request.id,
          await placeSchematicComponent(request.command.payload),
        );
      case 'schematic.create_wire':
        return createSuccessResponse(
          request.id,
          await createSchematicWire(request.command.payload),
        );
      default:
        return createErrorResponse(request.id, {
          code: 'UNSUPPORTED_ACTION',
          message: `No execution branch is available for ${commandKey}`,
          retryable: false,
          details: {
            command: commandKey,
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
        command: commandKey,
      },
    });
  }
}

export async function executeBridgeCommand(command: BridgeCommandName): Promise<BridgeResponse> {
  const [domain, action] = command.split('.', 2) as [BridgeRequest['command']['domain'], string];

  return executeBridgeRequest({
    id: `local_${command}`,
    type: 'command.request',
    protocolVersion: BRIDGE_PROTOCOL_VERSION,
    sessionId: 'local-extension-session',
    command: {
      domain,
      action,
      payload: {},
    },
  });
}
