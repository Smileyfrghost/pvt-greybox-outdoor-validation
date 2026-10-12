"""Gap-safe exploratory baselines; not a replay of frozen manuscript models."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_INPUTS = ("G_W_m2", "T_tank_C", "flow_kg_s")


@dataclass
class RidgeModel:
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    rank: int = 0
    n_parameters: int = 0

    def predict(self, features: np.ndarray) -> np.ndarray:
        standardized = (np.asarray(features) - self.mean) / self.scale
        return np.column_stack([np.ones(len(standardized)), standardized]) @ self.coefficients


def fit_ridge(features: np.ndarray, target: np.ndarray, penalty: float = 0.0) -> RidgeModel:
    x, y = np.asarray(features, dtype=float), np.asarray(target, dtype=float)
    if x.ndim != 2 or y.ndim != 1 or len(x) != len(y) or not len(y):
        raise ValueError("A nonempty 2-D design and aligned 1-D targets are required")
    if not np.isfinite(x).all() or not np.isfinite(y).all() or penalty < 0:
        raise ValueError("Training values must be finite and penalty nonnegative")
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-12] = 1.0
    design = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    rank = int(np.linalg.matrix_rank(design))
    if penalty:
        regularizer = np.sqrt(penalty) * np.eye(design.shape[1])
        regularizer[0, 0] = 0.0
        solve_x = np.vstack([design, regularizer])
        solve_y = np.concatenate([y, np.zeros(design.shape[1])])
    else:
        solve_x, solve_y = design, y
    coefficients = np.linalg.lstsq(solve_x, solve_y, rcond=None)[0]
    return RidgeModel(mean, scale, coefficients, rank, design.shape[1])


def metrics(observed: np.ndarray, predicted: np.ndarray) -> dict:
    actual, prediction = np.asarray(observed, float), np.asarray(predicted, float)
    if actual.ndim != 1 or prediction.shape != actual.shape:
        raise ValueError("Metric arrays must have equal 1-D shape")
    n = len(actual)
    result = {"N": n, "mae_C": None, "rmse_C": None, "bias_C": None, "r2": None}
    if not n:
        return result | {"status": "EMPTY_SUPPORT"}
    if not np.isfinite(actual).all() or not np.isfinite(prediction).all():
        return result | {"status": "NONFINITE_PREDICTIONS"}
    with np.errstate(over="ignore", invalid="ignore"):
        error = prediction - actual
        square = float(np.mean(error**2))
    if not np.isfinite(square):
        return result | {"status": "NONFINITE_PREDICTIONS"}
    denominator = float(np.sum((actual - actual.mean()) ** 2))
    result.update(mae_C=float(np.mean(abs(error))), rmse_C=float(np.sqrt(square)),
                  bias_C=float(np.mean(error)),
                  r2=1.0 - square * n / denominator if denominator > 0 else None)
    return result | {"status": "OK"}


def parse_validity(values: pd.Series) -> np.ndarray:
    mapped = values.astype("string").str.strip().str.lower().map(
        {"true": True, "false": False, "1": True, "0": False}
    )
    if mapped.isna().any():
        raise ValueError("Validity flags must be explicit true/false or 1/0")
    return mapped.to_numpy(dtype=bool)


def resample_days(dataset: pd.DataFrame, step_s: float, *,
                  input_columns=DEFAULT_INPUTS, target_column="T_panel_C",
                  time_column="elapsed_s", valid_column="valid_sensor_range",
                  segment_column=None, max_gap_s=None) -> dict[str, pd.DataFrame]:
    if not np.isfinite(step_s) or step_s <= 0:
        raise ValueError("step_s must be positive and finite")
    gap = 2 * step_s if max_gap_s is None else float(max_gap_s)
    if not np.isfinite(gap) or gap <= 0:
        raise ValueError("max_gap_s must be positive and finite")
    columns = list(dict.fromkeys([target_column, *input_columns]))
    required = {"date", time_column, valid_column, *columns}
    if segment_column:
        required.add(segment_column)
    if missing := required.difference(dataset.columns):
        raise ValueError(f"Missing columns: {sorted(missing)}")
    work = dataset.copy()
    if work["date"].isna().any():
        raise ValueError("Every observation needs an experiment day")
    work["date"] = work["date"].astype(str)
    if pd.api.types.is_numeric_dtype(work[time_column]):
        work["_seconds"] = pd.to_numeric(work[time_column], errors="coerce")
    else:
        times = pd.to_datetime(work[time_column], utc=True, errors="coerce")
        work["_seconds"] = times.dt.as_unit("ns").astype("int64") / 1e9
        work.loc[times.isna(), "_seconds"] = np.nan
    if not np.isfinite(work["_seconds"]).all():
        raise ValueError("Invalid clock values; resolve the timebase before resampling")
    work["_valid"] = parse_validity(work[valid_column])
    for column in columns:
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work["_valid"] &= np.isfinite(work[columns]).all(axis=1)
    days = {}
    for day, frame in work.groupby("date", sort=True):
        frame = frame.sort_values("_seconds").reset_index(drop=True)
        if frame["_seconds"].duplicated().any():
            raise ValueError(f"Duplicate clock values on {day}; do not silently deduplicate")
        labels = frame[segment_column] if segment_column else pd.Series("one", index=frame.index)
        if labels.isna().any():
            raise ValueError("Segment labels cannot be missing")
        split = frame["_seconds"].diff().gt(gap) | labels.ne(labels.shift())
        # Invalid rows break both adjoining histories even when the time gap is small.
        split |= ~frame["_valid"] | ~frame["_valid"].shift(fill_value=False)
        frame["_part"] = split.cumsum()
        chunks = list(frame.loc[frame["_valid"]].groupby("_part", sort=True))
        for index, (_, chunk) in enumerate(chunks, 1):
            time = chunk["_seconds"].to_numpy(float)
            count = int(np.floor((time[-1] - time[0]) / step_s + 1e-9)) + 1
            grid = time[0] + np.arange(count) * step_s
            grid = grid[grid <= time[-1] + 1e-9]
            values = {column: np.interp(grid, time, chunk[column].to_numpy(float)) for column in columns}
            key = day if len(chunks) == 1 else f"{day}#part{index:03d}"
            result = pd.DataFrame(values)
            result["elapsed_s"], result["date"], result["segment_id"] = grid, day, key
            days[key] = result
    if not days:
        raise ValueError("No valid segments remain")
    return days


@dataclass(frozen=True)
class ARXSpec:
    inputs: tuple[str, ...] = DEFAULT_INPUTS
    target: str = "T_panel_C"
    n_a: int = 2
    n_b: int = 2
    n_k: int = 1
    flow_column: str = "flow_kg_s"

    def __post_init__(self):
        if self.n_a < 1 or self.n_b < 1 or self.n_k < 0 or not self.inputs:
            raise ValueError("ARX needs positive orders, nonnegative n_k and named inputs")
        if len(set(self.inputs)) != len(self.inputs) or self.target in self.inputs:
            raise ValueError("Distinct exogenous inputs must exclude the prediction target")

    @property
    def burn(self):
        return max(self.n_a, self.n_b + self.n_k)

    def feature(self, history, inputs, target):
        if target < self.burn:
            raise ValueError("History is shorter than the configured ARX lags")
        result = [history[target - lag] for lag in range(1, self.n_a + 1)]
        for column, name in enumerate(self.inputs):
            count = 1 if name == self.flow_column else self.n_b
            result.extend(inputs[target - 1 - self.n_k - lag, column] for lag in range(count))
        return np.asarray(result, float)


def fit_arx(segments, spec: ARXSpec) -> RidgeModel:
    features, targets = [], []
    for frame in segments:
        y, u = frame[spec.target].to_numpy(float), frame[list(spec.inputs)].to_numpy(float)
        for target in range(spec.burn, len(frame)):
            features.append(spec.feature(y, u, target))
            targets.append(y[target])
    if not targets:
        raise ValueError("No training segment contains enough ARX history")
    return fit_ridge(np.asarray(features), np.asarray(targets), penalty=0.0)


def predict_arx(frame, model: RidgeModel, spec: ARXSpec, *, origin=None, horizon=None, one_step=False):
    y, u = frame[spec.target].to_numpy(float), frame[list(spec.inputs)].to_numpy(float)
    prediction = np.full(len(y), np.nan)
    if one_step:
        for target in range(spec.burn, len(y)):
            with np.errstate(over="ignore", invalid="ignore"):
                prediction[target] = model.predict(spec.feature(y, u, target)[None, :])[0]
        return prediction
    start = spec.burn - 1 if origin is None else int(origin)
    stop = len(y) - 1 if horizon is None else start + int(horizon)
    if start < spec.burn - 1 or start >= len(y) or stop < start or stop >= len(y):
        raise ValueError("Forecast history or horizon leaves its segment")
    prediction[:start + 1] = y[:start + 1]
    for target in range(start + 1, stop + 1):
        with np.errstate(over="ignore", invalid="ignore"):
            prediction[target] = model.predict(spec.feature(prediction, u, target)[None, :])[0]
    return prediction


def make_folds(days, train_days=None, evaluation_days=None):
    available = sorted({str(frame["date"].iloc[0]) for frame in days.values()})
    if train_days is None and evaluation_days is None:
        if len(available) < 2:
            raise ValueError("Leave-one-day-out requires at least two experiment days")
        return [(day, [other for other in available if other != day]) for day in available]
    if not train_days or not evaluation_days:
        raise ValueError("Both train-days and evaluation-days are required")
    training, evaluation = set(train_days), set(evaluation_days)
    if training & evaluation:
        raise ValueError("Training and evaluation days overlap")
    if missing := (training | evaluation).difference(available):
        raise ValueError(f"Declared days are unavailable: {sorted(missing)}")
    return [(day, sorted(training)) for day in sorted(evaluation)]


def evaluate_baselines(days, *, spec=None, horizons=(5, 15, 30, 60), step_s=60.0,
                       train_days=None, evaluation_days=None):
    spec = ARXSpec() if spec is None else spec
    if not np.isfinite(step_s) or step_s <= 0:
        raise ValueError("step_s must be positive and finite")
    if len(set(horizons)) != len(horizons):
        raise ValueError("Forecast horizons must be unique")
    horizon_steps = []
    for minute in horizons:
        steps = float(minute) * 60 / step_s
        if not np.isfinite(steps) or steps < 1 or abs(steps - round(steps)) > 1e-9:
            raise ValueError("Each positive horizon must be an exact multiple of step_s")
        horizon_steps.append((float(minute), int(round(steps))))
    rows, details, fitted = [], [], []
    for day, train_dates in make_folds(days, train_days, evaluation_days):
        training = [frame for frame in days.values() if frame["date"].iloc[0] in train_dates]
        test = [frame for frame in days.values() if frame["date"].iloc[0] == day]
        static = fit_ridge(np.vstack([frame[list(spec.inputs)].to_numpy(float) for frame in training]),
                           np.concatenate([frame[spec.target].to_numpy(float) for frame in training]))
        arx = fit_arx(training, spec)
        fitted.append({"evaluation_day": day, "training_days": train_dates,
                       "static": model_record(static), "arx": model_record(arx)})
        points = []
        for frame in test:
            if len(frame) <= spec.burn:
                continue
            y = frame[spec.target].to_numpy(float)
            time = frame["elapsed_s"].to_numpy(float)
            segment = str(frame["segment_id"].iloc[0])
            static_prediction = static.predict(frame[list(spec.inputs)].to_numpy(float))
            one_step = predict_arx(frame, arx, spec, one_step=True)
            free_run = predict_arx(frame, arx, spec)

            def add(model, task, target, origin, value, horizon_min=None):
                points.append({"date": day, "segment": segment, "model": model, "task": task,
                               "horizon_min": horizon_min, "target_index": target,
                               "origin_index": origin, "origin_time_s": float(time[origin]),
                               "target_time_s": float(time[target]), "observed_C": float(y[target]),
                               "predicted_C": float(value)})

            for target in range(spec.burn, len(frame)):
                add("Static_OLS", "contemporaneous", target, target, static_prediction[target])
                add("Persistence", "one_step", target, target - 1, y[target - 1])
                add("ARX", "one_step", target, target - 1, one_step[target])
                add("Persistence", "free_run", target, spec.burn - 1, y[spec.burn - 1])
                add("ARX", "free_run", target, spec.burn - 1, free_run[target])
            for minute, steps in horizon_steps:
                for origin in range(spec.burn - 1, len(frame) - steps):
                    target = origin + steps
                    prediction = predict_arx(frame, arx, spec, origin=origin, horizon=steps)[target]
                    add("Persistence", "conditional_horizon", target, origin, y[origin], minute)
                    add("ARX", "conditional_horizon", target, origin, prediction, minute)
        if not points:
            raise ValueError(f"No post-history evaluation targets on {day}")
        details.extend(points)
        table = pd.DataFrame(points)
        cases = [("Static_OLS", "contemporaneous", None)]
        cases += [(model, task, None) for task in ("one_step", "free_run") for model in ("Persistence", "ARX")]
        cases += [(model, "conditional_horizon", minute) for minute, _ in horizon_steps for model in ("Persistence", "ARX")]
        for model, task, horizon in cases:
            selected = (table["model"] == model) & (table["task"] == task)
            selected &= table["horizon_min"].isna() if horizon is None else table["horizon_min"].eq(horizon)
            group = table.loc[selected]
            rows.append({"date": day, "training_days": ";".join(train_dates), "model": model,
                         "task": task, "horizon_min": horizon,
                         "segments": int(group["segment"].nunique()),
                         **metrics(group["observed_C"].to_numpy(), group["predicted_C"].to_numpy())})
    return pd.DataFrame(rows), pd.DataFrame(details), fitted


def model_record(model):
    return {"training_mean": model.mean.tolist(), "training_scale": model.scale.tolist(),
            "scaled_coefficients": model.coefficients.tolist(), "design_rank": model.rank,
            "n_parameters": model.n_parameters, "rank_deficient": model.rank < model.n_parameters}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--step-s", type=float, default=60.0)
    parser.add_argument("--time-column", default="elapsed_s")
    parser.add_argument("--allow-legacy-clock", action="store_true")
    parser.add_argument("--target-column", default="T_panel_C")
    parser.add_argument("--input-columns", nargs="+", default=list(DEFAULT_INPUTS))
    parser.add_argument("--flow-column", default="flow_kg_s")
    parser.add_argument("--valid-column", default="valid_sensor_range")
    parser.add_argument("--segment-column")
    parser.add_argument("--max-gap-s", type=float)
    parser.add_argument("--train-days", nargs="+")
    parser.add_argument("--evaluation-days", nargs="+")
    parser.add_argument("--horizons-min", nargs="+", type=float, default=[5, 15, 30, 60])
    args = parser.parse_args()
    if args.time_column == "elapsed_s" and not args.allow_legacy_clock:
        parser.error("elapsed_s is a legacy operational clock; acknowledge it with --allow-legacy-clock or provide a reviewed time column")
    if (args.train_days is None) != (args.evaluation_days is None):
        parser.error("--train-days and --evaluation-days must be supplied together")
    outputs = ["baseline_metrics.csv", "baseline_predictions.csv", "baseline_run_manifest.json"]
    if any((args.output_dir / name).exists() for name in outputs):
        parser.error("Choose a new output directory; existing baseline outputs are not overwritten")
    input_hash = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    dataset = pd.read_csv(args.dataset, dtype={"date": "string"})
    spec = ARXSpec(tuple(args.input_columns), args.target_column, flow_column=args.flow_column)
    days = resample_days(dataset, args.step_s, input_columns=spec.inputs, target_column=spec.target,
                         time_column=args.time_column, valid_column=args.valid_column,
                         segment_column=args.segment_column, max_gap_s=args.max_gap_s)
    results, predictions, fitted = evaluate_baselines(
        days, spec=spec, horizons=args.horizons_min, step_s=args.step_s,
        train_days=args.train_days, evaluation_days=args.evaluation_days)
    if hashlib.sha256(args.dataset.read_bytes()).hexdigest() != input_hash:
        raise RuntimeError("Input changed during the run")
    manifest = {"scope": "EXPLORATORY_BASELINE_NOT_FROZEN_MANUSCRIPT_REPLAY",
                "split": "EXPLICIT_DAYS" if args.train_days else "LEAVE_ONE_DAY_OUT",
                "step_s": args.step_s, "horizons_min": args.horizons_min,
                "time_column": args.time_column, "legacy_clock_acknowledged": args.allow_legacy_clock,
                "target_column": spec.target, "input_columns": list(spec.inputs),
                "valid_column": args.valid_column, "segment_column": args.segment_column,
                "max_gap_s": args.max_gap_s if args.max_gap_s is not None else 2 * args.step_s,
                "arx": {"n_a": spec.n_a, "n_b_nonflow": spec.n_b, "n_b_flow": 1,
                        "n_k": spec.n_k, "input_index": "target - 1 - n_k - lag", "burn": spec.burn},
                "conditional_inputs": "REALIZED_EXOGENOUS_INPUTS", "temperature_clipping": False,
                "input_sha256": input_hash,
                "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                "fitted_models": fitted}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output_dir / outputs[0], index=False)
    predictions.to_csv(args.output_dir / outputs[1], index=False)
    (args.output_dir / outputs[2]).write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"scope": manifest["scope"], "metric_rows": len(results),
                      "nonfinite_metric_rows": int((results["status"] == "NONFINITE_PREDICTIONS").sum())}))


if __name__ == "__main__":
    main()
