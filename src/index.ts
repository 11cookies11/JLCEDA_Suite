import * as extensionConfig from '../extension.json';
import { executeBridgeCommand } from './bridge/handlers';
import { BRIDGE_PROTOCOL_VERSION } from './bridge/protocol';
import { getSupportedCommandNames, IMPLEMENTED_COMMANDS } from './bridge/registry';
import { remoteBridgeClient } from './remote/client';
import { openBridgeDialog } from './ui/bridge-dialog';

function getStatusLines(): Array<string> {
  const remoteStatus = remoteBridgeClient.getStatus();

  return [
    `插件：${extensionConfig.displayName}`,
    `版本：${extensionConfig.version}`,
    `协议：${BRIDGE_PROTOCOL_VERSION}`,
    `命令支持：${getSupportedCommandNames().length} / ${IMPLEMENTED_COMMANDS.length}`,
    `远程配置：${remoteStatus.configured ? '已完成' : '未配置'}`,
    `连接状态：${remoteStatus.connected ? '已连接' : remoteStatus.connecting ? '连接中' : '未连接'}`,
  ];
}

function formatSection(title: string, lines: string[]): string {
  return [title, ...lines].join('\n');
}

function formatValue(value: unknown, fallback = '暂无'): string {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }

  return String(value);
}

export function activate(status?: 'onStartupFinished', arg?: string): void {
  void status;
  void arg;
  void remoteBridgeClient.autoConnectIfEnabled();
}

export function about(): void {
  const message = [
    'JLCEDA AI桥接',
    '让 Codex 通过受控桥接连接嘉立创 EDA。',
    `版本：${extensionConfig.version}`,
  ].join('\n');

  eda.sys_Dialog.showInformationMessage(message, '关于插件');
}

export async function showBridgeStatus(): Promise<void> {
  const response = await executeBridgeCommand('system.get_bridge_status');
  if (response.status !== 'success') {
    eda.sys_Dialog.showInformationMessage(
      [
        ...getStatusLines(),
        '',
        `错误代码：${response.error.code}`,
        `错误信息：${response.error.message}`,
      ].join('\n'),
      '桥接状态',
    );
    return;
  }

  const resultData = (response.result.data ?? {}) as {
    runtime?: {
      isClient?: boolean;
      isWeb?: boolean;
      language?: string;
      theme?: string;
      frontendUnit?: string;
    };
  };

  const summary = [
    formatSection('概览', getStatusLines()),
    '',
    formatSection('运行环境', [
      `客户端环境：${resultData.runtime?.isClient ? '是' : '否'}`,
      `网页环境：${resultData.runtime?.isWeb ? '是' : '否'}`,
      `语言：${formatValue(resultData.runtime?.language)}`,
      `主题：${formatValue(resultData.runtime?.theme)}`,
      `单位：${formatValue(resultData.runtime?.frontendUnit)}`,
    ]),
  ].join('\n');

  eda.sys_Dialog.showInformationMessage(summary, '桥接状态');
}

export async function inspectCurrentDocument(): Promise<void> {
  const response = await executeBridgeCommand('project.get_document_summary');
  if (response.status !== 'success') {
    eda.sys_Dialog.showInformationMessage(
      `读取当前文档失败\n\n错误代码：${response.error.code}\n错误信息：${response.error.message}`,
      '当前文档',
    );
    return;
  }

  const resultData = (response.result.data ?? {}) as {
    document?: {
      kind?: string;
      uuid?: string;
      tabId?: string;
    };
    workspace?: {
      name?: string;
    };
    project?: {
      name?: string;
      uuid?: string;
      dataCount?: number;
    };
    schematic?: {
      name?: string;
      pageCount?: number;
    };
    board?: {
      name?: string;
    };
    selection?: {
      documentKind?: string;
      count?: number;
    };
  };

  const message = [
    formatSection('当前文档', [
      `类型：${formatValue(resultData.document?.kind)}`,
      `文档 ID：${formatValue(resultData.document?.uuid)}`,
      `标签页：${formatValue(resultData.document?.tabId)}`,
    ]),
    '',
    formatSection('工程信息', [
      `工作区：${formatValue(resultData.workspace?.name)}`,
      `工程名称：${formatValue(resultData.project?.name)}`,
      `工程 ID：${formatValue(resultData.project?.uuid)}`,
      `文档数量：${formatValue(resultData.project?.dataCount)}`,
    ]),
    '',
    formatSection('编辑上下文', [
      `原理图：${formatValue(resultData.schematic?.name)}`,
      `原理图页数：${formatValue(resultData.schematic?.pageCount)}`,
      `PCB：${formatValue(resultData.board?.name)}`,
      `当前选区：${formatValue(resultData.selection?.count, '0')} 项`,
    ]),
  ].join('\n');

  eda.sys_Dialog.showInformationMessage(message, '当前文档');
}

