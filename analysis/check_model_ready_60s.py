"""Check the reviewed 60 s table interface; never fit or rebuild measurements."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data" / "metadata" / "model_ready_60s_contract.json"
CONFIG = ROOT / "data" / "metadata" / "processing_config_60s_frozen.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def boolean(series: pd.Series) -> pd.Series:
    values = series.astype(str).str.strip().str.lower()
    if not values.isin(["true", "false", "1", "0"]).all():
        raise ValueError(f"Invalid boolean values in {series.name}")
    return values.isin(["true", "1"])


def local_times(series: pd.Series, timezone: str) -> pd.Series:
    result = []
    for value in series:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            raise ValueError(f"Missing timestamp in {series.name}")
        result.append(stamp.tz_localize(timezone) if stamp.tzinfo is None else stamp.tz_convert(timezone))
    return pd.Series(pd.DatetimeIndex(result), index=series.index)


def check_table(frame: pd.DataFrame, contract: dict, config: dict) -> dict:
    missing = set(contract["required_columns"]) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Empty table has no interface acceptance evidence")
    if config["aggregation"]["window_seconds"] != 60:
        raise ValueError("This interface is defined only for 60 s windows")
    minimum = float(config["aggregation"]["minimum_fraction_valid"])
    if not 0 < minimum <= 1:
        raise ValueError("Invalid minimum valid fraction")
    frame = frame.copy().reset_index(drop=True)
    if frame[["date", "aggregation_segment", "pump_state", "quality_flag"]].isna().any().any():
        raise ValueError("Missing date, segment, pump state or quality label")
    start = local_times(frame["window_start"], contract["timezone"])
    end = local_times(frame["window_end"], contract["timezone"])
    if not ((end - start).dt.total_seconds() == 60).all():
        raise ValueError("Windows must span exactly 60 seconds")
    if not start.eq(start.dt.floor("min")).all():
        raise ValueError("Window starts must be on minute boundaries")
    if not start.dt.strftime("%Y-%m-%d").eq(frame["date"].astype(str)).all():
        raise ValueError("Date disagrees with the local window timestamp")
    frame["_start"] = start
    if frame.duplicated(["date", "aggregation_segment", "_start"]).any():
        raise ValueError("Duplicate window within an aggregation segment")
    if (frame["aggregation_segment"].astype(str).str.strip() == "").any():
        raise ValueError("Empty segment label")
    flags = {column: boolean(frame[column]) for column in contract["boolean_columns"]}
    counts = frame[["n_expected_samples", "n_raw_samples", "n_valid_samples"]].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(counts.to_numpy()).all() or not counts.eq(np.floor(counts)).all().all():
        raise ValueError("Sample counts must be finite integers")
    if (counts["n_expected_samples"] <= 0).any() or (counts[["n_raw_samples", "n_valid_samples"]] < 0).any().any():
        raise ValueError("Invalid sample counts")
    if (counts["n_valid_samples"] > counts["n_raw_samples"]).any():
        raise ValueError("Valid sample count exceeds raw count")
    fraction = pd.to_numeric(frame["fraction_valid"], errors="raise")
    expected_fraction = np.minimum(1, counts["n_valid_samples"] / counts["n_expected_samples"])
    if not np.isfinite(fraction).all() or not np.allclose(fraction, expected_fraction, rtol=0, atol=1e-12):
        raise ValueError("Valid fraction disagrees with sample counts")
    ready = flags["model_ready_use"]
    blocked = (fraction < minimum) | flags["event_boundary_window"] | flags["contains_review_required_native"] | flags["diagnostic_only"]
    if (ready & blocked).any():
        raise ValueError("Model-ready flag conflicts with coverage, event, review or diagnostic exclusion")
    if (ready & frame["quality_flag"].ne("good")).any():
        raise ValueError("Model-ready rows require good quality")
    for column in ["identification_use", "validation_use", "model_selection_use", "tuning_use"]:
        if (flags[column] & ~ready).any():
            raise ValueError(f"{column} cannot enable a non-model-ready row")
    if (flags["identification_use"] & flags["validation_use"]).any():
        raise ValueError("Identification and validation roles overlap")
    heldout = frame["date"].eq(contract["held_out_date"])
    if (heldout & (flags["identification_use"] | flags["model_selection_use"] | flags["tuning_use"])).any():
        raise ValueError("Held-out date cannot enable identification, selection or tuning")
    validation_scope = heldout & frame["aggregation_segment"].astype(str).str.startswith("326_post_intervention")
    if (flags["validation_use"] & ~validation_scope).any():
        raise ValueError("Validation use is limited to the reviewed post-intervention scope")
    if (frame["date"].eq("2026-03-22") & ready).any():
        raise ValueError("Rejected day cannot supply model-ready rows")
    values = frame[contract["model_inputs"] + [contract["target"]]].apply(pd.to_numeric, errors="raise")
    finite = pd.Series(np.isfinite(values.to_numpy()).all(axis=1))
    flow = values["flow_mL_min"]
    if (flow.dropna() < 0).any() or (~frame["pump_state"].isin(["on", "off"])).any():
        raise ValueError("Invalid flow or pump state")
    if (frame["pump_state"].eq("off") & flow.ne(0)).any():
        raise ValueError("Pump-off rows require zero prescribed flow")
    complete = ready & finite
    # Duplicate minute fragments can exist in the audit, but cannot be eligible.
    shared_minute = frame.duplicated(["date", "_start"], keep=False)
    if (shared_minute & (ready | ~flags["event_boundary_window"])).any():
        raise ValueError("Split-minute fragments must be event-excluded audit rows")
    adjacent_pairs = 0
    runs = 0
    for _, part in frame.groupby(["date", "aggregation_segment"], sort=False):
        if not part["_start"].is_monotonic_increasing:
            raise ValueError("Nonmonotonic segment timestamps; do not silently sort")
        legal = complete.loc[part.index]
        adjacent = part["_start"].diff().dt.total_seconds().eq(60)
        paired = legal & legal.shift(1, fill_value=False) & adjacent
        adjacent_pairs += int(paired.sum())
        runs += int((legal & ~paired).sum())
    return {
        "status": "INTERFACE_CHECK_PASSED", "rows": len(frame),
        "declared_model_ready_rows": int(ready.sum()), "complete_model_input_rows": int(complete.sum()),
        "rows_missing_model_inputs": int((~finite).sum()),
        "continuous_60s_pairs": adjacent_pairs, "continuous_input_runs": runs,
        "role_counts": {name: int(values.sum()) for name, values in flags.items()},
        "data_scope": "USER_SUPPLIED_TABLE_NOT_VERIFIED_MEASUREMENT",
        "raw_qc_rebuilt": False, "model_fitted": False, "frozen_result_reproduced": False,
        "physical_validation": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; use a new path")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8-sig"))
    config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    report = check_table(pd.read_csv(args.dataset), contract, config)
    report["provenance"] = {
        "input_sha256": sha256(args.dataset), "contract_sha256": sha256(CONTRACT),
        "processing_config_sha256": sha256(CONFIG), "code_sha256": sha256(Path(__file__)),
        "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
