"""Diagnose, but do not silently assert, electro-thermal clock alignment.

Electrical logs contain wall-clock timestamps. Most thermal logger files contain
only a relative counter, so their clock offset is not identifiable from metadata
alone. This script scans candidate offsets using irradiance--power agreement,
reports ambiguity, and keeps file modification times as secondary forensic
evidence only. It does not write a paper-ready aligned dataset.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "pvt-matplotlib-cache"))


THERMAL_FILENAMES = {
    "2026-03-16": "3.16.txt",
    "2026-03-17": "3.17.docx",
    "2026-03-18": "3.18.txt",
    "2026-03-19": "3.19.txt",
    "2026-03-20": "3.20.txt",
    "2026-03-21": "3.21.txt",
    "2026-03-22": "3.22.txt",
    "2026-03-25": "3.25.txt",
    "2026-03-26": "3.26.txt",
}


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def _rank_correlation(x: np.ndarray, y: np.ndarray) -> float:
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 20:
        return math.nan
    x_rank = pd.Series(x[valid]).rank(method="average").to_numpy()
    y_rank = pd.Series(y[valid]).rank(method="average").to_numpy()
    if np.std(x_rank) == 0 or np.std(y_rank) == 0:
        return math.nan
    return float(np.corrcoef(x_rank, y_rank)[0, 1])


def _event_correlation(x: np.ndarray, y: np.ndarray) -> float:
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 20:
        return math.nan
    x_smooth = pd.Series(x[valid]).rolling(3, center=True, min_periods=1).median().to_numpy()
    y_smooth = pd.Series(y[valid]).rolling(3, center=True, min_periods=1).median().to_numpy()
    dx = np.diff(x_smooth)
    dy = np.diff(y_smooth)
    if np.std(dx) == 0 or np.std(dy) == 0:
        return math.nan
    return float(np.corrcoef(dx, dy)[0, 1])


def _alignment_score(irradiance: np.ndarray, power: np.ndarray) -> tuple[float, float, float, int]:
    valid = np.isfinite(irradiance) & np.isfinite(power)
    n_pairs = int(valid.sum())
    rank_corr = _rank_correlation(irradiance, power)
    event_corr = _event_correlation(irradiance, power)
    components = [(0.75, rank_corr), (0.25, event_corr)]
    available = [(weight, value) for weight, value in components if np.isfinite(value)]
    if not available:
        return math.nan, rank_corr, event_corr, n_pairs
    score = sum(weight * value for weight, value in available) / sum(weight for weight, _ in available)
    return float(score), rank_corr, event_corr, n_pairs


def estimate_reference_sample_period(thermal: pd.DataFrame) -> dict:
    """Estimate the normal thermal sampling period from the timestamped reference day."""
    timestamps = pd.to_datetime(thermal.get("timestamp"), errors="coerce")
    dated = thermal.assign(_timestamp=timestamps).dropna(subset=["_timestamp"])
    if dated.empty:
        raise ValueError("No timestamped thermal reference day is available")
    coverage = dated.groupby("experiment_date")["_timestamp"].count() / thermal.groupby("experiment_date").size()
    reference_dates = coverage[coverage >= 0.95].index.tolist()
    if not reference_dates:
        raise ValueError("No thermal day has at least 95% timestamp coverage")
    reference = dated[dated["experiment_date"] == reference_dates[0]].sort_values("sample_order")
    deltas = reference["_timestamp"].diff().dt.total_seconds().dropna()
    normal = deltas[(deltas > 0) & (deltas < 60)]
    if len(normal) < 20:
        raise ValueError("Too few normal timestamp intervals to estimate the sample period")
    return {
        "reference_date": str(reference_dates[0]),
        "sample_period_s": float(normal.median()),
        "p05_s": float(normal.quantile(0.05)),
        "p95_s": float(normal.quantile(0.95)),
        "normal_intervals": int(len(normal)),
        "long_gap_count": int((deltas >= 60).sum()),
        "maximum_gap_s": float(deltas.max()),
    }


def _relative_seconds(frame: pd.DataFrame, sample_period_s: float) -> pd.Series:
    wall_elapsed = (
        pd.to_numeric(frame["wall_elapsed_s"], errors="coerce")
        if "wall_elapsed_s" in frame
        else pd.Series(np.nan, index=frame.index)
    )
    if wall_elapsed.notna().mean() >= 0.95:
        return wall_elapsed
    return pd.to_numeric(frame["sample_order"], errors="raise") * sample_period_s


def _relative_thermal_bins(frame: pd.DataFrame, bin_seconds: int, sample_period_s: float) -> pd.Series:
    work = frame.loc[frame["valid_sensor_range"].astype(bool), ["sample_order", "G_W_m2"]].copy()
    work["relative_s"] = _relative_seconds(frame, sample_period_s).loc[work.index]
    work["bin"] = np.floor(work["relative_s"] / bin_seconds).astype(int)
    series = work.groupby("bin")["G_W_m2"].median()
    complete = series.reindex(range(int(series.index.max()) + 1))
    return complete.interpolate(limit=2, limit_direction="both")


def _electrical_bins(frame: pd.DataFrame, bin_seconds: int) -> pd.Series:
    work = frame.loc[frame["valid_for_model"].astype(bool), ["timestamp", "active_power_W"]].copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"])
    return (
        work.set_index("timestamp")["active_power_W"]
        .resample(f"{bin_seconds}s")
        .median()
        .interpolate(limit=2, limit_direction="both")
    )


def scan_candidate_offsets(
    thermal: pd.DataFrame,
    electrical: pd.DataFrame,
    bin_seconds: int = 30,
    sample_period_s: float = 5.834,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Scan start offsets that keep the full relative thermal record in the power log."""
    thermal_bins = _relative_thermal_bins(thermal, bin_seconds, sample_period_s)
    power_bins = _electrical_bins(electrical, bin_seconds)
    max_offset = len(power_bins) - len(thermal_bins)
    if max_offset < 0:
        raise ValueError("Thermal duration exceeds electrical duration; full-overlap scan is impossible")
    rows = []
    irradiance = thermal_bins.to_numpy(dtype=float)
    for offset_bin in range(max_offset + 1):
        power = power_bins.iloc[offset_bin : offset_bin + len(thermal_bins)].to_numpy(dtype=float)
        score, rank_corr, event_corr, n_pairs = _alignment_score(irradiance, power)
        start = power_bins.index[offset_bin]
        rows.append(
            {
                "offset_bin": offset_bin,
                "offset_from_electrical_start_s": offset_bin * bin_seconds,
                "candidate_start": start,
                "candidate_end": start + pd.Timedelta(seconds=int(thermal_bins.index.max() * bin_seconds)),
                "score": score,
                "rank_correlation": rank_corr,
                "event_correlation": event_corr,
                "paired_bins": n_pairs,
            }
        )
    return pd.DataFrame(rows), thermal_bins, power_bins


