import process from 'node:process';

interface LibraryTarget {
  label?: string;
  libraryUuid: string;
  symbolUuid: string;
  libraryType?: 'symbol' | 'footprint';
}

interface SourceRecord {
  header: { type?: string; [key: string]: unknown };
  body: { [key: string]: unknown };
}

interface PinInfo {
  number: string;
  name?: string;
  x: number;
  y: number;
  rotation: number;
  length: number;
}

function env(name: string, fallback = ''): string {
  const value = process.env[name];
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

function parseJson<T>(name: string, fallback: T): T {
  const raw = env(name);
  return raw ? JSON.parse(raw) as T : fallback;
}

function parseSourceRecord(line: string): SourceRecord | undefined {
  const separatorIndex = line.indexOf('||');
  if (separatorIndex < 0) {
    return undefined;
  }

  const headerText = line.slice(0, separatorIndex);
  let bodyText = line.slice(separatorIndex + 2);
  if (bodyText.endsWith('|')) {
    bodyText = bodyText.slice(0, -1);
  }

  try {
    return {
      header: JSON.parse(headerText) as SourceRecord['header'],
      body: JSON.parse(bodyText) as SourceRecord['body'],
    };
  }
  catch {
    return undefined;
  }
}

async function getJson<T>(url: string, token?: string): Promise<T> {
  const response = await fetch(url, {
    headers: token ? { 'x-bridge-control-token': token } : undefined,
  });
  if (!response.ok) {
    throw new Error(`Control query failed: ${response.status} ${response.statusText}`);
  }
  return await response.json() as T;
}

async function postJson<T>(url: string, body: unknown, token?: string): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(token ? { 'x-bridge-control-token': token } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Control request failed: ${response.status} ${response.statusText}`);
  }
  return await response.json() as T;
}

function extractPins(source: string): Array<PinInfo> {
  const pins: Array<PinInfo> = [];

  for (const line of source.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    const record = parseSourceRecord(trimmed);
    if (!record || record.header.type !== 'PIN') {
      continue;
    }

    const body = record.body;
    const pinNumber = String(body.pinNumber ?? body.pinNo ?? body.number ?? pins.length + 1);
    const pinName = typeof body.pinName === 'string'
      ? body.pinName
      : typeof body.name === 'string'
        ? body.name
        : undefined;
    const x = typeof body.x === 'number' ? body.x : typeof body.centerX === 'number' ? body.centerX : 0;
    const y = typeof body.y === 'number' ? body.y : typeof body.centerY === 'number' ? body.centerY : 0;
    const rotation = typeof body.rotation === 'number' ? body.rotation : 0;
    const length = typeof body.length === 'number'
      ? body.length
      : typeof body.pinLength === 'number'
        ? body.pinLength
        : 0;

    pins.push({ number: pinNumber, name: pinName, x, y, rotation, length });
  }

  return pins;
}

async function run(): Promise<void> {
  const controlUrl = env('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788');
  const controlToken = env('BRIDGE_CONTROL_TOKEN');
  const targets = parseJson<Array<LibraryTarget>>('BRIDGE_LIBRARY_TARGETS_JSON', []);

  if (!targets.length) {
    throw new Error('BRIDGE_LIBRARY_TARGETS_JSON is required.');
  }

  const sessionsPayload = await getJson<{ sessions: Array<{ clientId: string }> }>(`${controlUrl}/sessions`, controlToken);
  const clientId = env('BRIDGE_TARGET_CLIENT_ID') || sessionsPayload.sessions[0]?.clientId;
  if (!clientId) {
    throw new Error('No bridge clientId available.');
  }

  const results: Array<Record<string, unknown>> = [];

  for (const target of targets) {
    const openResponse = await postJson<{ response: { status: string; result?: { data?: { tabId?: string } } } }>(
      `${controlUrl}/request`,
      {
        clientId,
        request: {
          id: `open-${target.symbolUuid}`,
          type: 'command.request',
          protocolVersion: '0.1.0',
          sessionId: 'library-pin-inspector',
          command: {
            domain: 'project',
            action: 'open_library_document',
            requiresConfirmation: false,
            payload: {
              libraryUuid: target.libraryUuid,
              libraryType: target.libraryType ?? 'symbol',
              uuid: target.symbolUuid,
            },
          },
        },
      },
      controlToken,
    );

    const tabId = openResponse.response.result?.data?.tabId;
    if (!tabId) {
      throw new Error(`Failed to open library document for ${target.symbolUuid}.`);
    }

    const sourceResponse = await postJson<{ response: { status: string; result?: { data?: { result?: string } } } }>(
      `${controlUrl}/request`,
      {
        clientId,
        request: {
          id: `source-${target.symbolUuid}`,
          type: 'command.request',
          protocolVersion: '0.1.0',
          sessionId: 'library-pin-inspector',
          command: {
            domain: 'system',
            action: 'api_invoke',
            requiresConfirmation: false,
            payload: {
              path: 'sys_FileManager.getDocumentSource',
              args: [],
            },
          },
        },
      },
      controlToken,
    );

    const source = sourceResponse.response.result?.data?.result ?? '';
    const pins = extractPins(source);

    results.push({
      label: target.label ?? target.symbolUuid,
      libraryUuid: target.libraryUuid,
      symbolUuid: target.symbolUuid,
      tabId,
      pinCount: pins.length,
      pins,
    });
  }

  console.log(JSON.stringify({
    clientId,
    results,
  }, null, 2));
}

run().catch((error) => {
  console.error('Library pin inspector failed.');
  console.error(error);
  process.exitCode = 1;
});
