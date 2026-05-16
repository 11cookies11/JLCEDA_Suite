"""Inject JLC-MCP symbols into NexDAP hierarchical schematic.

Replaces AIAgent placeholder symbols in each sub-sheet with full JLC-MCP
symbol definitions from the installed libraries.
"""
import re, shutil, sys
from pathlib import Path
from collections import Counter

# Paths
PROJ_ROOT = Path('.where/nexdap-rp2040-esp32c3-isolated-wireless-cmsis-dap')
SCH_DIR = PROJ_ROOT / 'kicad-output' / 'nexdap_dual_chip_cmsis_dap'
SYM_DIR = PROJ_ROOT / 'libraries' / 'symbols'

# Mapping: AIAgent lib_id -> (JLC lib file stem, symbol name in that lib)
SYMBOL_MAP = {
    'ESP32_C3_Module': ('JLC-MCP-MCUs', 'ESP32-C3'),
    'RP2040_QFN56': ('JLC-MCP-MCUs', 'RP2040'),
    'Buck_Regulator': ('JLC-MCP-Power', 'SY8089A1AAC'),
    'Generic_2Pin': None,  # multiple possibilities, handled by role
    'LDO_3V3': ('JLC-MCP-Power', 'XC6206P332MR_C347376'),
}

# Role-based mapping for Generic_2Pin components (detected from sheet filename)
ROLE_TO_JLC = {
    'digital_isolation_barrier': ('JLC-MCP-ICs', 'CA-IS3742HW'),
    'isolated_dcdc_converter': ('JLC-MCP-Misc', 'B0505S-1WR3_C7465178'),
    'usb_esd_protection': ('JLC-MCP-Diodes', 'USBLC6-2SC6_C2827654'),
    'target_esd_protection': ('JLC-MCP-Diodes', 'SRV05-4_C2836319'),
    'rp2040_qspi_flash': ('JLC-MCP-Memory', 'GD25Q16ETIGR'),
    'target_power_switch': ('JLC-MCP-Power', 'TPS22918DBVR'),
    'target_side_ldo_3v3': ('JLC-MCP-Power', 'XC6206P332MR_C347376'),
    'main_3v3_buck': ('JLC-MCP-Power', 'SY8089A1AAC'),
    'chip_antenna_2g4': None,  # keep placeholder for now
    'swdio_direction_buffer': None,  # no JLC part
    'nreset_open_drain_nmos': None,  # 2N7002
    'input_efuse': ('JLC-MCP-Misc', 'MNCP380HSN05AAT1G'),
}

# Cache loaded JLC library content
JLC_LIBS = {}
for lib_file in SYM_DIR.glob('JLC-MCP-*.kicad_sym'):
    JLC_LIBS[lib_file.stem] = lib_file.read_text(encoding='utf-8')


def extract_symbol_units(lib_content: str, sym_name: str) -> tuple[str, list]:
    """Extract the main symbol definition and all derived unit symbols."""
    main_def = None
    derived = []

    for m in re.finditer(r'\(symbol\s+\"([^\"]+)\"', lib_content):
        name = m.group(1)
        start = m.start()
        depth = 0
        for i in range(start, len(lib_content)):
            if lib_content[i] == '(':
                depth += 1
            elif lib_content[i] == ')':
                depth -= 1
                if depth == 0:
                    body = lib_content[start:i+1]
                    if name == sym_name:
                        main_def = body
                    elif re.match(rf'{re.escape(sym_name)}_\d+_\d+$', name):
                        derived.append((name, body))
                    break

    return main_def, derived


