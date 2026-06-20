# Rev A Module Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| BQ24074 charge current or thermal setup wrong | Battery stress, charge failure, unstable USB behavior | Recalculate charger settings from final protected battery and verify thermal limits |
| AP2112K LDO efficiency too low | Short battery life | Accept for Rev A bring-up; reserve buck/buck-boost path for Rev B |
| MIC L/R polarity or sound-hole orientation wrong | Stereo swap or poor/no audio | Verify MSM261S3526Z0CM datasheet, footprint orientation and enclosure acoustic path |
| MIC_3V3 hard mute polarity wrong | Privacy failure | Validate SW4 direction, U9 ON polarity and boot/wake firmware behavior |
| Generated schematic shorts MIC_LR_SEL_R to I2S_BCLK | Microphone bus failure | Re-run KiCad export/ERC and inspect the audio sheet before PCB release |
| microSD card-detect or socket footprint mismatch | Storage failures | Confirm J5 pinout and card-detect behavior against exact footprint |
| microSD write interrupted by brownout or card removal | Corrupt recordings | Firmware must handle no-card, full-card, write failure, removal and power loss |
| WROOM antenna blocked by enclosure/battery/clip | Poor Wi-Fi/BLE range | Enforce antenna keep-out with mechanical stack-up review |
| NFC antenna detuned by battery or metal clip | Phone tap unreliable | Prototype antenna zone and tune with final enclosure materials |
| E-paper connector/panel mismatch | Display unusable | Lock exact 2.13 inch panel or adapter before PCB release |
| Motor noise couples into audio or resets system | Audio artifacts or unstable recording | Keep motor away from microphones, use short haptic events, tune C19 and supply routing |
