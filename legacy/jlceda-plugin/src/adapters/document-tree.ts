import type { BridgeResult } from '../bridge/protocol';

type MaybeRecord = Record<string, unknown>;

function summarizeWorkspace(item: { uuid: string; name: string }): MaybeRecord {
  return {
    uuid: item.uuid,
    name: item.name,
  };
}

function summarizeTeam(item: { uuid: string; name: string; identity: number }): MaybeRecord {
  return {
    uuid: item.uuid,
    name: item.name,
    identity: item.identity,
  };
}

function summarizeProjectBrief(item: {
  uuid: string;
  friendlyName: string;
  teamUuid: string;
  folderUuid?: string;
}): MaybeRecord {
  return {
    uuid: item.uuid,
    friendlyName: item.friendlyName,
    teamUuid: item.teamUuid,
    folderUuid: item.folderUuid,
  };
}

function summarizePcb(item: {
  uuid: string;
  name: string;
  parentProjectUuid: string;
  parentBoardName?: string;
}): MaybeRecord {
  return {
    uuid: item.uuid,
    name: item.name,
    parentProjectUuid: item.parentProjectUuid,
    parentBoardName: item.parentBoardName,
  };
}

function summarizeSchematicPage(item: {
  uuid: string;
  name: string;
  parentSchematicUuid: string;
  showTitleBlock: boolean;
  titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }>;
}): MaybeRecord {
  return {
    uuid: item.uuid,
    name: item.name,
    parentSchematicUuid: item.parentSchematicUuid,
    showTitleBlock: item.showTitleBlock,
    titleBlockFieldCount: Object.keys(item.titleBlockData ?? {}).length,
  };
}

function summarizeSchematic(item: {
  uuid: string;
  name: string;
  page: Array<{ uuid: string; name: string; parentSchematicUuid: string; showTitleBlock: boolean; titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }> }>;
  parentProjectUuid: string;
  parentBoardUuid?: string;
}): MaybeRecord {
  return {
    uuid: item.uuid,
    name: item.name,
    parentProjectUuid: item.parentProjectUuid,
    parentBoardUuid: item.parentBoardUuid,
    pageCount: item.page.length,
    pages: item.page.map(summarizeSchematicPage),
  };
}

function summarizeBoard(item: {
  name: string;
  schematic: {
    uuid: string;
    name: string;
    page: Array<{ uuid: string; name: string; parentSchematicUuid: string; showTitleBlock: boolean; titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }> }>;
    parentProjectUuid: string;
    parentBoardUuid?: string;
  };
  pcb: {
    uuid: string;
    name: string;
    parentProjectUuid: string;
    parentBoardName?: string;
  };
  parentProjectUuid: string;
}): MaybeRecord {
  return {
    name: item.name,
    parentProjectUuid: item.parentProjectUuid,
    schematic: summarizeSchematic(item.schematic),
    pcb: summarizePcb(item.pcb),
  };
}

function summarizeProjectDetailed(item: {
  uuid: string;
  friendlyName: string;
  teamUuid: string;
  folderUuid?: string;
  name: string;
  description?: string;
  collaborationMode?: unknown;
  data: Array<MaybeRecord>;
}): MaybeRecord {
  return {
    uuid: item.uuid,
    friendlyName: item.friendlyName,
    name: item.name,
    teamUuid: item.teamUuid,
    folderUuid: item.folderUuid,
    description: item.description,
    collaborationMode: item.collaborationMode,
    documentCount: item.data.length,
    documents: item.data.map(documentItem => ({
      ...documentItem,
      pageCount: Array.isArray((documentItem as { page?: unknown }).page)
        ? (documentItem as { page: unknown[] }).page.length
        : undefined,
    })),
  };
}

async function safeRead(reader: () => Promise<unknown>): Promise<any | undefined> {
  try {
    return await reader();
  }
  catch {
    return undefined;
  }
}

