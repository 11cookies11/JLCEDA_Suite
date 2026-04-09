import {
  CONFIG_KEY_AUTH_TOKEN,
  CONFIG_KEY_CONTROL_TOKEN,
  CONFIG_KEY_CONTROL_URL,
  CONFIG_KEY_SERVER_URL,
  deriveControlUrl,
  readStringConfig,
} from './bridge-config';

export interface RuleProfileSnapshot {
  name: string;
  description: string;
  schematic: {
    componentClearance: number;
    wireClearance: number;
    placementComponentClearance: number;
    placementWireClearance: number;
    labelPlacementStepFloor: number;
    labelGapMin: number;
    labelGapMax: number;
    labelClearance: number;
    wireLabelClearance: number;
    powerSpacing: number;
  };
  pcb: {
    componentClearance: number;
    trackClearance: number;
    labelHorizontalOffsetBase: number;
    labelHorizontalOffsetMax: number;
    labelVerticalOffsetBase: number;
    labelVerticalOffsetMax: number;
    labelClearance: number;
    boardEdgeClearance: number;
  };
}

export interface RuleProfileResponse {
  activeProfile?: string;
  profile?: RuleProfileSnapshot;
}

const DEFAULT_PROFILE: RuleProfileSnapshot = {
  name: 'default',
  description: 'Balanced defaults for general schematic-first development.',
  schematic: {
    componentClearance: 80,
    wireClearance: 48,
    placementComponentClearance: 48,
    placementWireClearance: 40,
    labelPlacementStepFloor: 64,
    labelGapMin: 24,
    labelGapMax: 56,
    labelClearance: 110,
    wireLabelClearance: 72,
    powerSpacing: 160,
  },
  pcb: {
    componentClearance: 120,
    trackClearance: 70,
    labelHorizontalOffsetBase: 28,
    labelHorizontalOffsetMax: 64,
    labelVerticalOffsetBase: 20,
    labelVerticalOffsetMax: 48,
    labelClearance: 90,
    boardEdgeClearance: 60,
  },
};

interface RuleProfileCache {
  cacheKey: string;
  loadedAt: number;
  profile: RuleProfileSnapshot;
}

const RULE_PROFILE_TTL_MS = 15_000;
let cachedProfile: RuleProfileCache | undefined;

function getFetchApi(): typeof fetch {
  if (typeof fetch !== 'function') {
    throw new TypeError('Fetch API is not available.');
  }

  return fetch;
}

function normalizeControlUrl(controlUrl: string): string {
  return controlUrl.trim().replace(/\/$/, '');
}

function buildCacheKey(serverUrl: string, controlUrl: string, token: string): string {
  return [serverUrl.trim(), controlUrl.trim(), token.trim()].join('|');
}

function getStoredRuleProfileConfig(): {
  serverUrl: string;
  controlUrl: string;
  token: string;
} {
  const serverUrl = readStringConfig(eda.sys_Storage.getExtensionUserConfig(CONFIG_KEY_SERVER_URL));
  const explicitControlUrl = readStringConfig(eda.sys_Storage.getExtensionUserConfig(CONFIG_KEY_CONTROL_URL));
  const controlUrl = explicitControlUrl || deriveControlUrl(serverUrl);
  const token = readStringConfig(eda.sys_Storage.getExtensionUserConfig(CONFIG_KEY_CONTROL_TOKEN))
    || readStringConfig(eda.sys_Storage.getExtensionUserConfig(CONFIG_KEY_AUTH_TOKEN));

  return {
    serverUrl,
    controlUrl,
    token,
  };
}

async function fetchRuleProfile(controlUrl: string, token: string): Promise<RuleProfileSnapshot | undefined> {
  if (!controlUrl) {
    return undefined;
  }

  const response = await getFetchApi()(`${normalizeControlUrl(controlUrl)}/profile`, {
    headers: {
      ...(token ? { 'x-bridge-control-token': token } : {}),
    },
  });

  if (!response.ok) {
    return undefined;
  }

  const payload = await response.json() as RuleProfileResponse;
  return payload.profile;
}

export function getDefaultRuleProfileSnapshot(): RuleProfileSnapshot {
  return DEFAULT_PROFILE;
}

export async function refreshRuleProfileSnapshot(force = false): Promise<RuleProfileSnapshot> {
  const { serverUrl, controlUrl, token } = getStoredRuleProfileConfig();
  const cacheKey = buildCacheKey(serverUrl, controlUrl, token);

  if (!force && cachedProfile && cachedProfile.cacheKey === cacheKey && (Date.now() - cachedProfile.loadedAt) < RULE_PROFILE_TTL_MS) {
    return cachedProfile.profile;
  }

  try {
    const profile = await fetchRuleProfile(controlUrl, token);
    const resolvedProfile = profile ?? DEFAULT_PROFILE;

    cachedProfile = {
      cacheKey,
      loadedAt: Date.now(),
      profile: resolvedProfile,
    };

    return resolvedProfile;
  }
  catch {
    cachedProfile = {
      cacheKey,
      loadedAt: Date.now(),
      profile: DEFAULT_PROFILE,
    };
    return DEFAULT_PROFILE;
  }
}

export async function getRuleProfileSnapshot(force = false): Promise<RuleProfileSnapshot> {
  return await refreshRuleProfileSnapshot(force);
}
