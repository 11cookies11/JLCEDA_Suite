import type { BridgeResult } from '../bridge/protocol';

export interface ApiInvokePayload {
  path: string;
  args?: Array<unknown>;
}

interface ResolvedApiTarget {
  receiver: unknown;
  key: string;
  value: unknown;
}

function getEdaRoot(): unknown {
  if (typeof eda !== 'undefined') {
    return eda;
  }

  return (globalThis as { eda?: unknown }).eda;
}

function resolvePath(path: string): ResolvedApiTarget {
  const segments = path
    .split('.')
    .map(segment => segment.trim())
    .filter(Boolean);

  if (!segments.length) {
    throw new Error('Missing API path.');
  }

  if (segments[0] === 'eda') {
    segments.shift();
  }

  const root = getEdaRoot();

  if (!root || typeof root !== 'object') {
    throw new Error('EDA runtime is not available.');
  }

  let receiver: unknown = root;
  let current: unknown = root;

  for (const segment of segments) {
    if (current === undefined || current === null) {
      return {
        receiver,
        key: segments[segments.length - 1],
        value: undefined,
      };
    }

    receiver = current;
    current = (current as Record<string, unknown>)[segment];
  }

  return {
    receiver,
    key: segments[segments.length - 1],
    value: current,
  };
}

function summarizeValue(value: unknown): unknown {
  if (value === undefined || value === null) {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map(item => summarizeValue(item));
  }

  if (typeof value === 'function') {
    return '[Function]';
  }

  if (typeof value === 'object') {
    if (value instanceof Blob) {
      return {
        kind: 'Blob',
        size: value.size,
        type: value.type,
      };
    }

    if (typeof File !== 'undefined' && value instanceof File) {
      return {
        kind: 'File',
        name: value.name,
        size: value.size,
        type: value.type,
      };
    }

    const entries = Object.entries(value as Record<string, unknown>);
    return Object.fromEntries(entries.map(([key, entry]) => [key, summarizeValue(entry)]));
  }

  return value;
}

export async function invokeEdaApiResult(payload: ApiInvokePayload): Promise<BridgeResult> {
  const resolved = resolvePath(payload.path);

  if (typeof resolved.value === 'function') {
    const result = await Reflect.apply(
      resolved.value as (...args: Array<unknown>) => unknown,
      resolved.receiver,
      payload.args ?? [],
    );

    return {
      summary: 'EDA API invoked',
      data: {
        path: payload.path,
        invoked: true,
        args: payload.args ?? [],
        result: summarizeValue(result),
      },
    };
  }

  return {
    summary: 'EDA API property collected',
    data: {
      path: payload.path,
      invoked: false,
      value: summarizeValue(resolved.value),
    },
  };
}
