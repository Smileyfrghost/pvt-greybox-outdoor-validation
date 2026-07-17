from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from diagnose_electrothermal_alignment import (
    estimate_reference_sample_period,
    reconstruct_thermal_timestamps,
    scan_candidate_offsets,
)


class AlignmentDiagnosticTests(unittest.TestCase):
    def test_scan_recovers_known_synthetic_offset(self):
        rng = np.random.default_rng(7)
        bins = 120
        irradiance = 500 + np.cumsum(rng.normal(0, 20, bins))
        irradiance = np.clip(irradiance, 20, 1_000)
        thermal = pd.DataFrame(
            {
                "sample_order": np.arange(bins),
                "G_W_m2": irradiance,
                "valid_sensor_range": True,
            }
        )
        offset_bins = 17
        power_values = np.full(bins + 40, 5.0)
        power_values[offset_bins : offset_bins + bins] = irradiance * 0.09
        electrical = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-03-21 08:00:00", periods=len(power_values), freq="30s"),
                "active_power_W": power_values,
                "valid_for_model": True,
            }
        )

        scan, _, _ = scan_candidate_offsets(
            thermal, electrical, bin_seconds=30, sample_period_s=30
        )
        best = scan.sort_values("score", ascending=False).iloc[0]

        self.assertEqual(int(best["offset_bin"]), offset_bins)
        self.assertGreater(float(best["score"]), 0.95)

    def test_reference_period_uses_normal_timestamp_intervals(self):
        timestamps = pd.date_range("2026-03-17 09:00:00", periods=100, freq="5834ms").to_series(index=None)
        timestamps.iloc[50:] = timestamps.iloc[50:] + pd.Timedelta(seconds=300)
        thermal = pd.DataFrame(
            {
                "experiment_date": "2026-03-17",
                "sample_order": np.arange(100),
                "timestamp": timestamps.to_numpy(),
            }
        )

        audit = estimate_reference_sample_period(thermal)

        self.assertAlmostEqual(audit["sample_period_s"], 5.834, places=3)
        self.assertEqual(audit["long_gap_count"], 1)

    def test_non_timestamped_log_is_anchored_to_electrical_stop(self):
        thermal = pd.DataFrame({"sample_order": [0, 1, 2], "timestamp": [pd.NaT] * 3})
        electrical = pd.DataFrame(
            {"timestamp": pd.date_range("2026-03-21 08:00:00", periods=7, freq="10s")}
        )

        aligned, basis = reconstruct_thermal_timestamps(thermal, electrical, sample_period_s=10)

        self.assertEqual(basis, "author_confirmed_common_stop_fixed_period")
        self.assertEqual(aligned.iloc[0], pd.Timestamp("2026-03-21 08:00:40"))
        self.assertEqual(aligned.iloc[-1], pd.Timestamp("2026-03-21 08:01:00"))


if __name__ == "__main__":
    unittest.main()
