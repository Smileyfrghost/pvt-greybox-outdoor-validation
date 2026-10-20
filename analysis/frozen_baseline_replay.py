"""Replay frozen baseline v1.1 on explicit external support, without fitting."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from .check_model_ready_60s import local_times
else:
    from check_model_ready_60s import local_times

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "data" / "metadata" / "frozen_baselines"
PARAMETERS = METADATA / "baseline_model_parameters.json"
INPUTS = ["G", "Tamb", "Ttank", "Pel", "flow"]
COLUMNS = ["G", "Tamb", "T_tank_measured", "P", "flow_mL_min"]
TASKS = {"one_step", "conditional_horizon", "free_run", "static_contemporaneous", "static_common"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_parameters() -> dict:
    sources = json.loads((METADATA / "source_manifest.json").read_text(encoding="utf-8-sig"))
    for item in sources["byte_preserved_files"]:
        path = METADATA / item["public_name"]
        if digest(path) != item["sha256"].lower():
            raise ValueError(f"Frozen source hash changed: {path.name}")
    return json.loads(PARAMETERS.read_text(encoding="utf-8-sig"))


def integer(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def arx_terminal(y: np.ndarray, u: np.ndarray, origin: int, horizon: int, model: dict) -> float:
    history = {index: float(y[index]) for index in range(origin - model["n_a"] + 1, origin + 1)}
    for target in range(origin + 1, origin + horizon + 1):
        value = float(model["intercept_raw"])
        for lag, coefficient in enumerate(model["a_raw"], 1):
            value += coefficient * history[target - lag]
        for column, name in enumerate(INPUTS):
            for lag, coefficient in enumerate(model["b_raw_by_input_and_lag"][name]):
                source = target - 1 - model["n_k"] - lag
                if source < 0 or source >= len(u):
                    raise ValueError("ARX input history leaves its segment")
                value += coefficient * u[source, column]
        history[target] = float(value)
    return history[origin + horizon]


def metrics(observed: np.ndarray, predicted: np.ndarray) -> dict:
    count = len(observed)
    if not count:
        return {"N": 0, "status": "EMPTY_SUPPORT", "RMSE_C": None, "MAE_C": None, "Bias_C": None}
    with np.errstate(over="ignore", invalid="ignore"):
        residual = predicted - observed
        values = [np.sqrt(np.mean(residual**2)), np.mean(np.abs(residual)), np.mean(residual)]
    if not np.isfinite(predicted).all() or not np.isfinite(values).all():
        return {"N": count, "status": "NONFINITE_PREDICTIONS", "RMSE_C": None, "MAE_C": None, "Bias_C": None}
    return dict(N=count, status="SCORED", **dict(zip(["RMSE_C", "MAE_C", "Bias_C"], map(float, values))))


def replay(frame: pd.DataFrame, support: dict, parameters: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    if support.get("schema") != "frozen-baseline-support-v1" or support.get("sampling_seconds") != 60:
        raise ValueError("Expected the 60 s frozen-baseline-support-v1 contract")
    if not support.get("segments"):
        raise ValueError("Support must explicitly contain segments")
    required = {"row_id", "date", "aggregation_segment", "window_start", "T_panel_center", *COLUMNS}
    if missing := required - set(frame):
        raise ValueError(f"Missing dataset fields: {sorted(missing)}")
    if frame["row_id"].isna().any() or frame["row_id"].astype(str).duplicated().any():
        raise ValueError("Row identifiers must be present and unique")
    indexed = frame.copy()
    indexed["row_id"] = indexed["row_id"].astype(str)
    indexed = indexed.set_index("row_id", drop=False)
    model = parameters["selected_arx"]
    if (model["n_a"], model["n_b"], model["n_k"], model["flow_n_b"], model["burn"]) != (2, 2, 1, 1, 3):
        raise ValueError("Frozen ARX structure must remain (2,2,1,flow1), burn=3")
    if len(model["a_raw"]) != 2 or any(len(model["b_raw_by_input_and_lag"][name]) != (1 if name == "flow" else 2) for name in INPUTS):
        raise ValueError("Frozen coefficient layout mismatch")
    coefficients = [model["intercept_raw"], *model["a_raw"], parameters["static"]["intercept_raw"]]
    coefficients += [b for name in INPUTS for b in model["b_raw_by_input_and_lag"][name]]
    coefficients += [parameters["static"]["coefficients_raw"][name] for name in INPUTS]
    if not np.isfinite(coefficients).all():
        raise ValueError("Nonfinite frozen coefficients")
    predictions, scores = [], []
    seen_ids, seen_rows = set(), set()
    for segment in support["segments"]:
        segment_id = segment["id"]
        row_ids = segment["row_ids"]
        if not isinstance(segment_id, str) or not segment_id.strip() or segment_id in seen_ids:
            raise ValueError("Segment identifiers must be nonempty and unique")
        seen_ids.add(segment_id)
        if not row_ids or any(not isinstance(row, str) or row not in indexed.index or row in seen_rows for row in row_ids) or len(row_ids) != len(set(row_ids)):
            raise ValueError("Unknown, duplicate or shared segment row identifier")
        seen_rows.update(row_ids)
        part = indexed.loc[row_ids]
        if part[["date", "aggregation_segment"]].isna().any().any() or part["date"].nunique() != 1 or part["aggregation_segment"].nunique() != 1:
            raise ValueError("A segment cannot cross dates or supplied event labels")
        times = local_times(part["window_start"], "Asia/Shanghai")
        if not times.dt.strftime("%Y-%m-%d").eq(part["date"].astype(str)).all() or not times.eq(times.dt.floor("min")).all():
            raise ValueError("Invalid date or minute label")
        if not times.diff().dropna().dt.total_seconds().eq(60).all():
            raise ValueError("A segment cannot bridge missing, duplicate or reordered minutes")
        values = part[["T_panel_center", *COLUMNS]].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Missing/nonfinite input: revise external support, never interpolate")
        y, u = values[:, 0], values[:, 1:]
        if (u[:, 4] < 0).any() or not np.all(u[:, 4] == u[0, 4]):
            raise ValueError("Negative flow or a supplied segment crossing a flow event")
        burn = integer(segment["initialization_rows"], "initialization_rows")
        if burn != model["burn"]:
            raise ValueError("Frozen replay requires the original three-row initialization")
        groups = segment.get("tasks")
        if not isinstance(groups, list) or not groups:
            raise ValueError("Each segment needs explicit tasks and support pairs")
        seen_groups = set()
        for group in groups:
            task = group["task"]
            horizon = group.get("horizon_steps")
            if task not in TASKS:
                raise ValueError("Unknown scoring task")
            if task in {"one_step", "conditional_horizon"}:
                horizon = integer(horizon, "horizon_steps")
                if horizon < 1 or (task == "one_step" and horizon != 1):
                    raise ValueError("Invalid prediction horizon")
            elif horizon is not None:
                raise ValueError("Static and free-run tasks do not have a fixed horizon")
            if (task, horizon) in seen_groups:
                raise ValueError("Duplicate task/horizon group")
            seen_groups.add((task, horizon))
            pairs = group["pairs"]
            if not isinstance(pairs, list):
                raise ValueError("Explicit support pairs must be a list, including when empty")
            normalized = []
            for pair in pairs:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("Support pairs must be [origin, target]")
                origin, target = pair
                target = integer(target, "target")
                if not 0 <= target < len(y) or (task != "static_contemporaneous" and target < burn):
                    raise ValueError("Target leaves segment or scores initialization")
                if task.startswith("static"):
                    if origin is not None:
                        raise ValueError("Static estimates require a null origin")
                else:
                    origin = integer(origin, "origin")
                    if task == "free_run":
                        if origin != 0:
                            raise ValueError("Frozen free-run origin is the segment start")
                    elif origin < burn - 1 or target != origin + horizon:
                        raise ValueError("Invalid origin, horizon or history support")
                normalized.append((origin, target))
            if len(normalized) != len(set(normalized)):
                raise ValueError("Duplicate scoring pairs")
            names = ["Static_OLS"] if task.startswith("static") else ["Persistence", model["name"]]
            local_predictions = {name: [] for name in names}
            trajectory = None
            if task == "free_run" and normalized:
                trajectory = np.full(len(y), np.nan)
                trajectory[:burn] = y[:burn]
                for target in range(burn, max(target for _, target in normalized) + 1):
                    trajectory[target] = arx_terminal(trajectory, u, target - 1, 1, model)
            for origin, target in normalized:
                if task.startswith("static"):
                    value = parameters["static"]["intercept_raw"] + sum(parameters["static"]["coefficients_raw"][name] * u[target, index] for index, name in enumerate(INPUTS))
                    predicted = [value]
                elif task == "free_run":
                    predicted = [y[0], trajectory[target]]
                else:
                    predicted = [y[origin], arx_terminal(y, u, origin, horizon, model)]
                for name, value in zip(names, predicted):
                    local_predictions[name].append(value)
                    predictions.append({"task": task, "model": name, "segment": segment_id, "origin_index": origin, "target_index": target, "horizon_steps": horizon, "row_id": row_ids[target], "observed_C": y[target], "predicted_C": value})
            observed = np.array([y[target] for _, target in normalized])
            for name in names:
                scores.append({"task": task, "model": name, "segment": segment_id, "horizon_steps": horizon, **metrics(observed, np.array(local_predictions[name]))})
    prediction_frame = pd.DataFrame(predictions, columns=["task", "model", "segment", "origin_index", "target_index", "horizon_steps", "row_id", "observed_C", "predicted_C"])
    return prediction_frame, pd.DataFrame(scores)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--support", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Use a new output directory; existing results are never overwritten")
    support = json.loads(args.support.read_text(encoding="utf-8-sig"))
    if support.get("dataset_sha256") != digest(args.dataset):
        parser.error("Dataset hash does not match the external support lock")
    predictions, scores = replay(pd.read_csv(args.dataset, dtype={"row_id": str}), support, load_parameters())
    manifest = {"input_sha256": digest(args.dataset), "support_sha256": digest(args.support), "parameters_sha256": digest(PARAMETERS), "code_sha256": digest(Path(__file__)), "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "support_provenance_claim": support.get("provenance", "unspecified"), "fit_calls": 0, "model_selection_calls": 0, "physical_validation": False, "support_authenticity_verified": False, "claim_boundary": "Fixed-parameter replay of supplied rows/support; not automatic manuscript reproduction or a new blind test."}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    predictions.to_csv(args.output_dir / "predictions.csv", index=False)
    scores.to_csv(args.output_dir / "metrics.csv", index=False)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"prediction_rows": len(predictions), "score_groups": len(scores), **manifest}, indent=2))


if __name__ == "__main__":
    main()
