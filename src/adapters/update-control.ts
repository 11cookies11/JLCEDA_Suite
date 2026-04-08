import type { BridgeResult } from '../bridge/protocol';
import * as extensionConfig from '../../extension.json';

export interface UpdateStatusSnapshot {
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

const RELEASES_LATEST_URL = 'https://api.github.com/repos/11cookies11/JLCEDA_AIAgent/releases/latest';

let updateStatus: UpdateStatusSnapshot = {
  currentVersion: extensionConfig.version,
  updateAvailable: false,
};

let updateRequest: Promise<UpdateStatusSnapshot> | undefined;

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
    `当前版本：${status.currentVersion}`,
    `最新版本：${latestVersion}`,
    `更新状态：${state}`,
    `检查时间：${checkedAt}`,
    `发布页：${status.latestReleaseUrl ?? '暂无'}`,
    `下载包：${status.latestDownloadUrl ?? '暂无'}`,
    `最近错误：${status.lastError ?? '无'}`,
  ];
}

async function fetchLatestRelease(): Promise<GitHubRelease> {
  if (typeof fetch !== 'function') {
    throw new TypeError('Fetch API is not available.');
  }

  const response = await fetch(RELEASES_LATEST_URL, {
    headers: {
      'accept': 'application/vnd.github+json',
      'user-agent': 'JLCEDA-AIAgent',
    },
  });

  if (!response.ok) {
    throw new Error(`GitHub release lookup failed: ${response.status} ${response.statusText}`);
  }

  return await response.json() as GitHubRelease;
}

export function getUpdateStatusSnapshot(): UpdateStatusSnapshot {
  return snapshotUpdateStatus();
}

export function getUpdateStatusLines(): Array<string> {
  return describeUpdateStatus(snapshotUpdateStatus());
}

export async function refreshUpdateStatus(force = false): Promise<UpdateStatusSnapshot> {
  if (!force && updateRequest) {
    return await updateRequest;
  }

  if (!force && updateStatus.checkedAt && !updateStatus.lastError) {
    return snapshotUpdateStatus();
  }

  updateRequest = (async () => {
    try {
      const release = await fetchLatestRelease();
      const latestVersion = release.tag_name?.trim() || undefined;
      const latestReleaseUrl = release.html_url?.trim() || undefined;
      const latestDownloadUrl = getLatestAssetUrl(release);
      const updateAvailable = compareVersionLabels(latestVersion, updateStatus.currentVersion) > 0;

      updateStatus = {
        currentVersion: extensionConfig.version,
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

export async function checkForUpdatesResult(force = true): Promise<BridgeResult> {
  const status = await refreshUpdateStatus(force);

  return {
    summary: status.updateAvailable ? 'update available' : 'plugin is up to date',
    data: status,
  };
}