async function listProjectsForScope(scope?: {
  teamUuid?: string;
  folderUuid?: string;
  workspaceUuid?: string;
}): Promise<Array<MaybeRecord>> {
  const projectUuids = (await safeRead(() =>
    eda.dmt_Project.getAllProjectsUuid(scope?.teamUuid, scope?.folderUuid, scope?.workspaceUuid),
  )) as Array<string> | undefined;

  if (!projectUuids?.length) {
    return [];
  }

  const projects = await Promise.all(
    projectUuids.map(async (projectUuid: string) => {
      const projectInfo = (await safeRead(() => eda.dmt_Project.getProjectInfo(projectUuid))) as
        | {
            uuid: string;
            friendlyName: string;
            teamUuid: string;
            folderUuid?: string;
          }
        | undefined;
      return projectInfo ? summarizeProjectBrief(projectInfo) : { uuid: projectUuid };
    }),
  );

  return projects;
}

export async function getSystemEnvironmentResult(): Promise<BridgeResult> {
  const [language, frontendUnit, theme, userInfo, editorVersion, compiledDate] = await Promise.all([
    eda.sys_I18n.getCurrentLanguage(),
    eda.sys_Unit.getFrontendDataUnit(),
    safeRead(() => eda.sys_Environment.getCurrentTheme()),
    safeRead(() => Promise.resolve(eda.sys_Environment.getUserInfo())),
    safeRead(() => Promise.resolve(eda.sys_Environment.getEditorCurrentVersion())),
    safeRead(() => Promise.resolve(eda.sys_Environment.getEditorCompliedDate())),
  ]);

  return {
    summary: 'system environment collected',
    data: {
      runtime: {
        isWeb: eda.sys_Environment.isWeb(),
        isClient: eda.sys_Environment.isClient(),
        isEasyEDAProEdition: eda.sys_Environment.isEasyEDAProEdition(),
        isJLCEDAProEdition: eda.sys_Environment.isJLCEDAProEdition(),
        isProPrivateEdition: eda.sys_Environment.isProPrivateEdition(),
        isOnlineMode: eda.sys_Environment.isOnlineMode(),
        isHalfOfflineMode: eda.sys_Environment.isHalfOfflineMode(),
        isOfflineMode: eda.sys_Environment.isOfflineMode(),
      },
      language,
      frontendUnit,
      theme,
      userInfo,
      editorVersion,
      compiledDate,
    },
  };
}

export async function getProjectInventoryResult(): Promise<BridgeResult> {
  const [
    currentDocumentInfo,
    currentProjectInfo,
    currentTeamInfo,
    currentWorkspaceInfo,
    currentSchematicInfo,
    currentPcbInfo,
    currentBoardInfo,
    workspaces,
    teams,
    involvedTeams,
    schematics,
    schematicPages,
    boards,
    pcbs,
  ] = await Promise.all([
    safeRead(() => eda.dmt_SelectControl.getCurrentDocumentInfo()),
    safeRead(() => eda.dmt_Project.getCurrentProjectInfo()),
    safeRead(() => eda.dmt_Team.getCurrentTeamInfo()),
    safeRead(() => eda.dmt_Workspace.getCurrentWorkspaceInfo()),
    safeRead(() => eda.dmt_Schematic.getCurrentSchematicInfo()),
    safeRead(() => eda.dmt_Pcb.getCurrentPcbInfo()),
    safeRead(() => eda.dmt_Board.getCurrentBoardInfo()),
    safeRead(() => eda.dmt_Workspace.getAllWorkspacesInfo()),
    safeRead(() => eda.dmt_Team.getAllTeamsInfo()),
    safeRead(() => eda.dmt_Team.getAllInvolvedTeamInfo()),
    safeRead(() => eda.dmt_Schematic.getAllSchematicsInfo()),
    safeRead(() => eda.dmt_Schematic.getAllSchematicPagesInfo()),
    safeRead(() => eda.dmt_Board.getAllBoardsInfo()),
    safeRead(() => eda.dmt_Pcb.getAllPcbsInfo()),
  ]);

  const projectSections = await Promise.all(
    ((teams ?? []) as Array<{ uuid: string; name: string; identity: number }>).map(async team => ({
      team: summarizeTeam(team),
      projects: await listProjectsForScope({ teamUuid: team.uuid }),
    })),
  );

  return {
    summary: 'project inventory collected',
    data: {
      current: {
        document: currentDocumentInfo,
        project: currentProjectInfo ? summarizeProjectDetailed(currentProjectInfo) : undefined,
        team: currentTeamInfo ? summarizeTeam(currentTeamInfo) : undefined,
        workspace: currentWorkspaceInfo ? summarizeWorkspace(currentWorkspaceInfo) : undefined,
        schematic: currentSchematicInfo ? summarizeSchematic(currentSchematicInfo) : undefined,
        pcb: currentPcbInfo ? summarizePcb(currentPcbInfo) : undefined,
        board: currentBoardInfo ? summarizeBoard(currentBoardInfo) : undefined,
      },
      workspaces: (workspaces ?? []).map(summarizeWorkspace),
      teams: (teams ?? []).map(summarizeTeam),
      involvedTeams: (involvedTeams ?? []).map(summarizeTeam),
      projectSections,
      schematics: (schematics ?? []).map(summarizeSchematic),
      schematicPages: (schematicPages ?? []).map(summarizeSchematicPage),
      boards: (boards ?? []).map(summarizeBoard),
      pcbs: (pcbs ?? []).map(summarizePcb),
    },
  };
}

