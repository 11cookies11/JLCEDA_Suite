"""Comprehensive post-process: embed all JLC-MCP symbols + fix ALL footprints to KiCad built-in.

Strategy:
1. Embed all JLC-MCP symbol definitions into each sub-sheet's lib_symbols
2. Replace ALL JLC-MCP footprint references with KiCad built-in equivalents
3. Fix USB-C footprint, test points
"""
import re, json, shutil, sys
from pathlib import Path

SCH_DIR = Path('.where/nexdap-rp2040-esp32c3-isolated-wireless-cmsis-dap/kicad-output-v2/nexdap_dual_chip_cmsis_dap')
SYM_DIR = Path('.where/nexdap-rp2040-esp32c3-isolated-wireless-cmsis-dap/libraries/symbols')

# Map JLC-MCP footprints to KiCad built-in
JLC_FP_TO_KICAD = {
    'JLC-MCP:R0603': 'Resistor_SMD:R_0603_1608Metric',
    'JLC-MCP:R0402': 'Resistor_SMD:R_0402_1005Metric',
    'JLC-MCP:C0603': 'Capacitor_SMD:C_0603_1608Metric',
    'JLC-MCP:C0805': 'Capacitor_SMD:C_0805_2012Metric',
    'JLC-MCP:C0402': 'Capacitor_SMD:C_0402_1005Metric',
    'JLC-MCP:LED0603-RD': 'LED_SMD:LED_0603_1608Metric',
    'JLC-MCP:LQFN-56_L7.0-W7.0-P0.4-EP': 'Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm',
    'JLC-MCP:QFN-32_L5.0-W5.0-P0.50-TL-EP3.7': 'Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm',
    'JLC-MCP:TSOT-23-5_L2.9-W1.6-P0.95-LS2.8-BR': 'Package_TO_SOT_SMD:SOT-23-5',
    'JLC-MCP:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR': 'Package_TO_SOT_SMD:SOT-23-5',
    'JLC-MCP:SOT-23-3_L3.0-W1.7-P0.95-LS2.9-BR': 'Package_TO_SOT_SMD:SOT-23',
    'JLC-MCP:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR': 'Package_TO_SOT_SMD:SOT-23-6',
    'JLC-MCP:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL': 'Package_TO_SOT_SMD:SOT-23-6',
    'JLC-MCP:SOIC-16_L10.3-W7.5-P1.27-LS10.3-BL': 'Package_SO:SOIC-16W_10.3x7.5mm_P1.27mm',
    'JLC-MCP:SOP-8_L4.9-W3.9-P1.27-LS6.0-BL': 'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm',
    'JLC-MCP:PWRM-TH_B0505S-1WR3': 'Converter_DCDC:Converter_DCDC_SIP-4_THT',
    'JLC-MCP:USB-C-SMD_TYPE-C16PIN': 'Connector_USB:USB_C_Receptacle_USB2.0',
    'USB-C_SMD': 'Connector_USB:USB_C_Receptacle_USB2.0',
    'JLC-MCP:SMB_L4.6-W3.6-LS5.3-RD': 'Diode_SMD:D_SMB',
    'JLC-MCP:CRYSTAL-SMD_4P-L3.2-W2.5-BL': 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm',
}


def load_all_jlc_symbols() -> dict:
    """Load all JLC-MCP symbol definitions keyed by (lib_stem, sym_name)."""
    symbols = {}
    for lib_file in sorted(SYM_DIR.glob('JLC-MCP-*.kicad_sym')):
        lib_stem = lib_file.stem
        content = lib_file.read_text(encoding='utf-8')
        for m in re.finditer(r'\(symbol\s+\"([^\"]+)\"', content):
            name = m.group(1)
            if re.search(r'_\d+_\d+$', name):
                continue  # skip derived, we'll re-extract them
            start = m.start()
            depth = 0
            for i in range(start, len(content)):
                if content[i] == '(':
                    depth += 1
                elif content[i] == ')':
                    depth -= 1
                    if depth == 0:
                        body = content[start:i+1]
                        # Also find derived units
                        derived = []
                        for dm in re.finditer(rf'\(symbol\s+\"({re.escape(name)}_\d+_\d+)\"', content):
                            d_name = dm.group(1)
                            d_start = dm.start()
                            d_depth = 0
                            for j in range(d_start, len(content)):
                                if content[j] == '(':
                                    d_depth += 1
                                elif content[j] == ')':
                                    d_depth -= 1
                                    if d_depth == 0:
                                        derived.append((d_name, content[d_start:j+1]))
                                        break
                        symbols[(lib_stem, name)] = (body, derived)
                        break
    return symbols


