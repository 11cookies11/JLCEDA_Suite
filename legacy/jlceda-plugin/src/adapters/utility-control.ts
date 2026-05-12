import type { BridgeResult } from '../bridge/protocol';

interface FilePayload {
  fileName?: string;
  mimeType?: string;
  contentBase64?: string;
  contentText?: string;
}

export interface FileSystemSavePayload extends FilePayload {
  uri?: string;
  force?: boolean;
}

export interface FileSystemListPayload {
  folderPath: string;
  recursive?: boolean;
}

export interface FileManagerFilePayload {
  fileName?: string;
  password?: string;
  fileType?: 'epro' | 'epro2' | 'elibz' | 'elibz2';
}

export interface StorageSetPayload {
  key: string;
  value: unknown;
}

export interface SystemHeaderMenuPayload {
  headerMenus?: Record<string, unknown>;
  env?: 'home' | 'blank' | 'sch' | 'symbol' | 'pcb' | 'footprint' | 'pcbView' | 'panel' | 'panelView';
  id?: Array<string>;
  props?: Record<string, unknown>;
}

export interface ToolComparisonPayload {
  left: string | {
    projectUuid: string;
    documentUuid?: string;
    schematicUuid?: string;
    pcbUuid?: string;
  };
  right: string | {
    projectUuid: string;
    documentUuid?: string;
    schematicUuid?: string;
    pcbUuid?: string;
  };
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunkSize = 0x8000;

  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }

  return globalThis.btoa(binary);
}

function base64ToBytes(base64: string): Uint8Array {
  const binary = globalThis.atob(base64);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes;
}

async function serializeFileLike(file: File | Blob | undefined, fallbackName?: string): Promise<Record<string, unknown> | undefined> {
  if (!file) {
    return undefined;
  }

  const buffer = await file.arrayBuffer();
  const name = file instanceof File ? file.name : fallbackName;

  return {
    name,
    type: file.type,
    size: file.size,
    base64: bytesToBase64(new Uint8Array(buffer)),
  };
}

function createFileLike(payload: FilePayload): File | Blob {
  if (payload.contentBase64) {
    const bytes = base64ToBytes(payload.contentBase64);
    const binary = bytes.buffer.slice(0) as ArrayBuffer;

    if (typeof File !== 'undefined') {
      return new File([binary], payload.fileName ?? 'file.bin', {
        type: payload.mimeType ?? 'application/octet-stream',
      });
    }

    return new Blob([binary], {
      type: payload.mimeType ?? 'application/octet-stream',
    });
  }

  const text = payload.contentText ?? '';

  if (typeof File !== 'undefined') {
    return new File([text], payload.fileName ?? 'file.txt', {
      type: payload.mimeType ?? 'text/plain',
    });
  }

  return new Blob([text], {
    type: payload.mimeType ?? 'text/plain',
  });
}

function summarizeComparisonResult(result: Array<{
  type: 'Net' | 'Component';
  object: string;
  netlist1Name: Array<string>;
  netlist2Name: Array<string>;
}>): Array<Record<string, unknown>> {
  return result.map(item => ({
    type: item.type,
    object: item.object,
    netlist1Name: item.netlist1Name,
    netlist2Name: item.netlist2Name,
  }));
}

export async function getExtensionFileResult(uri: string): Promise<BridgeResult> {
  const file = await eda.sys_FileSystem.getExtensionFile(uri);

  return {
    summary: 'extension file collected',
    data: {
      uri,
      file: await serializeFileLike(file, uri.split('/').pop()),
    },
  };
}

export async function saveFileResult(payload: FileSystemSavePayload): Promise<BridgeResult> {
  const file = createFileLike(payload);
  await eda.sys_FileSystem.saveFile(file, payload.fileName);

  return {
    summary: 'file saved',
    data: {
      saved: true,
      fileName: payload.fileName,
      mimeType: file.type,
      size: file.size,
    },
  };
}

