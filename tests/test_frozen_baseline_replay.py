import contextlib
import copy
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
from frozen_baseline_replay import INPUTS, PARAMETERS, arx_terminal, digest, load_parameters, main, metrics, replay


def fixture(count=10):
    time = np.arange(count, dtype=float)
    frame = pd.DataFrame({"row_id": [f"r{i}" for i in range(count)], "date": "2000-01-01", "aggregation_segment": "invented",
                          "window_start": pd.date_range("2000-01-01 10:00", periods=count, freq="min").astype(str),
                          "T_panel_center": 25 + time, "G": 400 + 5 * time, "Tamb": 20 + time / 10,
                          "T_tank_measured": 22 + time / 20, "P": 30 + time / 5, "flow_mL_min": 500})
    tasks = [
        {"task": "one_step", "horizon_steps": 1, "pairs": [[j - 1, j] for j in range(3, count)]},
        {"task": "free_run", "horizon_steps": None, "pairs": [[0, j] for j in range(3, count)]},
        {"task": "static_contemporaneous", "horizon_steps": None, "pairs": [[None, j] for j in range(count)]},
        {"task": "static_common", "horizon_steps": None, "pairs": [[None, j] for j in range(3, count)]},
        {"task": "conditional_horizon", "horizon_steps": 5, "pairs": [[k, k + 5] for k in range(2, count - 5)]},
        {"task": "conditional_horizon", "horizon_steps": 60, "pairs": []},
    ]
    return frame, {"schema": "frozen-baseline-support-v1", "sampling_seconds": 60, "provenance": "invented unit-test data", "segments": [{"id": "synthetic", "row_ids": frame.row_id.tolist(), "initialization_rows": 3, "tasks": tasks}]}


