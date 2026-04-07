import * as React from 'react';
import Reconciler from 'react-reconciler';
import * as ReconcilerConstants from 'react-reconciler/constants';
import * as extensionConfig from '../../extension.json';
import { executeBridgeCommand } from '../bridge/handlers';
import { BRIDGE_PROTOCOL_VERSION } from '../bridge/protocol';
import { getSupportedCommandNames, IMPLEMENTED_COMMANDS } from '../bridge/registry';
import { remoteBridgeClient } from '../remote/client';

type BridgeDialogTab = 'overview' | 'connection' | 'document' | 'diagnostics';

interface RemoteSettingsState {
  serverUrl: string;
  authToken: string;
  clientId: string;
  autoConnect: boolean;
}

interface BridgeDialogContext {
  render: (element: React.ReactNode) => void;
}

let dialogContextPromise: Promise<BridgeDialogContext> | undefined;

function h<P>(
  type: React.ElementType<P>,
  props?: P | null,
  ...children: React.ReactNode[]
): React.ReactElement<P> {
  return React.createElement(type, props, ...children);
}

async function getBridgeDialogContext(): Promise<BridgeDialogContext> {
  if (!dialogContextPromise) {
    dialogContextPromise = (async () => {
      const dialogInterface = await eda.sys_Dialog.createReactComponentizationDialogInterface(
        {
          createContext: React.createContext,
          useContext: React.useContext,
          useRef: React.useRef,
          useEffect: React.useEffect,
          createElement: React.createElement,
          useState: React.useState,
        },
        {
          default: Reconciler,
          constants: {
            ContinuousEventPriority: ReconcilerConstants.ContinuousEventPriority,
            DiscreteEventPriority: ReconcilerConstants.DiscreteEventPriority,
            DefaultEventPriority: ReconcilerConstants.DefaultEventPriority,
            ConcurrentRoot: ReconcilerConstants.ConcurrentRoot,
          },
        },
      );

      const portal = new dialogInterface.WorkerPortal();
      const root = new dialogInterface.VirtualRender();

      return {
        render: (element) => {
          root.render(h(portal.Provider, null, element));
        },
      };
    })();
  }

  return dialogContextPromise;
}

function summarizeBridgeStatus(): string[] {
  const remoteStatus = remoteBridgeClient.getStatus();

  return [
    `插件：${extensionConfig.displayName}`,
    `版本：${extensionConfig.version}`,
    `协议：${BRIDGE_PROTOCOL_VERSION}`,
    `命令支持：${getSupportedCommandNames().length} / ${IMPLEMENTED_COMMANDS.length}`,
    `远程状态：${remoteStatus.connected ? '已连接' : remoteStatus.connecting ? '连接中' : remoteStatus.configured ? '待连接' : '未配置'}`,
  ];
}

function summarizeRemoteStatus(): string[] {
  const remoteStatus = remoteBridgeClient.getStatus();

  return [
    `服务地址：${remoteStatus.serverUrl ?? '未设置'}`,
    `客户端 ID：${remoteStatus.clientId ?? '未设置'}`,
    `连接状态：${remoteStatus.connected ? '已连接' : remoteStatus.connecting ? '连接中' : '未连接'}`,
    `重连次数：${remoteStatus.reconnectAttempts}`,
    `等待重连：${remoteStatus.reconnectScheduled ? '是' : '否'}`,
    `最近错误：${remoteStatus.lastError ?? '无'}`,
  ];
}

function summarizeDocumentData(data: unknown): string[] {
  const resultData = (data ?? {}) as {
    document?: { kind?: string; uuid?: string; tabId?: string };
    workspace?: { name?: string };
    project?: { name?: string; uuid?: string; dataCount?: number };
    schematic?: { name?: string; pageCount?: number };
    board?: { name?: string };
    selection?: { count?: number };
  };

  return [
    `文档类型：${resultData.document?.kind ?? '未知'}`,
    `文档 ID：${resultData.document?.uuid ?? '暂无'}`,
    `标签页：${resultData.document?.tabId ?? '暂无'}`,
    `工作区：${resultData.workspace?.name ?? '暂无'}`,
    `工程名称：${resultData.project?.name ?? '暂无'}`,
    `工程文档数：${resultData.project?.dataCount ?? 0}`,
    `原理图：${resultData.schematic?.name ?? '暂无'}`,
    `PCB：${resultData.board?.name ?? '暂无'}`,
    `当前选区：${resultData.selection?.count ?? 0} 项`,
  ];
}

function summarizeSelfCheck(statuses: string[]): string[] {
  return statuses.map(item => `- ${item}`);
}

