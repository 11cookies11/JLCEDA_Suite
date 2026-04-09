# JLCEDA Bridge API Surface

This reference describes the API surface that the `jlceda-suite-skill` package can use.

Use it when you need to decide whether to call a dedicated bridge command or fall back to `system.api_invoke`.

## Table of contents

- [Access layers](#access-layers)
- [`system.api_invoke` rules](#systemapi_invoke-rules)
- [High-value API families](#high-value-api-families)
  - [Project and workspace](#project-and-workspace)
  - [Editor and document control](#editor-and-document-control)
  - [Schematic](#schematic)
  - [PCB](#pcb)
  - [File system and file manager](#file-system-and-file-manager)
  - [System, UI, and orchestration](#system-ui-and-orchestration)
  - [Tools and conversions](#tools-and-conversions)
  - [Library queries](#library-queries)
- [Suggested agent strategy](#suggested-agent-strategy)
- [Good call patterns](#good-call-patterns)

## Access layers

1. Dedicated bridge commands
   - Use these first for the common flows already wrapped by the bridge.
   - Good for stable, repeatable actions with built-in confirmation handling.
2. `system.api_invoke`
   - Use this for official JLCEDA API methods that are not wrapped as dedicated bridge commands.
   - Call it with a dotted path like `dmt_Project.getCurrentProjectInfo` or `eda.dmt_Project.getCurrentProjectInfo`.
   - Pass arguments in order through `payload.args`.

## `system.api_invoke` rules

- `payload.path` must target a real JLCEDA object or method.
- Prefix `eda.` is optional and ignored if present.
- If the target resolves to a function, it is invoked with the original receiver context.
- If the target resolves to a property, the property value is returned.
- Read-only calls should set `requiresConfirmation: false`.
- State-changing calls should keep confirmation enabled unless you are explicitly testing the mutation path.

## High-value API families

### Project and workspace

Use these to locate the current project, list available projects, or open/create a project.

- `dmt_Project.getCurrentProjectInfo`
- `dmt_Project.getAllProjectsUuid`
- `dmt_Project.getProjectInfo`
- `dmt_Project.openProject`
- `dmt_Project.createProject`
- `dmt_Workspace.getAllWorkspacesInfo`
- `dmt_Workspace.getCurrentWorkspaceInfo`
- `dmt_Team.getAllTeamsInfo`
- `dmt_Team.getAllInvolvedTeamInfo`
- `dmt_Folder.getAllFoldersUuid`

Typical order:

1. Find the current project or workspace.
2. Open or create the target project.
3. Inspect the returned project UUID and context before editing.

### Editor and document control

Use these to open documents, manage split screens, and control zoom/navigation.

- `dmt_EditorControl.openDocument`
- `dmt_EditorControl.openLibraryDocument`
- `dmt_EditorControl.closeDocument`
- `dmt_EditorControl.getSplitScreenTree`
- `dmt_EditorControl.getTabsBySplitScreenId`
- `dmt_EditorControl.createSplitScreen`
- `dmt_EditorControl.moveDocumentToSplitScreen`
- `dmt_EditorControl.activateDocument`
- `dmt_EditorControl.activateSplitScreen`
- `dmt_EditorControl.zoomTo`
- `dmt_EditorControl.zoomToRegion`
- `dmt_EditorControl.zoomToAllPrimitives`
- `dmt_EditorControl.zoomToSelectedPrimitives`
- `dmt_EditorControl.getCurrentRenderedAreaImage`

### Schematic

Use these for schematic generation, inspection, navigation, layout, routing, and DRC.

- `dmt_Schematic.getCurrentSchematicInfo`
- `dmt_Schematic.getAllSchematicsInfo`
- `dmt_Schematic.getAllSchematicPagesInfo`
- `dmt_Schematic.getSchematicInfo`
- `dmt_Schematic.getSchematicPageInfo`
- `dmt_Schematic.createSchematic`
- `dmt_Schematic.createSchematicPage`
- `sch_Document.importChanges`
- `sch_Document.save`
- `sch_Document.navigateToCoordinates`
- `sch_Document.navigateToRegion`
- `sch_Document.getPrimitiveAtPoint`
- `sch_Document.getPrimitivesInRegion`
- `sch_Document.getCurrentFilterConfiguration`
- `sch_Document.autoRouting`
- `sch_Document.autoLayout`
- `sch_Drc.check`

Typical order:

1. Create or open the schematic.
2. Inspect current schematic/page information.
3. Place or modify primitives.
4. Run save, layout, routing, and DRC.

### PCB

Use these for board creation, board inspection, canvas control, routing, and DRC.

- `dmt_Pcb.getCurrentPcbInfo`
- `dmt_Pcb.getAllPcbsInfo`
- `dmt_Pcb.getPcbInfo`
- `dmt_Pcb.createPcb`
- `pcb_Document.importChanges`
- `pcb_Document.save`
- `pcb_Document.getCalculatingRatlineStatus`
- `pcb_Document.startCalculatingRatline`
- `pcb_Document.stopCalculatingRatline`
- `pcb_Document.getCanvasOrigin`
- `pcb_Document.setCanvasOrigin`
- `pcb_Document.convertCanvasOriginToDataOrigin`
- `pcb_Document.convertDataOriginToCanvasOrigin`
- `pcb_Document.navigateToCoordinates`
- `pcb_Document.navigateToRegion`
- `pcb_Document.getPrimitiveAtPoint`
- `pcb_Document.getPrimitivesInRegion`
- `pcb_Document.zoomToBoardOutline`
- `pcb_Document.getCurrentFilterConfiguration`
- `pcb_Document.clearRouting`
- `pcb_Drc.check`

Typical order:

1. Create or open the PCB.
2. Inspect the current board state and canvas.
3. Apply edits, import changes, and save.
4. Run ratline, routing, and DRC as needed.

### File system and file manager

Use these to resolve paths, save files, and read or write document sources.

- `sys_FileSystem.getExtensionFile`
- `sys_FileSystem.saveFile`
- `sys_FileSystem.saveFileToFileSystem`
- `sys_FileSystem.listFilesOfFileSystem`
- `sys_FileSystem.deleteFileInFileSystem`
- `sys_FileSystem.getEdaPath`
- `sys_FileSystem.getDocumentsPath`
- `sys_FileSystem.getLibrariesPaths`
- `sys_FileSystem.getProjectsPaths`
- `sys_FileManager.getDocumentSource`
- `sys_FileManager.getDocumentFootprintSources`
- `sys_FileManager.setDocumentSource`
- `sys_FileManager.getProjectFileByProjectUuid`
- `sys_FileManager.getDeviceFileByDeviceUuid`
- `sys_FileManager.getSymbolFileBySymbolUuid`

Typical order:

1. Resolve the project or document path.
2. Read the current source or generate the output file.
3. Save or export to the filesystem.

### System, UI, and orchestration

Use these for environment info, logging, panels, windows, messages, shortcuts, timers, and menus.

- `sys_Environment.getCurrentTheme`
- `sys_Environment.getUserInfo`
- `sys_Environment.getEditorCurrentVersion`
- `sys_Environment.getEditorCompliedDate`
- `sys_Log.add`
- `sys_Log.clear`
- `sys_Log.export`
- `sys_Log.sort`
- `sys_Log.find`
- `sys_PanelControl.openLeftPanel`
- `sys_PanelControl.closeLeftPanel`
- `sys_PanelControl.toggleLeftPanelLockState`
- `sys_PanelControl.isLeftPanelLocked`
- `sys_Window.open`
- `sys_Window.openUI`
- `sys_Window.getCurrentTheme`
- `sys_Window.getUrlParam`
- `sys_Window.getUrlAnchor`
- `sys_Message.showToastMessage`
- `sys_Message.showFollowMouseTip`
- `sys_Message.removeFollowMouseTip`
- `sys_Dialog.showInformationMessage`
- `sys_Dialog.showConfirmationMessage`
- `sys_ShortcutKey.getShortcutKeys`
- `sys_ShortcutKey.registerShortcutKey`
- `sys_ShortcutKey.unregisterShortcutKey`
- `sys_Timer.setIntervalTimer`
- `sys_Timer.clearIntervalTimer`
- `sys_Timer.setTimeoutTimer`
- `sys_Timer.clearTimeoutTimer`
- `sys_RightClickMenu.changeMenu`
- `sys_HeaderMenu.insertHeaderMenus`
- `sys_HeaderMenu.replaceHeaderMenus`
- `sys_HeaderMenu.removeHeaderMenus`
- `sys_HeaderMenu.insertSystemHeaderMenuItem`
- `sys_HeaderMenu.removeSystemHeaderMenuItem`

### Tools and conversions

Use these for comparisons and library format conversions.

- `sys_Tool.netlistComparison`
- `sys_Tool.schematicComparison`
- `sys_Tool.pcbComparison`
- `sys_FormatConversion.convertAltiumDesignerLibrariesToEasyEDASingleFile`
- `sys_FormatConversion.convertAltiumDesignerLibrariesToEasyEDAMultiFiles`
- `sys_FormatConversion.convertDisaLibrariesToEasyEDASingleFile`
- `sys_FormatConversion.convertDisaLibrariesToEasyEDAMultiFiles`

### Library queries

Use these to search and fetch library objects before placing components or footprints.

- `LIB_LibrariesList.getAllLibrariesList`
- `LIB_LibrariesList.getSystemLibraryUuid`
- `LIB_LibrariesList.getPersonalLibraryUuid`
- `LIB_LibrariesList.getProjectLibraryUuid`
- `LIB_LibrariesList.getFavoriteLibraryUuid`
- `LIB_Device.search`
- `LIB_Device.get`
- `LIB_Device.create`
- `LIB_Symbol.search`
- `LIB_Symbol.get`
- `LIB_Footprint.search`
- `LIB_Footprint.get`
- `LIB_Cbb.search`
- `LIB_Cbb.get`

Typical order:

1. Resolve the correct library UUID.
2. Search the library object by keyword or UUID.
3. Fetch the object details.
4. Use the returned UUIDs when placing components or footprints.

## Suggested agent strategy

When asked to operate JLCEDA end to end:

1. Read the current project or document context first.
2. Prefer a dedicated bridge command if one already exists for the exact action.
3. Fall back to `system.api_invoke` for official API methods that are not wrapped.
4. Keep confirmation enabled for mutations unless the user explicitly wants a test invocation.
5. Reuse the same connected session for the whole task chain.

## Good call patterns

- Prefer the smallest method that answers the question.
- For inspection, start with project/document metadata before drilling into primitives.
- For design operations, fetch library identifiers before placement.
- For export and filesystem work, resolve the path first and then write the output.
