# Frozen one-state grey-box equation

## Scope and commands

This module publishes the existing one-state equation, original frozen shared parameters and deterministic numerical tests. It does not identify parameters, change the model structure, infer hidden states, score observations or supply the complete held-out support package. It needs only the Python standard library; the original fitting engine's SciPy optimizer is not part of this release.

```bash
python analysis/frozen_greybox.py \
  --input data/examples/greybox_synthetic_segments.json \
  --output-dir results/greybox_synthetic
python -m unittest discover -s tests -v
```

Every example input and initial state is invented. `states.csv` includes each initial state and the subsequent states; `manifest.json` records input, parameter, contract and code hashes and the software version. Existing output directories are protected. No observed temperature series is supplied or scored.

## Equation and exact update

```text
C_eff dT/dt = alpha_eff A G - UA_amb (T-Tamb)
             - (flow/flow_ref) UA_water (T-Ttank) - Pel
```

Here A=0.55 m2, flow_ref=500 mL/min, gamma_Pel=1, and the frozen grid is 60 s. The supported prescribed flow states are only 0 and 500 mL/min. The software rejects intermediate values rather than interpreting an unvalidated interpolation as a cross-flow result.

Let H=UA_amb+(flow/flow_ref)UA_water and q(T,u) be the signed right-hand-side heat balance. For inputs held constant during a transition:

```text
T[k+1] = T[k] + beta q(T[k],u[k])
beta = -expm1(-H dt/C_eff)/H      if H > 0
beta = dt/C_eff                   if H = 0
```

This is the analytical zero-order-hold update, not explicit Euler. Using `expm1` avoids cancellation at small H. The public `step` function permits other positive dt values for mathematical contract tests; the supplied segment runner always uses the frozen 60 s grid. Inputs[k] drives the transition from states[k] to states[k+1], so N input transitions produce N+1 states. The original identification trajectory API instead stored N state rows and consumed the first N-1 input rows; this indexing difference is explicit.

## Frozen parameters and measurement meanings

`data/metadata/frozen_greybox/shared_theta_frozen_v1.json` is a byte-preserved copy of the completed shared fit. The loader checks its source hash and the curated equation-contract hash. The parameters were shared across the 03-17/19/25 pump-on training days; 03-16 was a zero-flow diagnostic without refitting. The excluded early 03-25 transient is not restored. Unlike the baselines' training pool, 03-16 did not enter this shared fit.

The modeled state is effective panel-center temperature. The 60 s observed mean was treated as the state at its window label, which is an observation approximation, not exact point sampling. `Tamb` is a gridded 2 m air-temperature proxy; `Ttank` is tank water, not measured collector inlet; flow is a prescribed setting, not a flow-meter series. The unit coefficient subtracting electrical power is a modeling assumption.

The fitted C_eff approaches its upper bound and UA_amb its lower bound. The frozen status remains **IDENTIFIABILITY_LIMITED**. These are effective parameters, not established invariant physical properties. The software's mathematical equilibrium or decay tests do not establish the real collector's thermal mechanism or parameter identifiability.

## Segments and checks

The JSON input must declare independent segments, each with a unique id, initial temperature and an ordered list of `[G, Tamb, Ttank, Pel, flow_mL_min]` transitions. The caller is responsible for reviewed time, event and exclusion boundaries. Mixed flow within a segment is rejected. The runner cannot discover missing timestamps or undocumented interventions because it does not accept raw logger files. Each new segment initializes independently; later measured-temperature correction does not exist in this API.

Pump OFF removes water coupling exactly: an unavailable tank temperature may be represented by null. Pump ON requires a finite tank value. Nonfinite required values, invalid domains and nonfinite states raise errors; outputs are never clipped to a temperature range. Numerical tests cover energy signs, exact decay, equilibrium, the H=0 limit, semigroup behavior, pump-state boundaries and missing-water semantics.

## Provenance and scientific limits

The source manifest points to the completed identification engine, the original equation tests, frozen parameters, diagnostics and final claims. Earlier pending-approval or environment-stop documents remain historical sources, not current release authorization. The curated contract does not rewrite any of them.

Local numerical QA compares this implementation against the original scalar function on synthetic inputs and against an independent RK4 integration of the same assumed equation. Those checks establish equation/software consistency only. They do not constitute a new experiment, model fit, held-out validation, improved accuracy, deployment acceptance or hardware/HIL verification. Full observed 03-21/03-26 scoring and common support remain in release batch 05.
