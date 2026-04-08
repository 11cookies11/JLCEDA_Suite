import type { BridgeRequest, BridgeResponse } from '../bridge/protocol';
import type { AgentRegisterMessage, ServerToClientMessage } from '../server/protocol';
import * as extensionConfig from '../../extension.json';
import { executeBridgeRequest } from '../bridge/handlers';
import { BRIDGE_PROTOCOL_VERSION } from '../bridge/protocol';
import { getSupportedCommandNames } from '../bridge/registry';

const REMOTE_BRIDGE_SOCKET_ID = 'jlceda-aiagent-remote-bridge';
const CONFIG_KEY_SERVER_URL = 'remoteBridge.serverUrl';
const CONFIG_KEY_AUTH_TOKEN = 'remoteBridge.authToken';
const CONFIG_KEY_CLIENT_ID = 'remoteBridge.clientId';
const CONFIG_KEY_AUTO_CONNECT = 'remoteBridge.autoConnect';
const DEFAULT_CONNECT_TIMEOUT_MS = 15_000;
const DEFAULT_HEARTBEAT_INTERVAL_MS = 20_000;
const DEFAULT_RECONNECT_DELAY_MS = 5_000;

export interface RemoteBridgeSettings {
  serverUrl: string;
  authToken: string;
  clientId: string;
  autoConnect: boolean;
}

export interface RemoteBridgeStatus {
  configured: boolean;
  connected: boolean;
  connecting: boolean;
  clientId?: string;
  serverUrl?: string;
  lastRegisteredAt?: string;
  lastHeartbeatAt?: string;
  reconnectAttempts: number;
  reconnectScheduled: boolean;
  lastError?: string;
}

interface RemoteBridgeClientDependencies {
  registerSocket: (
    id: string,
    serviceUri: string,
    receiveMessageCallFn?: (event: MessageEvent<string>) => void | Promise<void>,
    connectedCallFn?: () => void | Promise<void>,
  ) => void;
  sendSocketData: (id: string, data: string) => void;
  closeSocket: (id: string, code?: number, reason?: string) => void;
  getConfig: (key: string) => unknown;
  setConfig: (key: string, value: unknown) => Promise<boolean>;
  executeRequest: (request: BridgeRequest) => Promise<BridgeResponse>;
}

function createDefaultClientId(): string {
  const suffix = Math.random().toString(36).slice(2, 10);
  return `jlceda-client-${suffix}`;
}

