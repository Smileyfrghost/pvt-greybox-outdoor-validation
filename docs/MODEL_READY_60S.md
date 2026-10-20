# Reviewed 60 s table interface

## Scope and execution

This interface checks an already reviewed model-ready table. It does not run raw-file parsing, clock reconstruction, native QC, the original aggregation/freezing scripts, weather retrieval, or any fitted model. The original processing configuration is preserved byte-for-byte in `data/metadata/processing_config_60s_frozen.json`; source hashes and extraction scope are in `data/metadata/model_ready_60s_sources.json`.

```bash
python analysis/check_model_ready_60s.py \
  --dataset data/examples/synthetic_model_ready_60s.csv \
  --output results/synthetic_60s_interface/report.json
python -m unittest discover -s tests -v
```

**Every value in the example CSV is invented.** Its date labels illustrate the existing role protocol, not observations on those dates. The output verifies table consistency, never experiment authenticity. Existing outputs are protected. Input, configuration, contract and code hashes and software versions accompany the report.

## Preprocessing and boundaries

The frozen preprocessing specification uses arithmetic means within 60 s minute windows and a minimum valid-sample fraction of 0.8. Coverage is `min(1, n_valid / n_expected)`, not `n_valid / n_raw`. The original native code estimates expected counts from reviewed native intervals. Means can remain in insufficient windows for audit, but those windows are not model-ready; no gap-filling experimental interpolation is authorized by this interface.

Native aggregation segments reflect pump/electrical state, interventions, exclusions, clock segments and anomalies. Split event minutes are retained as excluded audit fragments. Eligible continuity requires consecutive 60 s rows within the same supplied segment, complete finite model inputs, and eligibility on both sides. Missing rows/inputs and segment changes interrupt continuity. This checker does not detect undocumented physical events, validate source sampling intervals, or recompute the means. It rejects inconsistent declared counts, dates, boolean flags, duplicated segment timestamps, reordered histories and enabled excluded windows.

## Channel and input meanings

| Field | Unit | Evidence boundary |
|---|---|---|
| `T_panel_center` | degC | Measured panel-center T1; not automatically cell-junction temperature |
| `T_tank_measured` | degC | Measured tank water; conditional water-side boundary proxy, not measured collector inlet |
| `Tamb` | degC | Gridded 2 m air-temperature proxy; not onsite measurement |
| `G` | W/m2 | Reviewed irradiance input, not absorbed thermal power |
| `P` | W | Reviewed active power; its use as thermal subtraction is a separate modeling assumption |
| `flow_mL_min` | mL/min | Prescribed operating setting, not flow-meter time series |

The native T2/T3 meanings change by day. For the reviewed 03-16/17/19/20/21 records, tank is T3 and outlet-side local is T2. For 03-25/26, tank is T2 and outlet-side local is T3. Use the semantic columns rather than one global channel rename. 03-18 has no automatic physical mapping here; 03-22 is rejected. The legacy `T_inlet_C` field is not an inlet measurement.

The weather derivative linearly interpolates archived hourly provider temperature at experimental-window midpoints. No extrapolation is permitted; a missing bracket or a bracket longer than 1.5 native intervals remains unavailable. This release documents that mapping, not a new weather implementation. The archived source names IFS, but the exact provider selector/version/API URL was not preserved. Accepted experimental clock alignment remains candidate-based, not independently calibrated synchronization.

## Data roles versus model roles

The copied configuration and its `identification_use` describe preprocessing eligibility in a candidate pool. They do not define the final fitted sample. Grey-box v1 uses 03-17/19/25 pump-on training days; frozen Static/ARX additionally include the zero-flow 03-16 day. The retained `final_model_training_dates` contract field refers only to grey-box v1. The study uses 03-21 internal validation and reviewed 03-26 post-intervention support for final held-out evaluation. 03-21 also informed ARX selection, so it is not an unseen ARX test. 03-26 pre-intervention material is sensitivity-only; 03-26 must not enable fitting, model selection or tuning. See [frozen baseline replay](FROZEN_BASELINE_REPLAY.md) for the fixed coefficients and external-support interface.

`model_ready_use` is neither fitting permission nor proof of physical correctness. This checker distinguishes declared preprocessing eligibility from complete model inputs and only reports continuity counts. It neither chooses training samples nor supplies frozen model coefficients/support masks. Those belong to later release batches.

## Reproduction limits

The configuration was copied from the existing frozen source, while the portable checker and synthetic fixture are new software interfaces. This is not a byte-for-byte re-execution of native QC or a replay of manuscript predictions. Synthetic tests establish only the tested software contracts. Full raw-to-frozen reproduction, frozen baselines, grey-box equations and held-out metric replay are outside this release.