def _direct_timestamp_score(
    thermal: pd.DataFrame, electrical: pd.DataFrame, bin_seconds: int
) -> dict | None:
    timestamps = pd.to_datetime(thermal.get("timestamp"), errors="coerce")
    if timestamps.notna().mean() < 0.95:
        return None
    thermal_work = thermal.loc[timestamps.notna() & thermal["valid_sensor_range"].astype(bool), ["G_W_m2"]].copy()
    thermal_work.index = timestamps[timestamps.notna() & thermal["valid_sensor_range"].astype(bool)]
    irradiance = thermal_work["G_W_m2"].resample(f"{bin_seconds}s").median()
    power = _electrical_bins(electrical, bin_seconds)
    paired = pd.concat([irradiance.rename("G"), power.rename("P")], axis=1, join="inner").dropna()
    score, rank_corr, event_corr, n_pairs = _alignment_score(
        paired["G"].to_numpy(dtype=float), paired["P"].to_numpy(dtype=float)
    )
    return {
        "start": timestamps.min().isoformat(),
        "end": timestamps.max().isoformat(),
        "score": score,
        "rank_correlation": rank_corr,
        "event_correlation": event_corr,
        "paired_bins": n_pairs,
        "timestamp_coverage_fraction": float(timestamps.notna().mean()),
    }


