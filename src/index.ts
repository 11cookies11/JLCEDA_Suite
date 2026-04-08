import * as extensionConfig from '../extension.json';
import { getUpdateStatusLines, getUpdateStatusSnapshot, refreshUpdateStatus } from './adapters/update-control';
import { executeBridgeCommand } from './bridge/handlers';
import { BRIDGE_PROTOCOL_VERSION } from './bridge/protocol';
import { getSupportedCommandNames, IMPLEMENTED_COMMANDS } from './bridge/registry';
import { remoteBridgeClient } from './remote/client';

const BRIDGE_UI_RPC_TOPIC = 'jlceda-aiagent.bridge-ui';
const BRIDGE_UI_REQUEST_TOPIC = `${BRIDGE_UI_RPC_TOPIC}.request`;
const BRIDGE_UI_RESPONSE_TOPIC_PREFIX = `${BRIDGE_UI_RPC_TOPIC}.response.`;
const BRIDGE_IFRAME_ID = 'ai-bridge-window';
let bridgeUiRpcRegistered = false;
let bridgeUiRequestBridgeRegistered = false;

function ensureBridgeUiRpcRegistered(): void {
  if (bridgeUiRpcRegistered) {
    return;
  }

  eda.sys_MessageBus.rpcService(BRIDGE_UI_RPC_TOPIC, handleBridgeUiRpc);
  eda.sys_MessageBus.rpcServicePublic(BRIDGE_UI_RPC_TOPIC, handleBridgeUiRpc);
  bridgeUiRpcRegistered = true;
}

function ensureBridgeUiRequestBridgeRegistered(): void {
  if (bridgeUiRequestBridgeRegistered) {
    return;
  }

  eda.sys_MessageBus.subscribePublic(BRIDGE_UI_REQUEST_TOPIC, (payload) => {
    void (async () => {
      const requestId = typeof payload?.requestId === 'string' ? payload.requestId : '';
      const message = payload?.message;
      let response: any;

      if (!requestId) {
        return;
      }

      try {
        response = await handleBridgeUiRpc(message);
      }
      catch (error) {
        response = {
          ok: false,
          title: 'AI桥接',
          lines: [
            '窗口与插件通信失败。',
            '',
            error instanceof Error ? error.message : '未知错误',
          ],
          remoteStatus: remoteBridgeClient.getStatus(),
        };
      }

      eda.sys_MessageBus.publishPublic(`${BRIDGE_UI_RESPONSE_TOPIC_PREFIX}${requestId}`, response);
    })();
  });

  bridgeUiRequestBridgeRegistered = true;
}