export async function saveFileToFileSystemResult(payload: FileSystemSavePayload): Promise<BridgeResult> {
  if (!payload.uri) {
    throw new Error('Missing uri for file system save.');
  }

  const file = createFileLike(payload);
  const saved = await eda.sys_FileSystem.saveFileToFileSystem(payload.uri, file, payload.fileName, payload.force);

  if (!saved) {
    throw new Error(`Failed to save file to ${payload.uri}.`);
  }

  return {
    summary: 'file system save completed',
    data: {
      saved: true,
      uri: payload.uri,
      fileName: payload.fileName,
      force: Boolean(payload.force),
    },
  };
}

export async function listFilesOfFileSystemResult(payload: FileSystemListPayload): Promise<BridgeResult> {
  const files = await eda.sys_FileSystem.listFilesOfFileSystem(payload.folderPath, payload.recursive);

  return {
    summary: 'file system files collected',
    data: {
      folderPath: payload.folderPath,
      recursive: Boolean(payload.recursive),
      files,
      count: files.length,
    },
  };
}

export async function deleteFileInFileSystemResult(payload: { uri: string; force?: boolean }): Promise<BridgeResult> {
  const deleted = await eda.sys_FileSystem.deleteFileInFileSystem(payload.uri, payload.force);

  if (!deleted) {
    throw new Error(`Failed to delete file system entry: ${payload.uri}`);
  }

  return {
    summary: 'file system entry deleted',
    data: {
      deleted: true,
      ...payload,
    },
  };
}

export async function getEdaPathResult(): Promise<BridgeResult> {
  return {
    summary: 'EDA path collected',
    data: {
      path: await eda.sys_FileSystem.getEdaPath(),
    },
  };
}

export async function getDocumentsPathResult(): Promise<BridgeResult> {
  return {
    summary: 'documents path collected',
    data: {
      path: await eda.sys_FileSystem.getDocumentsPath(),
    },
  };
}

export async function getLibrariesPathsResult(): Promise<BridgeResult> {
  return {
    summary: 'libraries paths collected',
    data: {
      paths: await eda.sys_FileSystem.getLibrariesPaths(),
    },
  };
}

export async function getProjectsPathsResult(): Promise<BridgeResult> {
  return {
    summary: 'projects paths collected',
    data: {
      paths: await eda.sys_FileSystem.getProjectsPaths(),
    },
  };
}

export async function getProjectFileResult(payload: FileManagerFilePayload): Promise<BridgeResult> {
  const file = await eda.sys_FileManager.getProjectFile(payload.fileName, payload.password, payload.fileType);

  return {
    summary: 'project file collected',
    data: {
      file: await serializeFileLike(file, payload.fileName),
    },
  };
}

export async function getDocumentFileResult(payload: FileManagerFilePayload): Promise<BridgeResult> {
  const file = await eda.sys_FileManager.getDocumentFile(payload.fileName, payload.password, payload.fileType);

  return {
    summary: 'document file collected',
    data: {
      file: await serializeFileLike(file, payload.fileName),
    },
  };
}

export async function getDocumentSourceResult(): Promise<BridgeResult> {
  return {
    summary: 'document source collected',
    data: {
      source: await eda.sys_FileManager.getDocumentSource(),
    },
  };
}

export async function getDocumentFootprintSourcesResult(): Promise<BridgeResult> {
  return {
    summary: 'document footprint sources collected',
    data: {
      sources: await eda.sys_FileManager.getDocumentFootprintSources(),
    },
  };
}

export async function setDocumentSourceResult(payload: { source: string }): Promise<BridgeResult> {
  const updated = await eda.sys_FileManager.setDocumentSource(payload.source);

  if (!updated) {
    throw new Error('Failed to update document source.');
  }

  return {
    summary: 'document source updated',
    data: {
      updated: true,
    },
  };
}

export async function getProjectFileByProjectUuidResult(payload: { projectUuid: string } & FileManagerFilePayload): Promise<BridgeResult> {
  const file = await eda.sys_FileManager.getProjectFileByProjectUuid(
    payload.projectUuid,
    payload.fileName,
    payload.password,
    payload.fileType,
  );

  return {
    summary: 'project file by uuid collected',
    data: {
      projectUuid: payload.projectUuid,
      file: await serializeFileLike(file, payload.fileName),
    },
  };
}