export async function listWorkspacesResult(): Promise<BridgeResult> {
  const workspaces = (await safeRead(() => eda.dmt_Workspace.getAllWorkspacesInfo())) as
    | Array<{ uuid: string; name: string }>
    | undefined;

  return {
    summary: 'workspace list collected',
    data: {
      workspaces: (workspaces ?? []).map(summarizeWorkspace),
    },
  };
}

export async function listTeamsResult(includeInvolved = false): Promise<BridgeResult> {
  const teams = (includeInvolved
    ? await safeRead(() => eda.dmt_Team.getAllInvolvedTeamInfo())
    : await safeRead(() => eda.dmt_Team.getAllTeamsInfo())) as
    | Array<{ uuid: string; name: string; identity: number }>
    | undefined;

  return {
    summary: 'team list collected',
    data: {
      teams: (teams ?? []).map(summarizeTeam),
      scope: includeInvolved ? 'involved' : 'direct',
    },
  };
}

export async function listProjectsResult(scope?: {
  teamUuid?: string;
  folderUuid?: string;
  workspaceUuid?: string;
}): Promise<BridgeResult> {
  const projects = await listProjectsForScope(scope);

  return {
    summary: 'project list collected',
    data: {
      scope: scope ?? {},
      projects,
      count: projects.length,
    },
  };
}

export async function getProjectInfoResult(projectUuid: string): Promise<BridgeResult> {
  const projectInfo = await eda.dmt_Project.getProjectInfo(projectUuid);

  if (!projectInfo) {
    throw new Error(`Project not found: ${projectUuid}`);
  }

  return {
    summary: 'project info collected',
    data: summarizeProjectBrief(projectInfo),
  };
}

export async function openProjectResult(projectUuid: string): Promise<BridgeResult> {
  const opened = await eda.dmt_Project.openProject(projectUuid);

  if (!opened) {
    throw new Error(`Failed to open project: ${projectUuid}`);
  }

  const currentProjectInfo = await safeRead(() => eda.dmt_Project.getCurrentProjectInfo());

  return {
    summary: 'project opened',
    data: {
      opened: true,
      projectUuid,
      currentProject: currentProjectInfo ? summarizeProjectDetailed(currentProjectInfo) : undefined,
    },
  };
}

export async function createProjectResult(payload: {
  projectFriendlyName: string;
  projectName?: string;
  teamUuid?: string;
  folderUuid?: string;
  description?: string;
  collaborationMode?: string;
}): Promise<BridgeResult> {
  const projectUuid = await eda.dmt_Project.createProject(
    payload.projectFriendlyName,
    payload.projectName,
    payload.teamUuid,
    payload.folderUuid,
    payload.description,
    payload.collaborationMode as never,
  );

  if (!projectUuid) {
    throw new Error('Failed to create project.');
  }

  const projectInfo = await safeRead(() => eda.dmt_Project.getProjectInfo(projectUuid));

  return {
    summary: 'project created',
    data: {
      projectUuid,
      project: projectInfo ? summarizeProjectBrief(projectInfo) : undefined,
    },
  };
}