function getStatusLines(): Array<string> {
  const remoteStatus = remoteBridgeClient.getStatus();

  return [
    `插件：${extensionConfig.displayName}`,
    `版本：${extensionConfig.version}`,
    `协议：${BRIDGE_PROTOCOL_VERSION}`,
    `命令支持：${IMPLEMENTED_COMMANDS.length} / ${getSupportedCommandNames().length}`,
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

function summarizeBridgeStatus(): Array<string> {
  return getStatusLines();
}

function summarizeRemoteStatus(): Array<string> {
  const remoteStatus = remoteBridgeClient.getStatus();

  return [
    `服务地址：${remoteStatus.serverUrl ?? '未设置'}`,
    `客户端 ID：${remoteStatus.clientId ?? '未设置'}`,
    `当前状态：${remoteStatus.connected ? '已连接' : remoteStatus.connecting ? '连接中' : '未连接'}`,
    `重连次数：${remoteStatus.reconnectAttempts}`,
    `等待重连：${remoteStatus.reconnectScheduled ? '是' : '否'}`,
    `最近注册：${remoteStatus.lastRegisteredAt ?? '暂无'}`,
    `最近心跳：${remoteStatus.lastHeartbeatAt ?? '暂无'}`,
    `最近错误：${remoteStatus.lastError ?? '无'}`,
  ];
}

function summarizeUpdateStatus(): Array<string> {
  return getUpdateStatusLines();
}

function summarizeDocumentData(data: unknown): Array<string> {
  const resultData = (data ?? {}) as {
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
      count?: number;
    };
  };

  return [
    `文档类型：${formatValue(resultData.document?.kind)}`,
    `文档 ID：${formatValue(resultData.document?.uuid)}`,
    `标签页：${formatValue(resultData.document?.tabId)}`,
    `工作区：${formatValue(resultData.workspace?.name)}`,
    `工程名称：${formatValue(resultData.project?.name)}`,
    `工程 ID：${formatValue(resultData.project?.uuid)}`,
    `工程文档数：${formatValue(resultData.project?.dataCount, '0')}`,
    `原理图：${formatValue(resultData.schematic?.name)}`,
    `原理图页数：${formatValue(resultData.schematic?.pageCount, '0')}`,
    `PCB：${formatValue(resultData.board?.name)}`,
    `当前选区：${formatValue(resultData.selection?.count, '0')} 项`,
  ];
}

async function handleBridgeUiRpc(message: any): Promise<any> {
  switch (message?.type) {
    case 'getInitialState': {
      return {
        ok: true,
        title: '桥接概览',
        lines: [
          ...summarizeBridgeStatus(),
          '',
          ...summarizeRemoteStatus(),
          '',
          ...summarizeUpdateStatus(),
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
        remoteSettings: remoteBridgeClient.getSettings(),
        updateStatus: getUpdateStatusSnapshot(),
      };
    }

    case 'showBridgeStatus': {
      const response = await executeBridgeCommand('system.get_bridge_status');

      if (response.status !== 'success') {
        return {
          ok: false,
          title: '桥接状态',
          lines: [
            `错误代码：${response.error.code}`,
            `错误信息：${response.error.message}`,
            '',
            ...summarizeUpdateStatus(),
          ],
          remoteStatus: remoteBridgeClient.getStatus(),
          updateStatus: getUpdateStatusSnapshot(),
        };
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

      return {
        ok: true,
        title: '桥接状态',
        lines: [
          ...summarizeBridgeStatus(),
          '',
          `客户端环境：${resultData.runtime?.isClient ? '是' : '否'}`,
          `网页环境：${resultData.runtime?.isWeb ? '是' : '否'}`,
          `语言：${formatValue(resultData.runtime?.language)}`,
          `主题：${formatValue(resultData.runtime?.theme)}`,
          `单位：${formatValue(resultData.runtime?.frontendUnit)}`,
          '',
          ...summarizeUpdateStatus(),
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
        updateStatus: getUpdateStatusSnapshot(),
      };
    }

    case 'inspectCurrentDocument': {
      const response = await executeBridgeCommand('project.get_document_summary');

      if (response.status !== 'success') {
        return {
          ok: false,
          title: '当前文档',
          lines: [
            `错误代码：${response.error.code}`,
            `错误信息：${response.error.message}`,
            '',
            ...summarizeUpdateStatus(),
          ],
          remoteStatus: remoteBridgeClient.getStatus(),
          updateStatus: getUpdateStatusSnapshot(),
        };
      }

      return {
        ok: true,
        title: '当前文档',
        lines: [
          ...summarizeDocumentData(response.result.data),
          '',
          ...summarizeUpdateStatus(),
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
        updateStatus: getUpdateStatusSnapshot(),
      };
    }

    case 'runSelfCheck': {
      const checks = await Promise.all([
        executeBridgeCommand('system.ping', { echo: 'iframe-self-check' }),
        executeBridgeCommand('system.get_bridge_status'),
        executeBridgeCommand('project.get_document_summary'),
        executeBridgeCommand('project.get_selection_snapshot'),
      ]);

      const lines = checks.map((response, index) => {
        const label = ['连通性', '桥接状态', '文档摘要', '选区摘要'][index];
        const statusText = response.status === 'success'
          ? '正常'
          : response.status === 'confirmation_required'
            ? '待确认'
            : '异常';
        return `${label}：${statusText}`;
      });

      const updateStatus = await refreshUpdateStatus(false);

      return {
        ok: true,
        title: '桥接自检',
        lines: [
          ...lines,
          '',
          ...summarizeUpdateStatus(),
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
        updateStatus,
      };
    }

    case 'checkForUpdates': {
      const updateStatus = await refreshUpdateStatus(true);

      return {
        ok: true,
        title: '版本更新',
        lines: summarizeUpdateStatus(),
        remoteStatus: remoteBridgeClient.getStatus(),
        updateStatus,
      };
    }

    case 'openLatestReleasePage': {
      const updateStatus = await refreshUpdateStatus(true);
      const targetUrl = updateStatus.latestDownloadUrl
        ?? updateStatus.latestReleaseUrl
        ?? 'https://github.com/11cookies11/JLCEDA_AIAgent/releases/latest';

      eda.sys_Window.open(targetUrl, '_blank');

      return {
        ok: true,
        title: '版本更新',
        lines: [
          `已打开：${targetUrl}`,
          '',
          ...summarizeUpdateStatus(),
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
        updateStatus,
      };
    }

    case 'saveRemoteSettings': {
      await remoteBridgeClient.saveSettings({
        serverUrl: typeof message?.payload?.serverUrl === 'string' ? message.payload.serverUrl : '',
        authToken: typeof message?.payload?.authToken === 'string' ? message.payload.authToken : '',
        clientId: typeof message?.payload?.clientId === 'string' ? message.payload.clientId : '',
        autoConnect: message?.payload?.autoConnect !== false,
      });

      return {
        ok: true,
        title: '远程服务',
        lines: [
          '配置已保存',
          '',
          ...summarizeRemoteStatus(),
          '',
          ...summarizeUpdateStatus(),
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
        remoteSettings: remoteBridgeClient.getSettings(),
        updateStatus: getUpdateStatusSnapshot(),
      };
    }

    case 'connectRemoteBridge': {
      await remoteBridgeClient.connect();

      return {
        ok: true,
        title: '远程服务',
        lines: [
          '已开始连接远程服务',
          '',
          ...summarizeRemoteStatus(),
          '',
          ...summarizeUpdateStatus(),
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
        updateStatus: getUpdateStatusSnapshot(),
      };
    }

    case 'disconnectRemoteBridge': {
      remoteBridgeClient.disconnect();

      return {
        ok: true,
        title: '远程服务',
        lines: [
          '远程服务已断开',
          '',
          ...summarizeRemoteStatus(),
          '',
          ...summarizeUpdateStatus(),
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
        updateStatus: getUpdateStatusSnapshot(),
      };
    }

    case 'showRemoteBridgeStatus': {
      return {
        ok: true,
        title: '远程状态',
        lines: [
          ...summarizeRemoteStatus(),
          '',
          ...summarizeUpdateStatus(),
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
        updateStatus: getUpdateStatusSnapshot(),
      };
    }

    default:
      return {
        ok: false,
        title: 'AI桥接',
        lines: [
          '未识别的窗口动作。',
        ],
        remoteStatus: remoteBridgeClient.getStatus(),
      };
  }
}

export function activate(status?: 'onStartupFinished', arg?: string): void {
  void status;
  void arg;
  ensureBridgeUiRpcRegistered();
  ensureBridgeUiRequestBridgeRegistered();
  void remoteBridgeClient.autoConnectIfEnabled();
  void refreshUpdateStatus().catch(() => undefined);
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
    '',
    formatSection('更新状态', summarizeUpdateStatus()),
  ].join('\n');

  eda.sys_Dialog.showInformationMessage(summary, '桥接状态');
}

export async function inspectCurrentDocument(): Promise<void> {
  const response = await executeBridgeCommand('project.get_document_summary');
  if (response.status !== 'success') {
    eda.sys_Dialog.showInformationMessage(
      [
        '读取当前文档失败',
        '',
        `错误代码：${response.error.code}`,
        `错误信息：${response.error.message}`,
        '',
        ...summarizeUpdateStatus(),
      ].join('\n'),
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
    '',
    formatSection('更新状态', summarizeUpdateStatus()),
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

  eda.sys_Dialog.showInformationMessage([
    summaryLines.join('\n'),
    '',
    ...summarizeUpdateStatus(),
  ].join('\n'), '桥接自检');
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
    '',
    formatSection('更新状态', summarizeUpdateStatus()),
  ].join('\n');

  eda.sys_Dialog.showInformationMessage(message, '远程状态');
}

async function _openBridgeMenuFallback(): Promise<void> {
  const remoteStatus = remoteBridgeClient.getStatus();
  const action = await showSelectDialog(
    [
      { value: 'status', displayContent: '桥接状态  查看当前桥接与运行环境' },
      { value: 'document', displayContent: '当前文档  查看当前工程与选区摘要' },
      { value: 'self-check', displayContent: '桥接自检  快速检查桥接链路' },
      { value: 'check-update', displayContent: '检查更新  查询最新插件版本' },
      { value: 'open-update-page', displayContent: '打开更新页  前往最新插件下载页' },
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
      `更新状态：${getUpdateStatusSnapshot().updateAvailable ? '可更新' : '已是最新'}`,
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
    case 'check-update':
      await refreshUpdateStatus(true);
      eda.sys_Dialog.showInformationMessage(
        [
          '更新检查已完成。',
          '',
          ...summarizeUpdateStatus(),
        ].join('\n'),
        '版本更新',
      );
      break;
    case 'open-update-page': {
      const updateStatus = await refreshUpdateStatus(true);
      const targetUrl = updateStatus.latestDownloadUrl
        ?? updateStatus.latestReleaseUrl
        ?? 'https://github.com/11cookies11/JLCEDA_AIAgent/releases/latest';

      eda.sys_Window.open(targetUrl, '_blank');
      break;
    }
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

async function openBridgeMenuInternal(): Promise<void> {
  ensureBridgeUiRpcRegistered();
  ensureBridgeUiRequestBridgeRegistered();

  const openOptions = {
    title: 'AI桥接',
    maximizeButton: true,
    minimizeButton: true,
    grayscaleMask: true,
  } as const;

  try {
    const alreadyExists = await eda.sys_IFrame.isIFrameAlreadyExist(BRIDGE_IFRAME_ID);

    if (alreadyExists) {
      const shown = await eda.sys_IFrame.showIFrame(BRIDGE_IFRAME_ID);

      if (shown) {
        return;
      }

      // Some runtime builds report an existing window but refuse to foreground it.
      // Recreate the window instead of forcing users into the simplified fallback.
      await eda.sys_IFrame.closeIFrame(BRIDGE_IFRAME_ID);
    }

    await eda.sys_IFrame.openIFrame('/iframe/bridge/index.html', 980, 720, BRIDGE_IFRAME_ID, openOptions);
    // Treat a resolved openIFrame call as success. Some runtime builds open the
    // window correctly but report stale results for follow-up existence checks.
  }
  catch (error) {
    eda.sys_Dialog.showInformationMessage(
      [
        'AI桥接窗口未能正常打开。',
        '',
        error instanceof Error ? error.message : '未知错误',
        '',
        '已保留 IFrame 方案，请重试一次；若仍失败，再考虑兼容模式。',
      ].join('\n'),
      'AI桥接',
    );
  }
}

export function openBridgeMenu(): void {
  void openBridgeMenuInternal();
}
