# Claim boundaries

## Supported by the current repository

- Nine outdoor logger days can be parsed into a consistent temperature/irradiance schema.
- The observed day-level flow settings are 300 and 500 mL/min.
- Sensor-range failures can be explicitly flagged without silently dropping samples.
- Whole-day holdout baselines can be evaluated using code in this repository.
- Nine electrical exports can be parsed with explicit unit and voltage-current-power checks.
- Four available XLSX exports exactly match their Markdown counterparts for timestamps, voltage, current, and active power.

## Not supported by the current measurements

- Measured thermal power or thermal efficiency: outlet-water temperature is absent.
- Continuous flow-control performance: flow is recorded only as a day-level setting.
- Water savings: the rig used recirculation and no defensible consumption baseline is available.
- Weather-normalized generalization: ambient temperature and wind are missing from the March logger.
- Independent HIL validation: historical compiled-controller co-simulation is not hardware-in-the-loop evidence.
- A physics-informed neural network contribution: historical surrogate work is outside this release and requires separate validation.

## Pending work

Electrical parsing and quality control are complete. Pointwise electro-thermal claims remain pending because only the 2026-03-17 thermal file contains wall-clock timestamps. Correlation-ranked offsets on the other days are exploratory candidates. External start/end anchors or original timestamped serial logs are required before those days enter confirmatory electro-thermal modeling.
