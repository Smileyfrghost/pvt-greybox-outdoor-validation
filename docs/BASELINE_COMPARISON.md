# Exploratory baseline comparison

## Models and tasks

| Model | Task | Information used |
|---|---|---|
| Persistence | One step | Most recent measured target |
| Persistence | Fixed horizon | Target at forecast origin, held constant |
| Persistence | Segment free run | Last measured initialization target, held constant |
| Static OLS | Contemporaneous estimate | Inputs at the target time; not a forecast |
| ARX | One step | Measured output history and lagged inputs |
| ARX | Fixed horizon | Measured history up to the origin, then recursive output history with realized inputs |
| ARX | Segment free run | Measured initialization history, then recursive outputs with realized inputs |

The default input set is `G_W_m2`, `T_tank_C`, `flow_kg_s`, which is available in the legacy thermal table. `T_inlet_C` is not used by default: its legacy name is not a verified inlet measurement. Other reviewed inputs can be specified explicitly. All three models share the configured exogenous input set, where applicable.

The ARX structure is fixed at two output lags, two non-flow input terms and one flow term. Its implemented indexing is explicit: input index = `target - 1 - n_k - lag`, with `n_k=1`; therefore non-flow terms use `u[t-2]` and `u[t-3]`. This follows the local baseline implementation's convention, rather than silently assuming that every identification package uses the same `n_k` convention. Three history rows are reserved in each segment.

Parameters are fitted anew to the supplied training segments using scaled ordinary least squares. Rank deficiency is recorded in the manifest; minimum-norm coefficients are not evidence of unique parameters. This runner does not load the frozen manuscript coefficients or select an ARX structure using an evaluation day. A structure informed by earlier research also does not become a new preregistered blind test when reused here.

## Splits, clocks and continuity

Without explicit dates, leave-one-day-out is exploratory: all parts of an evaluated date are excluded together from fitting and scaling. For a fixed split, supply both `--train-days` and `--evaluation-days`; overlapping or unavailable dates are rejected.

The default grid is 60 s, changed from the earlier exploratory 10 s default. Raw `elapsed_s` is an operational logger clock, so the CLI requires `--allow-legacy-clock` when using it. This acknowledgement permits a diagnostic run; it does not validate the clock. Prefer a reviewed numeric elapsed-time field or timestamp field through `--time-column`. UTC timestamps are normalized to nanosecond resolution before duration conversion.

Invalid quality flags, missing model channels, supplied segment-label changes and gaps exceeding `--max-gap-s` break histories. The default gap limit is twice the grid interval. Interpolation only occurs inside a valid segment, and the grid never extends beyond its last observation. Duplicate clock values require resolution rather than silent deduplication. These numerical boundaries do not discover unknown physical interventions; pass reviewed segment labels with `--segment-column`.

## Scoring contract

Persistence and ARX use identical origin/target pairs within each task. Initialization rows are excluded from metrics. Static OLS is reported in its own contemporaneous task, on the same post-history targets for bookkeeping; it is not ranked against free-run forecasts. No global model winner or cross-task mean error is produced.

Fixed horizons default to 5, 15, 30 and 60 minutes and must be exact multiples of the sample interval. They use realized exogenous inputs and are conditional forecasts. Insufficient horizon support is reported as `EMPTY_SUPPORT` with `N=0`. Nonfinite predictions retain the intended support count and report `NONFINITE_PREDICTIONS` with unavailable metrics; they are not dropped or temperature-clipped. R-squared is unavailable for constant observations.

## Commands

Historical thermal-clock diagnostic:

```bash
python analysis/fit_panel_temperature_models.py \
  --dataset data/processed/experimental_clean_v1.csv \
  --output-dir results/exploratory_baselines_v2 \
  --step-s 60 --allow-legacy-clock
```

Example for a separately reviewed table with an explicit split:

```bash
python analysis/fit_panel_temperature_models.py \
  --dataset path/to/reviewed.csv \
  --output-dir results/reviewed_baseline_diagnostic \
  --time-column window_start --target-column T_panel_center \
  --input-columns G Tamb T_tank_measured P flow_mL_min \
  --flow-column flow_mL_min --valid-column eligible_for_this_diagnostic \
  --segment-column aggregation_segment \
  --train-days 2026-03-17 2026-03-19 2026-03-25 \
  --evaluation-days 2026-03-21
```

The example assumes the named reviewed columns already exist. Eligibility must be defined outside the model using the appropriate role, event and quality rules. The runner does not derive manuscript train/test masks or promote a model-ready flag into test permission.

Outputs are `baseline_metrics.csv`, `baseline_predictions.csv` and `baseline_run_manifest.json`. They record task, horizon, date/segment support, fitted coefficients/scalers, rank, input/code hashes and software versions. Existing named outputs are not overwritten. The former mixed-task ranking and hard-coded 3.21/3.26 plot are retired; their historical implementation remains in Git history.

No measured experiment has been refitted or rescored to validate this code change. Synthetic checks verify software contracts; the later frozen manuscript protocol and effective-parameter claim limits remain separate.