def reconstruct_thermal_timestamps(
    thermal: pd.DataFrame,
    electrical: pd.DataFrame,
    sample_period_s: float,
) -> tuple[pd.Series, str]:
    """Use recorded timestamps when present; otherwise anchor the fixed-rate log at power stop."""
    recorded = pd.to_datetime(thermal.get("timestamp"), errors="coerce")
    if recorded.notna().mean() >= 0.95:
        return recorded, "recorded_wall_clock"
    electrical_end = pd.to_datetime(electrical["timestamp"]).max()
    relative = _relative_seconds(thermal, sample_period_s)
    aligned_start = electrical_end - pd.Timedelta(seconds=float(relative.max()))
    return aligned_start + pd.to_timedelta(relative, unit="s"), "author_confirmed_common_stop_fixed_period"


def _score_at_timestamps(
    thermal: pd.DataFrame,
    electrical: pd.DataFrame,
    aligned_timestamps: pd.Series,
    bin_seconds: int,
) -> tuple[dict, pd.DataFrame]:
    thermal_valid = thermal["valid_sensor_range"].astype(bool) & aligned_timestamps.notna()
    thermal_work = thermal.loc[
        thermal_valid, ["T_panel_C", "T_tank_C", "T_inlet_C", "G_W_m2"]
    ].copy()
    thermal_work.index = pd.DatetimeIndex(aligned_timestamps[thermal_valid])
    thermal_bins = thermal_work.resample(f"{bin_seconds}s").median()

    electrical_valid = electrical["valid_for_model"].astype(bool)
    electrical_work = electrical.loc[
        electrical_valid, ["timestamp", "voltage_V", "current_A", "active_power_W"]
    ].copy()
    electrical_work["timestamp"] = pd.to_datetime(electrical_work["timestamp"])
    electrical_bins = electrical_work.set_index("timestamp").resample(f"{bin_seconds}s").median()

    paired = thermal_bins.join(electrical_bins, how="inner").dropna(subset=["G_W_m2", "active_power_W"])
    score, rank_corr, event_corr, n_pairs = _alignment_score(
        paired["G_W_m2"].to_numpy(dtype=float), paired["active_power_W"].to_numpy(dtype=float)
    )
    summary = {
        "start": aligned_timestamps.min().isoformat(),
        "end": aligned_timestamps.max().isoformat(),
        "overlap_start": paired.index.min().isoformat() if len(paired) else None,
        "overlap_end": paired.index.max().isoformat() if len(paired) else None,
        "paired_bins": n_pairs,
        "score": score,
        "rank_correlation": rank_corr,
        "event_correlation": event_corr,
    }
    return summary, paired


def _alignment_sensitivity(
    thermal: pd.DataFrame,
    electrical: pd.DataFrame,
    aligned_timestamps: pd.Series,
    bin_seconds: int,
) -> list[dict]:
    rows = []
    for shift_s in (-120, -60, -30, 0, 30, 60, 120):
        summary, _ = _score_at_timestamps(
            thermal,
            electrical,
            aligned_timestamps + pd.Timedelta(seconds=shift_s),
            bin_seconds,
        )
        rows.append({"shift_s": shift_s, "score": summary["score"], "paired_bins": summary["paired_bins"]})
    return rows


