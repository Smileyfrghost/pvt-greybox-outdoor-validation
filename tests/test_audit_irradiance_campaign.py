import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from audit_irradiance_campaign import (
    exact_horizon_ramps,
    find_column,
    integrate_valid_intervals,
    load_campaign,
    timestamp_gap_table,
)


class IrradianceAuditTests(unittest.TestCase):
    def test_ambiguous_header_is_rejected(self):
        with self.assertRaises(ValueError):
            find_column(["time_a", "time_b"], required=("time",))

    def test_constant_irradiance_has_expected_energy_units(self):
        times = pd.Series(pd.date_range("2026-01-01", periods=3, freq="min"))
        self.assertAlmostEqual(
            integrate_valid_intervals(times, pd.Series([100.0] * 3)), 0.012
        )

    def test_integration_does_not_bridge_a_missing_minute(self):
        times = pd.Series(pd.to_datetime([
            "2026-01-01 10:00", "2026-01-01 10:01", "2026-01-01 10:03"
        ]))
        self.assertAlmostEqual(
            integrate_valid_intervals(times, pd.Series([100.0] * 3)), 0.006
        )

    def test_ramps_require_the_exact_time_difference(self):
        campaign = pd.DataFrame({
            "timestamp": pd.to_datetime([
                "2026-01-01 10:00", "2026-01-01 10:01", "2026-01-01 10:03"
            ]),
            "date": "2026-01-01",
            "total_w_m2": [100.0, 200.0, 400.0],
            "direct_w_m2": [50.0, 100.0, 300.0],
        })
        summary, events = exact_horizon_ramps(campaign, horizons_minutes=(1,))
        total = summary.loc[summary["channel"] == "total_w_m2"].iloc[0]
        self.assertEqual(total["valid_ramp_n"], 1)
        self.assertEqual(total["absolute_ramp_max_w_m2_per_min"], 100.0)
        self.assertTrue((events["timestamp"] == pd.Timestamp("2026-01-01 10:01")).all())

    def test_gap_table_preserves_source_and_missing_sample_count(self):
        campaign = pd.DataFrame({
            "timestamp": pd.to_datetime([
                "2026-01-01 10:00", "2026-01-01 10:01",
                "2026-01-01 10:02", "2026-01-01 10:04",
            ]),
            "source_file": "synthetic.xlsx",
            "source_sheet": "Sheet1",
        })
        gaps = timestamp_gap_table(campaign)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps.iloc[0]["estimated_missing_sample_n"], 1)
        self.assertEqual(gaps.iloc[0]["source_file"], "synthetic.xlsx")

    def test_workbook_load_reports_duplicates_and_partial_coverage(self):
        frame = pd.DataFrame({
            "时间": pd.to_datetime([
                "2026-01-01 10:00", "2026-01-01 10:01", "2026-01-01 10:01"
            ]),
            "总辐射瞬时": [100, 200, 300],
        })
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic.xlsx"
            frame.to_excel(source, index=False)
            coverage, campaign, schema = load_campaign(Path(directory))
        self.assertEqual(coverage.iloc[0]["duplicate_timestamp_n"], 1)
        self.assertEqual(coverage.iloc[0]["coverage_status"], "partial_start_and_end")
        self.assertEqual(len(campaign), 3)
        self.assertTrue(np.isnan(campaign["direct_w_m2"]).all())
        self.assertEqual(schema[0]["status"], "loaded")


if __name__ == "__main__":
    unittest.main()
