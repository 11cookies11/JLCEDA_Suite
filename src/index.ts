import * as extensionConfig from '../extension.json';

function getStatusLines(): Array<string> {
  return [
    `Extension: ${extensionConfig.displayName}`,
    `Version: ${extensionConfig.version}`,
    'Bridge: scaffold ready',
    'Next step: implement Codex command protocol',
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
