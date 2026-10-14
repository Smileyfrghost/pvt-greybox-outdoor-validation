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
from check_model_ready_60s import CONTRACT, CONFIG, check_table, main, sha256


class ModelReadyInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8-sig"))
        self.config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        self.frame = pd.read_csv(ROOT / "data" / "examples" / "synthetic_model_ready_60s.csv")

    def check(self, frame=None):
        return check_table(self.frame if frame is None else frame, self.contract, self.config)

    def test_synthetic_table_and_continuity(self):
        result = self.check()
        self.assertEqual(result["rows"], 14)
        self.assertEqual(result["complete_model_input_rows"], 12)
        self.assertEqual(result["continuous_60s_pairs"], 10)
        self.assertFalse(result["model_fitted"])
        self.assertFalse(result["frozen_result_reproduced"])

    def test_frozen_config_bytes_match_recorded_source(self):
        sources = json.loads((CONFIG.parent / "model_ready_60s_sources.json").read_text(encoding="utf-8-sig"))
        source = next(item for item in sources["sources"] if item["project_relative_path"] == sources["copied_byte_for_byte"]["source"])
        self.assertEqual(sha256(CONFIG), source["sha256"])

    def test_missing_column_and_empty_table(self):
        with self.assertRaisesRegex(ValueError, "Missing required"):
            self.check(self.frame.drop(columns="Tamb"))
        with self.assertRaisesRegex(ValueError, "Empty"):
            self.check(self.frame.iloc[:0])

    def test_string_false_and_invalid_boolean(self):
        self.frame["diagnostic_only"] = "false"
        self.check()
        self.frame.loc[0, "diagnostic_only"] = "maybe"
        with self.assertRaisesRegex(ValueError, "Invalid boolean"):
            self.check()

    def test_window_duration_and_alignment(self):
        self.frame.loc[0, "window_end"] = "2026-03-17 10:00:30"
        with self.assertRaisesRegex(ValueError, "exactly 60"):
            self.check()

    def test_date_timezone_and_minute_alignment(self):
        aware = self.frame.copy()
        for column in ["window_start", "window_end"]:
            aware[column] = pd.to_datetime(aware[column]).dt.tz_localize("Asia/Shanghai").dt.tz_convert("UTC").astype(str)
        self.check(aware)
        self.frame.loc[0, "date"] = "2026-03-16"
        with self.assertRaisesRegex(ValueError, "Date disagrees"):
            self.check()

    def test_fraction_threshold_is_inclusive_and_counts_are_checked(self):
        self.frame.loc[0, ["n_valid_samples", "fraction_valid"]] = [8, 0.8]
        self.check()
        self.frame.loc[0, "n_valid_samples"] = 7
        with self.assertRaisesRegex(ValueError, "disagrees"):
            self.check()
        self.frame.loc[0, "fraction_valid"] = 0.7
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.check()

    def test_event_and_review_do_not_become_eligible(self):
        for column in ["event_boundary_window", "contains_review_required_native", "diagnostic_only"]:
            frame = self.frame.copy()
            frame.loc[0, column] = True
            with self.assertRaisesRegex(ValueError, "conflicts"):
                self.check(frame)

    def test_heldout_cannot_be_training_or_tuning(self):
        for column in ["identification_use", "model_selection_use", "tuning_use"]:
            frame = self.frame.copy()
            frame.loc[8, "validation_use"] = False
            frame.loc[8, column] = True
            with self.assertRaisesRegex(ValueError, "Held-out"):
                self.check(frame)

    def test_pre_intervention_and_role_overlap_are_rejected(self):
        self.frame.loc[8, "aggregation_segment"] = "326_pre_intervention"
        with self.assertRaisesRegex(ValueError, "post-intervention"):
            self.check()
        self.frame.loc[0, "validation_use"] = True
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.check()

    def test_gap_and_missing_input_break_pairs_without_interpolation(self):
        frame = self.frame.drop(index=2).reset_index(drop=True)
        self.assertEqual(self.check(frame)["continuous_60s_pairs"], 8)
        frame = self.frame.copy()
        frame.loc[2, "Tamb"] = np.nan
        result = self.check(frame)
        self.assertEqual(result["continuous_60s_pairs"], 8)
        self.assertEqual(result["rows_missing_model_inputs"], 1)
        self.assertTrue(pd.isna(frame.loc[2, "Tamb"]))

    def test_duplicate_and_reverse_order_are_not_silently_fixed(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.check(pd.concat([self.frame, self.frame.iloc[:1]], ignore_index=True))
        frame = self.frame.iloc[[1, 0] + list(range(2, 14))].reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, "Nonmonotonic"):
            self.check(frame)

    def test_split_minute_audit_fragments_cannot_be_eligible(self):
        fragment = self.frame.iloc[[6]].copy()
        fragment["aggregation_segment"] = "event_other_side"
        frame = pd.concat([self.frame, fragment], ignore_index=True)
        self.check(frame)
        frame.loc[6, "event_boundary_window"] = False
        with self.assertRaisesRegex(ValueError, "Split-minute"):
            self.check(frame)

    def test_cli_records_provenance_and_protects_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            args = ["check_model_ready_60s", "--dataset", str(ROOT / "data" / "examples" / "synthetic_model_ready_60s.csv"), "--output", str(output)]
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                main()
            report = json.loads(output.read_text())
            self.assertEqual(len(report["provenance"]["input_sha256"]), 64)
            with patch.object(sys, "argv", args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()


if __name__ == "__main__":
    unittest.main()
