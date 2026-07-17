from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_experimental_dataset import _continuous_elapsed, _records_from_text, load_day


class ExperimentalDatasetTests(unittest.TestCase):
    def test_logger_reset_is_reconstructed_monotonically(self):
        elapsed = _continuous_elapsed(np.array([1.0, 2.0, 3.0, 0.5, 1.5]))
        self.assertTrue(np.all(np.diff(elapsed) > 0))

    def test_text_parser_and_channel_mapping(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.txt"
            path.write_text("28.8,21.0,19.3,691.4,1934.1\n28.6,21.0,19.1,687.1,1938.3\n", encoding="utf-8")
            records = _records_from_text(path)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["T_panel_C"], 28.8)
            self.assertEqual(records[0]["T_inlet_C"], 19.3)
            self.assertEqual(records[0]["G_W_m2"], 691.4)

    def test_load_day_adds_flow_and_quality_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.txt"
            path.write_text("28.8,21.0,19.3,691.4,10\n28.6,21.0,19.1,687.1,12\n", encoding="utf-8")
            frame = load_day(Path(temp_dir), "3.20", "sample.txt", 300.0)
            self.assertEqual(frame["experiment_date"].iloc[0], "2026-03-20")
            self.assertEqual(frame["date"].iloc[0], "3.20")
            self.assertEqual(frame["flow_kg_s"].iloc[0], 0.005)
            self.assertTrue(frame["timestamp"].isna().all())
            self.assertTrue(frame["wall_elapsed_s"].isna().all())
            self.assertTrue(frame["valid_sensor_range"].all())
            self.assertTrue(frame["active_irradiance"].all())


if __name__ == "__main__":
    unittest.main()