export async function listSchematicsResult(): Promise<BridgeResult> {
  const schematics = (await safeRead(() => eda.dmt_Schematic.getAllSchematicsInfo())) as
    | Array<{
        uuid: string;
        name: string;
        page: Array<{
          uuid: string;
          name: string;
          parentSchematicUuid: string;
          showTitleBlock: boolean;
          titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }>;
        }>;
        parentProjectUuid: string;
        parentBoardUuid?: string;
      }>
    | undefined;

  return {
    summary: 'schematic list collected',
    data: {
      schematics: (schematics ?? []).map(summarizeSchematic),
      count: schematics?.length ?? 0,
    },
  };
}

export async function listSchematicPagesResult(schematicUuid?: string): Promise<BridgeResult> {
  const schematicPages = (schematicUuid
    ? await safeRead(() =>
        eda.dmt_Schematic.getSchematicInfo(schematicUuid).then((info: any) => info?.page ?? []),
      )
    : await safeRead(() => eda.dmt_Schematic.getAllSchematicPagesInfo())) as
    | Array<{
        uuid: string;
        name: string;
        parentSchematicUuid: string;
        showTitleBlock: boolean;
        titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }>;
      }>
    | undefined;

  return {
    summary: 'schematic page list collected',
    data: {
      schematicUuid,
      pages: (schematicPages ?? []).map(summarizeSchematicPage),
      count: schematicPages?.length ?? 0,
    },
  };
}

export async function getCurrentSchematicInfoResult(): Promise<BridgeResult> {
  const schematicInfo = (await eda.dmt_Schematic.getCurrentSchematicInfo()) as
    | {
        uuid: string;
        name: string;
        page: Array<{
          uuid: string;
          name: string;
          parentSchematicUuid: string;
          showTitleBlock: boolean;
          titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }>;
        }>;
        parentProjectUuid: string;
        parentBoardUuid?: string;
      }
    | undefined;

  if (!schematicInfo) {
    throw new Error('No current schematic is available.');
  }

  return {
    summary: 'current schematic info collected',
    data: summarizeSchematic(schematicInfo),
  };
}

export async function createSchematicResult(boardName?: string): Promise<BridgeResult> {
  const schematicUuid = await eda.dmt_Schematic.createSchematic(boardName);

  if (!schematicUuid) {
    throw new Error('Failed to create schematic.');
  }

  const schematicInfo = (await safeRead(() => eda.dmt_Schematic.getSchematicInfo(schematicUuid))) as
    | {
        uuid: string;
        name: string;
        page: Array<{
          uuid: string;
          name: string;
          parentSchematicUuid: string;
          showTitleBlock: boolean;
          titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }>;
        }>;
        parentProjectUuid: string;
        parentBoardUuid?: string;
      }
    | undefined;

  return {
    summary: 'schematic created',
    data: {
      schematicUuid,
      schematic: schematicInfo ? summarizeSchematic(schematicInfo) : undefined,
    },
  };
}

export async function createSchematicPageResult(schematicUuid: string): Promise<BridgeResult> {
  const schematicPageUuid = await eda.dmt_Schematic.createSchematicPage(schematicUuid);

  if (!schematicPageUuid) {
    throw new Error(`Failed to create schematic page for ${schematicUuid}.`);
  }

  const schematicPageInfo = (await safeRead(() => eda.dmt_Schematic.getSchematicPageInfo(schematicPageUuid))) as
    | {
        uuid: string;
        name: string;
        parentSchematicUuid: string;
        showTitleBlock: boolean;
        titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }>;
      }
    | undefined;

  return {
    summary: 'schematic page created',
    data: {
      schematicPageUuid,
      schematicPage: schematicPageInfo ? summarizeSchematicPage(schematicPageInfo) : undefined,
    },
  };
}

export async function listBoardsResult(): Promise<BridgeResult> {
  const boards = (await safeRead(() => eda.dmt_Board.getAllBoardsInfo())) as
    | Array<{
        name: string;
        schematic: {
          uuid: string;
          name: string;
          page: Array<{
            uuid: string;
            name: string;
            parentSchematicUuid: string;
            showTitleBlock: boolean;
            titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }>;
          }>;
          parentProjectUuid: string;
          parentBoardUuid?: string;
        };
        pcb: {
          uuid: string;
          name: string;
          parentProjectUuid: string;
          parentBoardName?: string;
        };
        parentProjectUuid: string;
      }>
    | undefined;

  return {
    summary: 'board list collected',
    data: {
      boards: (boards ?? []).map(summarizeBoard),
      count: boards?.length ?? 0,
    },
  };
}

