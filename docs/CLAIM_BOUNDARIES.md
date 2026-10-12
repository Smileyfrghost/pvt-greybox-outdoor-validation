# Claim boundaries

These boundaries describe the historical code workflow. [Methods and evidence](METHODS_AND_EVIDENCE.md) explains reviewed sensor semantics and the distinct later frozen protocol. A legacy `T_inlet_C` field is not proof of a measured collector inlet.

## Supported by the current repository

- Nine outdoor logger days can be parsed into a consistent temperature/irradiance schema.
- The observed day-level flow settings are 300 and 500 mL/min.
- Sensor-range failures can be explicitly flagged without silently dropping samples.
- Whole-day holdout baselines can be evaluated using code in this repository.
- Nine electrical exports can be parsed with explicit unit and voltage-current-power checks.
- Four available XLSX exports exactly match their Markdown counterparts for timestamps, voltage, current, and active power.
- The timestamped 2026-03-17 thermal record establishes a normal 5.834 s sample period; author-confirmed common-stop acquisition supports an operational clock reconstruction on the other eight days.
- A 30 s aligned electrothermal table can be regenerated with explicit alignment basis and timing sensitivity.

## Not supported by the current measurements

- Measured thermal power or thermal efficiency: outlet-water temperature is absent.
- Continuous flow-control performance: flow is recorded only as a day-level setting.
- Water savings: the rig used recirculation and no defensible consumption baseline is available.
- Weather-normalized generalization: ambient temperature and wind are missing from the March logger.
- Independent HIL validation: historical compiled-controller co-simulation is not hardware-in-the-loop evidence.
- A physics-informed neural network contribution: historical surrogate work is outside this release and requires separate validation.

## Pending work

Electrical parsing, quality control, and operational clock reconstruction are complete. Confirmatory electrothermal modeling remains pending whole-day validation, +/-30/60/120 s timing sensitivity, and explicit treatment of load-off intervals such as early 2026-03-22. Correlation-ranked offsets are diagnostic and do not replace recorded or acquisition-process anchors.
