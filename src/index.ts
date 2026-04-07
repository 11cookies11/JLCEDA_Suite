import * as extensionConfig from '../extension.json';
import { executeBridgeCommand } from './bridge/handlers';
import { BRIDGE_PROTOCOL_VERSION } from './bridge/protocol';
import { getSupportedCommandNames, IMPLEMENTED_COMMANDS } from './bridge/registry';
import { remoteBridgeClient } from './remote/client';

function getStatusLines(): Array<string> {
  const remoteStatus = remoteBridgeClient.getStatus();

  return [
    `Extension: ${extensionConfig.displayName}`,
    `Version: ${extensionConfig.version}`,
    `Protocol: ${BRIDGE_PROTOCOL_VERSION}`,
    `Supported commands: ${getSupportedCommandNames().length}`,
    `Implemented commands: ${IMPLEMENTED_COMMANDS.length}`,
    `Remote bridge configured: ${remoteStatus.configured ? 'yes' : 'no'}`,
    `Remote bridge connected: ${remoteStatus.connected ? 'yes' : 'no'}`,
    'Bridge: first workflow ready',
    'Next step: finish plugin-side remote transport validation',
  ];
}

export function activate(status?: 'onStartupFinished', arg?: string): void {
  void status;
  void arg;
  void remoteBridgeClient.autoConnectIfEnabled();
}

export function about(): void {
  const message = [
    'JLCEDA AIAgent',
    'A controlled bridge between Codex and JLCEDA.',
    `Version: ${extensionConfig.version}`,
  ].join('\n');

  eda.sys_Dialog.showInformationMessage(message, 'About');
}

export async function showBridgeStatus(): Promise<void> {
  const response = await executeBridgeCommand('system.get_bridge_status');
  const payload = response.status === 'success'
    ? JSON.stringify(response.result.data, null, 2)
    : JSON.stringify(response.error, null, 2);

  eda.sys_Dialog.showInformationMessage(`${getStatusLines().join('\n')}\n\n${payload}`, 'Bridge Status');
}

export async function inspectCurrentDocument(): Promise<void> {
  const response = await executeBridgeCommand('project.get_document_summary');
  const payload = response.status === 'success'
    ? JSON.stringify(response.result.data, null, 2)
    : JSON.stringify(response.error, null, 2);

  eda.sys_Dialog.showInformationMessage(payload, 'Current Document Summary');
}

export async function runBridgeSelfCheck(): Promise<void> {
  const checks = await Promise.all([
    executeBridgeCommand('system.ping', { echo: 'self-check' }),
    executeBridgeCommand('system.get_bridge_status'),
    executeBridgeCommand('project.get_document_summary'),
    executeBridgeCommand('project.get_selection_snapshot'),
  ]);

  const summaryLines = checks.map((response, index) => {
    const label = ['ping', 'bridge_status', 'document_summary', 'selection_snapshot'][index];
    return `${label}: ${response.status}`;
  });

  eda.sys_Dialog.showInformationMessage(summaryLines.join('\n'), 'Bridge Self Check');
}

function showInputDialog(
  beforeContent: string,
  title: string,
  type: 'password' | 'text' | 'url',
  value = '',
): Promise<string | undefined> {
  return new Promise((resolve) => {
    eda.sys_Dialog.showInputDialog(
      beforeContent,
      '',
      title,
      type,
      value,
      {
        placeholder: value || undefined,
      },
      (inputValue) => {
        resolve(typeof inputValue === 'string' ? inputValue : undefined);
      },
    );
  });
}

export async function configureRemoteBridge(): Promise<void> {
  const currentSettings = remoteBridgeClient.getSettings();
  const serverUrl = await showInputDialog(
    'Input the remote bridge WebSocket URL',
    'Remote Bridge URL',
    'url',
    currentSettings.serverUrl,
  );

  if (serverUrl === undefined) {
    return;
  }

  const authToken = await showInputDialog(
    'Input the remote bridge auth token',
    'Remote Bridge Token',
    'password',
    currentSettings.authToken,
  );

  if (authToken === undefined) {
    return;
  }

  const clientId = await showInputDialog(
    'Input the remote bridge client ID',
    'Remote Bridge Client ID',
    'text',
    currentSettings.clientId,
  );

  if (clientId === undefined) {
    return;
  }

  await remoteBridgeClient.saveSettings({
    serverUrl,
    authToken,
    clientId,
    autoConnect: true,
  });

  eda.sys_Dialog.showInformationMessage('Remote bridge settings saved.', 'Remote Bridge');
}

export async function connectRemoteBridge(): Promise<void> {
  try {
    await remoteBridgeClient.connect();
    eda.sys_Dialog.showInformationMessage('Remote bridge connection started.', 'Remote Bridge');
  }
  catch (error) {
    eda.sys_Dialog.showInformationMessage(
      error instanceof Error ? error.message : 'Failed to start remote bridge connection.',
      'Remote Bridge',
    );
  }
}

export function disconnectRemoteBridge(): void {
  remoteBridgeClient.disconnect();
  eda.sys_Dialog.showInformationMessage('Remote bridge disconnected.', 'Remote Bridge');
}

export function showRemoteBridgeStatus(): void {
  const remoteStatus = remoteBridgeClient.getStatus();
  eda.sys_Dialog.showInformationMessage(JSON.stringify(remoteStatus, null, 2), 'Remote Bridge Status');
}
