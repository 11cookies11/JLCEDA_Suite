import * as extensionConfig from '../extension.json';
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

export function showBridgeStatus(): void {
  eda.sys_Dialog.showInformationMessage(getStatusLines().join('\n'), 'Bridge Status');
}