export async function runBridgeSelfCheck(): Promise<void> {
  const checks = await Promise.all([
    executeBridgeCommand('system.ping', { echo: 'self-check' }),
    executeBridgeCommand('system.get_bridge_status'),
    executeBridgeCommand('project.get_document_summary'),
    executeBridgeCommand('project.get_selection_snapshot'),
  ]);

  const summaryLines = checks.map((response, index) => {
    const label = ['连通性', '桥接状态', '文档摘要', '选区摘要'][index];
    const statusText = response.status === 'success' ? '正常' : response.status === 'confirmation_required' ? '待确认' : '异常';
    return `${label}：${statusText}`;
  });

  eda.sys_Dialog.showInformationMessage(summaryLines.join('\n'), '桥接自检');
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

function showSelectDialog(
  options: Array<{ value: string; displayContent: string }>,
  beforeContent: string,
  title: string,
): Promise<string | undefined> {
  return new Promise((resolve) => {
    eda.sys_Dialog.showSelectDialog(
      options,
      beforeContent,
      '',
      title,
      options[0]?.value,
      false,
      (value) => {
        resolve(typeof value === 'string' ? value : undefined);
      },
    );
  });
}

export async function configureRemoteBridge(): Promise<void> {
  const currentSettings = remoteBridgeClient.getSettings();
  const serverUrl = await showInputDialog(
    '请输入远程服务 WebSocket 地址',
    '远程服务地址',
    'url',
    currentSettings.serverUrl,
  );

  if (serverUrl === undefined) {
    return;
  }

  const authToken = await showInputDialog(
    '请输入远程服务令牌',
    '远程服务令牌',
    'password',
    currentSettings.authToken,
  );

  if (authToken === undefined) {
    return;
  }

  const clientId = await showInputDialog(
    '请输入当前设备的客户端 ID',
    '客户端 ID',
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

  eda.sys_Dialog.showInformationMessage('远程服务配置已保存。', '远程服务');
}

export async function connectRemoteBridge(): Promise<void> {
  try {
    await remoteBridgeClient.connect();
    eda.sys_Dialog.showInformationMessage('已开始连接远程服务。', '远程服务');
  }
  catch (error) {
    eda.sys_Dialog.showInformationMessage(
      error instanceof Error ? error.message : '启动远程连接失败。',
      '远程服务',
    );
  }
}

export function disconnectRemoteBridge(): void {
  remoteBridgeClient.disconnect();
  eda.sys_Dialog.showInformationMessage('远程服务已断开。', '远程服务');
}

export function showRemoteBridgeStatus(): void {
  const remoteStatus = remoteBridgeClient.getStatus();
  const message = [
    formatSection('连接概览', [
      `当前状态：${remoteStatus.connected ? '已连接' : remoteStatus.connecting ? '连接中' : '未连接'}`,
      `服务地址：${formatValue(remoteStatus.serverUrl, '未设置')}`,
      `客户端 ID：${formatValue(remoteStatus.clientId, '未设置')}`,
    ]),
    '',
    formatSection('连接恢复', [
      `重连次数：${remoteStatus.reconnectAttempts}`,
      `等待重连：${remoteStatus.reconnectScheduled ? '是' : '否'}`,
    ]),
    '',
    formatSection('最近活动', [
      `最近注册：${formatValue(remoteStatus.lastRegisteredAt)}`,
      `最近心跳：${formatValue(remoteStatus.lastHeartbeatAt)}`,
      `最近错误：${formatValue(remoteStatus.lastError, '无')}`,
    ]),
  ].join('\n');

  eda.sys_Dialog.showInformationMessage(message, '远程状态');
}

async function openBridgeMenuFallback(): Promise<void> {
  const remoteStatus = remoteBridgeClient.getStatus();
  const action = await showSelectDialog(
    [
      { value: 'status', displayContent: '桥接状态  查看当前桥接与运行环境' },
      { value: 'document', displayContent: '当前文档  查看当前工程与选区摘要' },
      { value: 'self-check', displayContent: '桥接自检  快速检查桥接链路' },
      { value: 'configure', displayContent: '配置远程服务  设置地址、令牌与客户端 ID' },
      {
        value: remoteStatus.connected ? 'disconnect' : 'connect',
        displayContent: remoteStatus.connected ? '断开远程服务  结束当前连接' : '连接远程服务  启动远程桥接',
      },
      { value: 'remote-status', displayContent: '远程状态  查看连接细节与最近错误' },
      { value: 'about', displayContent: '关于插件  查看插件简介与版本' },
    ],
    [
      '选择一个操作',
      '',
      `远程状态：${remoteStatus.connected ? '已连接' : remoteStatus.connecting ? '连接中' : remoteStatus.configured ? '待连接' : '未配置'}`,
      `插件版本：${extensionConfig.version}`,
    ].join('\n'),
    'AI桥接',
  );

  switch (action) {
    case 'status':
      await showBridgeStatus();
      break;
    case 'document':
      await inspectCurrentDocument();
      break;
    case 'self-check':
      await runBridgeSelfCheck();
      break;
    case 'configure':
      await configureRemoteBridge();
      break;
    case 'connect':
      await connectRemoteBridge();
      break;
    case 'disconnect':
      disconnectRemoteBridge();
      break;
    case 'remote-status':
      showRemoteBridgeStatus();
      break;
    case 'about':
      about();
      break;
  }
}

export async function openBridgeMenu(): Promise<void> {
  try {
    await openBridgeDialog();
  }
  catch (error) {
    eda.sys_Dialog.showInformationMessage(
      [
        '高级弹窗当前未能正常打开，已切换到简化模式。',
        '',
        error instanceof Error ? error.message : '未知错误',
      ].join('\n'),
      'AI桥接',
    );
    await openBridgeMenuFallback();
  }
}
