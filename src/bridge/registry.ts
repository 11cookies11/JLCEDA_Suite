import type { BridgeCommandName, BridgeDomain } from './protocol';

export interface BridgeCommandDescriptor {
  name: BridgeCommandName;
  domain: BridgeDomain;
  requiresConfirmationByDefault: boolean;
  summary: string;
}

export const IMPLEMENTED_COMMANDS: BridgeCommandName[] = [
  'system.get_bridge_status',
  'project.get_document_summary',
  'project.get_selection_snapshot',
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
    name: 'project.export_bom',
    domain: 'project',
    requiresConfirmationByDefault: true,
    summary: 'Export a BOM artifact for the current project.',
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
    name: 'pcb.get_board_summary',
    domain: 'pcb',
    requiresConfirmationByDefault: false,
    summary: 'Return a compact summary of the current PCB board.',
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
