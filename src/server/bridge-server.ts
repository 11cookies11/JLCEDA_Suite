import type { IncomingMessage } from 'node:http';
import type { BridgeRequest, BridgeResponse } from '../bridge/protocol';
import type {
  AgentHeartbeatMessage,
  AgentRegisterMessage,
  BridgeAgentRegistration,
  BridgeResponseMessage,
  BridgeSessionSummary,
  ClientToServerMessage,
  ServerToClientMessage,
} from './protocol';
import { randomUUID } from 'node:crypto';
import WebSocket, { WebSocketServer } from 'ws';

interface BridgeSession {
  registration: BridgeAgentRegistration;
  socket: WebSocket;
  connectedAt: Date;
  lastSeenAt: Date;
}

interface PendingBridgeRequest {
  clientId: string;
  timeout: NodeJS.Timeout;
  resolve: (response: BridgeResponse) => void;
  reject: (error: Error) => void;
}

export interface BridgeServerOptions {
  port: number;
  host?: string;
  authToken?: string;
  requestTimeoutMs?: number;
}

export class BridgeServer {
  private readonly options: Required<BridgeServerOptions>;
  private readonly sessions = new Map<string, BridgeSession>();
  private readonly socketClients = new Map<WebSocket, string>();
  private readonly pendingRequests = new Map<string, PendingBridgeRequest>();
  private readonly server: WebSocketServer;

  constructor(options: BridgeServerOptions) {
    this.options = {
      host: options.host ?? '0.0.0.0',
      authToken: options.authToken ?? '',
      requestTimeoutMs: options.requestTimeoutMs ?? 15_000,
      port: options.port,
    };

    this.server = new WebSocketServer({
      host: this.options.host,
      port: this.options.port,
    });
  }

  async start(): Promise<void> {
    this.server.on('connection', (socket, request) => {
      this.handleConnection(socket, request);
    });

    await new Promise<void>((resolve, reject) => {
      this.server.once('listening', resolve);
      this.server.once('error', reject);
    });
  }

  async stop(): Promise<void> {
    for (const pendingRequest of this.pendingRequests.values()) {
      clearTimeout(pendingRequest.timeout);
      pendingRequest.reject(new Error('Bridge server stopped before response was received.'));
    }

    this.pendingRequests.clear();

    for (const session of this.sessions.values()) {
      session.socket.close();
    }

    this.sessions.clear();
    this.socketClients.clear();

    await new Promise<void>((resolve, reject) => {
      this.server.close((error) => {
        if (error) {
          reject(error);
          return;
        }

        resolve();
      });
    });
  }

  listSessions(): BridgeSessionSummary[] {
    return [...this.sessions.values()].map(session => ({
      ...session.registration,
      connectedAt: session.connectedAt.toISOString(),
      lastSeenAt: session.lastSeenAt.toISOString(),
    }));
  }

