import type { BridgeResult } from '../bridge/protocol';
import * as extensionConfig from '../../extension.json';

export interface UpdateCheckConfigSnapshot {
  repoOwner: string;
  repoName: string;
  githubTokenConfigured: boolean;
}

export interface UpdateStatusSnapshot extends UpdateCheckConfigSnapshot {
  currentVersion: string;
  latestVersion?: string;
  latestReleaseUrl?: string;
  latestDownloadUrl?: string;
  updateAvailable: boolean;
  checkedAt?: string;
  lastError?: string;
}

interface GitHubReleaseAsset {
  name?: string;
  browser_download_url?: string;
}

interface GitHubRelease {
  tag_name?: string;
  html_url?: string;
  assets?: Array<GitHubReleaseAsset>;
}

interface UpdateCheckSettings {
  repoOwner: string;
  repoName: string;
  githubToken?: string;
}

const DEFAULT_REPO_OWNER = '11cookies11';
const DEFAULT_REPO_NAME = 'JLCEDA_Suite';
const UPDATE_CHECK_REPO_OWNER_KEY = 'updateCheck.repoOwner';
const UPDATE_CHECK_REPO_NAME_KEY = 'updateCheck.repoName';
const UPDATE_CHECK_GITHUB_TOKEN_KEY = 'updateCheck.githubToken';

let updateSettingsLoaded = false;
let updateSettings: UpdateCheckSettings = {
  repoOwner: DEFAULT_REPO_OWNER,
  repoName: DEFAULT_REPO_NAME,
};

let updateStatus: UpdateStatusSnapshot = {
  currentVersion: extensionConfig.version,
  repoOwner: DEFAULT_REPO_OWNER,
  repoName: DEFAULT_REPO_NAME,
  githubTokenConfigured: false,
  updateAvailable: false,
};

let updateRequest: Promise<UpdateStatusSnapshot> | undefined;

