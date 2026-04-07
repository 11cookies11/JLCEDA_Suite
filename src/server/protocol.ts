import type { BridgeCommandName, BridgeRequest, BridgeResponse } from '../bridge/protocol';

export interface BridgeAgentRegistration {
  clientId: string;
  pluginVersion: string;
  protocolVersion: string;
  supportedCommands: BridgeCommandName[];
}

export interface BridgeSessionSummary extends BridgeAgentRegistration {
  connectedAt: string;
  lastSeenAt: string;
}

export interface AgentRegisterMessage {
  type: 'agent.register';
  token?: string;
  client: BridgeAgentRegistration;
}

export interface AgentHeartbeatMessage {
  type: 'agent.heartbeat';
  clientId: string;
  timestamp: string;
}

export interface BridgeResponseMessage {
  type: 'bridge.response';
  clientId: string;
  response: BridgeResponse;
}

export interface BridgeEventMessage {
  type: 'bridge.event';
  clientId: string;
  event: {
    level: 'info' | 'warn' | 'error';
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface ServerRegisteredMessage {
  type: 'server.registered';
  clientId: string;
  session: BridgeSessionSummary;
}

export interface ServerHeartbeatAckMessage {
  type: 'server.heartbeat_ack';
  clientId: string;
  timestamp: string;
}

export interface BridgeRequestMessage {
  type: 'bridge.request';
  request: BridgeRequest;
}

export interface ServerErrorMessage {
  type: 'server.error';
  code: 'AUTH_FAILED' | 'INVALID_MESSAGE' | 'UNKNOWN_CLIENT' | 'REQUEST_TIMEOUT';
  message: string;
  details?: Record<string, unknown>;
}

export type ClientToServerMessage = AgentRegisterMessage | AgentHeartbeatMessage | BridgeResponseMessage | BridgeEventMessage;

export type ServerToClientMessage = ServerRegisteredMessage | ServerHeartbeatAckMessage | BridgeRequestMessage | ServerErrorMessage;
