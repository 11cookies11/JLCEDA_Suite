# 07 Part Resolution Notes

Status: Draft

## Tool Status

`hwtool agent jlc search` currently starts but JLC/EasyEDA search returns HTTP 403 in this environment.

Observed command result:

```text
ERROR:root:JLCPCB search failed: HTTP Error 403: Forbidden
```

The missing Python dependency `easyeda2kicad` was installed locally so the command can run. The remaining blocker is the upstream search request being rejected.

Because of this, automated search is still not the source of truth for new selections in this environment. Rev A candidate selections were applied after manual/web lookup and then verified by `resolve-symbols`.

## Workflow Execution Status

The project is now using the agent workflow layer for part-selection work.

Commands used:

```powershell
python hwtool_entry.py agent workflow run --project examples\ai-memory-badge-v1 --template lcsc_selection_v1 --timeout 120
python hwtool_entry.py agent workflow status --project examples\ai-memory-badge-v1
```

Current workflow state:

- active workflow: none
- status: completed
- initial selection tasks: 72
- pending selection tasks after Rev A candidate selection: 0
- explicitly LCSC-exempt components: 16
- current task: none

Low-risk commodity selections were applied through `agent run set_selected_part` for passives, buttons, the USB-C connector, the 4-pin header, and the green status LED. Those selections are present in the resolved model overlay and allow the workflow task count to decrease.

The workflow now uses conservative explicit opt-out rules for non-LCSC items. A component is exempt from LCSC selection only when it has a machine-readable marker such as `bom_exclude: true`, `part_source: "internal"`, or `assembly: "dnp"`. Descriptive text such as `value: "DNP"` or a `test_point` role does not skip LCSC by itself.

Rev A controller decision:

- `U1` is selected as `ESP32-S3R8`, LCSC `C2913194`.
- `U5` external PSRAM is marked `assembly: "dnp"` because ESP32-S3R8 includes in-package 8 MB PSRAM.
- `U4` external SPI flash remains required.

Additional selected Rev A ICs:

- `U2` is selected as `AP2112K-3.3TRG1`, LCSC `C51118`.
- `U3` is selected as `MCP73831T-2ACI/OT`, LCSC `C424093`.
- `U4` is selected as `W25Q128JVSIQ`, LCSC `C97521`.

Additional selected standard parts:

- `U6` USB ESD is selected as `USBLC6-2SC6`, LCSC `C7519`.
- `D2` red recording LED is selected as `KT-0603R`, LCSC `C2286`.
- Standard selected resistors now cover `R1`, `R2`, `R3`, `R8`, `R9`, `R10`, `R11`, `R12`, `R13`, `R17`, and `R18`.

Rev A mechanical, RF, audio, and haptics candidates are selected in the source model:

- `J2` JST PH battery connector, LCSC `C295747`.
- `J3` U.FL/IPEX RF connector, LCSC `C88374`.
- `Y1` 40 MHz 3225 crystal, LCSC `C5380316`.
- `C8`/`C9` 18 pF C0G load capacitors, LCSC `C1647`.
- `J5` microSD socket, LCSC `C125617`.
- `MK1`/`MK2` I2S MEMS microphones, LCSC `C966933`.
- `SW4` mute slide switch, LCSC `C431541`.
- `Q1` vibration motor NMOS, LCSC `C20917`.
- `M1` 3 V flat vibration motor, LCSC `C2759981`.

Non-LCSC/internal handling:

- `TP1` through `TP12` are explicit `part_source: "internal"` and `bom_exclude: true` items.
- They use the project-local `TP_1P` symbol and `TP-SMD_1P` footprint in `libraries/`.
- Intentional DNP/reserve components may still carry an LCSC ID when a CAD library is useful, but assembly remains controlled by `assembly: "dnp"`.

Important workflow rule:

`lcsc_selection_v1` treats unresolved components as needing a `selected_part.lcsc_id` unless they are explicitly marked as non-LCSC. This keeps real BOM parts on the EasyEDA/LCSC path and prevents accidental skipping of connectors, ICs, passives, switches, and other assembled components.

Validation/export note:

`build-ir` succeeds and `validate-ir` has 0 errors and 0 warnings after source-level test point classification. KiCad export succeeds and generates the root schematic, ten hierarchical sheets, PCB file, and local copied libraries under `output/ai_memory_badge_v1/`.

