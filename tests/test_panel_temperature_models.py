from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from fit_panel_temperature_models import fit_ridge, metrics, resample_days


class PanelTemperatureModelTests(unittest.TestCase):
    def test_ridge_recovers_simple_linear_relation(self):
        x = np.arange(20, dtype=float).reshape(-1, 1)
        y = 2.0 + 3.0 * x[:, 0]
        model = fit_ridge(x, y, penalty=0.0)
        np.testing.assert_allclose(model.predict(x), y, atol=1e-10)

    def test_metrics_are_zero_for_perfect_prediction(self):
        observed = np.array([1.0, 2.0, 4.0])
        result = metrics(observed, observed.copy())
        self.assertEqual(result["mae_C"], 0.0)
        self.assertEqual(result["rmse_C"], 0.0)
        self.assertEqual(result["bias_C"], 0.0)
        self.assertEqual(result["r2"], 1.0)

    def test_resampling_preserves_day_and_endpoints(self):
        frame = pd.DataFrame(
            {
                "date": ["3.16"] * 3,
                "elapsed_s": [0.0, 5.0, 10.0],
                "T_panel_C": [20.0, 22.0, 24.0],
                "T_tank_C": [18.0, 18.5, 19.0],
                "T_inlet_C": [17.0, 17.5, 18.0],
                "G_W_m2": [100.0, 200.0, 300.0],
                "flow_kg_s": [0.005] * 3,
                "valid_sensor_range": [True] * 3,
            }
        )
        day = resample_days(frame, step_s=5.0)["3.16"]
        self.assertEqual(len(day), 3)
        self.assertEqual(day["T_panel_C"].iloc[-1], 24.0)


if __name__ == "__main__":
    unittest.main()