export async function getDeviceFileByDeviceUuidResult(payload: {
  deviceUuid: string | Array<string>;
  libraryUuid?: string;
  fileType?: 'elibz' | 'elibz2';
}): Promise<BridgeResult> {
  const file = await eda.sys_FileManager.getDeviceFileByDeviceUuid(payload.deviceUuid, payload.libraryUuid, payload.fileType);

  return {
    summary: 'device file collected',
    data: {
      ...payload,
      file: await serializeFileLike(file),
    },
  };
}

export async function getSymbolFileBySymbolUuidResult(payload: {
  symbolUuid: string | Array<string>;
  libraryUuid?: string;
  fileType?: 'elibz' | 'elibz2';
}): Promise<BridgeResult> {
  const file = await eda.sys_FileManager.getSymbolFileBySymbolUuid(payload.symbolUuid, payload.libraryUuid, payload.fileType);

  return {
    summary: 'symbol file collected',
    data: {
      ...payload,
      file: await serializeFileLike(file),
    },
  };
}

export async function getExtensionAllUserConfigsResult(): Promise<BridgeResult> {
  return {
    summary: 'extension configs collected',
    data: eda.sys_Storage.getExtensionAllUserConfigs(),
  };
}

export async function setExtensionAllUserConfigsResult(payload: { configs: Record<string, unknown> }): Promise<BridgeResult> {
  const updated = await eda.sys_Storage.setExtensionAllUserConfigs(payload.configs);

  if (!updated) {
    throw new Error('Failed to update extension configs.');
  }

  return {
    summary: 'extension configs updated',
    data: {
      updated: true,
    },
  };
}

export async function clearExtensionAllUserConfigsResult(): Promise<BridgeResult> {
  const cleared = await eda.sys_Storage.clearExtensionAllUserConfigs();

  if (!cleared) {
    throw new Error('Failed to clear extension configs.');
  }

  return {
    summary: 'extension configs cleared',
    data: {
      cleared: true,
    },
  };
}

export async function getExtensionUserConfigResult(payload: { key: string }): Promise<BridgeResult> {
  return {
    summary: 'extension user config collected',
    data: {
      key: payload.key,
      value: eda.sys_Storage.getExtensionUserConfig(payload.key),
    },
  };
}

export async function setExtensionUserConfigResult(payload: { key: string; value: unknown }): Promise<BridgeResult> {
  const updated = await eda.sys_Storage.setExtensionUserConfig(payload.key, payload.value);

  if (!updated) {
    throw new Error('Failed to set extension user config.');
  }

  return {
    summary: 'extension user config updated',
    data: {
      updated: true,
      key: payload.key,
    },
  };
}

export async function deleteExtensionUserConfigResult(payload: { key: string }): Promise<BridgeResult> {
  const deleted = await eda.sys_Storage.deleteExtensionUserConfig(payload.key);

  if (!deleted) {
    throw new Error('Failed to delete extension user config.');
  }

  return {
    summary: 'extension user config deleted',
    data: {
      deleted: true,
      key: payload.key,
    },
  };
}

export async function netlistComparisonResult(payload: ToolComparisonPayload): Promise<BridgeResult> {
  const result = await eda.sys_Tool.netlistComparison(payload.left as never, payload.right as never);

  return {
    summary: 'netlist comparison completed',
    data: {
      result: summarizeComparisonResult(result),
      count: result.length,
    },
  };
}

export async function schematicComparisonResult(payload: ToolComparisonPayload): Promise<BridgeResult> {
  const result = await eda.sys_Tool.schematicComparison(payload.left as never, payload.right as never);

  return {
    summary: 'schematic comparison completed',
    data: result,
  };
}

export async function pcbComparisonResult(payload: ToolComparisonPayload): Promise<BridgeResult> {
  const result = await eda.sys_Tool.pcbComparison(payload.left as never, payload.right as never);

  return {
    summary: 'pcb comparison completed',
    data: result,
  };
}

