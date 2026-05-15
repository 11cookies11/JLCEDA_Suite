"""Inject full JLC-MCP symbol definitions into a KiCad schematic.

The pipeline generates stubs (2-pin placeholders) in the lib_symbols section.
This script replaces those stubs with the full symbol definitions from the
upgraded JLC-MCP library files, keeping the library-prefixed symbol names.
"""
import re
from pathlib import Path

PROJ_DIR = Path('.where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1')
SCH_PATH = PROJ_DIR / 'nema23_industrial_stepper_driver_v0_1.kicad_sch'
SYM_DIR = PROJ_DIR / 'libraries' / 'symbols'

sch = SCH_PATH.read_text(encoding='utf-8')

# Find the lib_symbols section
lib_start = sch.find('(lib_symbols')
if lib_start < 0:
    print('No lib_symbols section found!')
    exit(1)

depth = 0
lib_end = lib_start
for i in range(lib_start, len(sch)):
    if sch[i] == '(':
        depth += 1
    elif sch[i] == ')':
        depth -= 1
        if depth == 0:
            lib_end = i + 1
            break

lib_section = sch[lib_start:lib_end]
print(f'lib_symbols section: {len(lib_section)} chars')

# Collect all JLC-MCP library files
lib_files = sorted(SYM_DIR.glob('JLC-MCP-*.kicad_sym'))

replaced = 0
for lib_file in lib_files:
    lib_name = lib_file.stem  # e.g., JLC-MCP-MCUs
    lib_content = lib_file.read_text(encoding='utf-8')

    # Find all symbols in this library
    for sym_match in re.finditer(r'\(symbol\s+\"([^\"]+)\"', lib_content):
        sym_name = sym_match.group(1)
        # Skip derived symbols
        if re.search(r'_\d+_\d+$', sym_name):
            continue

        full_lib_id = f'{lib_name}:{sym_name}'

        # Check if this symbol is referenced in lib_symbols (as a stub)
        if f'(symbol "{full_lib_id}"' not in lib_section:
            continue

        # Extract the full symbol definition from the library
        sym_start = sym_match.start()
        depth2 = 0
        sym_end = sym_start
        for j in range(sym_start, len(lib_content)):
            if lib_content[j] == '(':
                depth2 += 1
            elif lib_content[j] == ')':
                depth2 -= 1
                if depth2 == 0:
                    sym_end = j + 1
                    break

        full_sym_def = lib_content[sym_start:sym_end]

        # Extract derived symbols too (e.g., STM32G431CBT6_0_1)
        derived = []
        for deriv_match in re.finditer(rf'\(symbol\s+\"{re.escape(sym_name)}_\d+_\d+\"', lib_content):
            d_start = deriv_match.start()
            depth3 = 0
            d_end = d_start
            for j in range(d_start, len(lib_content)):
                if lib_content[j] == '(':
                    depth3 += 1
                elif lib_content[j] == ')':
                    depth3 -= 1
                    if depth3 == 0:
                        d_end = j + 1
                        break
            deriv_name = deriv_match.group(1)
            derived.append((deriv_name, lib_content[d_start:d_end]))

        # Find the stub in lib_section
        stub_idx = lib_section.find(f'(symbol "{full_lib_id}"')
        if stub_idx < 0:
            continue

        # Find end of this stub
        depth4 = 0
        stub_end = stub_idx
        for j in range(stub_idx, len(lib_section)):
            if lib_section[j] == '(':
                depth4 += 1
            elif lib_section[j] == ')':
                depth4 -= 1
                if depth4 == 0:
                    stub_end = j + 1
                    break

        old_stub = lib_section[stub_idx:stub_end]

        # Build replacement: rename symbol to have library prefix
        # In the .kicad_sym file: (symbol "STM32G431CBT6" ...)
        # In the .kicad_sch file: (symbol "JLC-MCP-MCUs:STM32G431CBT6" ...)
        new_content = full_sym_def.replace(f'(symbol "{sym_name}"', f'(symbol "{full_lib_id}"', 1)

        # Add derived symbols with prefixed names
        for deriv_name, deriv_def in derived:
            prefixed_deriv_name = f'{lib_name}:{deriv_name}'
            deriv_def_renamed = deriv_def.replace(f'(symbol "{deriv_name}"', f'(symbol "{prefixed_deriv_name}"', 1)
            new_content += '\n' + deriv_def_renamed

        # Remove trailing newline artifacts
        new_content = new_content.strip()

        # Replace stub with full definition
        lib_section = lib_section.replace(old_stub, new_content, 1)
        replaced += 1
        pin_count = full_sym_def.count('(pin ')
        print(f'  {full_lib_id}: {len(old_stub)} -> {len(new_content)} chars, {pin_count} pins')

# Build new schematic
new_sch = sch[:lib_start] + lib_section + sch[lib_end:]

# Validate: check for duplicate symbol names
symbols = re.findall(r'\(symbol\s+\"([^\"]+)\"', new_sch)
from collections import Counter
dupes = {n: c for n, c in Counter(symbols).items() if c > 1}
if dupes:
    print(f'\nWARNING: {len(dupes)} duplicate names still exist!')
    for n, c in list(dupes.items())[:5]:
        print(f'  "{n}": {c}x')
    # Remove duplicates — keep only first occurrence of each
    # This is complex for nested structures; let's just report it
else:
    SCH_PATH.write_text(new_sch, encoding='utf-8')
    print(f'\nReplaced {replaced} stubs, no duplicates')
    print(f'New lib_symbols: {len(lib_section)} chars (was {len(sch[lib_start:lib_end])})')
    print(f'New schematic: {len(new_sch)} chars')