def process_sheet(sch_path: Path, dry_run: bool = False) -> int:
    """Process one schematic sheet, replacing AIAgent symbols with JLC-MCP."""
    content = sch_path.read_text(encoding='utf-8')
    original = content

    # Find lib_symbols section
    lib_start = content.find('(lib_symbols')
    if lib_start < 0:
        return 0

    # Find the matching closing paren
    depth = 0
    lib_end = lib_start
    for i in range(lib_start, len(content)):
        if content[i] == '(':
            depth += 1
        elif content[i] == ')':
            depth -= 1
            if depth == 0:
                lib_end = i + 1
                break

    lib_section = content[lib_start:lib_end]
    replacements = 0

    # For each AIAgent symbol found in this sheet
    for ai_match in re.finditer(r'\(symbol\s+\"AIAgent:([^\"]+)\"', lib_section):
        ai_sym = ai_match.group(1)
        full_ai_id = f'AIAgent:{ai_sym}'

        # Check symbol map
        target = SYMBOL_MAP.get(ai_sym)
        if target is None:
            # Try role-based matching from sheet filename
            sheet_role = sch_path.stem.split('_', 1)[1] if '_' in sch_path.stem else ''
            target = ROLE_TO_JLC.get(sheet_role)

        if target is None:
            continue

        jlc_lib, jlc_sym = target
        if jlc_lib not in JLC_LIBS:
            print(f'    Library {jlc_lib} not found, skipping {ai_sym}')
            continue

        main_def, derived_units = extract_symbol_units(JLC_LIBS[jlc_lib], jlc_sym)
        if main_def is None:
            print(f'    Symbol {jlc_sym} not found in {jlc_lib}, skipping')
            continue

        # Find the full AIAgent stub definition
        ai_start = ai_match.start()
        depth2 = 0
        ai_end = ai_start
        for i in range(ai_start, len(lib_section)):
            if lib_section[i] == '(':
                depth2 += 1
            elif lib_section[i] == ')':
                depth2 -= 1
                if depth2 == 0:
                    ai_end = i + 1
                    break

        old_stub = lib_section[ai_start:ai_end]

        # Build replacement: rename JLC symbol with library prefix
        new_full_id = f'{jlc_lib}:{jlc_sym}'
        new_def = main_def.replace(f'(symbol "{jlc_sym}"', f'(symbol "{new_full_id}"', 1)

        # Add derived units with prefixed names
        for deriv_name, deriv_body in derived_units:
            prefixed = f'{jlc_lib}:{deriv_name}'
            renamed = deriv_body.replace(f'(symbol "{deriv_name}"', f'(symbol "{prefixed}"', 1)
            new_def += '\n' + renamed

        # Replace stub with full definition
        lib_section = lib_section.replace(old_stub, new_def.strip(), 1)
        pin_count = main_def.count('(pin ')
        print(f'    {full_ai_id} -> {new_full_id}: {pin_count} pins')
        replacements += 1

        # Also update the symbol instance reference in the sheet
        # KiCad V10 format: (symbol (lib_id "AIAgent:XXX") ...)
        # Replace with: (symbol (lib_id "JLC-MCP-XXX:YYY") ...)
        new_jlc_lib_id = f'{jlc_lib}:{jlc_sym}'
        content = content.replace(
            f'(lib_id "AIAgent:{ai_sym}")',
            f'(lib_id "{new_jlc_lib_id}")'
        )

    if replacements > 0:
        new_content = content[:lib_start] + lib_section + content[lib_end:]
        if not dry_run:
            # Backup
            bak = sch_path.with_suffix('.kicad_sch.bak')
            if not bak.exists():
                shutil.copy2(sch_path, bak)
            sch_path.write_text(new_content, encoding='utf-8')
        return replacements

    return 0


def main():
    dry_run = '--dry-run' in sys.argv
    total = 0
    sheets = sorted(SCH_DIR.glob('*.kicad_sch'))
    # Skip main schematic (it only has sheet references)
    main_sch = SCH_DIR / 'nexdap_dual_chip_cmsis_dap.kicad_sch'

    print(f'Processing {len(sheets)} sheets...')
    print(f'JLC libraries loaded: {list(JLC_LIBS.keys())}')
    print()

    for sch_path in sheets:
        if sch_path.name == main_sch.name:
            continue
        n = process_sheet(sch_path, dry_run=dry_run)
        if n > 0:
            print(f'  {sch_path.name}: {n} replacement(s)')
        total += n

    print(f'\nTotal replacements: {total}')
    if dry_run:
        print('DRY RUN - no files modified')
    else:
        print('Done. Backups saved as .kicad_sch.bak')


if __name__ == '__main__':
    main()
