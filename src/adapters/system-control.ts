import type { BridgeResult } from '../bridge/protocol';

export interface LogPayload {
  message: string;
  type?: 'info' | 'warn' | 'error' | 'fatalError' | 'find' | 'replace' | 'openProject';
}

export interface LogQueryPayload {
  types?: Array<LogPayload['type']> | LogPayload['type'];
}

export interface PanelOpenPayload {
  tab?: string;
}

export interface WindowOpenPayload {
  url: string;
  target?: '_blank' | '_self';
}

export interface WindowOpenUiPayload {
  uiName: string;
  args?: Record<string, unknown>;
}

export interface ToastPayload {
  message: string;
  messageType?: 'error' | 'warn' | 'info' | 'success' | 'question';
  timer?: number;
  bottomPanel?: string;
  buttonTitle?: string;
  buttonCallbackFn?: string;
}

export interface FollowMouseTipPayload {
  tip: string;
  msTimeout?: number;
}

export interface MessageBoxPayload {
  content: string;
  title?: string;
  buttonTitle?: string;
}

export interface ConfirmationMessagePayload extends MessageBoxPayload {
  mainButtonTitle?: string;
}

export interface ShortcutQueryPayload {
  includeSystem?: boolean;
}

export async function addSystemLogResult(payload: LogPayload): Promise<BridgeResult> {
  eda.sys_Log.add(payload.message, payload.type as never);

  return {
    summary: 'system log added',
    data: {
      added: true,
      ...payload,
    },
  };
}

export async function clearSystemLogResult(): Promise<BridgeResult> {
  eda.sys_Log.clear();

  return {
    summary: 'system log cleared',
    data: {
      cleared: true,
    },
  };
}

export async function exportSystemLogResult(payload?: LogQueryPayload): Promise<BridgeResult> {
  eda.sys_Log.export(payload?.types as never);

  return {
    summary: 'system log exported',
    data: {
      exported: true,
      types: payload?.types ?? [],
    },
  };
}

export async function sortSystemLogResult(payload?: LogQueryPayload): Promise<BridgeResult> {
  const logs = await eda.sys_Log.sort(payload?.types as never);

  return {
    summary: 'system log collected',
    data: {
      logs,
      count: logs.length,
      types: payload?.types ?? [],
    },
  };
}

export async function findSystemLogResult(payload: {
  message: string | Array<string | {
    text: string;
    attr?: {
      id?: string;
      path?: string;
      sheet?: string;
      pcbid?: string;
      type?: string;
    };
  }>;
  types?: Array<LogPayload['type']> | LogPayload['type'];
}): Promise<BridgeResult> {
  const logs = await eda.sys_Log.find(payload.message as never, payload.types as never);

  return {
    summary: 'system log search completed',
    data: {
      logs,
      count: logs.length,
      types: payload.types ?? [],
    },
  };
}

export async function openLeftPanelResult(payload?: PanelOpenPayload): Promise<BridgeResult> {
  eda.sys_PanelControl.openLeftPanel(payload?.tab as never);

  return {
    summary: 'left panel opened',
    data: {
      opened: true,
      tab: payload?.tab,
    },
  };
}

export async function closeLeftPanelResult(): Promise<BridgeResult> {
  eda.sys_PanelControl.closeLeftPanel();

  return {
    summary: 'left panel closed',
    data: {
      closed: true,
    },
  };
}

export async function toggleLeftPanelLockResult(payload?: { state?: boolean }): Promise<BridgeResult> {
  eda.sys_PanelControl.toggleLeftPanelLockState(payload?.state);

  return {
    summary: 'left panel lock toggled',
    data: {
      state: payload?.state ?? null,
    },
  };
}

export async function isLeftPanelLockedResult(): Promise<BridgeResult> {
  const locked = await eda.sys_PanelControl.isLeftPanelLocked();

  return {
    summary: 'left panel lock state collected',
    data: {
      locked,
    },
  };
}

export async function openRightPanelResult(payload?: PanelOpenPayload): Promise<BridgeResult> {
  eda.sys_PanelControl.openRightPanel(payload?.tab as never);

  return {
    summary: 'right panel opened',
    data: {
      opened: true,
      tab: payload?.tab,
    },
  };
}

export async function closeRightPanelResult(): Promise<BridgeResult> {
  eda.sys_PanelControl.closeRightPanel();

  return {
    summary: 'right panel closed',
    data: {
      closed: true,
    },
  };
}

export async function toggleRightPanelLockResult(payload?: { state?: boolean }): Promise<BridgeResult> {
  eda.sys_PanelControl.toggleRightPanelLockState(payload?.state);

  return {
    summary: 'right panel lock toggled',
    data: {
      state: payload?.state ?? null,
    },
  };
}

