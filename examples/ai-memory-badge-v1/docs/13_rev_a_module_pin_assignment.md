# Rev A Module Pin Assignment

## ESP32-S3-WROOM-1 Signals

| Module Pin / GPIO | Net | Function |
| --- | --- | --- |
| 3V3 | SYS_3V3 | Module power |
| GND | GND | Ground |
| EN | ESP_EN | Reset / enable |
| GPIO0 | ESP_BOOT | Boot strap button |
| GPIO1 | VBAT_SENSE | Battery ADC divider |
| GPIO2 | LED_POWER | Power/status LED |
| GPIO4 | LED_RECORD | Dedicated recording/privacy LED |
| GPIO5 | I2C_SCL | I2C bus for NFC and secure-element reserve |
| GPIO6 | BTN_MARK | Mark button |
| GPIO7 | SD_CD | microSD card detect |
| GPIO8 | SD_CS | microSD SPI chip select |
| GPIO9 | SD_MISO | microSD SPI MISO |
| GPIO10 | SD_SCLK | microSD SPI clock |
| GPIO11 | SD_MOSI | microSD SPI MOSI |
| GPIO12 | I2S_BCLK | Microphone I2S bit clock |
| GPIO13 | I2S_LRCLK | Microphone I2S word select |
| GPIO14 | I2S_DIN | Microphone I2S data into MCU |
| GPIO15 | EPD_PWR_EN | E-paper power/adapter enable reserve |
| GPIO16 | SD_PWR_EN | microSD load-switch enable |
| GPIO17 | SW_MUTE | MCU-readable mute state |
| GPIO18 | MOTOR_DRV | Haptic motor drive |
| GPIO19 | USB_D_N | Native USB D- |
| GPIO20 | USB_D_P | Native USB D+ |
| GPIO21 | I2C_SDA | I2C bus for NFC and secure-element reserve |
| GPIO33 | EPD_SCLK | E-paper SPI clock |
| GPIO34 | EPD_MOSI | E-paper SPI MOSI |
| GPIO35 | EPD_CS | E-paper chip select |
| GPIO36 | EPD_DC | E-paper data/command |
| GPIO37 | EPD_RST | E-paper reset |
| GPIO38 | EPD_BUSY | E-paper busy input |
| GPIO39 | REC_BTN | REC user button |
| GPIO40 | MODE_BTN | MODE user button |
| GPIO41 | NFC_GPO | NFC field-detect / GPO interrupt |
| U0TXD | UART0_TX | Debug UART TX |
| U0RXD | UART0_RX | Debug UART RX |

## Interface Notes

- I2S microphones share BCLK/LRCLK/DIN. MK1 and MK2 are separated by L/R select straps.
- microSD uses SPI mode with CS, card detect, CMD/MOSI and DAT0/MISO pullups.
- E-paper uses a dedicated SPI-style group instead of forcing shared microSD SPI in Rev A.
- NFC is a dynamic tag on I2C with a dedicated GPO/FIELD_DETECT signal.
- REC and MUTE should be wake-capable in firmware planning.
