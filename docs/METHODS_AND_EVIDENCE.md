# Methods and evidence scope

## Early code supplied here

The parsers retain the nine-day source inventory and its quality-control flags. The alignment diagnostic reconstructs an operational clock from a timestamped reference period and a common-stop assumption. The baseline script evaluates exploratory leave-one-day-out regressions. These commands reproduce their own historical workflow; they do not implement the later frozen manuscript protocol.

The maintained baseline entry now fits Persistence/Static OLS/ARX comparisons with gap-safe segments and separate contemporaneous, one-step, conditional-horizon and free-run scores. See [BASELINE_COMPARISON.md](BASELINE_COMPARISON.md). The earlier clipped, mixed-task baseline implementation remains in Git history; its results must not be silently relabelled as outputs of the repaired runner.

Names in an old export schema are not independent sensor identification. `T_inlet_C` is a legacy parser field and must not be treated as a confirmed collector-inlet measurement. Refer to the reviewed sensor map before assigning a thermal boundary condition.

## Frozen temperature-model study

The later study targets measured panel-centre T1. Its water-side input uses tank temperature as a proxy, and its ambient-air input uses a gridded 2 m temperature proxy. It compares Persistence, contemporaneous Static OLS, a frozen ARX model and a first-order grey-box model using task-specific supports. One-step prediction, fixed-horizon conditional forecasting and segment-wise free-run simulation answer different questions.

Shared grey-box parameters were identified using 2026-03-17, 03-19 and 03-25. The 03-21 data have an internal-validation role and also informed ARX selection. The final 03-26 evaluation was held out from the audited fitting and selection chain; historical QC access to that date still occurred. Conditional forecasts use realized exogenous inputs rather than forecasts of unknown future weather and water-side conditions.

The frozen study found no consistent grey-box advantage over Persistence and retained recursive-drift and parameter-identifiability limitations. These are temperature-prediction results, not validation of invariant physical parameters, hardware control, efficiency improvement or water savings. Subsequent analyses that reuse 03-26 are known-test-day diagnostics rather than new blind validation.

The later frozen pipelines, parameters and result artifacts require their own reviewed import before a repository command can be described as reproducing that study. The exploratory baseline command must not be substituted for them.

## Irradiance workbook audit

`analysis/audit_irradiance_campaign.py` reads minute-resolution station workbooks and reports coverage, duplicates, gaps, channel summaries, exact observed ramps and aggregation sensitivity. Expected columns contain Chinese tokens for time, instantaneous total/direct/UV irradiance and daily accumulations. Expected units are W/m2, MJ/m2 and h.

The script assumes minute observations for its minute-count and row-shift diagnostics. Conflicting overlapping records need external resolution: coverage flags duplicates, while summaries retain the first repeated timestamp. A direct-versus-total diagnostic alone cannot establish a sensor fault, because beam-normal and horizontal irradiance have different geometry. Weather records are not automatically panel-plane irradiance or on-site ambient measurements.

## Provenance and permissions

Hardware specifications are participant-confirmed where stated; missing nameplate fields and sensor calibration remain unknown. Historical reports describe evidence available at their original date, including superseded module ratings and early clock assumptions. Original measurements and full-text literature are not redistributed by this code release.
