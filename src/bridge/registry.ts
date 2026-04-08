import type { BridgeCommandName, BridgeDomain } from './protocol';

export interface BridgeCommandDescriptor {
  name: BridgeCommandName;
  domain: BridgeDomain;
  requiresConfirmationByDefault: boolean;
  summary: string;
}

export const IMPLEMENTED_COMMANDS: BridgeCommandName[] = [
  'system.ping',
  'system.get_bridge_status',
  'system.get_environment',
  'project.get_inventory',
  'project.get_document_summary',
  'project.get_selection_snapshot',
  'project.list_workspaces',
  'project.list_teams',
  'project.list_involved_teams',
  'project.list_projects',
  'project.get_project_info',
  'project.open_project',
  'project.create_project',
  'project.list_schematics',
  'project.list_schematic_pages',
  'project.list_boards',
  'project.list_pcbs',
  'project.get_board_summary',
  'project.create_board',
  'project.export_bom',
  'schematic.get_current_schematic_info',
  'schematic.create_schematic',
  'schematic.create_schematic_page',
  'schematic.place_component',
  'schematic.create_wire',
  'schematic.annotate_net',
  'schematic.create_net_flag',
  'schematic.create_net_port',
  'schematic.create_short_circuit_flag',
  'pcb.get_board_summary',
  'pcb.get_current_pcb_info',
  'pcb.list_pcbs',
  'pcb.create_pcb',
  'pcb.place_footprint',
];

export const SUPPORTED_COMMANDS: BridgeCommandDescriptor[] = [
  {
    name: 'system.ping',
    domain: 'system',
    requiresConfirmationByDefault: false,
    summary: 'Check whether the bridge runtime is reachable.',
  },
  {
    name: 'system.get_bridge_status',
    domain: 'system',
    requiresConfirmationByDefault: false,
    summary: 'Return bridge version and supported command metadata.',
  },
  {
    name: 'system.get_environment',
    domain: 'system',
    requiresConfirmationByDefault: false,
    summary: 'Return runtime, version, and user environment details.',
  },
  {
    name: 'project.get_inventory',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'Return a broad inventory of the current project tree and related objects.',
  },
  {
    name: 'project.get_document_summary',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'Return a compact summary of the current JLCEDA document.',
  },
  {
    name: 'project.get_selection_snapshot',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'Return a structured snapshot of the current selection.',
  },
  {
    name: 'project.list_workspaces',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'List all workspaces visible to the current account.',
  },
  {
    name: 'project.list_teams',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'List all direct teams visible to the current account.',
  },
  {
    name: 'project.list_involved_teams',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'List all teams the current account participates in.',
  },
  {
    name: 'project.list_projects',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'List projects for a scope defined by team, folder, or workspace.',
  },
  {
    name: 'project.get_project_info',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'Return brief metadata for a specific project.',
  },
  {
    name: 'project.open_project',
    domain: 'project',
    requiresConfirmationByDefault: true,
    summary: 'Open a project in the JLCEDA editor.',
  },
  {
    name: 'project.create_project',
    domain: 'project',
    requiresConfirmationByDefault: true,
    summary: 'Create a new project in the current account scope.',
  },
  {
    name: 'project.list_schematics',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'List all schematics in the current project scope.',
  },
  {
    name: 'project.list_schematic_pages',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'List schematic pages, optionally scoped to one schematic.',
  },
  {
    name: 'project.list_boards',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'List all boards in the current project.',
  },
  {
    name: 'project.list_pcbs',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'List all PCBs in the current project.',
  },
  {
    name: 'project.get_board_summary',
    domain: 'project',
    requiresConfirmationByDefault: false,
    summary: 'Return a board-centric summary of the current project.',
  },
  {
    name: 'project.create_board',
    domain: 'project',
    requiresConfirmationByDefault: true,
    summary: 'Create a board that links schematic and PCB documents.',
  },
  {
    name: 'project.export_bom',
    domain: 'project',
    requiresConfirmationByDefault: true,
    summary: 'Export a BOM artifact for the current project.',
  },
  {
    name: 'schematic.get_current_schematic_info',
    domain: 'schematic',
    requiresConfirmationByDefault: false,
    summary: 'Return detailed metadata for the current schematic.',
  },
  {
    name: 'schematic.create_schematic',
    domain: 'schematic',
    requiresConfirmationByDefault: true,
    summary: 'Create a schematic in the current project.',
  },
  {
    name: 'schematic.create_schematic_page',
    domain: 'schematic',
    requiresConfirmationByDefault: true,
    summary: 'Create a schematic page in a specific schematic.',
  },
  {
    name: 'schematic.place_component',
    domain: 'schematic',
    requiresConfirmationByDefault: true,
    summary: 'Place a component at a specific schematic position.',
  },
  {
    name: 'schematic.create_wire',
    domain: 'schematic',
    requiresConfirmationByDefault: true,
    summary: 'Create a schematic wire with explicit points.',
  },
  {
    name: 'schematic.annotate_net',
    domain: 'schematic',
    requiresConfirmationByDefault: true,
    summary: 'Add or update a schematic net label.',
  },
  {
    name: 'schematic.create_net_flag',
    domain: 'schematic',
    requiresConfirmationByDefault: true,
    summary: 'Create a schematic net flag symbol.',
  },
  {
    name: 'schematic.create_net_port',
    domain: 'schematic',
    requiresConfirmationByDefault: true,
    summary: 'Create a schematic net port symbol.',
  },
  {
    name: 'schematic.create_short_circuit_flag',
    domain: 'schematic',
    requiresConfirmationByDefault: true,
    summary: 'Create a schematic short-circuit flag.',
  },
  {
    name: 'pcb.get_board_summary',
    domain: 'pcb',
    requiresConfirmationByDefault: false,
    summary: 'Return a compact summary of the current PCB board.',
  },
  {
    name: 'pcb.get_current_pcb_info',
    domain: 'pcb',
    requiresConfirmationByDefault: false,
    summary: 'Return detailed metadata for the current PCB.',
  },
  {
    name: 'pcb.list_pcbs',
    domain: 'pcb',
    requiresConfirmationByDefault: false,
    summary: 'List all PCBs in the current project.',
  },
  {
    name: 'pcb.create_pcb',
    domain: 'pcb',
    requiresConfirmationByDefault: true,
    summary: 'Create a PCB in the current project.',
  },
  {
    name: 'pcb.place_footprint',
    domain: 'pcb',
    requiresConfirmationByDefault: true,
    summary: 'Place a footprint on the PCB at a specific coordinate.',
  },
];

export function getSupportedCommandNames(): Array<BridgeCommandName> {
  return SUPPORTED_COMMANDS.map(command => command.name);
}

export function getCommandDescriptor(name: BridgeCommandName): BridgeCommandDescriptor | undefined {
  return SUPPORTED_COMMANDS.find(command => command.name === name);
}

export function isCommandImplemented(name: BridgeCommandName): boolean {
  return IMPLEMENTED_COMMANDS.includes(name);
}
