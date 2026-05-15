# Test Plan: NEMA23 Industrial Stepper Driver V0.1

## 1. Bare Board Checks

- Check input-to-ground resistance.
- Check 3.3V-to-ground resistance.
- Check VM bus-to-ground resistance.
- Inspect shunt Kelvin routing and MOSFET footprints before assembly.

## 2. Low-Voltage Power-Up

- Use a current-limited bench supply.
- Start at 12V or lower.
- Verify 5V rail.
- Verify 3.3V rail.
- Verify MCU SWD access.
- Verify UART boot/status output.

## 3. Gate Driver Test

- Do not connect motor.
- Use low bus voltage or logic-only driver supply where possible.
- Output low-duty PWM.
- Measure gate waveforms with an oscilloscope.
- Verify dead time.
- Verify no high-side/low-side shoot-through.

## 4. Current Sense Test

- Inject known current or use a controlled load path.
- Measure shunt voltage.
- Measure amplifier output.
- Verify ADC reading.
- Calibrate IA and IB scaling.

## 5. Low-Current Motor Test

- Set reduced current limit.
- Connect a small or unloaded stepper motor.
- Test EN behavior.
- Test STEP/DIR.
- Test low-speed rotation.
- Test 1/16 and 1/32 microstep modes.

## 6. Protection Tests

- Simulate undervoltage.
- Simulate overvoltage threshold with divider input when safe.
- Trigger overcurrent comparator using injected sense voltage before testing real short-current conditions.
- Simulate overtemperature.
- Verify fault latch and `clear_fault` behavior.

## 7. Review Gates

- Do not raise current above 2A RMS until thermal rise is measured.
- Do not fabricate a production batch until MOSFET thermal design, terminal current rating, and current-sense accuracy are reviewed.
