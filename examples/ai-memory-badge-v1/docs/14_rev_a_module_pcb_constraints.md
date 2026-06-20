# Rev A Module PCB Constraints

## ESP32-S3-WROOM Antenna

- Place U1 on the top PCB edge with the PCB antenna facing outward.
- Do not pour copper under the antenna keep-out.
- Keep battery, NFC antenna, metal back clip, screws, e-paper FPC and enclosure metal away from the antenna front and underside.
- Do not let a metal badge clip press directly over the antenna area.

## Microphones

- Place MK1/MK2 acoustic ports on the outward-facing top or side badge edge.
- Align bottom acoustic ports to enclosure sound holes.
- Keep ports clear of ribs, glue, lanyard holes, screw bosses, battery, display, back clip and dust mesh blockage.
- Keep motor, high-current power paths and RF antenna away from the microphones.
- Keep MIC_3V3 quiet and physically switchable.

## NFC

- Put the NFC antenna on the back side or a defined back-side antenna area.
- Keep it away from large copper, battery protection PCB and metal clip.
- Do not overlap NFC antenna with magnetic/pogo charging reserve.
- Reserve access for antenna matching and tuning measurements.

## USB And Storage

- Place USB ESD protection close to the Type-C connector.
- Route USB D+/D- short, paired and with minimal vias.
- Place microSD at an accessible edge and keep SPI traces short.
- Add ESD/structure review for exposed microSD slot.

## Display And Buttons

- Place J6 where the 2.13 inch e-paper FPC or adapter board can reach the front display area.
- Side buttons must match the enclosure action direction and silkscreen.
- MUTE switch silkscreen and enclosure label must match the actual MIC ON / MIC OFF electrical state.

## Test Access

- Keep Rev A test points accessible for oscilloscope/logic-analyzer probing.
- Required access includes USB_5V, BAT_P, SYS_3V3, GND, EN, BOOT, UART, USB, I2S, MIC_3V3, SD, SW_MUTE, CHG_STAT, EPD, NFC_GPO, REC, MARK and MODE.