function readStringConfig(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function snapshotUpdateConfig(): UpdateCheckConfigSnapshot {
  return {
    repoOwner: updateSettings.repoOwner,
    repoName: updateSettings.repoName,
    githubTokenConfigured: Boolean(updateSettings.githubToken),
  };
}

function snapshotUpdateStatus(): UpdateStatusSnapshot {
  return {
    ...updateStatus,
  };
}

function normalizeVersion(version: string | undefined): Array<number> {
  if (!version) {
    return [];
  }

  const segments = version.replace(/^v/i, '').split('.').map(segment => Number.parseInt(segment, 10));

  return segments.map(segment => Number.isFinite(segment) ? segment : 0);
}

function compareVersionLabels(left: string | undefined, right: string | undefined): number {
  const leftSegments = normalizeVersion(left);
  const rightSegments = normalizeVersion(right);
  const maxLength = Math.max(leftSegments.length, rightSegments.length, 3);

  for (let index = 0; index < maxLength; index += 1) {
    const difference = (leftSegments[index] ?? 0) - (rightSegments[index] ?? 0);
    if (difference !== 0) {
      return difference;
    }
  }

  return 0;
}

function getLatestAssetUrl(release: GitHubRelease): string | undefined {
  const asset = release.assets?.find(entry => typeof entry.browser_download_url === 'string' && /\.eext$/i.test(entry.name ?? ''));

  return asset?.browser_download_url;
}

function describeUpdateStatus(status: UpdateStatusSnapshot): Array<string> {
  const latestVersion = status.latestVersion ?? '暂无';
  const checkedAt = status.checkedAt ?? '未检查';
  const state = status.lastError
    ? '检查失败'
    : status.updateAvailable
      ? '可更新'
      : status.latestVersion
        ? '已是最新'
        : '未检查';

  return [
    `仓库：${status.repoOwner}/${status.repoName}`,
    `当前版本：${status.currentVersion}`,
    `最新版本：${latestVersion}`,
    `更新状态：${state}`,
    `检查时间：${checkedAt}`,
    `发布页：${status.latestReleaseUrl ?? '暂无'}`,
    `下载包：${status.latestDownloadUrl ?? '暂无'}`,
    `GitHub Token：${status.githubTokenConfigured ? '已配置' : '未配置'}`,
    `最近错误：${status.lastError ?? '无'}`,
  ];
}

function buildLatestReleaseUrl(settings: UpdateCheckSettings): string {
  return `https://api.github.com/repos/${encodeURIComponent(settings.repoOwner)}/${encodeURIComponent(settings.repoName)}/releases/latest`;
}

function getGitHubRequestHeaders(settings: UpdateCheckSettings): Record<string, string> {
  return {
    'accept': 'application/vnd.github+json',
    'user-agent': 'JLCEDA-Suite',
    ...(settings.githubToken ? { authorization: `Bearer ${settings.githubToken}` } : {}),
    'x-github-api-version': '2022-11-28',
  };
}

async function fetchLatestReleaseViaFetch(settings: UpdateCheckSettings): Promise<GitHubRelease> {
  const response = await fetch(buildLatestReleaseUrl(settings), {
    headers: getGitHubRequestHeaders(settings),
  });

  if (!response.ok) {
    throw new Error(`GitHub release lookup failed: ${response.status} ${response.statusText}`);
  }

  return await response.json() as GitHubRelease;
}

async function fetchLatestReleaseViaXmlHttpRequest(settings: UpdateCheckSettings): Promise<GitHubRelease> {
  const XmlHttpRequestCtor = (globalThis as {
    XMLHttpRequest?: new () => {
      open: (method: string, url: string, async?: boolean) => void;
      setRequestHeader: (name: string, value: string) => void;
      send: () => void;
      readyState: number;
      status: number;
      statusText: string;
      responseText: string;
      onreadystatechange: (() => void) | null;
      onerror: (() => void) | null;
    };
  }).XMLHttpRequest;

  if (typeof XmlHttpRequestCtor !== 'function') {
    throw new TypeError('Neither fetch nor XMLHttpRequest is available.');
  }

  return await new Promise<GitHubRelease>((resolve, reject) => {
    const request = new XmlHttpRequestCtor();

    request.open('GET', buildLatestReleaseUrl(settings), true);

    for (const [key, value] of Object.entries(getGitHubRequestHeaders(settings))) {
      request.setRequestHeader(key, value);
    }

    request.onreadystatechange = () => {
      if (request.readyState !== 4) {
        return;
      }

      if (request.status < 200 || request.status >= 300) {
        reject(new Error(`GitHub release lookup failed: ${request.status} ${request.statusText || 'request failed'}`));
        return;
      }

      try {
        resolve(JSON.parse(request.responseText) as GitHubRelease);
      }
      catch {
        reject(new Error('GitHub release lookup returned invalid JSON.'));
      }
    };

    request.onerror = () => {
      reject(new Error('GitHub release lookup failed: network error.'));
    };

    request.send();
  });
}

async function fetchLatestRelease(settings: UpdateCheckSettings): Promise<GitHubRelease> {
  if (typeof fetch === 'function') {
    return await fetchLatestReleaseViaFetch(settings);
  }

  return await fetchLatestReleaseViaXmlHttpRequest(settings);
}

async function loadUpdateSettingsFromStorage(): Promise<UpdateCheckSettings> {
  if (updateSettingsLoaded) {
    return updateSettings;
  }

  const repoOwner = readStringConfig(eda.sys_Storage.getExtensionUserConfig(UPDATE_CHECK_REPO_OWNER_KEY)) ?? DEFAULT_REPO_OWNER;
  const repoName = readStringConfig(eda.sys_Storage.getExtensionUserConfig(UPDATE_CHECK_REPO_NAME_KEY)) ?? DEFAULT_REPO_NAME;
  const githubToken = readStringConfig(eda.sys_Storage.getExtensionUserConfig(UPDATE_CHECK_GITHUB_TOKEN_KEY));

  updateSettings = {
    repoOwner,
    repoName,
    githubToken,
  };
  updateSettingsLoaded = true;

  return updateSettings;
}

async function persistUpdateSettings(nextSettings: UpdateCheckSettings): Promise<void> {
  const repoOwner = nextSettings.repoOwner.trim() || DEFAULT_REPO_OWNER;
  const repoName = nextSettings.repoName.trim() || DEFAULT_REPO_NAME;

  await eda.sys_Storage.setExtensionUserConfig(UPDATE_CHECK_REPO_OWNER_KEY, repoOwner);
  await eda.sys_Storage.setExtensionUserConfig(UPDATE_CHECK_REPO_NAME_KEY, repoName);

  if (nextSettings.githubToken) {
    await eda.sys_Storage.setExtensionUserConfig(UPDATE_CHECK_GITHUB_TOKEN_KEY, nextSettings.githubToken);
  }
  else {
    await eda.sys_Storage.deleteExtensionUserConfig(UPDATE_CHECK_GITHUB_TOKEN_KEY);
  }

  updateSettings = {
    repoOwner,
    repoName,
    githubToken: nextSettings.githubToken,
  };
  updateSettingsLoaded = true;
}

export function getUpdateConfigSnapshot(): UpdateCheckConfigSnapshot {
  return snapshotUpdateConfig();
}

export function getUpdateStatusSnapshot(): UpdateStatusSnapshot {
  return snapshotUpdateStatus();
}

export function getUpdateStatusLines(): Array<string> {
  return describeUpdateStatus(snapshotUpdateStatus());
}

async function ensureLoaded(): Promise<UpdateCheckSettings> {
  return await loadUpdateSettingsFromStorage();
}

function isUpdateStatusFresh(settings: UpdateCheckSettings): boolean {
  return Boolean(
    updateStatus.checkedAt
    && !updateStatus.lastError
    && updateStatus.repoOwner === settings.repoOwner
    && updateStatus.repoName === settings.repoName
    && updateStatus.githubTokenConfigured === Boolean(settings.githubToken),
  );
}

export async function refreshUpdateStatus(force = false): Promise<UpdateStatusSnapshot> {
  const settings = await ensureLoaded();

  if (!force && updateRequest) {
    return await updateRequest;
  }

  if (!force && isUpdateStatusFresh(settings)) {
    return snapshotUpdateStatus();
  }

  updateRequest = (async () => {
    try {
      const release = await fetchLatestRelease(settings);
      const latestVersion = release.tag_name?.trim() || undefined;
      const latestReleaseUrl = release.html_url?.trim() || undefined;
      const latestDownloadUrl = getLatestAssetUrl(release);
      const updateAvailable = compareVersionLabels(latestVersion, updateStatus.currentVersion) > 0;

      updateStatus = {
        currentVersion: extensionConfig.version,
        repoOwner: settings.repoOwner,
        repoName: settings.repoName,
        githubTokenConfigured: Boolean(settings.githubToken),
        latestVersion,
        latestReleaseUrl,
        latestDownloadUrl,
        updateAvailable,
        checkedAt: new Date().toISOString(),
        lastError: undefined,
      };
    }
    catch (error) {
      updateStatus = {
        ...updateStatus,
        currentVersion: extensionConfig.version,
        repoOwner: settings.repoOwner,
        repoName: settings.repoName,
        githubTokenConfigured: Boolean(settings.githubToken),
        updateAvailable: false,
        checkedAt: new Date().toISOString(),
        lastError: error instanceof Error ? error.message : 'Unknown update check failure.',
      };
    }
    finally {
      updateRequest = undefined;
    }

    return snapshotUpdateStatus();
  })();

  return await updateRequest;
}

export async function getUpdateStatusResult(): Promise<BridgeResult> {
  return {
    summary: 'update status collected',
    data: getUpdateStatusSnapshot(),
  };
}

export async function getUpdateConfigResult(): Promise<BridgeResult> {
  await ensureLoaded();

  return {
    summary: 'update config collected',
    data: getUpdateConfigSnapshot(),
  };
}

export async function saveUpdateConfigResult(payload: {
  repoOwner?: string;
  repoName?: string;
  githubToken?: string;
}): Promise<BridgeResult> {
  const currentSettings = await ensureLoaded();
  const nextSettings: UpdateCheckSettings = {
    repoOwner: readStringConfig(payload.repoOwner) ?? DEFAULT_REPO_OWNER,
    repoName: readStringConfig(payload.repoName) ?? DEFAULT_REPO_NAME,
    githubToken: readStringConfig(payload.githubToken) ?? currentSettings.githubToken,
  };

  await persistUpdateSettings(nextSettings);

  updateStatus = {
    currentVersion: extensionConfig.version,
    ...snapshotUpdateConfig(),
    updateAvailable: false,
    checkedAt: undefined,
    lastError: undefined,
  };

  return {
    summary: 'update config saved',
    data: {
      ...getUpdateConfigSnapshot(),
      currentVersion: extensionConfig.version,
    },
  };
}

export async function checkForUpdatesResult(force = true): Promise<BridgeResult> {
  const status = await refreshUpdateStatus(force);

  return {
    summary: status.updateAvailable ? 'update available' : 'plugin is up to date',
    data: status,
  };
}
