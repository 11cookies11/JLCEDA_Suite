# JLCEDA Bridge Task Sequences

This reference condenses the bridge into the shortest useful call sequences for common tasks.

Use it when the agent already knows the goal and wants the fewest calls needed to act safely.

## 1. Inspect the current session

Goal: learn what is already open before editing.

Recommended calls:

1. `system.get_bridge_status`
2. `project.get_document_summary`
3. `project.get_selection_snapshot`

Use `system.api_invoke` if the dedicated bridge command is missing for the exact read.


Recommended script:

- `scripts/server-context-summary.mjs`

What to extract from the result:

- active project and document kind
- current schematic name and page count
- current selection count
- immediate next safe action for component selection or schematic refinement

## 2. Create or open a project

Goal: start from a fresh project or reopen an existing one.

Recommended calls:

1. `system.api_invoke` -> `dmt_Project.createProject`
2. `system.api_invoke` -> `dmt_Project.openProject`
3. `system.api_invoke` -> `dmt_Project.getProjectInfo`

Notes:

- Prefer creating with a stable project code and a human-friendly display name.
- Read the returned project UUID before moving on.
- Keep confirmation enabled for creation unless you are intentionally testing the mutation path.

## 3. Build a schematic

Goal: create the minimum schematic structure for a design task.

Recommended calls:

1. `system.api_invoke` -> `dmt_Schematic.createSchematic`
2. `system.api_invoke` -> `dmt_Schematic.createSchematicPage`
3. `system.api_invoke` -> `dmt_Schematic.getCurrentSchematicInfo`
4. `system.api_invoke` -> `dmt_EditorControl.openDocument`

Then, for inspection and editing:

1. `system.api_invoke` -> `sch_Document.getPrimitivesInRegion`
2. `system.api_invoke` -> `sch_Document.importChanges`
3. `system.api_invoke` -> `sch_Document.save`

## 4. Place schematic content

Goal: add components and wires, then verify the result.

Recommended calls:

1. Dedicated bridge command for the placement action if available.
2. `system.api_invoke` -> the smallest placement or lookup method needed for unresolved API gaps.
3. `system.api_invoke` -> `sch_Document.navigateToRegion` or `sch_Document.navigateToCoordinates`
4. `system.api_invoke` -> `sch_Document.getPrimitiveAtPoint`
5. `system.api_invoke` -> `sch_Document.save`

Before placement:

- Resolve the library UUID.
- Search the symbol or device object.
- Confirm the object UUID before mutating the document.

## 5. Build a PCB

Goal: create the minimum board context for layout work.

Recommended calls:

1. `system.api_invoke` -> `dmt_Pcb.createPcb`
2. `system.api_invoke` -> `dmt_Pcb.getCurrentPcbInfo`
3. `system.api_invoke` -> `pcb_Document.importChanges`
4. `system.api_invoke` -> `pcb_Document.save`

For board inspection:

1. `system.api_invoke` -> `pcb_Document.getCanvasOrigin`
2. `system.api_invoke` -> `pcb_Document.navigateToRegion`
3. `system.api_invoke` -> `pcb_Document.getPrimitivesInRegion`

## 6. Export or hand off deliverables

Goal: produce files for review or downstream use.

Recommended calls:

1. Dedicated bridge command if the export already exists.
2. `project.export_bom` or the corresponding export command.
3. `sys_FileSystem.saveFile` or `sys_FileSystem.saveFileToFileSystem` for file outputs.
4. `sys_FileManager.getDocumentSource` or `sys_FileManager.setDocumentSource` when source text is needed.

## 7. Generic official API fallback

When the exact method is not wrapped:

1. Check [api-surface.md](api-surface.md) for the family and recommended order.
2. Call `system.api_invoke` with a dotted path.
3. Keep the call focused on one object and one action.
4. Inspect the result before chaining the next call.

## 8. Safe sequencing rules

- Read first, mutate second.
- Prefer one document or one object at a time.
- Use dedicated bridge commands for stable common actions.
- Use `system.api_invoke` only for official API methods you can name precisely.
- Save after each meaningful edit batch.
- Run DRC or comparison checks before exporting final artifacts.

## 9. Component selection and schematic co-design

Goal: help the user choose parts and improve the current schematic together.

Recommended sequence:

1. `system.get_bridge_status`
2. `project.get_document_summary`
3. `project.get_selection_snapshot`
4. `schematic.get_current_schematic_info`
5. Library search or `system.api_invoke` for unresolved catalog calls
6. Dedicated schematic edit command or `system.api_invoke` for the smallest safe edit
7. `project.get_document_summary` again to verify the new state

Notes:

- Do not jump straight into mutation before the current function block is understood.
- When the user asks for component selection, capture the requirements first and then compare candidates. Prefer candidates whose symbol pin geometry is already verified.
- When the user asks for schematic improvement, prefer one local function block at a time.