## Candidate Parts Found By Web Lookup

These are candidate parts to verify in LCSC/JLCPCB manually or after the CLI search path works again.

| Block | Candidate | LCSC | Notes |
| --- | --- | --- | --- |
| ESP32-S3 bare SoC | ESP32-S3R8 | C2913194 | QFN-56, includes in-package PSRAM class memory; may change external PSRAM plan |
| ESP32-S3 bare SoC | ESP32-S3FN8 | C2913196 | QFN-56-EP, includes in-package flash; may reduce external flash need |
| ESP32-S3 bare SoC | ESP32-S3 | C2913192 | Base bare SoC; likely best match if using external flash and external PSRAM |
| SPI flash | Winbond W25Q128JVSIQ | C97521 / C113767 | 128 Mbit / 16 MB SPI NOR flash candidate |
| LiPo charger | Microchip MCP73831T-2ACI/OT | C424093 | SOT-23-5 single-cell Li-ion/LiPo linear charger |
| 3.3 V regulator | Diodes AP2112K-3.3TRG1 | C51118 | 600 mA 3.3 V LDO candidate |
| USB-C connector | HCTL HC-TYPE-C-16P-01B | C2894898 | 16-pin USB-C receptacle candidate |
| USB-C connector | SHOU HAN TYPE-C 16P(073) | C668624 | Alternate 16-pin USB-C receptacle candidate |
| USB-C connector | Kinghelm KH-TYPE-C-16P | C709357 | Alternate 16-pin USB-C receptacle candidate |

## ESP32-S3 Variant Decision

The current circuit model assumes:

- ESP32-S3 bare SoC
- external SPI flash
- external PSRAM

Before committing to a schematic, choose one of these paths:

### Option A: Base ESP32-S3 + External Flash + External PSRAM

Best matches the current model.

Pros:

- maximum control over memory choices
- keeps memory architecture explicit in schematic
- good learning path for bare-chip design

Cons:

- more routing risk
- more parts
- memory compatibility must be checked carefully

### Option B: ESP32-S3R8 + External Flash

Uses in-package PSRAM class memory and keeps external flash.

Pros:

- simplifies PSRAM routing
- still keeps external flash flexible
- likely better for Rev A bring-up than fully external memory

Cons:

- model must remove or DNP external PSRAM
- some GPIO/memory pins may be unavailable or constrained
- ESP-IDF configuration must match R8 memory mode

### Option C: ESP32-S3FN8

Uses in-package flash.

Pros:

- simplest boot path
- fewer external memory parts

Cons:

- less aligned with the current external memory model
- may limit flexibility
- still need to confirm PSRAM availability for audio buffering

## Current Recommendation

Use `ESP32-S3R8` for Rev A and keep the external PSRAM footprint as DNP reserve.

Reasoning:

- It remains a bare-chip design.
- It reduces one of the highest-risk routing areas.
- 8 MB PSRAM is useful for audio buffering and future local VAD/wake-word experiments.
- External SPI flash can still provide firmware/storage flexibility.

If strict full external-memory design is desired, keep the base `ESP32-S3` candidate and retain both `U4` flash and `U5` PSRAM.

## Verification Searches

When JLC search works again, verify these exact queries:

```powershell
hwtool agent jlc search "ESP32-S3R8" -n 5
hwtool agent jlc search "ESP32-S3 C2913192" -n 5
hwtool agent jlc search "W25Q128JVSIQ" -n 5
hwtool agent jlc search "I2S MEMS microphone ICS-43434" -n 10
hwtool agent jlc search "microSD socket card detect" -n 10
hwtool agent jlc search "MCP73831T-2ACI/OT" -n 5
hwtool agent jlc search "AP2112K-3.3TRG1" -n 5
hwtool agent jlc search "USB-C 16P receptacle" -n 10
hwtool agent jlc search "U.FL IPEX connector" -n 10
hwtool agent jlc search "ATECC608" -n 5
```

## Do Not Lock Yet

Do not write final `selected_part` entries until:

- LCSC/JLCPCB search confirms availability.
- Symbols and footprints can be downloaded or resolved.
- ESP32-S3 memory variant choice is finalized.
- The chosen microphone package and sound-port orientation match the mechanical plan.
- USB-C and microSD footprints are reviewed against the real connector drawings.
