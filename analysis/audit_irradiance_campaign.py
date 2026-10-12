#!/usr/bin/env python3
"""Audit minute-resolution irradiance workbooks without altering raw measurements.

The script accepts a directory of .xlsx copies (or .xls files when an Excel
engine such as xlrd is installed), validates timestamps and channel ranges,
and writes compact CSV/JSON evidence tables for research-direction decisions.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TIMESTAMP_KEY = "时间"
TOTAL_INSTANT_KEY = "总辐射"
DIRECT_INSTANT_KEY = "直接辐射"
UV_INSTANT_KEY = "紫外辐射"
SUNSHINE_KEY = "日照时"
DAILY_CUMULATIVE_KEY = "日累计"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing daily .xls/.xlsx workbooks.",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory for audit CSV/JSON outputs.",
    )
    return parser.parse_args()


def find_column(
    columns: list[str],
    *,
    required: tuple[str, ...],
    forbidden: tuple[str, ...] = (),
) -> str | None:
    matches = [
        column
        for column in columns
        if all(key in column for key in required)
        and not any(key in column for key in forbidden)
    ]
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous columns for required={required}, forbidden={forbidden}: "
            f"{matches}"
        )
    return matches[0] if matches else None


def finite_or_none(value: Any) -> float | int | str | None:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def numeric_summary(series: pd.Series, prefix: str) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce")
    finite = values[np.isfinite(values)]
    result: dict[str, Any] = {
        f"{prefix}_missing_n": int(values.isna().sum()),
        f"{prefix}_negative_n": int((finite < 0).sum()),
        f"{prefix}_zero_n": int((finite == 0).sum()),
    }
    if finite.empty:
        for suffix in ("min", "p01", "median", "p99", "max", "mean", "std"):
            result[f"{prefix}_{suffix}"] = None
        return result
    quantiles = finite.quantile([0.01, 0.50, 0.99])
    result.update(
        {
            f"{prefix}_min": float(finite.min()),
            f"{prefix}_p01": float(quantiles.loc[0.01]),
            f"{prefix}_median": float(quantiles.loc[0.50]),
            f"{prefix}_p99": float(quantiles.loc[0.99]),
            f"{prefix}_max": float(finite.max()),
            f"{prefix}_mean": float(finite.mean()),
            f"{prefix}_std": float(finite.std(ddof=1)),
        }
    )
    return result


def integrate_valid_intervals(
    timestamps: pd.Series,
    values: pd.Series,
    *,
    maximum_interval_seconds: float = 90.0,
) -> float | None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, errors="coerce"),
            "value": pd.to_numeric(values, errors="coerce"),
        }
    ).dropna()
    if len(frame) < 2:
        return None
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
    dt_seconds = frame["timestamp"].diff().dt.total_seconds()
    previous = frame["value"].shift(1)
    valid = (
        dt_seconds.gt(0)
        & dt_seconds.le(maximum_interval_seconds)
        & np.isfinite(previous)
        & np.isfinite(frame["value"])
    )
    joules_per_square_metre = (
        0.5
        * (previous.loc[valid] + frame.loc[valid, "value"])
        * dt_seconds.loc[valid]
    ).sum()
    return float(joules_per_square_metre / 1_000_000.0)


def workbook_frames(path: Path) -> list[tuple[str, pd.DataFrame]]:
    workbook = pd.read_excel(path, sheet_name=None)
    return [(str(sheet_name), frame) for sheet_name, frame in workbook.items()]


def load_campaign(
    input_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    paths = sorted(
        [
            path
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".xls", ".xlsx"}
        ],
        key=lambda path: str(path).lower(),
    )
    if not paths:
        raise FileNotFoundError(f"No .xls/.xlsx files found under {input_dir}")

    coverage_rows: list[dict[str, Any]] = []
    all_rows: list[pd.DataFrame] = []
    schema_records: list[dict[str, Any]] = []

    for path in paths:
        for sheet_name, raw in workbook_frames(path):
            raw.columns = [str(column).strip() for column in raw.columns]
            columns = list(raw.columns)
            timestamp_column = find_column(columns, required=(TIMESTAMP_KEY,))
            if timestamp_column is None:
                schema_records.append(
                    {
                        "file": str(path),
                        "sheet": sheet_name,
                        "status": "no_timestamp_column",
                        "columns": columns,
                    }
                )
                continue

            total_column = find_column(
                columns,
                required=(TOTAL_INSTANT_KEY, "瞬时"),
            )
            direct_column = find_column(
                columns,
                required=(DIRECT_INSTANT_KEY, "瞬时"),
            )
            uv_column = find_column(
                columns,
                required=(UV_INSTANT_KEY, "瞬时"),
            )
            sunshine_column = find_column(
                columns,
                required=(SUNSHINE_KEY, DAILY_CUMULATIVE_KEY),
            )
            total_cumulative_column = find_column(
                columns,
                required=(TOTAL_INSTANT_KEY, DAILY_CUMULATIVE_KEY),
            )
            uv_cumulative_column = find_column(
                columns,
                required=(UV_INSTANT_KEY, DAILY_CUMULATIVE_KEY),
            )

            timestamps_original = pd.to_datetime(
                raw[timestamp_column], errors="coerce"
            )
            valid_timestamps = timestamps_original.dropna()
            duplicate_n = int(valid_timestamps.duplicated().sum())
            original_deltas = valid_timestamps.diff().dt.total_seconds()
            non_monotonic_n = int(original_deltas.lt(0).sum())
            sorted_unique = valid_timestamps.sort_values().drop_duplicates()
            intervals = sorted_unique.diff().dt.total_seconds().dropna()

            if valid_timestamps.empty:
                first_timestamp = None
                last_timestamp = None
                observed_dates = []
            else:
                first_timestamp = valid_timestamps.min()
                last_timestamp = valid_timestamps.max()
                observed_dates = sorted(
                    str(date) for date in valid_timestamps.dt.date.unique()
                )

            median_interval_seconds = (
                float(intervals.median()) if not intervals.empty else None
            )
            maximum_gap_minutes = (
                float(intervals.max() / 60.0) if not intervals.empty else None
            )
            interval_p05_seconds = (
                float(intervals.quantile(0.05)) if not intervals.empty else None
            )
            interval_p95_seconds = (
                float(intervals.quantile(0.95)) if not intervals.empty else None
            )
            large_internal_gap_n = (
                int(
                    (
                        intervals
                        > (1.5 * float(median_interval_seconds))
                    ).sum()
                )
                if median_interval_seconds is not None
                else 0
            )

            full_day_expected_n: int | None = None
            missing_expected_n: int | None = None
            coverage_status = "unusable"
            if (
                first_timestamp is not None
                and last_timestamp is not None
                and median_interval_seconds is not None
                and median_interval_seconds > 0
                and len(observed_dates) == 1
            ):
                full_day_expected_n = int(
                    round(24 * 60 * 60 / median_interval_seconds)
                )
                missing_expected_n = max(
                    full_day_expected_n - int(len(sorted_unique)), 0
                )
                day_start = first_timestamp.normalize()
                expected_last = day_start + pd.Timedelta(days=1) - pd.Timedelta(
                    seconds=median_interval_seconds
                )
                starts_at_midnight = first_timestamp == day_start
                ends_at_expected_last = last_timestamp == expected_last
                has_large_internal_gap = large_internal_gap_n > 0
                if (
                    starts_at_midnight
                    and ends_at_expected_last
                    and missing_expected_n == 0
                    and duplicate_n == 0
                    and non_monotonic_n == 0
                    and not has_large_internal_gap
                ):
                    coverage_status = "complete"
                elif not starts_at_midnight and not ends_at_expected_last:
                    coverage_status = "partial_start_and_end"
                elif not starts_at_midnight:
                    coverage_status = "partial_start"
                elif not ends_at_expected_last:
                    coverage_status = "partial_end"
                else:
                    coverage_status = "internal_gaps_or_duplicates"
                if (
                    has_large_internal_gap
                    and "internal_gaps" not in coverage_status
                ):
                    coverage_status += "_with_internal_gaps"
            elif len(observed_dates) > 1:
                coverage_status = "multiple_dates_in_file"

            coverage_rows.append(
                {
                    "file": str(path),
                    "sheet": sheet_name,
                    "row_n": int(len(raw)),
                    "valid_timestamp_n": int(valid_timestamps.notna().sum()),
                    "unique_timestamp_n": int(len(sorted_unique)),
                    "observed_dates": ";".join(observed_dates),
                    "first_timestamp": first_timestamp,
                    "last_timestamp": last_timestamp,
                    "median_interval_seconds": median_interval_seconds,
                    "interval_p05_seconds": interval_p05_seconds,
                    "interval_p95_seconds": interval_p95_seconds,
                    "maximum_gap_minutes": maximum_gap_minutes,
                    "large_internal_gap_n": large_internal_gap_n,
                    "duplicate_timestamp_n": duplicate_n,
                    "non_monotonic_timestamp_n": non_monotonic_n,
                    "full_day_expected_n": full_day_expected_n,
                    "missing_expected_n": missing_expected_n,
                    "coverage_status": coverage_status,
                }
            )

            schema_records.append(
                {
                    "file": str(path),
                    "sheet": sheet_name,
                    "status": "loaded",
                    "columns": columns,
                    "mapping": {
                        "timestamp": timestamp_column,
                        "total_instant": total_column,
                        "direct_instant": direct_column,
                        "uv_instant": uv_column,
                        "sunshine_cumulative": sunshine_column,
                        "total_cumulative": total_cumulative_column,
                        "uv_cumulative": uv_cumulative_column,
                    },
                }
            )

            normalized = pd.DataFrame(
                {
                    "timestamp": timestamps_original,
                    "total_w_m2": (
                        pd.to_numeric(raw[total_column], errors="coerce")
                        if total_column
                        else np.nan
                    ),
                    "direct_w_m2": (
                        pd.to_numeric(raw[direct_column], errors="coerce")
                        if direct_column
                        else np.nan
                    ),
                    "uv_w_m2": (
                        pd.to_numeric(raw[uv_column], errors="coerce")
                        if uv_column
                        else np.nan
                    ),
                    "sunshine_cumulative_h": (
                        pd.to_numeric(raw[sunshine_column], errors="coerce")
                        if sunshine_column
                        else np.nan
                    ),
                    "total_cumulative_mj_m2": (
                        pd.to_numeric(
                            raw[total_cumulative_column], errors="coerce"
                        )
                        if total_cumulative_column
                        else np.nan
                    ),
                    "uv_cumulative_mj_m2": (
                        pd.to_numeric(
                            raw[uv_cumulative_column], errors="coerce"
                        )
                        if uv_cumulative_column
                        else np.nan
                    ),
                }
            )
            normalized["source_file"] = str(path)
            normalized["source_sheet"] = sheet_name
            all_rows.append(normalized)

    if not all_rows:
        raise ValueError("No sheets with a timestamp column were found.")

    campaign = pd.concat(all_rows, ignore_index=True)
    campaign = campaign.dropna(subset=["timestamp"])
    campaign["date"] = campaign["timestamp"].dt.date.astype(str)
    campaign["minute_of_day"] = (
        campaign["timestamp"].dt.hour * 60 + campaign["timestamp"].dt.minute
    )
    return pd.DataFrame(coverage_rows), campaign, schema_records


def daily_channel_summary(campaign: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date, day_original in campaign.groupby("date", sort=True):
        day = (
            day_original.sort_values("timestamp")
            .drop_duplicates("timestamp", keep="first")
            .copy()
        )
        hard_night = (day["minute_of_day"] < 5 * 60) | (
            day["minute_of_day"] >= 20 * 60
        )
        sunlit = day["total_w_m2"] >= 20
        relation_mask = (
            sunlit
            & day["total_w_m2"].notna()
            & day["direct_w_m2"].notna()
        )

        row: dict[str, Any] = {
            "date": date,
            "row_n": int(len(day_original)),
            "unique_timestamp_n": int(day["timestamp"].nunique()),
            "first_timestamp": day["timestamp"].min(),
            "last_timestamp": day["timestamp"].max(),
            "sunlit_row_n_total_ge_20": int(sunlit.sum()),
            "hard_night_row_n": int(hard_night.sum()),
        }
        direct_ge_120_hours = float(
            (day["direct_w_m2"] >= 120).sum() / 60.0
        )
        sunshine_finite = day["sunshine_cumulative_h"].dropna()
        final_sunshine_hours = (
            float(sunshine_finite.iloc[-1])
            if not sunshine_finite.empty
            else None
        )
        row["direct_ge_120_w_m2_hours_from_minute_count"] = (
            direct_ge_120_hours
        )
        row["sunshine_cumulative_final_h"] = final_sunshine_hours
        row["sunshine_minus_direct_ge_120_hours"] = (
            final_sunshine_hours - direct_ge_120_hours
            if final_sunshine_hours is not None
            else None
        )
        row.update(numeric_summary(day["total_w_m2"], "total"))
        row.update(numeric_summary(day["direct_w_m2"], "direct"))
        row.update(numeric_summary(day["uv_w_m2"], "uv"))

        for channel in ("total_w_m2", "direct_w_m2", "uv_w_m2"):
            night_values = day.loc[hard_night, channel].dropna()
            row[f"{channel}_hard_night_median"] = (
                float(night_values.median()) if not night_values.empty else None
            )
            row[f"{channel}_hard_night_p99"] = (
                float(night_values.quantile(0.99))
                if not night_values.empty
                else None
            )

        if relation_mask.any():
            row["direct_gt_total_sunlit_n"] = int(
                (
                    day.loc[relation_mask, "direct_w_m2"]
                    > day.loc[relation_mask, "total_w_m2"]
                ).sum()
            )
            row["direct_gt_total_sunlit_fraction"] = float(
                (
                    day.loc[relation_mask, "direct_w_m2"]
                    > day.loc[relation_mask, "total_w_m2"]
                ).mean()
            )
            ratios = (
                day.loc[relation_mask, "direct_w_m2"]
                / day.loc[relation_mask, "total_w_m2"]
            )
            row["direct_to_total_sunlit_median"] = float(ratios.median())
            row["direct_to_total_sunlit_p95"] = float(ratios.quantile(0.95))
        else:
            row["direct_gt_total_sunlit_n"] = 0
            row["direct_gt_total_sunlit_fraction"] = None
            row["direct_to_total_sunlit_median"] = None
            row["direct_to_total_sunlit_p95"] = None

        integrated_total = integrate_valid_intervals(
            day["timestamp"], day["total_w_m2"]
        )
        cumulative_total = day["total_cumulative_mj_m2"].dropna()
        final_cumulative_total = (
            float(cumulative_total.iloc[-1])
            if not cumulative_total.empty
            else None
        )
        row["total_integrated_valid_intervals_mj_m2"] = integrated_total
        row["total_cumulative_final_mj_m2"] = final_cumulative_total
        if (
            integrated_total is not None
            and final_cumulative_total is not None
            and final_cumulative_total != 0
        ):
            row["total_integration_relative_difference"] = float(
                (integrated_total - final_cumulative_total)
                / final_cumulative_total
            )
        else:
            row["total_integration_relative_difference"] = None

        for column in (
            "sunshine_cumulative_h",
            "total_cumulative_mj_m2",
            "uv_cumulative_mj_m2",
        ):
            differences = day[column].diff()
            row[f"{column}_decrease_n"] = int((differences < -1e-9).sum())
            finite = day[column].dropna()
            row[f"{column}_final"] = (
                float(finite.iloc[-1]) if not finite.empty else None
            )

        rows.append(row)
    return pd.DataFrame(rows)


def timestamp_gap_table(campaign: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouping = campaign.groupby(
        ["source_file", "source_sheet"], sort=True
    )
    for (source_file, source_sheet), frame in grouping:
        timestamps = (
            frame["timestamp"].dropna().sort_values().drop_duplicates()
        )
        if len(timestamps) < 2:
            continue
        deltas = timestamps.diff().dt.total_seconds()
        median_seconds = float(deltas.dropna().median())
        gap_positions = np.flatnonzero(
            (deltas > 1.5 * median_seconds).to_numpy()
        )
        for position in gap_positions:
            gap_start = timestamps.iloc[position - 1]
            gap_end = timestamps.iloc[position]
            gap_seconds = float((gap_end - gap_start).total_seconds())
            rows.append(
                {
                    "source_file": source_file,
                    "source_sheet": source_sheet,
                    "gap_start_timestamp": gap_start,
                    "gap_end_timestamp": gap_end,
                    "gap_minutes_between_observations": gap_seconds / 60.0,
                    "estimated_missing_sample_n": max(
                        int(round(gap_seconds / median_seconds)) - 1,
                        0,
                    ),
                    "median_sampling_interval_seconds": median_seconds,
                }
            )
    return pd.DataFrame(rows)


def exact_horizon_ramps(
    campaign: pd.DataFrame,
    horizons_minutes: tuple[int, ...] = (1, 5, 10, 15, 30),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, Any]] = []
    event_frames: list[pd.DataFrame] = []
    for date, day_original in campaign.groupby("date", sort=True):
        day = (
            day_original.sort_values("timestamp")
            .drop_duplicates("timestamp", keep="first")
            .set_index("timestamp")
        )
        for channel in ("total_w_m2", "direct_w_m2"):
            values = day[channel]
            sunlit = day["total_w_m2"] >= 20
            for horizon in horizons_minutes:
                previous = values.shift(horizon)
                previous_time = values.index.to_series().shift(horizon)
                exact_interval = (
                    values.index.to_series() - previous_time
                    == pd.Timedelta(minutes=horizon)
                )
                valid = (
                    exact_interval
                    & sunlit
                    & sunlit.shift(horizon, fill_value=False)
                    & values.notna()
                    & previous.notna()
                )
                ramp = (values - previous) / float(horizon)
                ramp_valid = ramp.loc[valid]
                absolute = ramp_valid.abs()
                summary_rows.append(
                    {
                        "date": date,
                        "channel": channel,
                        "horizon_minutes": horizon,
                        "valid_ramp_n": int(len(ramp_valid)),
                        "signed_ramp_mean_w_m2_per_min": (
                            float(ramp_valid.mean())
                            if not ramp_valid.empty
                            else None
                        ),
                        "absolute_ramp_p50_w_m2_per_min": (
                            float(absolute.quantile(0.50))
                            if not absolute.empty
                            else None
                        ),
                        "absolute_ramp_p90_w_m2_per_min": (
                            float(absolute.quantile(0.90))
                            if not absolute.empty
                            else None
                        ),
                        "absolute_ramp_p95_w_m2_per_min": (
                            float(absolute.quantile(0.95))
                            if not absolute.empty
                            else None
                        ),
                        "absolute_ramp_p99_w_m2_per_min": (
                            float(absolute.quantile(0.99))
                            if not absolute.empty
                            else None
                        ),
                        "absolute_ramp_max_w_m2_per_min": (
                            float(absolute.max()) if not absolute.empty else None
                        ),
                    }
                )
                if horizon == 1 and not ramp_valid.empty:
                    events = pd.DataFrame(
                        {
                            "timestamp": ramp_valid.index,
                            "date": date,
                            "channel": channel,
                            "horizon_minutes": horizon,
                            "value_w_m2": values.loc[ramp_valid.index].to_numpy(),
                            "previous_value_w_m2": previous.loc[
                                ramp_valid.index
                            ].to_numpy(),
                            "ramp_w_m2_per_min": ramp_valid.to_numpy(),
                        }
                    )
                    event_frames.append(events)

    ramp_summary = pd.DataFrame(summary_rows)
    if event_frames:
        all_events = pd.concat(event_frames, ignore_index=True)
        all_events["absolute_ramp_w_m2_per_min"] = all_events[
            "ramp_w_m2_per_min"
        ].abs()
        top_events = (
            all_events.sort_values(
                ["channel", "absolute_ramp_w_m2_per_min"],
                ascending=[True, False],
            )
            .groupby("channel", as_index=False, group_keys=False)
            .head(50)
            .reset_index(drop=True)
        )
    else:
        top_events = pd.DataFrame()
    return ramp_summary, top_events


def aggregation_sensitivity(
    campaign: pd.DataFrame,
    intervals_minutes: tuple[int, ...] = (1, 2, 5, 10, 15, 30),
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date, day_original in campaign.groupby("date", sort=True):
        day = (
            day_original.sort_values("timestamp")
            .drop_duplicates("timestamp", keep="first")
            .set_index("timestamp")
        )
        for channel in ("total_w_m2", "direct_w_m2"):
            base_values = day[channel].loc[day["total_w_m2"] >= 20].copy()
            if len(base_values) < 2:
                continue
            baseline_std = float(base_values.std(ddof=1))
            baseline_ramp = base_values.diff()
            baseline_dt = (
                base_values.index.to_series().diff().dt.total_seconds() / 60
            )
            baseline_ramp_rate = (
                baseline_ramp / baseline_dt
            ).loc[baseline_dt == 1]
            baseline_abs = baseline_ramp_rate.abs().dropna()
            baseline_p99 = (
                float(baseline_abs.quantile(0.99))
                if not baseline_abs.empty
                else None
            )
            baseline_max = (
                float(baseline_abs.max()) if not baseline_abs.empty else None
            )

            for interval in intervals_minutes:
                if interval == 1:
                    aggregated = base_values
                else:
                    aggregated = (
                        day[channel]
                        .resample(f"{interval}min")
                        .mean()
                        .dropna()
                    )
                    total_aggregated = (
                        day["total_w_m2"]
                        .resample(f"{interval}min")
                        .mean()
                        .reindex(aggregated.index)
                    )
                    aggregated = aggregated.loc[total_aggregated >= 20]
                dt_minutes = (
                    aggregated.index.to_series().diff().dt.total_seconds() / 60
                )
                ramp_rate = (
                    aggregated.diff() / dt_minutes
                ).loc[dt_minutes == interval]
                absolute = ramp_rate.abs().dropna()
                std = (
                    float(aggregated.std(ddof=1))
                    if len(aggregated) >= 2
                    else None
                )
                p99 = (
                    float(absolute.quantile(0.99))
                    if not absolute.empty
                    else None
                )
                maximum = (
                    float(absolute.max()) if not absolute.empty else None
                )
                rows.append(
                    {
                        "date": date,
                        "channel": channel,
                        "aggregation_minutes": interval,
                        "aggregated_value_n": int(len(aggregated)),
                        "std_w_m2": std,
                        "std_retained_fraction_vs_1min": (
                            std / baseline_std
                            if std is not None and baseline_std > 0
                            else None
                        ),
                        "absolute_ramp_p99_w_m2_per_min": p99,
                        "p99_ramp_retained_fraction_vs_1min": (
                            p99 / baseline_p99
                            if p99 is not None
                            and baseline_p99 is not None
                            and baseline_p99 > 0
                            else None
                        ),
                        "absolute_ramp_max_w_m2_per_min": maximum,
                        "max_ramp_retained_fraction_vs_1min": (
                            maximum / baseline_max
                            if maximum is not None
                            and baseline_max is not None
                            and baseline_max > 0
                            else None
                        ),
                    }
                )
    return pd.DataFrame(rows)


def build_campaign_summary(
    coverage: pd.DataFrame,
    campaign: pd.DataFrame,
    daily: pd.DataFrame,
    gaps: pd.DataFrame,
    ramps: pd.DataFrame,
    aggregation: pd.DataFrame,
    schema_records: list[dict[str, Any]],
) -> dict[str, Any]:
    observed_dates = sorted(campaign["date"].unique())
    first_date = pd.Timestamp(observed_dates[0]).date()
    last_date = pd.Timestamp(observed_dates[-1]).date()
    calendar_dates = pd.date_range(first_date, last_date, freq="D")
    missing_calendar_dates = [
        str(date.date())
        for date in calendar_dates
        if str(date.date()) not in set(observed_dates)
    ]

    complete = coverage.loc[coverage["coverage_status"] == "complete"]
    partial = coverage.loc[coverage["coverage_status"] != "complete"]

    sunlit = campaign["total_w_m2"] >= 20
    relation = campaign.loc[
        sunlit
        & campaign["total_w_m2"].notna()
        & campaign["direct_w_m2"].notna()
    ]
    hard_night = (campaign["minute_of_day"] < 5 * 60) | (
        campaign["minute_of_day"] >= 20 * 60
    )

    campaign_ramp_summary: dict[str, Any] = {}
    for channel in ("total_w_m2", "direct_w_m2"):
        channel_rows = ramps.loc[
            (ramps["channel"] == channel)
            & (ramps["horizon_minutes"] == 1)
        ]
        campaign_ramp_summary[channel] = {
            "daily_p99_median_w_m2_per_min": (
                float(
                    channel_rows[
                        "absolute_ramp_p99_w_m2_per_min"
                    ].median()
                )
                if not channel_rows.empty
                else None
            ),
            "daily_max_maximum_w_m2_per_min": (
                float(
                    channel_rows[
                        "absolute_ramp_max_w_m2_per_min"
                    ].max()
                )
                if not channel_rows.empty
                else None
            ),
        }

    aggregation_medians: dict[str, Any] = {}
    for channel in ("total_w_m2", "direct_w_m2"):
        channel_rows = aggregation.loc[aggregation["channel"] == channel]
        aggregation_medians[channel] = {}
        for interval, group in channel_rows.groupby("aggregation_minutes"):
            aggregation_medians[channel][str(int(interval))] = {
                "median_std_retained_fraction_vs_1min": finite_or_none(
                    group["std_retained_fraction_vs_1min"].median()
                ),
                "median_p99_ramp_retained_fraction_vs_1min": finite_or_none(
                    group[
                        "p99_ramp_retained_fraction_vs_1min"
                    ].median()
                ),
                "median_max_ramp_retained_fraction_vs_1min": finite_or_none(
                    group[
                        "max_ramp_retained_fraction_vs_1min"
                    ].median()
                ),
            }

    summary = {
        "input_workbook_n": int(coverage["file"].nunique()),
        "loaded_sheet_n": int(len(coverage)),
        "timestamp_row_n": int(len(campaign)),
        "observed_date_n": int(len(observed_dates)),
        "first_observed_date": observed_dates[0],
        "last_observed_date": observed_dates[-1],
        "complete_day_n": int(len(complete)),
        "partial_or_problem_day_n": int(len(partial)),
        "partial_or_problem_files": partial[
            [
                "file",
                "first_timestamp",
                "last_timestamp",
                "row_n",
                "coverage_status",
            ]
        ].to_dict(orient="records"),
        "missing_calendar_dates_between_first_and_last": missing_calendar_dates,
        "duplicate_timestamp_n_total": int(
            coverage["duplicate_timestamp_n"].sum()
        ),
        "non_monotonic_timestamp_n_total": int(
            coverage["non_monotonic_timestamp_n"].sum()
        ),
        "median_sampling_interval_seconds": finite_or_none(
            coverage["median_interval_seconds"].median()
        ),
        "maximum_internal_gap_minutes": finite_or_none(
            coverage["maximum_gap_minutes"].max()
        ),
        "large_internal_gap_n_total": int(len(gaps)),
        "total_irradiance_range_w_m2": {
            "min": finite_or_none(campaign["total_w_m2"].min()),
            "max": finite_or_none(campaign["total_w_m2"].max()),
        },
        "direct_irradiance_range_w_m2": {
            "min": finite_or_none(campaign["direct_w_m2"].min()),
            "max": finite_or_none(campaign["direct_w_m2"].max()),
        },
        "uv_irradiance_range_w_m2": {
            "min": finite_or_none(campaign["uv_w_m2"].min()),
            "max": finite_or_none(campaign["uv_w_m2"].max()),
        },
        "hard_night_median_w_m2": {
            "total": finite_or_none(
                campaign.loc[hard_night, "total_w_m2"].median()
            ),
            "direct": finite_or_none(
                campaign.loc[hard_night, "direct_w_m2"].median()
            ),
            "uv": finite_or_none(
                campaign.loc[hard_night, "uv_w_m2"].median()
            ),
        },
        "direct_gt_total_sunlit_fraction": (
            finite_or_none(
                (relation["direct_w_m2"] > relation["total_w_m2"]).mean()
            )
            if not relation.empty
            else None
        ),
        "daily_total_integration_relative_difference": {
            "median": finite_or_none(
                daily["total_integration_relative_difference"].median()
            ),
            "p95_absolute": finite_or_none(
                daily["total_integration_relative_difference"]
                .abs()
                .quantile(0.95)
            ),
        },
        "sunshine_counter_vs_direct_ge_120_w_m2": {
            "median_absolute_difference_hours": finite_or_none(
                daily["sunshine_minus_direct_ge_120_hours"].abs().median()
            ),
            "maximum_absolute_difference_hours": finite_or_none(
                daily["sunshine_minus_direct_ge_120_hours"].abs().max()
            ),
        },
        "uv_channel_day_counts": {
            "nonzero_day_n": int((daily["uv_max"] > 0).sum()),
            "all_zero_day_n": int((daily["uv_max"] == 0).sum()),
        },
        "one_minute_ramps": campaign_ramp_summary,
        "aggregation_sensitivity_daily_medians": aggregation_medians,
        "schema_records": schema_records,
    }
    return json.loads(
        json.dumps(summary, ensure_ascii=False, default=finite_or_none)
    )


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    coverage, campaign, schema_records = load_campaign(input_dir)
    daily = daily_channel_summary(campaign)
    gaps = timestamp_gap_table(campaign)
    ramps, top_events = exact_horizon_ramps(campaign)
    aggregation = aggregation_sensitivity(campaign)
    summary = build_campaign_summary(
        coverage,
        campaign,
        daily,
        gaps,
        ramps,
        aggregation,
        schema_records,
    )

    coverage.to_csv(
        output_dir / "coverage_by_file.csv",
        index=False,
        encoding="utf-8-sig",
    )
    daily.to_csv(
        output_dir / "daily_channel_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    gaps.to_csv(
        output_dir / "timestamp_gaps.csv",
        index=False,
        encoding="utf-8-sig",
    )
    ramps.to_csv(
        output_dir / "ramp_summary_by_day.csv",
        index=False,
        encoding="utf-8-sig",
    )
    top_events.to_csv(
        output_dir / "top_one_minute_ramp_events.csv",
        index=False,
        encoding="utf-8-sig",
    )
    aggregation.to_csv(
        output_dir / "aggregation_sensitivity_by_day.csv",
        index=False,
        encoding="utf-8-sig",
    )
    with (output_dir / "campaign_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
