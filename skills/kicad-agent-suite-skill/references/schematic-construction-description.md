# Schematic Construction Description (SCD)

This reference defines the strict human-readable text format used to describe a theory schematic before any drawing or execution step.

Use this format when the user wants:

- a readable circuit construction description
- a structured intermediate artifact before `CircuitModel`
- a text source for `schemdraw`, Graphviz, or execution-plan synthesis

## Purpose

SCD is a strict, block-based textual representation of a schematic intent.

It is intentionally narrower than free-form chat text:

- easy for humans to read
- easy for the agent to validate
- easy for downstream parsers to convert into topology, drawings, or actions

## Required file shape

```text
# Title: <string>
# Version: <string>
# Purpose: <string>

[Block: <block_name>]
- Role: <string>
- Scope: <string>

<statement>
<statement>

[Notes]
- <note>

[Checks]
- <check>
```

## Strict syntax

## Formal parsing model

The parser should read the document in four phases:

1. header
2. block start
3. block body
4. optional notes and checks

If a line does not match the current phase, the parser should emit a structured error instead of inferring intent.

### Token classes

- `HEADER_LINE` matches `^# (Title|Version|Purpose): .+$`
- `BLOCK_LINE` matches `^\[Block: .+\]$`
- `SECTION_LINE` matches `^\[(Notes|Checks)\]$`
- `BULLET_LINE` matches `^- .+$`
- `STATEMENT_LINE` matches one of the allowed connection forms

### Core terminals

- `IDENT` is a non-empty token without whitespace
- `NET` is an `IDENT` that may start with `+`
- `DEVICE` is an `IDENT`
- `PIN` is an `IDENT`
- `VALUE` is a free token sequence with no leading or trailing whitespace

### EBNF

```ebnf
document        = header , block+ ;
header          = title-line , version-line , purpose-line ;
title-line      = "# Title: " , text ;
version-line    = "# Version: " , text ;
purpose-line    = "# Purpose: " , text ;

block           = block-line , role-line , scope-line , statement+ , optional-sections ;
block-line      = "[Block: " , text , "]" ;
role-line       = "- Role: " , text ;
scope-line      = "- Scope: " , text ;

statement       = net-to-pin
                | pin-to-net
                | net-to-ground-via-component
                | net-to-net-via-component
                | net-to-pin-to-net ;

net-to-pin                  = net , " -> " , device-pin ;
pin-to-net                  = device-pin , " -> " , net ;
net-to-ground-via-component = net , " -> " , component-value , " -> " , "GND" ;
net-to-net-via-component    = net , " -> " , component-value , " -> " , net ;
net-to-pin-to-net           = net , " -> " , device-pin , " -> " , net ;

optional-sections = { notes-section | checks-section } ;
notes-section     = "[Notes]" , bullet+ ;
checks-section    = "[Checks]" , bullet+ ;

bullet            = "- " , text ;
device-pin        = device , "." , pin ;
component-value    = component , [ whitespace , value ] ;
component         = ident ;
net               = ident ;
device            = ident ;
pin               = ident ;
value             = text ;
text              = ? any non-empty text without leading or trailing spaces ? ;
whitespace        = " " ;
ident             = ? non-empty non-whitespace token ? ;
```

### Canonical constraints

- A document must contain exactly one header at the top.
- A block must contain `Role` and `Scope` lines in that order.
- A block must contain at least one statement.
- `Notes` and `Checks` are optional, but if present they must be section headers followed by bullet lines.
- Blank lines are allowed between major sections only.
- Statements are not allowed inside `Notes` or `Checks`.
- Bullet lines are not allowed inside the main statement area.

### Statement normalization

Before parsing downstream, the agent should normalize these cases:

- collapse repeated spaces around `->`
- trim trailing whitespace
- preserve case for device and pin names
- preserve leading `+` in power nets
- preserve value text attached to components

## Strict syntax

### Header

The file must begin with these three lines in this order:

```text
# Title: ...
# Version: ...
# Purpose: ...
```

### Block

Each functional block must use:

```text
[Block: <block_name>]
- Role: <string>
- Scope: <string>
```

Each block should contain at least one connection statement.

### Connection statements

Only the following statement forms are allowed:

```text
NET -> DEVICE.PIN
DEVICE.PIN -> NET
NET -> COMPONENT VALUE -> GND
NET_A -> COMPONENT VALUE -> NET_B
NET -> DEVICE.PIN -> NET
```

Rules:

- one statement per line
- no free-form prose inside connection lines
- always keep explicit pin names when a pin is being referenced
- keep component values next to the component name when relevant
- if a component is unnamed in the source intent, create a stable placeholder such as `C1`, `R2`, or `U3`
- if a statement cannot be matched to one of the allowed forms, return a syntax error

### Statement examples

Valid:

```text
VBUS -> +5V_USB
LDO.OUT -> +3V3
CC1 -> R1 5.1k -> GND
ESP32-C3.VDD_SPI -> +3V3
```

Invalid:

```text
USB power to 3V3
CC1 and CC2 -> GND
VDD_SPI to 3V3 with 1uF
```

## Identifier rules

### Net names

Allowed examples:

- `+5V_USB`
- `+3V3`
- `GND`
- `USB_DP`
- `USB_DM`

Rules:

- no spaces
- may contain `+`, `-`, `_`, `/`, `.`
- power nets should usually start with `+`

### Device names

Allowed examples:

- `LDO`
- `ESP32-C3`
- `USB-C`
- `R1`
- `C5`

Rules:

- no spaces
- may contain `-` and `_`

### Pin names

Use the explicit form:

```text
DEVICE.PIN
```

Examples:

- `LDO.IN`
- `LDO.OUT`
- `ESP32-C3.VDD`
- `ESP32-C3.VDD_SPI`
- `ESP32-C3.USB_DP`

## Optional sections

### Notes

Use `[Notes]` for:

- design intent
- placement hints
- selection rationale
- non-functional constraints

### Checks

Use `[Checks]` for:

- human review items
- electrical sanity checks
- topology verification points

## Recommended block ordering

For a typical mixed USB-power-MCU design, use this order:

1. `USB Type-C`
2. `Input Protection`
3. `Input Filter`
4. `Regulator`
5. `Main Power Rail`
6. `Local Decoupling`
7. `MCU Interface`
8. `Debug / Programming`

Keep each block small enough to review independently.

## Example

```text
# Title: ESP32-C3 USB Power Baseboard
# Version: v1
# Purpose: USB-C power input, LDO conversion to 3.3V, and local MCU decoupling

[Block: USB Type-C]
- Role: Power input and USB data entry
- Scope: USB-C connector, CC pull-downs, USB data lines

VBUS -> +5V_USB
GND -> GND
D+ -> ESP32-C3.USB_DP
D- -> ESP32-C3.USB_DM
CC1 -> R1 5.1k -> GND
CC2 -> R2 5.1k -> GND

[Notes]
- CC1 and CC2 must both be present for USB-C power detection.

[Checks]
- CC1 exists
- CC2 exists
- D+ and D- target the correct USB pins

[Block: Input Filter]
- Role: Decouple and stabilize the 5V input rail
- Scope: input capacitors and LDO input

+5V_USB -> C1 0.1uF -> GND
+5V_USB -> C2 10uF -> GND
+5V_USB -> LDO.IN

[Notes]
- Input capacitors should stay close to the USB input and LDO input.

[Checks]
- C1 value is correct
- C2 value is correct
- LDO.IN is tied to +5V_USB

[Block: LDO]
- Role: Convert 5V to 3.3V
- Scope: LDO body and output decoupling

LDO.GND -> GND
LDO.OUT -> +3V3

[Notes]
- Verify the LDO can supply the ESP32-C3 peak current.

[Checks]
- LDO.OUT is stable
- Output current margin is sufficient

[Block: 3V3 Main Rail]
- Role: Supply the MCU main power pins
- Scope: MCU power pins and main decoupling

+3V3 -> ESP32-C3.VDD
+3V3 -> C3 0.1uF -> GND
+3V3 -> C4 10uF -> GND

[Notes]
- Main decoupling should be close to the MCU power pins.

[Checks]
- VDD decoupling is complete
- Capacitors are placed near the chip

[Block: VDD_SPI Local Decoupling]
- Role: Provide a local stable supply for VDD_SPI
- Scope: VDD_SPI pin and its local decoupling capacitor

+3V3 -> ESP32-C3.VDD_SPI
+3V3 -> C5 1uF -> GND

[Notes]
- This is a local power branch, not an ordinary signal line.

[Checks]
- VDD_SPI is explicitly tied to 3V3
- Local decoupling exists
```

## Agent behavior

When the user asks for theory schematic generation, the agent should:

1. produce or normalize SCD first
2. validate blocks, statements, and identifiers
3. summarize the SCD in human-readable form
4. only then synthesize `CircuitModel` or any drawing/execution artifact

If the agent detects a parsing error, it should return:

- error code
- line number when available
- offending line text
- a short corrective hint

If the input violates the SCD syntax, the agent should return structured errors instead of guessing missing structure.
