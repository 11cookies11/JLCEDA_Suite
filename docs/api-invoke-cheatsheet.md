# `system.api_invoke` 速查

`system.api_invoke` 是桥接层里的通用入口。它不会替你猜 API，而是直接按你给的路径调用 JLCEDA 原生对象方法。

## 用法

```json
{
  "domain": "system",
  "action": "api_invoke",
  "requiresConfirmation": false,
  "payload": {
    "path": "dmt_Project.getCurrentProjectInfo",
    "args": []
  }
}
```

规则：

- `path` 写成 `对象.方法`
- 也可以写成 `eda.对象.方法`，前缀会自动忽略
- `args` 按方法的参数顺序传数组
- 读操作建议显式传 `requiresConfirmation: false`
- 写操作默认保留确认门禁

## 最常用

### 项目与工程树

- `dmt_Project.getCurrentProjectInfo()`
- `dmt_Project.getAllProjectsUuid(teamUuid?, folderUuid?, workspaceUuid?)`
- `dmt_Project.getProjectInfo(projectUuid)`
- `dmt_Project.openProject(projectUuid)`
- `dmt_Project.createProject(projectFriendlyName, projectName?, teamUuid?, folderUuid?, description?, collaborationMode?)`
- `dmt_Workspace.getAllWorkspacesInfo()`
- `dmt_Workspace.getCurrentWorkspaceInfo()`
- `dmt_Team.getAllTeamsInfo()`
- `dmt_Team.getAllInvolvedTeamInfo()`
- `dmt_Folder.getAllFoldersUuid(teamUuid?, folderUuid?, workspaceUuid?)`

### 文档与编辑器

- `dmt_SelectControl.getCurrentDocumentInfo()`
- `dmt_EditorControl.openDocument(documentUuid, splitScreenId?)`
- `dmt_EditorControl.openLibraryDocument(libraryUuid, libraryType, uuid, splitScreenId?)`
- `dmt_EditorControl.closeDocument(tabId)`
- `dmt_EditorControl.getSplitScreenTree()`
- `dmt_EditorControl.getTabsBySplitScreenId(splitScreenId)`
- `dmt_EditorControl.createSplitScreen(splitScreenType, tabId)`
- `dmt_EditorControl.moveDocumentToSplitScreen(tabId, splitScreenId)`
- `dmt_EditorControl.activateDocument(tabId)`
- `dmt_EditorControl.activateSplitScreen(splitScreenId)`
- `dmt_EditorControl.zoomTo(x?, y?, scaleRatio?, tabId?)`
- `dmt_EditorControl.zoomToRegion(left, right, top, bottom, tabId?)`
- `dmt_EditorControl.zoomToAllPrimitives(tabId?)`
- `dmt_EditorControl.zoomToSelectedPrimitives(tabId?)`
- `dmt_EditorControl.getCurrentRenderedAreaImage(tabId?)`

### 原理图

- `dmt_Schematic.getCurrentSchematicInfo()`
- `dmt_Schematic.getAllSchematicsInfo()`
- `dmt_Schematic.getAllSchematicPagesInfo()`
- `dmt_Schematic.getSchematicInfo(schematicUuid)`
- `dmt_Schematic.getSchematicPageInfo(pageUuid)`
- `dmt_Schematic.createSchematic(boardName?)`
- `dmt_Schematic.createSchematicPage(schematicUuid)`
- `sch_Document.importChanges()`
- `sch_Document.save()`
- `sch_Document.navigateToCoordinates(x, y)`
- `sch_Document.navigateToRegion(left, right, top, bottom)`
- `sch_Document.getPrimitiveAtPoint(x, y)`
- `sch_Document.getPrimitivesInRegion(left, right, top, bottom)`
- `sch_Document.getCurrentFilterConfiguration()`
- `sch_Document.autoRouting(props?)`
- `sch_Document.autoLayout(props?)`
- `sch_Drc.check(strict, userInterface, includeVerboseError)`

### PCB

- `dmt_Pcb.getCurrentPcbInfo()`
- `dmt_Pcb.getAllPcbsInfo()`
- `dmt_Pcb.getPcbInfo(pcbUuid)`
- `dmt_Pcb.createPcb(boardName?)`
- `pcb_Document.importChanges(uuid?)`
- `pcb_Document.save(uuid)`
- `pcb_Document.getCalculatingRatlineStatus()`
- `pcb_Document.startCalculatingRatline()`
- `pcb_Document.stopCalculatingRatline()`
- `pcb_Document.getCanvasOrigin()`
- `pcb_Document.setCanvasOrigin(offsetX, offsetY)`
- `pcb_Document.convertCanvasOriginToDataOrigin(x, y)`
- `pcb_Document.convertDataOriginToCanvasOrigin(x, y)`
- `pcb_Document.navigateToCoordinates(x, y)`
- `pcb_Document.navigateToRegion(left, right, top, bottom)`
- `pcb_Document.getPrimitiveAtPoint(x, y)`
- `pcb_Document.getPrimitivesInRegion(left, right, top, bottom)`
- `pcb_Document.zoomToBoardOutline()`
- `pcb_Document.getCurrentFilterConfiguration()`
- `pcb_Document.clearRouting(type?)`
- `pcb_Drc.check(strict, userInterface, includeVerboseError)`

### 文件与导出

