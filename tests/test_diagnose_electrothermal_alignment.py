from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from diagnose_electrothermal_alignment import scan_candidate_offsets


class AlignmentDiagnosticTests(unittest.TestCase):
    def test_scan_recovers_known_synthetic_offset(self):
        rng = np.random.default_rng(7)
        bins = 120
        irradiance = 500 + np.cumsum(rng.normal(0, 20, bins))
        irradiance = np.clip(irradiance, 20, 1_000)
        thermal = pd.DataFrame(
            {
                "elapsed_s": np.arange(bins) * 30,
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

        scan, _, _ = scan_candidate_offsets(thermal, electrical, bin_seconds=30)
        best = scan.sort_values("score", ascending=False).iloc[0]

        self.assertEqual(int(best["offset_bin"]), offset_bins)
        self.assertGreater(float(best["score"]), 0.95)


if __name__ == "__main__":
    unittest.main()
