"""Evaluate modest, reproducible panel-temperature models on whole-day holdouts.

This script is intentionally narrower than the B610 competition report.  It
uses only channels that are actually present in the experiment logger and does
not calculate thermal efficiency, water savings, or dynamic-control benefits.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:  # Metrics still run in minimal scientific runtimes.
    plt = None


@dataclass
class RidgeModel:
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray

    def predict(self, features: np.ndarray) -> np.ndarray:
        standardized = (features - self.mean) / self.scale
        design = np.column_stack([np.ones(len(standardized)), standardized])
        return design @ self.coefficients


def fit_ridge(features: np.ndarray, target: np.ndarray, penalty: float = 1e-4) -> RidgeModel:
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale < 1e-12] = 1.0
    standardized = (features - mean) / scale
    design = np.column_stack([np.ones(len(standardized)), standardized])
    regularizer = np.eye(design.shape[1]) * penalty
    regularizer[0, 0] = 0.0
    coefficients = np.linalg.solve(design.T @ design + regularizer, design.T @ target)
    return RidgeModel(mean=mean, scale=scale, coefficients=coefficients)


def resample_days(dataset: pd.DataFrame, step_s: float) -> dict[str, pd.DataFrame]:
    days = {}
    columns = ["T_panel_C", "T_tank_C", "T_inlet_C", "G_W_m2", "flow_kg_s"]
    usable = dataset[dataset["valid_sensor_range"]].copy()
    for day, frame in usable.groupby("date", sort=False):
        frame = frame.sort_values("elapsed_s").drop_duplicates("elapsed_s")
        time = frame["elapsed_s"].to_numpy(float)
        grid = np.arange(time[0], time[-1] + 0.5 * step_s, step_s)
        resampled = {"elapsed_s": grid}
        for column in columns:
            resampled[column] = np.interp(grid, time, frame[column].to_numpy(float))
        day_frame = pd.DataFrame(resampled)
        day_frame["date"] = day
        day_frame["active_irradiance"] = day_frame["G_W_m2"] >= 100.0
        days[day] = day_frame
    return days


def static_features(frame: pd.DataFrame, include_flow: bool) -> np.ndarray:
    features = [
        frame["G_W_m2"].to_numpy(float),
        frame["T_inlet_C"].to_numpy(float),
        frame["T_tank_C"].to_numpy(float),
    ]
    if include_flow:
        flow = frame["flow_kg_s"].to_numpy(float)
        features.extend([flow, flow * frame["G_W_m2"].to_numpy(float)])
    return np.column_stack(features)


def dynamic_features(frame: pd.DataFrame, panel_state: np.ndarray, include_flow: bool) -> np.ndarray:
    base = static_features(frame, include_flow)
    return np.column_stack([panel_state, base])


def metrics(observed: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - observed
    return {
        "mae_C": float(np.mean(np.abs(error))),
        "rmse_C": float(np.sqrt(np.mean(error**2))),
        "bias_C": float(np.mean(error)),
        "r2": float(1.0 - np.sum(error**2) / np.sum((observed - observed.mean()) ** 2)),
    }


def evaluate_leave_one_day_out(days: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    rows = []
    predictions = {}
    for held_out, test in days.items():
        train_days = [frame for day, frame in days.items() if day != held_out]

        for include_flow, label_suffix in [(False, "no_flow"), (True, "with_flow")]:
            x_static = np.vstack([static_features(frame, include_flow) for frame in train_days])
            y_static = np.concatenate([frame["T_panel_C"].to_numpy(float) for frame in train_days])
            static_model = fit_ridge(x_static, y_static)
            static_prediction = static_model.predict(static_features(test, include_flow))

            x_dynamic = np.vstack(
                [
                    dynamic_features(frame.iloc[:-1], frame["T_panel_C"].to_numpy(float)[:-1], include_flow)
                    for frame in train_days
                ]
            )
            y_dynamic = np.concatenate([frame["T_panel_C"].to_numpy(float)[1:] for frame in train_days])
            dynamic_model = fit_ridge(x_dynamic, y_dynamic, penalty=1e-3)

            free_run = np.empty(len(test), dtype=float)
            free_run[0] = float(test["T_panel_C"].iloc[0])
            for index in range(len(test) - 1):
                current = test.iloc[index : index + 1]
                feature = dynamic_features(current, np.array([free_run[index]]), include_flow)
                free_run[index + 1] = np.clip(dynamic_model.predict(feature)[0], -20.0, 100.0)

            active = test["active_irradiance"].to_numpy(bool)
            observed = test.loc[active, "T_panel_C"].to_numpy(float)
            for model_name, prediction in [
                (f"static_{label_suffix}", static_prediction),
                (f"dynamic_free_run_{label_suffix}", free_run),
            ]:
                result = {"date": held_out, "flow_ml_min": float(test["flow_kg_s"].iloc[0] * 60_000), "model": model_name}
                result.update(metrics(observed, prediction[active]))
                rows.append(result)
                predictions[(held_out, model_name)] = prediction

    return pd.DataFrame(rows), predictions


def make_figure(days: dict[str, pd.DataFrame], results: pd.DataFrame, predictions: dict, output: Path) -> None:
    if plt is None:
        return
    colors = {"observed": "#222222", "model": "#0072B2"}
    fig = plt.figure(figsize=(11.0, 7.2), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.05])
    axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])]
    examples = ["3.21", "3.26"]
    model_name = "dynamic_free_run_with_flow"
    for axis, day in zip(axes, examples):
        frame = days[day]
        time_h = frame["elapsed_s"] / 3600.0
        axis.plot(time_h, frame["T_panel_C"], color=colors["observed"], lw=1.7, label="Measured")
        axis.plot(time_h, predictions[(day, model_name)], color=colors["model"], lw=1.4, label="Whole-day holdout prediction")
        axis.set_title(f"{day} — {frame['flow_kg_s'].iloc[0] * 60_000:.0f} mL min$^{{-1}}$")
        axis.set_xlabel("Elapsed time (h)")
        axis.set_ylabel("Panel temperature (°C)")
        axis.grid(True, alpha=0.25)
        axis.legend(frameon=False, fontsize=8)

    bar_axis = fig.add_subplot(grid[1, :])
    subset = results[results["model"].isin(["static_with_flow", "dynamic_free_run_with_flow"])].copy()
    dates = list(days)
    positions = np.arange(len(dates))
    width = 0.38
    for offset, (model, label, color) in enumerate(
        [
            ("static_with_flow", "Static regression", "#D55E00"),
            ("dynamic_free_run_with_flow", "Dynamic free-run", "#0072B2"),
        ]
    ):
        values = [float(subset[(subset["date"] == day) & (subset["model"] == model)]["rmse_C"].iloc[0]) for day in dates]
        bar_axis.bar(positions + (offset - 0.5) * width, values, width=width, color=color, label=label)
    bar_axis.set_xticks(positions, dates)
    bar_axis.set_xlabel("Held-out experiment day")
    bar_axis.set_ylabel("RMSE (°C)")
    bar_axis.set_title("Leave-one-day-out prediction error")
    bar_axis.grid(axis="y", alpha=0.25)
    bar_axis.legend(frameon=False, ncol=2)
    fig.savefig(output, dpi=300, facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--step-s", type=float, default=10.0)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset = pd.read_csv(args.dataset)
    days = resample_days(dataset, args.step_s)
    results, predictions = evaluate_leave_one_day_out(days)
    results.to_csv(args.output_dir / "panel_temperature_lodo_metrics.csv", index=False)

    summary = (
        results.groupby("model")[["mae_C", "rmse_C", "bias_C", "r2"]]
        .agg(["mean", "median", "max"])
        .round(4)
    )
    (args.output_dir / "panel_temperature_lodo_summary.txt").write_text(summary.to_string() + "\n", encoding="utf-8")
    figure_path = args.output_dir / "panel_temperature_lodo.png"
    make_figure(days, results, predictions, figure_path)

    best = results.groupby("model")["rmse_C"].mean().sort_values()
    print(
        json.dumps(
            {"mean_rmse_C": best.round(4).to_dict(), "figure_created": figure_path.exists()},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