class FrozenBaselineReplayTests(unittest.TestCase):
    def setUp(self):
        self.frame, self.support = fixture()
        self.parameters = load_parameters()

    def run_replay(self, frame=None, support=None):
        return replay(self.frame if frame is None else frame, self.support if support is None else support, self.parameters)

    def test_source_hashes_and_training_roles_are_frozen(self):
        self.assertEqual(digest(PARAMETERS), "9a0149c2c11d4beedb4f9f12e1232dfcbdf15358b3b1918ed93fe8be6e6ab4d9")
        self.assertEqual(self.parameters["selected_arx"]["training_scaler"]["source_days"], ["2026-03-16", "2026-03-17", "2026-03-19", "2026-03-25"])

    def test_bundled_example_hash_and_support_match(self):
        source = ROOT / "data/examples/frozen_baseline_synthetic.csv"
        support = json.loads((ROOT / "data/examples/frozen_baseline_synthetic_support.json").read_text())
        self.assertEqual(digest(source), support["dataset_sha256"])
        predictions, _ = self.run_replay(pd.read_csv(source), support)
        self.assertFalse(predictions.empty)

    def test_prediction_never_calls_fit(self):
        before = copy.deepcopy(self.parameters)
        with patch.object(np.linalg, "lstsq", side_effect=AssertionError("Refitting forbidden")):
            predictions, scores = self.run_replay()
        self.assertFalse(predictions.empty)
        self.assertEqual(self.parameters, before)
        self.assertTrue((scores[scores.task == "one_step"].N == 7).all())

    def test_lag_indexing_matches_independent_expansion(self):
        model = self.parameters["selected_arx"]
        y, u = np.arange(8, dtype=float), np.arange(40, dtype=float).reshape(8, 5)
        expected = model["intercept_raw"] + model["a_raw"][0] * y[3] + model["a_raw"][1] * y[2]
        for column, name in enumerate(INPUTS):
            expected += model["b_raw_by_input_and_lag"][name][0] * u[2, column]
            if name != "flow":
                expected += model["b_raw_by_input_and_lag"][name][1] * u[1, column]
        self.assertAlmostEqual(arx_terminal(y, u, 3, 1, model), expected, places=11)

    def test_horizon_does_not_read_future_target_measurements(self):
        model = self.parameters["selected_arx"]
        y = np.arange(12, dtype=float)
        u = np.ones((12, 5))
        before = arx_terminal(y, u, 3, 5, model)
        y[4:] += 10000
        self.assertEqual(before, arx_terminal(y, u, 3, 5, model))

    def test_free_run_uses_only_first_three_outputs(self):
        before, _ = self.run_replay()
        self.frame.loc[3:, "T_panel_center"] += 10000
        after, _ = self.run_replay()
        left = before.loc[before.task == "free_run", "predicted_C"]
        right = after.loc[after.task == "free_run", "predicted_C"]
        np.testing.assert_array_equal(left, right)
        persistence = before[(before.task == "free_run") & (before.model == "Persistence")]
        self.assertTrue((persistence.predicted_C == 25).all())

    def test_dynamic_models_share_explicit_pairs(self):
        predictions, _ = self.run_replay()
        for task in ["one_step", "free_run", "conditional_horizon"]:
            subset = predictions[predictions.task == task]
            columns = ["segment", "origin_index", "target_index", "horizon_steps", "row_id"]
            left = subset[subset.model == "Persistence"][columns].reset_index(drop=True)
            right = subset[subset.model == "ARX_2_2_1_flow1"][columns].reset_index(drop=True)
            pd.testing.assert_frame_equal(left, right)

    def test_support_is_not_automatically_expanded(self):
        self.support["segments"][0]["tasks"][0]["pairs"] = [[4, 5]]
        predictions, scores = self.run_replay()
        self.assertEqual(len(predictions[predictions.task == "one_step"]), 2)
        self.assertTrue((scores[scores.task == "one_step"].N == 1).all())

    def test_static_and_empty_horizons_are_separate(self):
        predictions, scores = self.run_replay()
        static = predictions[predictions.task == "static_contemporaneous"]
        self.assertEqual(len(static), 10)
        self.assertTrue(static.origin_index.isna().all())
        empty = scores[scores.horizon_steps == 60]
        self.assertTrue((empty.status == "EMPTY_SUPPORT").all())
        self.assertTrue((empty.N == 0).all())

    def test_scores_do_not_drop_nonfinite_predictions(self):
        result = metrics(np.array([1., 2.]), np.array([1., np.inf]))
        self.assertEqual(result["N"], 2)
        self.assertEqual(result["status"], "NONFINITE_PREDICTIONS")
        self.assertIsNone(result["RMSE_C"])

    def test_no_temperature_clipping(self):
        self.parameters["selected_arx"]["intercept_raw"] = 1000
        predictions, _ = self.run_replay()
        self.assertGreater(predictions[predictions.task == "free_run"].predicted_C.max(), 120)

    def test_gap_missing_input_flow_or_label_change_is_rejected(self):
        modifications = [("window_start", "2000-01-01 11:00:00"), ("Tamb", np.nan), ("flow_mL_min", 0), ("aggregation_segment", "other")]
        for column, value in modifications:
            frame = self.frame.copy()
            frame.loc[4, column] = value
            with self.assertRaises(ValueError):
                self.run_replay(frame)

    def test_invalid_initialization_and_support_are_rejected(self):
        for pair in [[1, 2], [2, 9], [True, 3], [2, 10], [2, -1]]:
            support = copy.deepcopy(self.support)
            support["segments"][0]["tasks"][0]["pairs"] = [pair]
            with self.assertRaises(ValueError):
                self.run_replay(support=support)
        self.support["segments"][0]["initialization_rows"] = 2
        with self.assertRaises(ValueError):
            self.run_replay()

    def test_duplicate_pairs_rows_and_segments_are_rejected(self):
        for change in ["pairs", "rows", "segments"]:
            support = copy.deepcopy(self.support)
            segment = support["segments"][0]
            if change == "pairs":
                segment["tasks"][0]["pairs"] *= 2
            elif change == "rows":
                segment["row_ids"][1] = segment["row_ids"][0]
            else:
                support["segments"].append(copy.deepcopy(segment))
            with self.assertRaises(ValueError):
                self.run_replay(support=support)

    def test_cli_hash_lock_and_output_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, support, output = root / "data.csv", root / "support.json", root / "run"
            self.frame.to_csv(source, index=False)
            self.support["dataset_sha256"] = digest(source)
            support.write_text(json.dumps(self.support))
            args = ["frozen_baseline_replay", "--dataset", str(source), "--support", str(support), "--output-dir", str(output)]
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                main()
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["fit_calls"], 0)
            with patch.object(sys, "argv", args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
            self.support["dataset_sha256"] = "0" * 64
            support.write_text(json.dumps(self.support))
            args[-1] = str(root / "second_run")
            with patch.object(sys, "argv", args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
            self.assertFalse((root / "second_run").exists())


if __name__ == "__main__":
    unittest.main()
