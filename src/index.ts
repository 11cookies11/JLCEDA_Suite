import * as extensionConfig from '../extension.json';
import { executeBridgeCommand } from './bridge/handlers';
import { BRIDGE_PROTOCOL_VERSION } from './bridge/protocol';
import { getSupportedCommandNames } from './bridge/registry';

function getStatusLines(): Array<string> {
  return [
    `Extension: ${extensionConfig.displayName}`,
    `Version: ${extensionConfig.version}`,
    `Protocol: ${BRIDGE_PROTOCOL_VERSION}`,
    `Supported commands: ${getSupportedCommandNames().length}`,
    'Bridge: protocol draft ready',
    'Next step: implement read-only project inspection commands',
  ];
}

export function activate(status?: 'onStartupFinished', arg?: string): void {
  void status;
  void arg;
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
