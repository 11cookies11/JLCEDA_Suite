# Rev A Module Change Summary

## Goal

Convert AI Memory Badge V1 Rev A from a bare ESP32-S3 boot-chain validation board into a module-based electronic recording badge core board that can be sampled, powered, debugged, record audio, and reserve e-paper and NFC expansion paths.

## Replaced

- U1 changed from ESP32-S3R8 bare QFN-56 SoC to ESP32-S3-WROOM-1-N8R8 module, LCSC C2913201.
- U3 changed from MCP73831 simple charger to BQ24074RGTR power-path charger, LCSC C54313.
- The power path is now USB_5V -> U3 -> VSYS -> U2/AP2112K -> SYS_3V3.

## Removed From Assembled Rev A

- U4 external W25Q128 SPI flash.
- U5 external PSRAM reserve.
- Y1 40 MHz crystal.
- C8/C9 crystal load capacitors.
- J3 U.FL antenna connector.
- R10/C12/C13 bare-chip RF pi network.
- Bare-chip flash, PSRAM, crystal, LNA_IN/RF_IO and antenna-feed nets.

## Added

- U8 ST25DV04KC dynamic NFC tag, not an NFC reader.
- J6 2.13 inch black-white e-paper SPI connector.
- U9 TPS22918 MIC_3V3 load switch for hardware microphone power cut.
- U10 TPS22918 SD_3V3 load switch for microSD power control experiments.
- SW5 REC button and SW6 MODE button.
- NFC antenna pads/connector and DNP tuning capacitors.
- EPD, NFC, REC, MODE, SD card-detect, USB D+/D-, MIC power-enable, SD_3V3 and other bring-up test points.

## DNP / Optional

- NFC tuning capacitors C20/C21 are DNP until antenna measurement.
- E-paper connector exact footprint is TBD until the selected panel or adapter board is locked.
- SD_3V3 switching can be evaluated during Rev A bring-up.
- AP2112K remains a Rev A bring-up LDO; Rev B should evaluate buck or buck-boost.

## Remaining Review Items

- Verify BQ24074 charger resistor values, thermal behavior and power-path pins against the final battery.
- Verify MSM261S3526Z0CM L/R polarity, acoustic port orientation, reflow constraints and footprint sound-hole direction.
- Verify physical mute switch polarity against U9 load-switch ON polarity and enclosure labels.
- Verify e-paper connector pinout against the final 2.13 inch module/adapter.
- Tune NFC antenna after enclosure, battery and metal clip geometry are known.