def _separated_top_candidates(scan: pd.DataFrame, bin_seconds: int, count: int = 5) -> pd.DataFrame:
    separation_bins = max(1, round(600 / bin_seconds))
    chosen = []
    for row in scan.sort_values("score", ascending=False).itertuples(index=False):
        if all(abs(row.offset_bin - previous.offset_bin) >= separation_bins for previous in chosen):
            chosen.append(row)
        if len(chosen) == count:
            break
    return pd.DataFrame(chosen, columns=scan.columns)


def _classify_candidate(scan: pd.DataFrame, bin_seconds: int) -> dict:
    ranked = scan.sort_values("score", ascending=False).reset_index(drop=True)
    best = ranked.iloc[0]
    separated = _separated_top_candidates(scan, bin_seconds)
    competitor_score = float(separated.iloc[1]["score"]) if len(separated) > 1 else math.nan
    margin = float(best["score"] - competitor_score) if np.isfinite(competitor_score) else math.nan
    near_peak = scan[scan["score"] >= float(best["score"]) - 0.02]
    peak_width_s = int((near_peak["offset_bin"].max() - near_peak["offset_bin"].min()) * bin_seconds)
    if best["score"] >= 0.75 and margin >= 0.05 and peak_width_s <= 300:
        classification = "strong_candidate_not_clock_confirmed"
    elif best["score"] >= 0.55 and margin >= 0.02 and peak_width_s <= 1_200:
        classification = "moderate_candidate_not_clock_confirmed"
    else:
        classification = "ambiguous_candidate"
    return {
        "classification": classification,
        "best_score": float(best["score"]),
        "best_start": pd.Timestamp(best["candidate_start"]).isoformat(),
        "best_end": pd.Timestamp(best["candidate_end"]).isoformat(),
        "margin_to_10min_separated_competitor": margin,
        "near_peak_width_s": peak_width_s,
    }


def _forensic_mtime(
    date: str, raw_dir: Path | None, electrical_end: pd.Timestamp, thermal_duration_s: float
) -> dict | None:
    if raw_dir is None or date not in THERMAL_FILENAMES:
        return None
    path = raw_dir / THERMAL_FILENAMES[date]
    if not path.exists():
        return None
    modified = pd.Timestamp.fromtimestamp(path.stat().st_mtime)
    return {
        "source_file": path.name,
        "file_modified_time": modified.isoformat(),
        "gap_from_electrical_end_s": float((modified - electrical_end).total_seconds()),
        "start_if_mtime_were_end": (modified - pd.Timedelta(seconds=thermal_duration_s)).isoformat(),
        "use_restriction": "secondary forensic evidence only; not a measured logger timestamp and not used in scoring",
    }


