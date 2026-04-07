import type {
  BridgeCommandName,
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
import { BRIDGE_PROTOCOL_VERSION } from './protocol';

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

function getCommandKey(request: BridgeRequest): BridgeCommandName | undefined {
  const commandKey = `${request.command.domain}.${request.command.action}`;
  return commandKey as BridgeCommandName;
}

export async function executeBridgeRequest(request: BridgeRequest): Promise<BridgeResponse> {
  const commandKey = getCommandKey(request);

  try {
    switch (commandKey) {
      case 'system.get_bridge_status':
        return createSuccessResponse(request.id, await getBridgeStatusResult());
      case 'project.get_document_summary':
        return createSuccessResponse(request.id, await getDocumentSummaryResult());
      case 'project.get_selection_snapshot':
        return createSuccessResponse(request.id, await getSelectionSnapshotResult());
      default:
        return createErrorResponse(request.id, {
          code: 'UNSUPPORTED_ACTION',
          message: `Unsupported bridge command: ${commandKey ?? 'unknown'}`,
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
