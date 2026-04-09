import type { BridgeResult } from '../bridge/protocol';

export interface ExportBomPayload {
  format?: 'json' | 'csv';
  fileName?: string;
  saveToLocal?: boolean;
}

function normalizeBomFileType(format?: 'json' | 'csv'): 'xlsx' | 'csv' {
  return format === 'csv' ? 'csv' : 'xlsx';
}

export async function exportProjectBom(payload: ExportBomPayload): Promise<BridgeResult> {
  const fileType = normalizeBomFileType(payload.format);
  const defaultName = payload.fileName ?? `JLCEDA_Suite_BOM.${fileType}`;
  const bomFile = await eda.sch_ManufactureData.getBomFile(defaultName, fileType);

  if (!bomFile) {
    throw new Error('JLCEDA did not return a BOM file.');
  }

  if (payload.saveToLocal) {
    await eda.sys_FileSystem.saveFile(bomFile, bomFile.name || defaultName);
  }

  return {
    summary: payload.saveToLocal ? 'bom exported and save dialog opened' : 'bom file generated',
    data: {
      name: bomFile.name,
      type: bomFile.type,
      size: bomFile.size,
      savedToLocal: Boolean(payload.saveToLocal),
      format: fileType,
    },
    artifacts: [
      {
        kind: 'file',
        ref: bomFile.name || defaultName,
      },
    ],
  };
}