def process_sheet(sch_path: Path, jlc_symbols: dict, dry_run: bool = False) -> tuple:
    """Fix one schematic sheet."""
    content = sch_path.read_text(encoding='utf-8')
    embedded = 0
    fp_fixed = 0
    lib_fixed = 0

    # Step 1: Fix footprint references throughout the file
    for old, new in JLC_FP_TO_KICAD.items():
        count = content.count(old)
        if count > 0:
            content = content.replace(old, new)
            fp_fixed += count

    # Step 2: Find JLC-MCP symbol instances and embed their definitions
    jlc_refs = set()
    for m in re.finditer(r'\(lib_id\s+\"(JLC-MCP-\w+):([^\"]+)\"', content):
        jlc_refs.add((m.group(1), m.group(2)))

    if jlc_refs:
        # Find lib_symbols section
        lib_start = content.find('(lib_symbols')
        if lib_start >= 0:
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

            for lib_stem, sym_name in sorted(jlc_refs):
                key = (lib_stem, sym_name)
                if key not in jlc_symbols:
                    # Search all libs
                    found = False
                    for (ls, sn), val in jlc_symbols.items():
                        if sn == sym_name:
                            key = (ls, sn)
                            found = True
                            break
                    if not found:
                        continue

                main_def, derived = jlc_symbols[key]
                full_id = f'{lib_stem}:{sym_name}'

                # Check if already embedded
                if f'(symbol "{full_id}"' in content[lib_start:lib_end]:
                    continue

                # Rename main definition
                renamed = main_def.replace(
                    f'(symbol "{sym_name}"',
                    f'(symbol "{full_id}"',
                    1
                )

                # Add derived units
                for d_name, d_body in derived:
                    d_prefixed = f'{lib_stem}:{d_name}'
                    renamed += '\n' + d_body.replace(
                        f'(symbol "{d_name}"',
                        f'(symbol "{d_prefixed}"',
                        1
                    )

                # Insert before closing paren of lib_symbols
                insertion_point = lib_end - 1
                content = content[:insertion_point] + renamed.strip() + '\n' + content[insertion_point:]
                lib_end += len(renamed.strip()) + 1
                embedded += 1

    # Step 3: Fix symbol lib_id references (change JLC-MCP lib to match embedded)
    # This handles the case where the instance references a different JLC-MCP lib
    # than what we embedded - update instance to match

    if embedded > 0 and not dry_run:
        bak = sch_path.with_suffix('.kicad_sch.bak3')
        if not bak.exists():
            shutil.copy2(sch_path, bak)
        sch_path.write_text(content, encoding='utf-8')

    return embedded, fp_fixed


def main():
    dry_run = '--dry-run' in sys.argv
    jlc_symbols = load_all_jlc_symbols()
    print(f'Loaded {len(jlc_symbols)} JLC-MCP symbols:')
    for (lib, name) in sorted(jlc_symbols.keys()):
        pins = jlc_symbols[(lib, name)][0].count('(pin ')
        print(f'  {lib}:{name} ({pins} pins)')

    print()

    total_embedded = 0
    total_fp = 0

    for sch_path in sorted(SCH_DIR.glob('*.kicad_sch')):
        if sch_path.name == 'nexdap_dual_chip_cmsis_dap.kicad_sch':
            # Main sheet: only fix footprints (no symbols to embed)
            content = sch_path.read_text(encoding='utf-8')
            fp_count = 0
            for old, new in JLC_FP_TO_KICAD.items():
                c = content.count(old)
                if c > 0:
                    content = content.replace(old, new)
                    fp_count += c
            if fp_count > 0 and not dry_run:
                sch_path.write_text(content, encoding='utf-8')
            total_fp += fp_count
            if fp_count > 0:
                print(f'  {sch_path.name}: {fp_count} footprint fixes')
            continue

        emb, fp = process_sheet(sch_path, jlc_symbols, dry_run)
        total_embedded += emb
        total_fp += fp
        if emb > 0 or fp > 0:
            parts = []
            if emb > 0:
                parts.append(f'{emb} symbols embedded')
            if fp > 0:
                parts.append(f'{fp} footprint fixes')
            print(f'  {sch_path.name}: {", ".join(parts)}')

    print(f'\nTotal: {total_embedded} symbols embedded, {total_fp} footprint fixes')

    # Fix execution plan footprints
    ep_path = SCH_DIR / 'kicad-execution-plan.json'
    if ep_path.exists():
        with open(ep_path, 'r', encoding='utf-8') as f:
            ep = json.load(f)
        ep_fixed = 0
        for sym in ep.get('symbols', []):
            old_fp = sym.get('footprint', '')
            if old_fp in JLC_FP_TO_KICAD:
                sym['footprint'] = JLC_FP_TO_KICAD[old_fp]
                ep_fixed += 1
        if ep_fixed > 0 and not dry_run:
            with open(ep_path, 'w', encoding='utf-8') as f:
                json.dump(ep, f, indent=2, ensure_ascii=False)
        print(f'  Fixed {ep_fixed} footprints in execution plan')

    if dry_run:
        print('\nDRY RUN - no files modified')


if __name__ == '__main__':
    main()
