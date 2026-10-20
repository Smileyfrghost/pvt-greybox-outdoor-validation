# Frozen baseline v1.1 replay

## Two distinct runners

`analysis/baseline_comparison.py` fits exploratory models. `analysis/frozen_baseline_replay.py` does not fit, scale anew or select a model. It loads the byte-preserved `baseline_model_parameters.json` and accepts an explicit external scoring-support file. The CLI checks the dataset hash against that file and verifies frozen parameter/protocol hashes before executing. Both runners preserve separate scoring tasks; neither creates a global model ranking.

```bash
python analysis/frozen_baseline_replay.py \
  --dataset data/examples/frozen_baseline_synthetic.csv \
  --support data/examples/frozen_baseline_synthetic_support.json \
  --output-dir results/frozen_baseline_synthetic
python -m unittest discover -s tests -v
```

The example contains invented values and arbitrary year-2000 dates. It demonstrates interface execution, not the paper's measurements, support masks or accuracy. Output directories must be new. Predictions, task/segment metrics and an input/support/parameter/code/version manifest are written separately.

## Frozen definitions

The inputs are `G`, `Tamb`, tank temperature, active electrical power and prescribed flow in mL/min. The CSV fields are `G`, `Tamb`, `T_tank_measured`, `P`, `flow_mL_min`; the target is `T_panel_center`. `Tamb` remains a gridded 2 m proxy and tank temperature is not measured collector inlet. No unknown future weather is predicted: horizons use the supplied realized exogenous path.

Static OLS and ARX v1.1 were fitted using **03-16, 03-17, 03-19 and 03-25**. Grey-box v1 instead used the three pump-on days **03-17, 03-19 and 03-25**. Do not silently impose the grey-box training subset on the frozen baselines. 03-21 informed ARX selection and is internal validation, not an unseen ARX test. The dated protocol's blind-day wording records its historical pre-unsealing state; it is not a claim that 03-26 is still unopened today.

The selected structure is `ARX_2_2_1_flow1`. In raw units:

```text
y_hat[t] = intercept + sum(a[j-1] * y_history[t-j], j=1..2)
           + sum(b[input][lag] * u[t-2-lag, input])
```

Non-flow inputs have two lag terms, flow has one. Coefficients and original training statistics are retained; no evaluation-data scaler is computed. The raw-unit equation is checked against the accepted prediction records, so conversion from the original standardized fit is not re-estimated.

## Explicit support contract

The JSON schema is `frozen-baseline-support-v1` with `sampling_seconds: 60`, a byte-level `dataset_sha256`, a provenance description and a `segments` list. Each segment has a unique `id`, ordered `row_ids`, `initialization_rows: 3` and explicit `tasks`. Dataset row identifiers must be unique strings. Segment rows must have one date and aggregation label, constant prescribed flow, finite inputs and consecutive minute labels; no sorting, interpolation, row deletion or mask selection occurs inside the runner.

Each task provides `task`, `horizon_steps` and `pairs: [[origin, target], ...]`. Indices are zero-based within the supplied segment. Dynamic tasks reject targets in the first three rows. Missing origin/target pairs are **not** automatically added; empty groups produce `EMPTY_SUPPORT`.

| Task | Pair rule | Information used |
|---|---|---|
| `one_step` | origin >= 2, target = origin + 1, horizon 1 | Measured output history through origin |
| `conditional_horizon` | origin >= 2, target = origin + horizon | Measured history through origin, then recursive ARX and realized inputs |
| `free_run` | origin 0, target >= 3, no fixed horizon | ARX initializes its first three measured outputs and never corrects later; Persistence holds y[0] |
| `static_contemporaneous` | null origin, any declared target | Current inputs; not a forecast |
| `static_common` | null origin, target >= 3 | Same regression on explicitly supplied common targets |

Persistence and ARX share the exact task pairs. They do not necessarily consume identical initialization information: in the historical free-run protocol Persistence holds the first value, while ARX needs three initial output rows. This distinction is preserved rather than silently changing the frozen experiment. Static all-row and common-target scores remain separate. Nonfinite predictions retain the declared N and report failure; temperatures are not clipped.

## What This Release Does Not Establish

A support-file hash locks bytes, not scientific correctness or independent experiment provenance. The runner cannot discover undocumented interventions or authenticate observations. External row/segment/pair selection must come from a reviewed protocol. The real 03-21 support was adapted locally and compared with the existing frozen baseline prediction records without changing any fitted parameter; private observations and predictions are not part of this public package.

Full raw QC reconstruction, grey-box execution and the complete 03-26 held-out package remain separate releases. Synthetic/software acceptance or successful replay does not establish improved prediction, new blind validation, parameter physical validity, hardware validation or publication readiness.
