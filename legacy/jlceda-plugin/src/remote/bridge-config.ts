const DEFAULT_CONTROL_PORT_OFFSET = 1;

export const CONFIG_KEY_SERVER_URL = 'remoteBridge.serverUrl';
export const CONFIG_KEY_CONTROL_URL = 'remoteBridge.controlUrl';
export const CONFIG_KEY_AUTH_TOKEN = 'remoteBridge.authToken';
export const CONFIG_KEY_CONTROL_TOKEN = 'remoteBridge.controlToken';
export const CONFIG_KEY_CLIENT_ID = 'remoteBridge.clientId';
export const CONFIG_KEY_AUTO_CONNECT = 'remoteBridge.autoConnect';

export function readStringConfig(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function deriveControlUrl(serverUrl: string): string {
  const normalizedServerUrl = serverUrl.trim();
  if (!normalizedServerUrl) {
    return '';
  }

  try {
    const url = new URL(normalizedServerUrl);
    if (url.protocol === 'ws:') {
      url.protocol = 'http:';
    }
    else if (url.protocol === 'wss:') {
      url.protocol = 'https:';
    }

    if (url.port) {
      const port = Number(url.port);
      if (Number.isFinite(port) && port > 0) {
        url.port = String(port + DEFAULT_CONTROL_PORT_OFFSET);
      }
    }

    return url.toString().replace(/\/$/, '');
  }
  catch {
    return normalizedServerUrl.replace(/^ws:\/\//, 'http://').replace(/^wss:\/\//, 'https://');
  }
}