def _plot_scan_grid(scans: dict[str, pd.DataFrame], summaries: dict, output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 3, figsize=(12, 8.5), constrained_layout=True, sharey=True)
    for ax, date in zip(axes.flat, sorted(scans)):
        scan = scans[date]
        ax.plot(scan["candidate_start"], scan["score"], color="#0072B2", linewidth=1.2)
        best_start = pd.Timestamp(summaries[date]["candidate_assessment"]["best_start"])
        ax.axvline(best_start, color="#D55E00", linewidth=1.0, label="best candidate")
        operational = summaries[date]["operational_alignment"]
        ax.axvline(
            pd.Timestamp(operational["start"]),
            color="#009E73",
            linestyle="--",
            linewidth=1.0,
            label="operational alignment",
        )
        forensic = summaries[date].get("forensic_file_time")
        if forensic:
            ax.axvline(pd.Timestamp(forensic["start_if_mtime_were_end"]), color="0.4", linestyle=":", linewidth=0.9, label="mtime-derived")
        ax.set_title(f"{date}\n{summaries[date]['primary_alignment_status'].replace('_', ' ')}", fontsize=8)
        ax.grid(True, alpha=0.25)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.tick_params(axis="x", labelrotation=35, labelsize=7)
        ax.tick_params(axis="y", labelsize=7)
    axes[1, 0].set_ylabel("Alignment score")
    axes[-1, 1].set_xlabel("Candidate thermal start (wall-clock time)")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    if by_label:
        fig.legend(by_label.values(), by_label.keys(), loc="outside lower center", ncol=3, fontsize=8)
    fig.suptitle("Electro-thermal alignment scan with recorded/end-anchored operational clocks", fontsize=11)
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _plot_candidate_overlays(
    paired_by_date: dict[str, pd.DataFrame],
    summaries: dict,
    output_path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 3, figsize=(12, 8.5), constrained_layout=True, sharey=True)
    for ax, date in zip(axes.flat, sorted(paired_by_date)):
        paired = paired_by_date[date]
        g_values = paired["G_W_m2"].to_numpy(dtype=float)
        p_values = paired["active_power_W"].to_numpy(dtype=float)
        g_scale = np.nanpercentile(g_values, 95) or 1.0
        p_scale = np.nanpercentile(p_values, 95) or 1.0
        origin = paired.index.min()
        hours = (paired.index - origin).total_seconds() / 3600
        ax.plot(hours, g_values / g_scale, color="#E69F00", label="irradiance")
        ax.plot(hours, p_values / p_scale, color="#0072B2", label="power")
        source = summaries[date]["alignment_basis"].replace("_", " ")
        ax.set_title(f"{date} ({source})", fontsize=8)
        ax.grid(True, alpha=0.25)
        ax.tick_params(labelsize=7)
    axes[1, 0].set_ylabel("Normalized signal")
    axes[-1, 1].set_xlabel("Hours from plotted overlap origin")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="outside lower center", ncol=2, fontsize=8)
    fig.suptitle("Irradiance and electrical power under recorded/end-anchored alignment", fontsize=11)
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def diagnose(
    thermal_csv: Path,
    electrical_csv: Path,
    output_dir: Path,
    raw_thermal_dir: Path | None = None,
    bin_seconds: int = 30,
) -> dict:
    thermal = pd.read_csv(thermal_csv, dtype={"experiment_date": "string", "date": "string"})
    electrical = pd.read_csv(electrical_csv, dtype={"experiment_date": "string"}, parse_dates=["timestamp"])
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_period_audit = estimate_reference_sample_period(thermal)
    sample_period_s = float(sample_period_audit["sample_period_s"])
    scans: dict[str, pd.DataFrame] = {}
    summaries: dict[str, dict] = {}
    paired_by_date: dict[str, pd.DataFrame] = {}
    reconstructed_days = []
    aligned_bin_days = []
    top_rows = []

    dates = sorted(set(thermal["experiment_date"].dropna()) & set(electrical["experiment_date"].dropna()))
    for date in dates:
        thermal_day = thermal[thermal["experiment_date"] == date].copy()
        electrical_day = electrical[electrical["experiment_date"] == date].copy()
        scan, _, _ = scan_candidate_offsets(
            thermal_day,
            electrical_day,
            bin_seconds,
            sample_period_s=sample_period_s,
        )
        assessment = _classify_candidate(scan, bin_seconds)
        direct = _direct_timestamp_score(thermal_day, electrical_day, bin_seconds)
        aligned_timestamps, alignment_basis = reconstruct_thermal_timestamps(
            thermal_day,
            electrical_day,
            sample_period_s,
        )
        operational, paired = _score_at_timestamps(
            thermal_day,
            electrical_day,
            aligned_timestamps,
            bin_seconds,
        )
        sensitivity = _alignment_sensitivity(
            thermal_day,
            electrical_day,
            aligned_timestamps,
            bin_seconds,
        )
        electrical_end = pd.to_datetime(electrical_day["timestamp"]).max()
        thermal_duration_s = float(_relative_seconds(thermal_day, sample_period_s).max())
        electrical_duration_s = float(
            (pd.to_datetime(electrical_day["timestamp"]).max() - pd.to_datetime(electrical_day["timestamp"]).min()).total_seconds()
        )
        forensic = _forensic_mtime(date, raw_thermal_dir, electrical_end, thermal_duration_s)
        summaries[date] = {
            "thermal_rows": int(len(thermal_day)),
            "electrical_rows": int(len(electrical_day)),
            "thermal_reconstructed_duration_h": thermal_duration_s / 3600,
            "electrical_duration_h": electrical_duration_s / 3600,
            "duration_difference_min": (thermal_duration_s - electrical_duration_s) / 60,
            "candidate_assessment": assessment,
            "direct_timestamp_alignment": direct,
            "alignment_basis": alignment_basis,
            "operational_alignment": operational,
            "alignment_sensitivity": sensitivity,
            "primary_alignment_status": alignment_basis,
            "forensic_file_time": forensic,
        }
        separated = _separated_top_candidates(scan, bin_seconds)
        separated.insert(0, "experiment_date", date)
        top_rows.append(separated)
        scan.insert(0, "experiment_date", date)
        scans[date] = scan
        paired_by_date[date] = paired

        reconstructed = thermal_day.copy()
        reconstructed["aligned_timestamp"] = aligned_timestamps.to_numpy()
        reconstructed["alignment_basis"] = alignment_basis
        reconstructed["reference_sample_period_s"] = sample_period_s
        reconstructed_days.append(reconstructed)

        aligned_bins = paired.reset_index(names="timestamp")
        aligned_bins.insert(0, "experiment_date", date)
        aligned_bins.insert(1, "alignment_basis", alignment_basis)
        aligned_bin_days.append(aligned_bins)

    all_candidates = pd.concat(scans.values(), ignore_index=True)
    top_candidates = pd.concat(top_rows, ignore_index=True)
    all_candidates.to_csv(output_dir / "alignment_candidate_scores.csv", index=False)
    top_candidates.to_csv(output_dir / "alignment_top_candidates.csv", index=False)
    pd.concat(reconstructed_days, ignore_index=True).to_csv(
        output_dir / "thermal_clock_reconstruction_v1.csv", index=False
    )
    pd.concat(aligned_bin_days, ignore_index=True).to_csv(
        output_dir / "electrothermal_aligned_30s_v1.csv", index=False
    )
    report = {
        "method": {
            "bin_seconds": bin_seconds,
            "sample_period_audit": sample_period_audit,
            "score": "0.75 * Spearman-rank correlation(G, P) + 0.25 * correlation(smoothed first differences)",
            "search_domain": "candidate starts that keep the complete fixed-period thermal record inside the electrical log",
            "operational_rule": "Use recorded timestamps on 2026-03-17; otherwise reconstruct at the reference sampling period and anchor the final thermal sample to the final electrical timestamp.",
            "author_confirmation": "Electrical logging was generally started first, thermal/irradiance logging later, and the two were stopped together or in close succession.",
            "interpretation": "The end-anchored clock is a reproducible operational alignment supported by the timestamped reference day, duration agreement, file times where reliable, and the confirmed acquisition workflow. Sensitivity to residual shifts remains mandatory.",
        },
        "days": summaries,
    }
    report = _json_safe(report)
    (output_dir / "alignment_diagnostic.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    _plot_scan_grid(scans, summaries, output_dir / "alignment_score_grid.png")
    _plot_candidate_overlays(
        paired_by_date,
        summaries,
        output_dir / "alignment_candidate_overlays.png",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thermal-csv", type=Path, required=True)
    parser.add_argument("--electrical-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--raw-thermal-dir", type=Path)
    parser.add_argument("--bin-seconds", type=int, default=30)
    args = parser.parse_args()
    report = diagnose(
        args.thermal_csv,
        args.electrical_csv,
        args.output_dir,
        raw_thermal_dir=args.raw_thermal_dir,
        bin_seconds=args.bin_seconds,
    )
    print(json.dumps({"days": len(report["days"]), "output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