export async function getBoardSummaryResult(): Promise<BridgeResult> {
  const [boardInfo, currentProjectInfo, currentSchematicInfo, currentPcbInfo] = await Promise.all([
    safeRead(() => eda.dmt_Board.getCurrentBoardInfo()),
    safeRead(() => eda.dmt_Project.getCurrentProjectInfo()),
    safeRead(() => eda.dmt_Schematic.getCurrentSchematicInfo()),
    safeRead(() => eda.dmt_Pcb.getCurrentPcbInfo()),
  ]);

  return {
    summary: 'board summary collected',
    data: {
      board: boardInfo ? summarizeBoard(boardInfo) : undefined,
      project: currentProjectInfo ? summarizeProjectDetailed(currentProjectInfo) : undefined,
      schematic: currentSchematicInfo ? summarizeSchematic(currentSchematicInfo) : undefined,
      pcb: currentPcbInfo ? summarizePcb(currentPcbInfo) : undefined,
    },
  };
}

export async function createBoardResult(payload: {
  schematicUuid?: string;
  pcbUuid?: string;
}): Promise<BridgeResult> {
  const boardName = await eda.dmt_Board.createBoard(payload.schematicUuid, payload.pcbUuid);

  if (!boardName) {
    throw new Error('Failed to create board.');
  }

  const boardInfo = (await safeRead(() => eda.dmt_Board.getBoardInfo(boardName))) as
    | {
        name: string;
        schematic: {
          uuid: string;
          name: string;
          page: Array<{
            uuid: string;
            name: string;
            parentSchematicUuid: string;
            showTitleBlock: boolean;
            titleBlockData: Record<string, { showTitle: boolean; showValue: boolean; value: unknown }>;
          }>;
          parentProjectUuid: string;
          parentBoardUuid?: string;
        };
        pcb: {
          uuid: string;
          name: string;
          parentProjectUuid: string;
          parentBoardName?: string;
        };
        parentProjectUuid: string;
      }
    | undefined;

  return {
    summary: 'board created',
    data: {
      boardName,
      board: boardInfo ? summarizeBoard(boardInfo) : undefined,
    },
  };
}

export async function listPcbsResult(): Promise<BridgeResult> {
  const pcbs = (await safeRead(() => eda.dmt_Pcb.getAllPcbsInfo())) as
    | Array<{
        uuid: string;
        name: string;
        parentProjectUuid: string;
        parentBoardName?: string;
      }>
    | undefined;

  return {
    summary: 'pcb list collected',
    data: {
      pcbs: (pcbs ?? []).map(summarizePcb),
      count: pcbs?.length ?? 0,
    },
  };
}

export async function getCurrentPcbInfoResult(): Promise<BridgeResult> {
  const pcbInfo = (await eda.dmt_Pcb.getCurrentPcbInfo()) as
    | {
        uuid: string;
        name: string;
        parentProjectUuid: string;
        parentBoardName?: string;
      }
    | undefined;

  if (!pcbInfo) {
    throw new Error('No current PCB is available.');
  }

  return {
    summary: 'current pcb info collected',
    data: summarizePcb(pcbInfo),
  };
}

export async function createPcbResult(boardName?: string): Promise<BridgeResult> {
  const pcbUuid = await eda.dmt_Pcb.createPcb(boardName);

  if (!pcbUuid) {
    throw new Error('Failed to create PCB.');
  }

  const pcbInfo = (await safeRead(() => eda.dmt_Pcb.getPcbInfo(pcbUuid))) as
    | {
        uuid: string;
        name: string;
        parentProjectUuid: string;
        parentBoardName?: string;
      }
    | undefined;

  return {
    summary: 'pcb created',
    data: {
      pcbUuid,
      pcb: pcbInfo ? summarizePcb(pcbInfo) : undefined,
    },
  };
}