function readStringConfig(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function readBooleanConfig(value: unknown): boolean {
  return value === true;
}

function createDefaultDependencies(): RemoteBridgeClientDependencies {
  return {
    registerSocket: (id, serviceUri, receiveMessageCallFn, connectedCallFn) => {
      eda.sys_WebSocket.register(id, serviceUri, receiveMessageCallFn, connectedCallFn);
    },
    sendSocketData: (id, data) => {
      eda.sys_WebSocket.send(id, data);
    },
    closeSocket: (id, code, reason) => {
      eda.sys_WebSocket.close(id, code, reason);
    },
    getConfig: key => eda.sys_Storage.getExtensionUserConfig(key),
    setConfig: (key, value) => eda.sys_Storage.setExtensionUserConfig(key, value),
    executeRequest: request => executeBridgeRequest(request),
  };
}

export class RemoteBridgeClient {
  private readonly dependencies: RemoteBridgeClientDependencies;
  private connectTimer: ReturnType<typeof setTimeout> | undefined;
  private heartbeatTimer: ReturnType<typeof setInterval> | undefined;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private status: RemoteBridgeStatus = {
    configured: false,
    connected: false,
    connecting: false,
    reconnectAttempts: 0,
    reconnectScheduled: false,
  };

  constructor(dependencies?: Partial<RemoteBridgeClientDependencies>) {
    this.dependencies = {
      ...createDefaultDependencies(),
      ...dependencies,
    };
  }

  getStatus(): RemoteBridgeStatus {
    return { ...this.status };
  }

  getSettings(): RemoteBridgeSettings {
    const serverUrl = readStringConfig(this.dependencies.getConfig(CONFIG_KEY_SERVER_URL));
    const authToken = readStringConfig(this.dependencies.getConfig(CONFIG_KEY_AUTH_TOKEN));
    const storedClientId = readStringConfig(this.dependencies.getConfig(CONFIG_KEY_CLIENT_ID));
    const autoConnect = readBooleanConfig(this.dependencies.getConfig(CONFIG_KEY_AUTO_CONNECT));
    const clientId = storedClientId || createDefaultClientId();

    this.status = {
      ...this.status,
      configured: Boolean(serverUrl),
      clientId,
      serverUrl: serverUrl || undefined,
    };

    return {
      serverUrl,
      authToken,
      clientId,
      autoConnect,
    };
  }

  async saveSettings(settings: Partial<RemoteBridgeSettings>): Promise<void> {
    const current = this.getSettings();
    const nextSettings: RemoteBridgeSettings = {
      ...current,
      ...settings,
    };

    await this.dependencies.setConfig(CONFIG_KEY_SERVER_URL, nextSettings.serverUrl);
    await this.dependencies.setConfig(CONFIG_KEY_AUTH_TOKEN, nextSettings.authToken);
    await this.dependencies.setConfig(CONFIG_KEY_CLIENT_ID, nextSettings.clientId);
    await this.dependencies.setConfig(CONFIG_KEY_AUTO_CONNECT, nextSettings.autoConnect);

    this.status = {
      ...this.status,
      configured: Boolean(nextSettings.serverUrl),
      clientId: nextSettings.clientId,
      serverUrl: nextSettings.serverUrl || undefined,
    };
  }

  async ensureClientId(): Promise<string> {
    const settings = this.getSettings();

    if (settings.clientId) {
      await this.dependencies.setConfig(CONFIG_KEY_CLIENT_ID, settings.clientId);
      return settings.clientId;
    }

    const clientId = createDefaultClientId();
    await this.dependencies.setConfig(CONFIG_KEY_CLIENT_ID, clientId);
    this.status = {
      ...this.status,
      clientId,
    };
    return clientId;
  }

  async connect(): Promise<void> {
    const settings = this.getSettings();
    this.clearReconnectSchedule();
    this.clearConnectTimeout();

    if (!settings.serverUrl) {
      this.status = {
        ...this.status,
        configured: false,
        connecting: false,
        connected: false,
        lastError: 'Remote bridge server URL is not configured.',
      };
      throw new Error(this.status.lastError);
    }

    this.status = {
      ...this.status,
      configured: true,
      connecting: true,
      connected: false,
      lastError: undefined,
    };

    this.connectTimer = setTimeout(() => {
      this.connectTimer = undefined;

      if (this.status.connected) {
        return;
      }

      this.stopHeartbeat();
      this.status = {
        ...this.status,
        connecting: false,
        connected: false,
        lastError: 'Timed out waiting for remote bridge registration.',
      };
      this.scheduleReconnect();
    }, DEFAULT_CONNECT_TIMEOUT_MS);

    try {
      this.dependencies.registerSocket(
        REMOTE_BRIDGE_SOCKET_ID,
        settings.serverUrl,
        event => this.handleServerMessage(event.data),
        async () => {
          try {
            await this.sendRegister();
            this.clearConnectTimeout();
            this.startHeartbeat();
            this.status = {
              ...this.status,
              connecting: false,
              connected: true,
              reconnectScheduled: false,
              lastRegisteredAt: new Date().toISOString(),
              lastError: undefined,
            };
          }
          catch (error) {
            this.clearConnectTimeout();
            this.stopHeartbeat();
            this.status = {
              ...this.status,
              connecting: false,
              connected: false,
              lastError: error instanceof Error ? error.message : 'Failed to finish remote bridge registration.',
            };
            this.scheduleReconnect();
          }
        },
      );
    }
    catch (error) {
      this.status = {
        ...this.status,
        connecting: false,
        connected: false,
        lastError: error instanceof Error ? error.message : 'Failed to register remote bridge socket.',
      };
      this.scheduleReconnect();
      throw error;
    }
  }

  disconnect(): void {
    this.clearReconnectSchedule();
    this.clearConnectTimeout();
    this.stopHeartbeat();
    this.dependencies.closeSocket(REMOTE_BRIDGE_SOCKET_ID, 1000, 'manual disconnect');
    this.status = {
      ...this.status,
      connecting: false,
      connected: false,
      reconnectScheduled: false,
    };
  }

  async autoConnectIfEnabled(): Promise<void> {
    const settings = this.getSettings();

    if (!settings.serverUrl || !settings.autoConnect) {
      return;
    }

    await this.connect();
  }

  private async sendRegister(): Promise<void> {
    const settings = this.getSettings();
    const clientId = await this.ensureClientId();
    const registerMessage: AgentRegisterMessage = {
      type: 'agent.register',
      token: settings.authToken || undefined,
      client: {
        clientId,
        pluginVersion: extensionConfig.version,
        protocolVersion: BRIDGE_PROTOCOL_VERSION,
        supportedCommands: getSupportedCommandNames(),
      },
    };

    this.dependencies.sendSocketData(REMOTE_BRIDGE_SOCKET_ID, JSON.stringify(registerMessage));
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();

    this.heartbeatTimer = setInterval(() => {
      const clientId = this.getSettings().clientId;

      this.dependencies.sendSocketData(REMOTE_BRIDGE_SOCKET_ID, JSON.stringify({
        type: 'agent.heartbeat',
        clientId,
        timestamp: new Date().toISOString(),
      }));
    }, DEFAULT_HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (!this.heartbeatTimer) {
      return;
    }

    clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = undefined;
  }

  private scheduleReconnect(): void {
    const settings = this.getSettings();

    if (!settings.autoConnect || this.reconnectTimer) {
      return;
    }

    this.status = {
      ...this.status,
      reconnectScheduled: true,
      reconnectAttempts: this.status.reconnectAttempts + 1,
    };

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = undefined;
      void this.connect().catch(() => undefined);
    }, DEFAULT_RECONNECT_DELAY_MS);
  }

  private clearReconnectSchedule(): void {
    if (!this.reconnectTimer) {
      return;
    }

    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = undefined;
    this.status = {
      ...this.status,
      reconnectScheduled: false,
    };
  }

  private clearConnectTimeout(): void {
    if (!this.connectTimer) {
      return;
    }

    clearTimeout(this.connectTimer);
    this.connectTimer = undefined;
  }

  private async handleServerMessage(rawMessage: string): Promise<void> {
    let message: ServerToClientMessage;

    try {
      message = JSON.parse(rawMessage) as ServerToClientMessage;
    }
    catch {
      this.status = {
        ...this.status,
        lastError: 'Failed to parse remote bridge server message.',
      };
      return;
    }

    switch (message.type) {
      case 'server.registered':
        this.status = {
          ...this.status,
          connected: true,
          connecting: false,
          reconnectAttempts: 0,
          reconnectScheduled: false,
          clientId: message.clientId,
          lastRegisteredAt: message.session.connectedAt,
          lastHeartbeatAt: message.session.lastSeenAt,
          lastError: undefined,
        };
        break;
      case 'server.heartbeat_ack':
        this.status = {
          ...this.status,
          lastHeartbeatAt: message.timestamp,
          lastError: undefined,
        };
        break;
      case 'bridge.request':
        await this.handleBridgeRequest(message.request);
        break;
      case 'server.error':
        this.status = {
          ...this.status,
          connected: false,
          connecting: false,
          lastError: `${message.code}: ${message.message}`,
        };
        if (message.code !== 'AUTH_FAILED') {
          this.scheduleReconnect();
        }
        break;
    }
  }

  private async handleBridgeRequest(request: BridgeRequest): Promise<void> {
    const clientId = this.getSettings().clientId;
    const response = await this.dependencies.executeRequest(request);

    this.dependencies.sendSocketData(REMOTE_BRIDGE_SOCKET_ID, JSON.stringify({
      type: 'bridge.response',
      clientId,
      response,
    }));
  }
}

export const remoteBridgeClient = new RemoteBridgeClient();
