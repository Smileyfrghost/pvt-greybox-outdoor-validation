import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from baseline_comparison import (
    ARXSpec, RidgeModel, evaluate_baselines, fit_arx, main, make_folds,
    metrics, parse_validity, predict_arx, resample_days,
)


def synthetic_dataset(days=("a", "b", "c"), count=20):
    frames = []
    for index, day in enumerate(days):
        time = np.arange(count, dtype=float)
        frames.append(pd.DataFrame({
            "date": day, "elapsed_s": time * 60, "T_panel_C": 20 + time + index,
            "G_W_m2": 300 + 10 * np.sin(time + index), "T_tank_C": 18 + 0.1 * time,
            "flow_kg_s": 0.005 + index * 0.001, "valid_sensor_range": True,
        }))
    return pd.concat(frames, ignore_index=True)


class BaselineComparisonTests(unittest.TestCase):
    def test_false_string_is_not_truthy(self):
        np.testing.assert_array_equal(parse_validity(pd.Series(["true", "false", "0", "1"])), [True, False, False, True])
        with self.assertRaises(ValueError):
            parse_validity(pd.Series(["yes"]))

    def test_invalid_row_breaks_both_adjoining_histories(self):
        frame = synthetic_dataset(("a",), count=3)
        frame["valid_sensor_range"] = ["true", "false", "true"]
        segments = resample_days(frame, 60)
        self.assertEqual(len(segments), 2)
        self.assertEqual([len(part) for part in segments.values()], [1, 1])

    def test_large_gap_is_not_interpolated(self):
        frame = synthetic_dataset(("a",), count=4)
        frame["elapsed_s"] = [0, 60, 600, 660]
        segments = resample_days(frame, 60, max_gap_s=120)
        self.assertEqual(len(segments), 2)
        self.assertEqual(sum(map(len, segments.values())), 4)

    def test_event_segment_label_breaks_history(self):
        frame = synthetic_dataset(("a",), count=6)
        frame["segment"] = ["on"] * 3 + ["after_event"] * 3
        segments = resample_days(frame, 60, segment_column="segment")
        self.assertEqual(len(segments), 2)

    def test_resampling_never_extrapolates_past_last_observation(self):
        frame = synthetic_dataset(("a",), count=3)
        frame["elapsed_s"] = [0, 5, 13]
        result = resample_days(frame, 5, max_gap_s=20)["a"]
        self.assertEqual(result["elapsed_s"].tolist(), [0, 5, 10])

    def test_duplicate_timestamps_require_resolution(self):
        frame = synthetic_dataset(("a",), count=3)
        frame["elapsed_s"] = [0, 60, 60]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            resample_days(frame, 60)

    def test_timezone_clock_resolution_is_normalized_before_seconds_conversion(self):
        frame = synthetic_dataset(("a",), count=3)
        frame["aligned_timestamp"] = pd.Series(pd.date_range("2026-01-01", periods=3, freq="min", tz="UTC")).dt.as_unit("s")
        result = resample_days(frame, 60, time_column="aligned_timestamp")["a"]
        np.testing.assert_array_equal(np.diff(result["elapsed_s"]), [60, 60])

    def test_every_part_of_held_out_day_is_excluded_from_training(self):
        frame = synthetic_dataset()
        frame.loc[(frame["date"] == "a") & (frame["elapsed_s"] == 300), "valid_sensor_range"] = False
        days = resample_days(frame, 60)
        self.assertGreater(len([part for part in days.values() if part["date"].iloc[0] == "a"]), 1)
        self.assertEqual(dict(make_folds(days))["a"], ["b", "c"])
        with self.assertRaisesRegex(ValueError, "overlap"):
            make_folds(days, train_days=["a"], evaluation_days=["a"])

    def test_flow_has_only_one_lag_and_input_delay_is_explicit(self):
        spec = ARXSpec()
        y = np.arange(6, dtype=float)
        u = np.arange(18, dtype=float).reshape(6, 3)
        np.testing.assert_array_equal(spec.feature(y, u, 3), [2, 1, 3, 0, 4, 1, 5])

    def test_arx_recovers_a_known_synthetic_equation(self):
        rng = np.random.default_rng(82)
        u = rng.normal(size=80)
        y = np.zeros(80)
        for target in range(1, len(y)):
            y[target] = 0.7 * y[target - 1] + 0.2 * u[target - 1]
        frame = pd.DataFrame({"T_panel_C": y, "G_W_m2": u})
        spec = ARXSpec(inputs=("G_W_m2",), n_a=1, n_b=1, n_k=0)
        model = fit_arx([frame], spec)
        prediction = predict_arx(frame, model, spec, one_step=True)
        np.testing.assert_allclose(prediction[1:], y[1:], atol=1e-10)

    def test_conditional_rollout_does_not_read_future_target_measurements(self):
        frame = resample_days(synthetic_dataset(("a",)), 60)["a"]
        spec = ARXSpec()
        model = fit_arx([frame], spec)
        before = predict_arx(frame, model, spec, origin=5, horizon=3)[8]
        altered = frame.copy()
        altered.loc[6:, "T_panel_C"] += 10000
        after = predict_arx(altered, model, spec, origin=5, horizon=3)[8]
        self.assertEqual(before, after)

    def test_recursive_instability_is_not_hidden_by_temperature_clipping(self):
        frame = pd.DataFrame({"T_panel_C": np.zeros(4), "G_W_m2": np.zeros(4)})
        spec = ARXSpec(inputs=("G_W_m2",), n_a=1, n_b=1, n_k=0)
        model = RidgeModel(np.zeros(2), np.ones(2), np.array([200.0, 1.0, 0.0]))
        prediction = predict_arx(frame, model, spec)
        np.testing.assert_array_equal(prediction, [0, 200, 400, 600])

    def test_nonfinite_predictions_are_flagged_without_dropping_support(self):
        result = metrics(np.array([1.0, 2.0]), np.array([1.0, np.inf]))
        self.assertEqual(result["N"], 2)
        self.assertEqual(result["status"], "NONFINITE_PREDICTIONS")
        self.assertIsNone(result["rmse_C"])
        self.assertIsNone(metrics(np.ones(3), np.ones(3))["r2"])

    def test_initialization_is_excluded_and_dynamic_supports_match(self):
        days = resample_days(synthetic_dataset(), 60)
        results, details, fitted = evaluate_baselines(days, horizons=(1, 2, 60))
        persistence = results[(results["model"] == "Persistence") & (results["task"] == "one_step")]
        np.testing.assert_array_equal(persistence["N"], [17, 17, 17])
        np.testing.assert_allclose(persistence["mae_C"], 1.0)
        for task in ("one_step", "free_run", "conditional_horizon"):
            subset = details[details["task"] == task]
            columns = ["date", "segment", "origin_index", "target_index", "horizon_min"]
            left = subset[subset["model"] == "Persistence"][columns].reset_index(drop=True)
            right = subset[subset["model"] == "ARX"][columns].reset_index(drop=True)
            pd.testing.assert_frame_equal(left, right)
        self.assertTrue((results[results["horizon_min"] == 60]["status"] == "EMPTY_SUPPORT").all())
        self.assertTrue(all(item["evaluation_day"] not in item["training_days"] for item in fitted))

    def test_horizons_cannot_duplicate_or_have_fractional_sample_lengths(self):
        days = resample_days(synthetic_dataset(), 60)
        with self.assertRaises(ValueError):
            evaluate_baselines(days, horizons=(1, 1))
        with self.assertRaises(ValueError):
            evaluate_baselines(days, horizons=(1,), step_s=40)

    def test_cli_records_provenance_and_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "synthetic.csv", root / "run"
            synthetic_dataset().to_csv(source, index=False)
            args = ["baseline_comparison", "--dataset", str(source), "--output-dir", str(output),
                    "--allow-legacy-clock", "--horizons-min", "1", "2"]
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                main()
            manifest = json.loads((output / "baseline_run_manifest.json").read_text())
            self.assertFalse(manifest["temperature_clipping"])
            self.assertEqual(manifest["split"], "LEAVE_ONE_DAY_OUT")
            self.assertNotIn("T_inlet_C", manifest["input_columns"])
            self.assertEqual(len(manifest["input_sha256"]), 64)
            with patch.object(sys, "argv", args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()


if __name__ == "__main__":
    unittest.main()
