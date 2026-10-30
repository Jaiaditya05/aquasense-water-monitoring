# AquaSense dashboard update

## What changed
- Replaced the previous particle/metal mockup with TDS, turbidity, and water-temperature cards matching the project's intended sensors.
- Initial values and charts start at zero/empty. No readings appear until **Generate demo reading** is clicked.
- Added an explicit hardware-status panel. Demo generation does not mark the ESP32 or sensors as connected.
- Added recent readings, history search/filter, analytics averages, CSV export, dark/light mode, and chart-animation toggle.
- Labels synthetic values as `SIMULATED` and warns that values are illustrative until sensor calibration is verified.
- Removed unsupported claims that the current sensors can detect metals or certify drinking-water safety.

## Important integration status
This update is the dashboard UI only. It does **not** connect the ESP32 to Flask, and demo readings stay in the browser session rather than being written to PostgreSQL. The existing Flask routes and database code have been left unchanged in this first pass to reduce risk to the deployed Render app. The next step is to test the app's backend/database configuration, then implement a separate, clearly labelled real-reading API and hardware heartbeat.

## Apply locally
1. Back up the currently working project and do not replace the deployed Render version yet.
2. Replace `software/templates/index.html` with the version in this package.
3. Run locally with the project's configured environment and `DATABASE_URL` set to a test PostgreSQL database.
4. Confirm the dashboard loads, zero state is shown, demo readings work, reset clears them, and CSV export works.
5. Only after testing, commit and deploy the change.

## Sensor safety/accuracy
The current dashboard treats NTU and ppm as illustrative demo units. Verify the exact turbidity module, TDS module output voltage, probe type, ADC scaling, and calibration before presenting live values. ESP32 GPIOs are not 5 V tolerant. TDS and turbidity alone cannot identify specific heavy metals or prove water is safe to drink.