export async function isRightPanelLockedResult(): Promise<BridgeResult> {
  const locked = await eda.sys_PanelControl.isRightPanelLocked();

  return {
    summary: 'right panel lock state collected',
    data: {
      locked,
    },
  };
}

export async function openBottomPanelResult(payload?: PanelOpenPayload): Promise<BridgeResult> {
  eda.sys_PanelControl.openBottomPanel(payload?.tab as never);

  return {
    summary: 'bottom panel opened',
    data: {
      opened: true,
      tab: payload?.tab,
    },
  };
}

export async function closeBottomPanelResult(): Promise<BridgeResult> {
  eda.sys_PanelControl.closeBottomPanel();

  return {
    summary: 'bottom panel closed',
    data: {
      closed: true,
    },
  };
}

export async function toggleBottomPanelLockResult(payload?: { state?: boolean }): Promise<BridgeResult> {
  eda.sys_PanelControl.toggleBottomPanelLockState(payload?.state);

  return {
    summary: 'bottom panel lock toggled',
    data: {
      state: payload?.state ?? null,
    },
  };
}

export async function isBottomPanelLockedResult(): Promise<BridgeResult> {
  const locked = await eda.sys_PanelControl.isBottomPanelLocked();

  return {
    summary: 'bottom panel lock state collected',
    data: {
      locked,
    },
  };
}

export async function openWindowResult(payload: WindowOpenPayload): Promise<BridgeResult> {
  eda.sys_Window.open(payload.url, payload.target as never);

  return {
    summary: 'window opened',
    data: {
      opened: true,
      ...payload,
    },
  };
}

export async function openUiWindowResult(payload: WindowOpenUiPayload): Promise<BridgeResult> {
  await eda.sys_Window.openUI(payload.uiName, payload.args);

  return {
    summary: 'UI window opened',
    data: {
      opened: true,
      ...payload,
    },
  };
}

export async function getCurrentThemeResult(): Promise<BridgeResult> {
  const theme = await eda.sys_Window.getCurrentTheme();

  return {
    summary: 'window theme collected',
    data: {
      theme,
    },
  };
}

export async function getUrlParamResult(key: string): Promise<BridgeResult> {
  const value = eda.sys_Window.getUrlParam(key);

  return {
    summary: 'URL parameter collected',
    data: {
      key,
      value,
    },
  };
}

export async function getUrlAnchorResult(): Promise<BridgeResult> {
  const anchor = eda.sys_Window.getUrlAnchor();

  return {
    summary: 'URL anchor collected',
    data: {
      anchor,
    },
  };
}

export async function showToastMessageResult(payload: ToastPayload): Promise<BridgeResult> {
  eda.sys_Message.showToastMessage(
    payload.message,
    payload.messageType as never,
    payload.timer,
    payload.bottomPanel as never,
    payload.buttonTitle,
    payload.buttonCallbackFn,
  );

  return {
    summary: 'toast message shown',
    data: {
      shown: true,
      ...payload,
    },
  };
}

export async function showFollowMouseTipResult(payload: FollowMouseTipPayload): Promise<BridgeResult> {
  await eda.sys_Message.showFollowMouseTip(payload.tip, payload.msTimeout);

  return {
    summary: 'follow-mouse tip shown',
    data: {
      shown: true,
      ...payload,
    },
  };
}

export async function removeFollowMouseTipResult(payload?: { tip?: string }): Promise<BridgeResult> {
  await eda.sys_Message.removeFollowMouseTip(payload?.tip);

  return {
    summary: 'follow-mouse tip removed',
    data: {
      removed: true,
      tip: payload?.tip,
    },
  };
}

export async function showInformationMessageResult(payload: MessageBoxPayload): Promise<BridgeResult> {
  eda.sys_Dialog.showInformationMessage(payload.content, payload.title, payload.buttonTitle);

  return {
    summary: 'information message shown',
    data: {
      shown: true,
      ...payload,
    },
  };
}

export async function showConfirmationMessageResult(payload: ConfirmationMessagePayload): Promise<BridgeResult> {
  eda.sys_Dialog.showConfirmationMessage(payload.content, payload.title, payload.mainButtonTitle, payload.buttonTitle);

  return {
    summary: 'confirmation message shown',
    data: {
      shown: true,
      ...payload,
    },
  };
}

export async function getShortcutKeysResult(payload?: ShortcutQueryPayload): Promise<BridgeResult> {
  const shortcuts = await eda.sys_ShortcutKey.getShortcutKeys(payload?.includeSystem);

  return {
    summary: 'shortcut keys collected',
    data: {
      shortcuts,
      count: shortcuts.length,
      includeSystem: Boolean(payload?.includeSystem),
    },
  };
}
