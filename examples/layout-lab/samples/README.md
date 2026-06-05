# Layout Lab Samples

These scenarios are smaller test cases for the placement sandbox.

They are designed to show different layout styles:

- `sample_mcu_core.json`
  - center cluster
  - indicator edge placement
- `sample_power_usb.json`
  - power chain
  - power entry chain
  - USB interface chain
- `sample_rf_debug.json`
  - RF keepout island
  - analog island
  - debug access cluster
  - differential pair adjacency

Run them with:

```powershell
python scripts/layout_lab.py --scenario examples/layout-lab/samples/sample_mcu_core.json --out tmp/layout-lab-sample-mcu-core
python scripts/layout_lab.py --scenario examples/layout-lab/samples/sample_power_usb.json --out tmp/layout-lab-sample-power-usb
python scripts/layout_lab.py --scenario examples/layout-lab/samples/sample_rf_debug.json --out tmp/layout-lab-sample-rf-debug
```