function BridgeDialogApp(props: { onClose: () => void }): React.ReactElement {
  const [activeTab, setActiveTab] = React.useState<BridgeDialogTab>('overview');
  const [settings, setSettings] = React.useState<RemoteSettingsState>(remoteBridgeClient.getSettings());
  const [statusLines, setStatusLines] = React.useState<string[]>(summarizeBridgeStatus());
  const [resultTitle, setResultTitle] = React.useState('桥接概览');
  const [resultLines, setResultLines] = React.useState<string[]>([
    ...summarizeBridgeStatus(),
    '',
    ...summarizeRemoteStatus(),
  ]);
  const [busy, setBusy] = React.useState(false);

  const refreshSnapshots = React.useCallback(() => {
    setStatusLines(summarizeBridgeStatus());
    setSettings(remoteBridgeClient.getSettings());
  }, []);

  React.useEffect(() => {
    refreshSnapshots();
  }, [refreshSnapshots]);

  async function runWithFeedback(
    title: string,
    action: () => Promise<string[]>,
  ): Promise<void> {
    setBusy(true);
    setResultTitle(title);

    try {
      const lines = await action();
      setResultLines(lines);
      refreshSnapshots();
    }
    catch (error) {
      setResultLines([
        `操作失败`,
        '',
        error instanceof Error ? error.message : '未知错误',
      ]);
    }
    finally {
      setBusy(false);
    }
  }

  async function handleSaveSettings(): Promise<void> {
    await runWithFeedback('远程服务', async () => {
      await remoteBridgeClient.saveSettings(settings);
      return [
        '配置已保存',
        '',
        `服务地址：${settings.serverUrl || '未设置'}`,
        `客户端 ID：${settings.clientId || '未设置'}`,
        `自动连接：${settings.autoConnect ? '开启' : '关闭'}`,
      ];
    });
  }

  async function handleConnect(): Promise<void> {
    await runWithFeedback('远程服务', async () => {
      await remoteBridgeClient.connect();
      return [
        '已开始连接远程服务',
        '',
        ...summarizeRemoteStatus(),
      ];
    });
  }

  async function handleDisconnect(): Promise<void> {
    await runWithFeedback('远程服务', async () => {
      remoteBridgeClient.disconnect();
      return [
        '远程服务已断开',
        '',
        ...summarizeRemoteStatus(),
      ];
    });
  }

  async function handleInspectDocument(): Promise<void> {
    await runWithFeedback('当前文档', async () => {
      const response = await executeBridgeCommand('project.get_document_summary');

      if (response.status !== 'success') {
        return [
          `错误代码：${response.error.code}`,
          `错误信息：${response.error.message}`,
        ];
      }

      return summarizeDocumentData(response.result.data);
    });
  }

  async function handleSelfCheck(): Promise<void> {
    await runWithFeedback('桥接自检', async () => {
      const checks = await Promise.all([
        executeBridgeCommand('system.ping', { echo: 'dialog-check' }),
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

      return summarizeSelfCheck(lines);
    });
  }

  async function handleShowOverview(): Promise<void> {
    await runWithFeedback('桥接概览', async () => {
      const response = await executeBridgeCommand('system.get_bridge_status');
      const lines = summarizeBridgeStatus();

      if (response.status !== 'success') {
        return [
          ...lines,
          '',
          `错误代码：${response.error.code}`,
          `错误信息：${response.error.message}`,
        ];
      }

      const resultData = (response.result.data ?? {}) as {
        runtime?: { language?: string; theme?: string; frontendUnit?: string };
      };

      return [
        ...lines,
        '',
        `语言：${resultData.runtime?.language ?? '未知'}`,
        `主题：${resultData.runtime?.theme ?? '未知'}`,
        `单位：${resultData.runtime?.frontendUnit ?? '未知'}`,
      ];
    });
  }

  const navItems = [
    { id: 'overview', title: '概览' },
    { id: 'connection', title: '连接' },
    { id: 'document', title: '文档' },
    { id: 'diagnostics', title: '诊断' },
  ];

  const currentRemoteStatus = remoteBridgeClient.getStatus();

  const ui = React.useMemo(() => h(BridgeDialogInner, {
    activeTab,
    busy,
    navItems,
    onClose: props.onClose,
    onSelectTab: (tab: string) => setActiveTab(tab as BridgeDialogTab),
    resultTitle,
    resultLines,
    settings,
    setSettings,
    statusLines,
    currentRemoteStatus,
    onShowOverview: handleShowOverview,
    onSaveSettings: handleSaveSettings,
    onConnect: handleConnect,
    onDisconnect: handleDisconnect,
    onInspectDocument: handleInspectDocument,
    onSelfCheck: handleSelfCheck,
  }), [
    activeTab,
    busy,
    currentRemoteStatus,
    navItems,
    props.onClose,
    resultLines,
    resultTitle,
    settings,
    statusLines,
  ]);

  return ui;
}

function BridgeDialogInner(props: {
  activeTab: BridgeDialogTab;
  busy: boolean;
  navItems: Array<{ id: string; title: string }>;
  onClose: () => void;
  onSelectTab: (tab: string) => void;
  resultTitle: string;
  resultLines: string[];
  settings: RemoteSettingsState;
  setSettings: React.Dispatch<React.SetStateAction<RemoteSettingsState>>;
  statusLines: string[];
  currentRemoteStatus: ReturnType<typeof remoteBridgeClient.getStatus>;
  onShowOverview: () => Promise<void>;
  onSaveSettings: () => Promise<void>;
  onConnect: () => Promise<void>;
  onDisconnect: () => Promise<void>;
  onInspectDocument: () => Promise<void>;
  onSelfCheck: () => Promise<void>;
}): React.ReactElement {
  const Components = (eda as any).__bridgeDialogComponents as any;
  const {
    Modal,
    Dialog,
    Flex,
    FlexItem,
    Text,
    Input,
    Button,
    List,
    Grid,
    GridItem,
    CheckBox,
    Board,
  } = Components;

  function updateSetting(key: keyof RemoteSettingsState, value: string | boolean): void {
    props.setSettings(current => ({
      ...current,
      [key]: value,
    }));
  }

  function renderConnectionTab(): React.ReactElement {
    return h(Flex, { direction: 'column', gap: 14 }, h(Board, {
      title: '服务地址',
      padding: [14, 14, 14, 14],
      bgColor: '#f3f4f5',
    }, h(Input, {
      type: 'text',
      width: 430,
      value: props.settings.serverUrl,
      placeholder: 'wss://your-server.example/ws',
      onChange: (value: string) => updateSetting('serverUrl', value),
    })), h(Grid, { columns: 2, colGap: 14, rowGap: 14 }, h(GridItem, null, h(Board, {
      title: '访问令牌',
      padding: [14, 14, 14, 14],
      bgColor: '#f3f4f5',
    }, h(Input, {
      type: 'password',
      width: 208,
      value: props.settings.authToken,
      placeholder: '请输入访问令牌',
      onChange: (value: string) => updateSetting('authToken', value),
    }))), h(GridItem, null, h(Board, {
      title: '客户端 ID',
      padding: [14, 14, 14, 14],
      bgColor: '#f3f4f5',
    }, h(Input, {
      type: 'text',
      width: 208,
      value: props.settings.clientId,
      placeholder: '当前设备标识',
      onChange: (value: string) => updateSetting('clientId', value),
    })))), h(CheckBox, {
      checked: props.settings.autoConnect,
      text: '启动时自动连接远程服务',
      onChange: (checked: boolean) => updateSetting('autoConnect', checked),
    }), h(Flex, { direction: 'row', gap: 10 }, h(Button, {
      text: '保存配置',
      type: 'default',
      width: 110,
      onClick: () => {
        void props.onSaveSettings();
      },
    }), h(Button, {
      text: '保存并连接',
      type: 'primary',
      width: 130,
      onClick: () => {
        void props.onSaveSettings().then(props.onConnect);
      },
    })));
  }

  function renderOverviewTab(): React.ReactElement {
    return h(Flex, { direction: 'column', gap: 14 }, h(Board, {
      title: '桥接概览',
      padding: [14, 14, 14, 14],
      bgColor: '#f3f4f5',
    }, ...props.statusLines.map(line => h(Text, { value: line, fontSize: 12, color: '#404751' }))), h(Board, {
      title: '远程连接',
      padding: [14, 14, 14, 14],
      bgColor: '#f3f4f5',
    }, ...summarizeRemoteStatus().map(line => h(Text, { value: line, fontSize: 12, color: '#404751' }))), h(Flex, { direction: 'row', gap: 10 }, h(Button, {
      text: '刷新概览',
      type: 'default',
      width: 110,
      onClick: () => {
        void props.onShowOverview();
      },
    }), h(Button, {
      text: props.currentRemoteStatus.connected ? '断开连接' : '立即连接',
      type: props.currentRemoteStatus.connected ? 'default' : 'primary',
      width: 110,
      onClick: () => {
        void (props.currentRemoteStatus.connected ? props.onDisconnect() : props.onConnect());
      },
    })));
  }

  function renderDocumentTab(): React.ReactElement {
    return h(Flex, { direction: 'column', gap: 14 }, h(Board, {
      title: '工程上下文',
      padding: [14, 14, 14, 14],
      bgColor: '#f3f4f5',
    }, h(Text, {
      value: '适合在连通后快速确认当前文档、工程和选区是否正确。',
      fontSize: 12,
      color: '#404751',
    })), h(Flex, { direction: 'row', gap: 10 }, h(Button, {
      text: '读取当前文档',
      type: 'primary',
      width: 120,
      onClick: () => {
        void props.onInspectDocument();
      },
    }), h(Button, {
      text: '查看桥接状态',
      type: 'default',
      width: 120,
      onClick: () => {
        void props.onShowOverview();
      },
    })));
  }

  function renderDiagnosticsTab(): React.ReactElement {
    return h(Flex, { direction: 'column', gap: 14 }, h(Board, {
      title: '链路诊断',
      padding: [14, 14, 14, 14],
      bgColor: '#f3f4f5',
    }, h(Text, {
      value: '适合在首次导入、改动服务地址或出现连接异常时运行。',
      fontSize: 12,
      color: '#404751',
    })), h(Flex, { direction: 'row', gap: 10 }, h(Button, {
      text: '运行自检',
      type: 'primary',
      width: 110,
      onClick: () => {
        void props.onSelfCheck();
      },
    }), h(Button, {
      text: '查看远程状态',
      type: 'default',
      width: 120,
      onClick: () => {
        void props.onShowOverview();
      },
    })));
  }

  let content = renderOverviewTab();
  if (props.activeTab === 'connection') {
    content = renderConnectionTab();
  }
  else if (props.activeTab === 'document') {
    content = renderDocumentTab();
  }
  else if (props.activeTab === 'diagnostics') {
    content = renderDiagnosticsTab();
  }

  return h(Modal, {
    defaultTop: 72,
    defaultLeft: 180,
    defaultWidth: 860,
    defaultHeight: 620,
  }, h(Dialog, {
    title: 'AI桥接',
    onClose: props.onClose,
    buttons: [
      {
        text: '关闭',
        type: 'default',
        onClick: props.onClose,
      },
      {
        text: props.busy ? '处理中...' : '保存并连接',
        type: 'primary',
        onClick: () => {
          void props.onSaveSettings().then(props.onConnect);
        },
      },
    ],
  }, h(Flex, {
    direction: 'row',
    gap: 0,
    width: 820,
    height: 520,
  }, h(FlexItem, {
    width: 180,
    padding: [12, 12, 12, 12],
    backgroundColor: '#f3f4f5',
  }, h(Flex, { direction: 'column', gap: 12 }, h(Text, { value: 'ENGINEERING BRIDGE', fontSize: 10, color: '#707883' }), h(Text, { value: extensionConfig.displayName, fontSize: 16, color: '#191c1d' }), h(Text, { value: `远程状态：${props.currentRemoteStatus.connected ? '已连接' : props.currentRemoteStatus.connecting ? '连接中' : props.currentRemoteStatus.configured ? '待连接' : '未配置'}`, fontSize: 11, color: '#0060a8' }), h(List, {
    width: 156,
    height: 220,
    itemHeight: 38,
    border: false,
    expandEnable: false,
    list: props.navItems.map(item => ({
      id: item.id,
      title: item.title,
      selected: item.id === props.activeTab,
    })),
    onItemClick: (id: string) => {
      props.onSelectTab(id);
    },
  }))), h(FlexItem, {
    flexRatio: 1,
    padding: [18, 18, 18, 18],
    backgroundColor: '#ffffff',
  }, h(Flex, { direction: 'column', gap: 16 }, content, h(Board, {
    title: props.resultTitle,
    padding: [14, 14, 14, 14],
    bgColor: '#f8f9fa',
  }, ...props.resultLines.map(line => h(Text, {
    value: line,
    fontSize: 12,
    color: line.startsWith('错误') ? '#944a00' : '#404751',
  }))))))));
}

export async function openBridgeDialog(): Promise<void> {
  const context = await getBridgeDialogContext();

  function close(): void {
    context.render(null);
  }

  (eda as any).__bridgeDialogComponents = (await eda.sys_Dialog.createReactComponentizationDialogInterface(
    {
      createContext: React.createContext,
      useContext: React.useContext,
      useRef: React.useRef,
      useEffect: React.useEffect,
      createElement: React.createElement,
      useState: React.useState,
    },
    {
      default: Reconciler,
      constants: {
        ContinuousEventPriority: ReconcilerConstants.ContinuousEventPriority,
        DiscreteEventPriority: ReconcilerConstants.DiscreteEventPriority,
        DefaultEventPriority: ReconcilerConstants.DefaultEventPriority,
        ConcurrentRoot: ReconcilerConstants.ConcurrentRoot,
      },
    },
  )).Components;

  context.render(h(BridgeDialogApp, { onClose: close }));
}
