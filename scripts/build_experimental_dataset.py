"""Rebuild the PVT outdoor experiment dataset from the original logger files.

The old ``cleaned_experiment_*.csv`` files are intentionally not used because
they duplicate rows and mislabel the third temperature channel.  The original
3.16 header identifies the channels as panel, tank, inlet and irradiance; the
fifth value is the logger time counter.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from docx import Document


DAY_CONFIG = {
    "3.16": ("3.16.txt", 300.0),
    "3.17": ("3.17.docx", 300.0),
    "3.18": ("3.18.txt", 300.0),
    "3.19": ("3.19.txt", 300.0),
    "3.20": ("3.20.txt", 300.0),
    "3.21": ("3.21.txt", 300.0),
    "3.22": ("3.22.txt", 300.0),
    "3.25": ("3.25.txt", 500.0),
    "3.26": ("3.26.txt", 500.0),
}

VALUE_RE = re.compile(
    r"([-+]?\d+(?:\.\d+)?)\s*,\s*"
    r"([-+]?\d+(?:\.\d+)?)\s*,\s*"
    r"([-+]?\d+(?:\.\d+)?)\s*,\s*"
    r"([-+]?\d+(?:\.\d+)?)\s*,\s*"
    r"([-+]?\d+(?:\.\d+)?)"
)
TIMESTAMP_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]")


def _iso_experiment_date(day: str, year: int = 2026) -> str:
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})", day)
    if not match:
        raise ValueError(f"Expected an M.D experiment label, got {day!r}")
    month, day_of_month = (int(value) for value in match.groups())
    return f"{year:04d}-{month:02d}-{day_of_month:02d}"


def _decode_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig", errors="replace")


def _records_from_text(path: Path) -> list[dict]:
    records = []
    for line in _decode_text(path).splitlines():
        match = VALUE_RE.search(line)
        if not match:
            continue
        values = [float(value) for value in match.groups()]
        records.append(dict(zip(("T_panel_C", "T_tank_C", "T_inlet_C", "G_W_m2", "logger_time_s"), values)))
    return records


def _records_from_docx(path: Path) -> list[dict]:
    records: list[dict] = []
    pending_timestamp = None
    for paragraph in Document(path).paragraphs:
        text = paragraph.text.strip()
        timestamp_match = TIMESTAMP_RE.search(text)
        if timestamp_match:
            pending_timestamp = pd.Timestamp(timestamp_match.group(1))
            continue
        value_match = VALUE_RE.search(text)
        if not value_match:
            continue
        values = [float(value) for value in value_match.groups()]
        record = dict(zip(("T_panel_C", "T_tank_C", "T_inlet_C", "G_W_m2", "logger_time_s"), values))
        record["timestamp"] = pending_timestamp
        records.append(record)
        pending_timestamp = None
    return records


def _continuous_elapsed(raw_time: pd.Series | np.ndarray) -> np.ndarray:
    """Turn a resetting logger counter into a monotonic elapsed-time vector."""
    values = np.asarray(raw_time, dtype=float)
    if len(values) == 0:
        return values
    positive_steps = np.diff(values)
    positive_steps = positive_steps[positive_steps > 0]
    default_step = float(np.median(positive_steps)) if len(positive_steps) else 1.0
    elapsed = np.zeros(len(values), dtype=float)
    for index in range(1, len(values)):
        step = values[index] - values[index - 1]
        elapsed[index] = elapsed[index - 1] + (step if step > 0 else default_step)
    return elapsed


def load_day(raw_dir: Path, day: str, filename: str, flow_ml_min: float) -> pd.DataFrame:
    path = raw_dir / filename
    records = _records_from_docx(path) if path.suffix.lower() == ".docx" else _records_from_text(path)
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        raise ValueError(f"No numeric records parsed from {path}")

    frame.insert(0, "experiment_date", _iso_experiment_date(day))
    frame.insert(1, "date", day)
    frame.insert(2, "flow_ml_min", flow_ml_min)
    frame.insert(3, "flow_kg_s", flow_ml_min / 60_000.0)
    frame.insert(4, "sample_order", np.arange(len(frame), dtype=int))
    frame["elapsed_s"] = _continuous_elapsed(frame["logger_time_s"])
    if "timestamp" not in frame:
        frame["timestamp"] = pd.NaT
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    if frame["timestamp"].notna().all():
        frame["wall_elapsed_s"] = (frame["timestamp"] - frame["timestamp"].iloc[0]).dt.total_seconds()
    else:
        frame["wall_elapsed_s"] = np.nan

    temperatures = frame[["T_panel_C", "T_tank_C", "T_inlet_C"]]
    temperature_valid = temperatures.ge(-30.0).all(axis=1) & temperatures.le(90.0).all(axis=1)
    irradiance_valid = frame["G_W_m2"].between(0.0, 1_400.0)
    frame["valid_sensor_range"] = temperature_valid & irradiance_valid
    frame["active_irradiance"] = frame["G_W_m2"] >= 100.0
    return frame


def build_dataset(raw_dir: Path) -> tuple[pd.DataFrame, dict]:
    frames = [load_day(raw_dir, day, filename, flow) for day, (filename, flow) in DAY_CONFIG.items()]
    dataset = pd.concat(frames, ignore_index=True)

    qc_days = {}
    for day, frame in dataset.groupby("experiment_date", sort=False):
        positive_dt = frame["elapsed_s"].diff()
        positive_dt = positive_dt[positive_dt > 0]
        timestamp_coverage = float(frame["timestamp"].notna().mean())
        wall_duration_h = (
            float(frame["wall_elapsed_s"].iloc[-1]) / 3600.0 if timestamp_coverage == 1.0 else None
        )
        logger_duration_h = float(frame["elapsed_s"].iloc[-1]) / 3600.0
        qc_days[day] = {
            "flow_ml_min": float(frame["flow_ml_min"].iloc[0]),
            "rows": int(len(frame)),
            "invalid_sensor_rows": int((~frame["valid_sensor_range"]).sum()),
            "active_rows": int(frame["active_irradiance"].sum()),
            "exact_duplicate_rows": int(frame.duplicated(subset=["T_panel_C", "T_tank_C", "T_inlet_C", "G_W_m2", "logger_time_s"]).sum()),
            "duration_h": round(logger_duration_h, 3),
            "logger_counter_duration_h": round(logger_duration_h, 4),
            "timestamp_coverage_fraction": timestamp_coverage,
            "wall_clock_start": frame["timestamp"].iloc[0].isoformat() if timestamp_coverage == 1.0 else None,
            "wall_clock_end": frame["timestamp"].iloc[-1].isoformat() if timestamp_coverage == 1.0 else None,
            "wall_clock_duration_h": round(wall_duration_h, 4) if wall_duration_h is not None else None,
            "wall_to_logger_duration_ratio": (
                round(wall_duration_h / logger_duration_h, 4)
                if wall_duration_h is not None and logger_duration_h > 0
                else None
            ),
            "median_step_s": round(float(positive_dt.median()), 3),
            "panel_temperature_range_C": [round(float(frame["T_panel_C"].min()), 2), round(float(frame["T_panel_C"].max()), 2)],
            "inlet_temperature_range_C": [round(float(frame["T_inlet_C"].min()), 2), round(float(frame["T_inlet_C"].max()), 2)],
            "irradiance_range_W_m2": [round(float(frame["G_W_m2"].min()), 2), round(float(frame["G_W_m2"].max()), 2)],
        }

    qc = {
        "source": "original experiment logger files",
        "channel_definition": ["panel temperature", "tank temperature", "inlet temperature", "irradiance", "logger time"],
        "rows_total": int(len(dataset)),
        "rows_valid": int(dataset["valid_sensor_range"].sum()),
        "days": qc_days,
        "known_limitations": [
            "Flow is a day-level set point (300 or 500 mL/min), not a measured time series.",
            "No outlet-water temperature channel is present; thermal power and thermal efficiency cannot be measured directly.",
            "No ambient-air temperature channel is present in these logger files.",
            "Electrical measurements are stored separately and require timestamp-based alignment before use.",
            "The fifth logger channel is retained as logger_time_s, but its wall-clock meaning is not established. On the timestamped 2026-03-17 record, wall-clock and reconstructed logger-counter durations differ materially.",
        ],
    }
    return dataset, qc


def _write_qc_markdown(qc: dict, path: Path) -> None:
    lines = [
        "# Outdoor PVT experiment data quality report",
        "",
        f"Total rows: {qc['rows_total']}; valid sensor-range rows: {qc['rows_valid']}.",
        "",
        "| Date | Flow (mL/min) | Rows | Invalid | Active G>=100 | Duration (h) | Median dt (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for day, values in qc["days"].items():
        lines.append(
            f"| {day} | {values['flow_ml_min']:.0f} | {values['rows']} | "
            f"{values['invalid_sensor_rows']} | {values['active_rows']} | "
            f"{values['duration_h']:.3f} | {values['median_step_s']:.3f} |"
        )
    lines.extend(["", "## Known limitations", ""])
    lines.extend(f"- {item}" for item in qc["known_limitations"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset, qc = build_dataset(args.raw_dir)
    dataset.to_csv(args.output_dir / "experimental_clean_v1.csv", index=False)
    (args.output_dir / "experimental_clean_v1_qc.json").write_text(
        json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_qc_markdown(qc, args.output_dir / "experimental_clean_v1_qc.md")
    print(json.dumps({"rows": len(dataset), "valid": int(dataset["valid_sensor_range"].sum())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