  async sendBridgeRequest(clientId: string, request: BridgeRequest): Promise<BridgeResponse> {
    const session = this.sessions.get(clientId);

    if (!session || session.socket.readyState !== WebSocket.OPEN) {
      throw new Error(`Client is not connected: ${clientId}`);
    }

    return new Promise<BridgeResponse>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(request.id);
        reject(new Error(`Timed out waiting for bridge response: ${request.id}`));
      }, this.options.requestTimeoutMs);

      this.pendingRequests.set(request.id, {
        clientId,
        timeout,
        resolve,
        reject,
      });

      this.sendMessage(session.socket, {
        type: 'bridge.request',
        request,
      });
    });
  }

  private handleConnection(socket: WebSocket, request: IncomingMessage): void {
    void request;

    socket.on('message', (rawData) => {
      this.handleSocketMessage(socket, rawData.toString());
    });

    socket.on('close', () => {
      this.handleSocketClose(socket);
    });
  }

  private handleSocketMessage(socket: WebSocket, rawMessage: string): void {
    let message: ClientToServerMessage;

    try {
      message = JSON.parse(rawMessage) as ClientToServerMessage;
    }
    catch {
      this.sendMessage(socket, {
        type: 'server.error',
        code: 'INVALID_MESSAGE',
        message: 'Failed to parse client message as JSON.',
      });
      return;
    }

    switch (message.type) {
      case 'agent.register':
        this.handleAgentRegister(socket, message);
        break;
      case 'agent.heartbeat':
        this.handleAgentHeartbeat(socket, message);
        break;
      case 'bridge.response':
        this.handleBridgeResponse(message);
        break;
      case 'bridge.event':
        break;
      default:
        this.sendMessage(socket, {
          type: 'server.error',
          code: 'INVALID_MESSAGE',
          message: `Unsupported client message type: ${(message as { type?: string }).type ?? 'unknown'}`,
        });
    }
  }

  private handleAgentRegister(socket: WebSocket, message: AgentRegisterMessage): void {
    if (this.options.authToken && message.token !== this.options.authToken) {
      this.sendMessage(socket, {
        type: 'server.error',
        code: 'AUTH_FAILED',
        message: 'Agent registration token is invalid.',
      });
      socket.close();
      return;
    }

    const existingSession = this.sessions.get(message.client.clientId);
    if (existingSession) {
      existingSession.socket.close();
      this.socketClients.delete(existingSession.socket);
    }

    const session: BridgeSession = {
      registration: message.client,
      socket,
      connectedAt: new Date(),
      lastSeenAt: new Date(),
    };

    this.sessions.set(message.client.clientId, session);
    this.socketClients.set(socket, message.client.clientId);

    this.sendMessage(socket, {
      type: 'server.registered',
      clientId: message.client.clientId,
      session: {
        ...message.client,
        connectedAt: session.connectedAt.toISOString(),
        lastSeenAt: session.lastSeenAt.toISOString(),
      },
    });
  }

  private handleAgentHeartbeat(socket: WebSocket, message: AgentHeartbeatMessage): void {
    const clientId = this.socketClients.get(socket);

    if (!clientId || clientId !== message.clientId) {
      this.sendMessage(socket, {
        type: 'server.error',
        code: 'UNKNOWN_CLIENT',
        message: 'Heartbeat received before agent registration.',
      });
      return;
    }

    const session = this.sessions.get(clientId);
    if (!session) {
      this.sendMessage(socket, {
        type: 'server.error',
        code: 'UNKNOWN_CLIENT',
        message: `No active session found for ${clientId}.`,
      });
      return;
    }

    session.lastSeenAt = new Date(message.timestamp);

    this.sendMessage(socket, {
      type: 'server.heartbeat_ack',
      clientId,
      timestamp: new Date().toISOString(),
    });
  }

  private handleBridgeResponse(message: BridgeResponseMessage): void {
    const pendingRequest = this.pendingRequests.get(message.response.id);

    if (!pendingRequest || pendingRequest.clientId !== message.clientId) {
      return;
    }

    clearTimeout(pendingRequest.timeout);
    this.pendingRequests.delete(message.response.id);
    pendingRequest.resolve(message.response);
  }

  private handleSocketClose(socket: WebSocket): void {
    const clientId = this.socketClients.get(socket);

    if (!clientId) {
      return;
    }

    for (const [requestId, pendingRequest] of this.pendingRequests.entries()) {
      if (pendingRequest.clientId !== clientId) {
        continue;
      }

      clearTimeout(pendingRequest.timeout);
      pendingRequest.reject(new Error(`Client disconnected before responding: ${requestId}`));
      this.pendingRequests.delete(requestId);
    }

    this.sessions.delete(clientId);
    this.socketClients.delete(socket);
  }

  private sendMessage(socket: WebSocket, message: ServerToClientMessage): void {
    if (socket.readyState !== WebSocket.OPEN) {
      return;
    }

    socket.send(JSON.stringify(message));
  }
}

export function createBridgeRequestId(prefix = 'bridge_request'): string {
  return `${prefix}_${randomUUID()}`;
}