export async function replaceHeaderMenusResult(payload: { headerMenus: Record<string, unknown> }): Promise<BridgeResult> {
  await eda.sys_HeaderMenu.replaceHeaderMenus(payload.headerMenus as never);

  return {
    summary: 'header menus replaced',
    data: {
      replaced: true,
    },
  };
}

export async function insertHeaderMenusResult(payload: { headerMenus: Record<string, unknown> }): Promise<BridgeResult> {
  await eda.sys_HeaderMenu.insertHeaderMenus(payload.headerMenus as never);

  return {
    summary: 'header menus inserted',
    data: {
      inserted: true,
    },
  };
}

export async function removeHeaderMenusResult(): Promise<BridgeResult> {
  eda.sys_HeaderMenu.removeHeaderMenus();

  return {
    summary: 'header menus removed',
    data: {
      removed: true,
    },
  };
}

export async function insertSystemHeaderMenuItemResult(payload: SystemHeaderMenuPayload): Promise<BridgeResult> {
  if (!payload.env || !payload.id || !payload.props) {
    throw new Error('Missing env, id, or props for system header menu insertion.');
  }

  const id = await eda.sys_HeaderMenu.insertSystemHeaderMenuItem(
    payload.env as never,
    payload.id,
    payload.props as never,
  );

  return {
    summary: 'system header menu item inserted',
    data: {
      id,
    },
  };
}

export async function removeSystemHeaderMenuItemResult(payload: SystemHeaderMenuPayload): Promise<BridgeResult> {
  if (!payload.id) {
    throw new Error('Missing id for system header menu removal.');
  }

  const removed = await eda.sys_HeaderMenu.removeSystemHeaderMenuItem(payload.id);

  if (!removed) {
    throw new Error('Failed to remove system header menu item.');
  }

  return {
    summary: 'system header menu item removed',
    data: {
      removed: true,
      id: payload.id,
    },
  };
}

export async function convertAltiumDesignerLibrariesToEasyEDASingleFileResult(payload: { files: Array<FilePayload> | FilePayload }): Promise<BridgeResult> {
  const input = Array.isArray(payload.files)
    ? payload.files.map(createFileLike)
    : createFileLike(payload.files);
  const file = await eda.sys_FormatConversion.convertAltiumDesignerLibrariesToEasyEDASingleFile(input as never);

  return {
    summary: 'AD library converted to single file',
    data: {
      file: await serializeFileLike(file),
    },
  };
}

export async function convertAltiumDesignerLibrariesToEasyEDAMultiFilesResult(payload: { files: Array<FilePayload> | FilePayload }): Promise<BridgeResult> {
  const input = Array.isArray(payload.files)
    ? payload.files.map(createFileLike)
    : createFileLike(payload.files);
  const files = await eda.sys_FormatConversion.convertAltiumDesignerLibrariesToEasyEDAMultiFiles(input as never);

  return {
    summary: 'AD library converted to multiple files',
    data: {
      files: await Promise.all(files.map((file: File) => serializeFileLike(file))),
      count: files.length,
    },
  };
}

export async function convertDisaLibrariesToEasyEDASingleFileResult(payload: { files: Array<FilePayload> | FilePayload }): Promise<BridgeResult> {
  const input = Array.isArray(payload.files)
    ? payload.files.map(createFileLike)
    : createFileLike(payload.files);
  const file = await eda.sys_FormatConversion.convertDisaLibrariesToEasyEDASingleFile(input as never);

  return {
    summary: 'DISA library converted to single file',
    data: {
      file: await serializeFileLike(file),
    },
  };
}

export async function convertDisaLibrariesToEasyEDAMultiFilesResult(payload: { files: Array<FilePayload> | FilePayload }): Promise<BridgeResult> {
  const input = Array.isArray(payload.files)
    ? payload.files.map(createFileLike)
    : createFileLike(payload.files);
  const files = await eda.sys_FormatConversion.convertDisaLibrariesToEasyEDAMultiFiles(input as never);

  return {
    summary: 'DISA library converted to multiple files',
    data: {
      files: await Promise.all(files.map((file: File) => serializeFileLike(file))),
      count: files.length,
    },
  };
}