- `sys_FileSystem.getExtensionFile(uri)`
- `sys_FileSystem.saveFile(fileData, fileName?)`
- `sys_FileSystem.saveFileToFileSystem(uri, fileData, fileName?, force?)`
- `sys_FileSystem.listFilesOfFileSystem(folderPath, recursive?)`
- `sys_FileSystem.deleteFileInFileSystem(uri, force?)`
- `sys_FileSystem.getEdaPath()`
- `sys_FileSystem.getDocumentsPath()`
- `sys_FileSystem.getLibrariesPaths()`
- `sys_FileSystem.getProjectsPaths()`
- `sys_FileManager.getDocumentSource()`
- `sys_FileManager.getDocumentFootprintSources()`
- `sys_FileManager.setDocumentSource(source)`
- `sys_FileManager.getProjectFileByProjectUuid(projectUuid, fileName?, password?, fileType?)`
- `sys_FileManager.getDeviceFileByDeviceUuid(deviceUuid, libraryUuid?, fileType?)`
- `sys_FileManager.getSymbolFileBySymbolUuid(symbolUuid, libraryUuid?, fileType?)`

### 系统与 UI

- `sys_Environment.getCurrentTheme()`
- `sys_Environment.getUserInfo()`
- `sys_Environment.getEditorCurrentVersion()`
- `sys_Environment.getEditorCompliedDate()`
- `sys_Log.add(message, type?)`
- `sys_Log.clear()`
- `sys_Log.export(types?)`
- `sys_Log.sort(types?)`
- `sys_Log.find(message, types?)`
- `sys_PanelControl.openLeftPanel(tab?)`
- `sys_PanelControl.closeLeftPanel()`
- `sys_PanelControl.toggleLeftPanelLockState(state?)`
- `sys_PanelControl.isLeftPanelLocked()`
- `sys_Window.open(url, target?)`
- `sys_Window.openUI(uiName, args?)`
- `sys_Window.getCurrentTheme()`
- `sys_Window.getUrlParam(key)`
- `sys_Window.getUrlAnchor()`
- `sys_Message.showToastMessage(message, messageType?, timer?, bottomPanel?, buttonTitle?, buttonCallbackFn?)`
- `sys_Message.showFollowMouseTip(tip, msTimeout?)`
- `sys_Message.removeFollowMouseTip(tip?)`
- `sys_Dialog.showInformationMessage(content, title?, buttonTitle?)`
- `sys_Dialog.showConfirmationMessage(content, title?, mainButtonTitle?, buttonTitle?)`
- `sys_ShortcutKey.getShortcutKeys(includeSystem?)`
- `sys_ShortcutKey.registerShortcutKey(shortcutKey, title, callback, documentType?, scene?)`
- `sys_ShortcutKey.unregisterShortcutKey(shortcutKey)`
- `sys_Timer.setIntervalTimer(id, timeout, callback)`
- `sys_Timer.clearIntervalTimer(id)`
- `sys_Timer.setTimeoutTimer(id, timeout, callback)`
- `sys_Timer.clearTimeoutTimer(id)`
- `sys_RightClickMenu.changeMenu(menuId, menuItems)`
- `sys_HeaderMenu.insertHeaderMenus(headerMenus)`
- `sys_HeaderMenu.replaceHeaderMenus(headerMenus)`
- `sys_HeaderMenu.removeHeaderMenus()`
- `sys_HeaderMenu.insertSystemHeaderMenuItem(env, id, props)`
- `sys_HeaderMenu.removeSystemHeaderMenuItem(id, props?)`

### 工具与转换

- `sys_Tool.netlistComparison(left, right)`
- `sys_Tool.schematicComparison(left, right)`
- `sys_Tool.pcbComparison(left, right)`
- `sys_FormatConversion.convertAltiumDesignerLibrariesToEasyEDASingleFile(file)`
- `sys_FormatConversion.convertAltiumDesignerLibrariesToEasyEDAMultiFiles(file)`
- `sys_FormatConversion.convertDisaLibrariesToEasyEDASingleFile(file)`
- `sys_FormatConversion.convertDisaLibrariesToEasyEDAMultiFiles(file)`

### 库查询

- `LIB_LibrariesList.getAllLibrariesList()`
- `LIB_LibrariesList.getSystemLibraryUuid()`
- `LIB_LibrariesList.getPersonalLibraryUuid()`
- `LIB_LibrariesList.getProjectLibraryUuid()`
- `LIB_LibrariesList.getFavoriteLibraryUuid()`
- `LIB_Device.search(...)`
- `LIB_Device.get(...)`
- `LIB_Device.create(...)`
- `LIB_Symbol.search(...)`
- `LIB_Symbol.get(...)`
- `LIB_Footprint.search(...)`
- `LIB_Footprint.get(...)`
- `LIB_Cbb.search(...)`
- `LIB_Cbb.get(...)`

## 推荐执行顺序

如果你要让 Codex 一条指令走完一个设计任务，建议这样排：

1. 用 `dmt_Project.getCurrentProjectInfo` 或 `dmt_Project.getAllProjectsUuid` 找工程
2. 用 `dmt_Schematic.getCurrentSchematicInfo` 或 `dmt_Pcb.getCurrentPcbInfo` 找当前设计上下文
3. 用 `sch_Document` / `pcb_Document` 完成编辑、保存、导入、导航
4. 用 `sys_FileManager` / `sys_FileSystem` 做导出和文件处理
5. 用 `sys_Tool` 和 `*_Drc.check` 做检查
6. 用 `system.api_invoke` 调用尚未做成专用命令的官方 API

## 经验

- 读接口尽量只传最少参数
- 写接口先保持确认门禁，确认后再做自动化批处理
- 库相关操作建议先通过 `LIB_LibrariesList` 找到真实 UUID，再执行写操作
- 如果一个官方方法还没做成独立 bridge command，`system.api_invoke` 通常能先顶上
