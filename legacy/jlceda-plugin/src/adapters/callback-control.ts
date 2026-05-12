import type { BridgeResult } from '../bridge/protocol';

type ShortcutKey = Array<
  'SHIFT' | 'LEFT_SHIFT' | 'RIGHT_SHIFT' | 'FN' | 'ALT' | 'LEFT_ALT' | 'RIGHT_ALT' | 'CONTROL' | 'LEFT_CONTROL'
  | 'RIGHT_CONTROL' | 'COMMAND' | 'WIN' | 'OPTION' | 'SUPER' | 'TAB' | 'SPACE' | 'UP' | 'DOWN' | 'LEFT' | 'RIGHT'
  | 'F1' | 'F2' | 'F3' | 'F4' | 'F5' | 'F6' | 'F7' | 'F8' | 'F9' | 'F10' | 'F11' | 'F12' | 'F13' | 'F14' | 'F15'
  | 'F16' | 'F17' | 'F18' | 'F19' | 'F20' | '`' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9' | '0' | '-'
  | '=' | 'Q' | 'W' | 'E' | 'R' | 'T' | 'Y' | 'U' | 'I' | 'O' | 'P' | '[' | ']' | 'A' | 'S' | 'D' | 'F' | 'G' | 'H'
  | 'J' | 'K' | 'L' | ';' | "'" | '\\' | 'Z' | 'X' | 'C' | 'V' | 'B' | 'N' | 'M' | ',' | '.' | '/'
>;

interface CallbackEvent {
  id: string;
  kind: 'shortcut' | 'timer';
  name: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

interface ShortcutRegistrationPayload {
  shortcutKey: ShortcutKey;
  title: string;
  documentType?: Array<number>;
  scene?: Array<number>;
}

interface TimerRegistrationPayload {
  id: string;
  timeout: number;
}

interface RightClickMenuPayload {
  menuId: string;
  menuItems: Array<Record<string, unknown> | null>;
}

const callbackEvents: Array<CallbackEvent> = [];

function recordCallbackEvent(event: Omit<CallbackEvent, 'timestamp'>): void {
  callbackEvents.push({
    ...event,
    timestamp: new Date().toISOString(),
  });
}

export async function drainCallbackEventsResult(): Promise<BridgeResult> {
  const events = callbackEvents.splice(0, callbackEvents.length);

  return {
    summary: 'callback events drained',
    data: {
      events,
      count: events.length,
    },
  };
}

export async function listCallbackEventsResult(): Promise<BridgeResult> {
  return {
    summary: 'callback events listed',
    data: {
      events: callbackEvents,
      count: callbackEvents.length,
    },
  };
}

export async function registerShortcutKeyResult(payload: ShortcutRegistrationPayload): Promise<BridgeResult> {
  const registered = await eda.sys_ShortcutKey.registerShortcutKey(
    payload.shortcutKey as never,
    payload.title,
    async (shortcutKey: ShortcutKey) => {
      recordCallbackEvent({
        id: payload.title,
        kind: 'shortcut',
        name: 'shortcut.registered',
        payload: {
          shortcutKey,
          title: payload.title,
          documentType: payload.documentType ?? [],
          scene: payload.scene ?? [],
        },
      });
    },
    payload.documentType as never,
    payload.scene as never,
  );

  if (!registered) {
    throw new Error(`Failed to register shortcut: ${payload.title}`);
  }

  return {
    summary: 'shortcut registered',
    data: {
      registered: true,
      ...payload,
    },
  };
}

export async function unregisterShortcutKeyResult(payload: { shortcutKey: ShortcutKey }): Promise<BridgeResult> {
  const unregistered = await eda.sys_ShortcutKey.unregisterShortcutKey(payload.shortcutKey as never);

  if (!unregistered) {
    throw new Error('Failed to unregister shortcut key.');
  }

  return {
    summary: 'shortcut unregistered',
    data: {
      unregistered: true,
      shortcutKey: payload.shortcutKey,
    },
  };
}

export async function listShortcutKeysResult(payload?: { includeSystem?: boolean }): Promise<BridgeResult> {
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

export async function setIntervalTimerResult(payload: TimerRegistrationPayload): Promise<BridgeResult> {
  const registered = eda.sys_Timer.setIntervalTimer(
    payload.id,
    payload.timeout,
    () => {
      recordCallbackEvent({
        id: payload.id,
        kind: 'timer',
        name: 'timer.interval',
        payload: {
          id: payload.id,
          timeout: payload.timeout,
        },
      });
    },
  );

  if (!registered) {
    throw new Error(`Failed to set interval timer: ${payload.id}`);
  }

  return {
    summary: 'interval timer set',
    data: {
      registered: true,
      ...payload,
    },
  };
}

export async function clearIntervalTimerResult(payload: { id: string }): Promise<BridgeResult> {
  const cleared = eda.sys_Timer.clearIntervalTimer(payload.id);

  if (!cleared) {
    throw new Error(`Failed to clear interval timer: ${payload.id}`);
  }

  return {
    summary: 'interval timer cleared',
    data: {
      cleared: true,
      id: payload.id,
    },
  };
}

export async function setTimeoutTimerResult(payload: TimerRegistrationPayload): Promise<BridgeResult> {
  const registered = eda.sys_Timer.setTimeoutTimer(
    payload.id,
    payload.timeout,
    () => {
      recordCallbackEvent({
        id: payload.id,
        kind: 'timer',
        name: 'timer.timeout',
        payload: {
          id: payload.id,
          timeout: payload.timeout,
        },
      });
    },
  );

  if (!registered) {
    throw new Error(`Failed to set timeout timer: ${payload.id}`);
  }

  return {
    summary: 'timeout timer set',
    data: {
      registered: true,
      ...payload,
    },
  };
}

export async function clearTimeoutTimerResult(payload: { id: string }): Promise<BridgeResult> {
  const cleared = eda.sys_Timer.clearTimeoutTimer(payload.id);

  if (!cleared) {
    throw new Error(`Failed to clear timeout timer: ${payload.id}`);
  }

  return {
    summary: 'timeout timer cleared',
    data: {
      cleared: true,
      id: payload.id,
    },
  };
}

export async function changeRightClickMenuResult(payload: RightClickMenuPayload): Promise<BridgeResult> {
  await eda.sys_RightClickMenu.changeMenu(payload.menuId, payload.menuItems as never);

  return {
    summary: 'right click menu updated',
    data: {
      updated: true,
      ...payload,
    },
  };
}
