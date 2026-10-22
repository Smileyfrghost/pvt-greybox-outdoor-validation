import contextlib
import copy
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import frozen_greybox as gb


class FrozenGreyboxTests(unittest.TestCase):
    def setUp(self):
        self.p = gb.Parameters(10000, 0.75, 8, 15)
        self.u = [800, 20, 25, 50, 500]

    def test_frozen_parameter_bytes_and_values(self):
        self.assertEqual(gb.digest(gb.METADATA / "shared_theta_frozen_v1.json"), "b8960db460a08e66a5af0170b766d58829e2f51379a091a9784217520dcb6158")
        p = gb.load_parameters()
        self.assertAlmostEqual(p.C_eff, 49999.99999987257)
        self.assertAlmostEqual(p.UA_water, 3.335742484883569)

    def test_changed_source_hash_is_rejected(self):
        with patch.object(gb, "digest", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "hash changed"):
                gb.load_parameters()

    def test_energy_signs_and_zero_ambient_term(self):
        terms = gb.heat_terms(40, self.u, self.p)
        self.assertGreater(terms["solar_W"], 0)
        self.assertLess(terms["ambient_W"], 0)
        self.assertLess(terms["water_W"], 0)
        self.assertEqual(terms["electrical_W"], -50)
        self.assertEqual(gb.heat_terms(20, self.u, self.p)["ambient_W"], 0)

    def test_equilibrium_is_preserved(self):
        equilibrium = (0.75 * 0.55 * 800 + 8 * 20 + 15 * 25 - 50) / 23
        self.assertAlmostEqual(gb.step(equilibrium, self.u, self.p), equilibrium, places=12)

    def test_exact_cooling_decay(self):
        expected = 20 + 20 * math.exp(-8 * 60 / 10000)
        self.assertAlmostEqual(gb.step(40, [0, 20, None, 0, 0], self.p), expected, places=12)

    def test_zero_H_limit(self):
        p = gb.Parameters(10000, 0.75, 0, 0)
        expected = 20 + 60 * (0.75 * 0.55 * 800 - 50) / 10000
        self.assertAlmostEqual(gb.step(20, [800, 20, None, 50, 0], p), expected, places=12)

    def test_near_zero_H_is_numerically_stable(self):
        zero = gb.Parameters(10000, 0.75, 0, 0)
        small = gb.Parameters(10000, 0.75, 1e-12, 0)
        self.assertAlmostEqual(gb.step(20, self.u, zero), gb.step(20, self.u, small), places=11)

    def test_semigroup_for_constant_inputs(self):
        first = gb.step(35, self.u, self.p)
        self.assertAlmostEqual(gb.step(first, self.u, self.p), gb.step(35, self.u, self.p, dt=120), places=12)

    def test_more_irradiance_heats_more_electric_power_cools(self):
        base = gb.step(35, self.u, self.p)
        brighter = self.u.copy()
        brighter[0] += 100
        higher_power = self.u.copy()
        higher_power[3] += 30
        self.assertGreater(gb.step(35, brighter, self.p), base)
        self.assertLess(gb.step(35, higher_power, self.p), base)

    def test_pump_off_ignores_missing_or_changed_water(self):
        values = [gb.step(35, [800, 20, water, 50, 0], self.p) for water in [None, math.nan, -100, 1000]]
        self.assertEqual(len(set(values)), 1)
        self.assertEqual(gb.heat_terms(35, [800, 20, None, 50, 0], self.p)["water_W"], 0)

    def test_pump_on_requires_finite_water(self):
        for water in [None, math.nan, math.inf]:
            with self.assertRaises(ValueError):
                gb.step(35, [800, 20, water, 50, 500], self.p)

    def test_unsupported_or_mixed_flow_is_rejected(self):
        with self.assertRaises(ValueError):
            gb.step(35, [800, 20, 25, 50, 300], self.p)
        with self.assertRaisesRegex(ValueError, "Flow event"):
            gb.simulate(35, [self.u, [800, 20, None, 50, 0]], self.p)

    def test_nonfinite_required_inputs_and_states_are_rejected(self):
        for index in [0, 1, 3, 4]:
            for bad in [math.nan, math.inf, -math.inf]:
                u = self.u.copy()
                u[index] = bad
                with self.assertRaises(ValueError):
                    gb.step(35, u, self.p)
        with self.assertRaises(ValueError):
            gb.step(math.nan, self.u, self.p)

    def test_invalid_parameter_or_timestep_domains(self):
        for values in [(0, 0.75, 8, 15), (10000, -1, 8, 15), (10000, 0.75, -1, 15), (10000, 0.75, 8, math.inf)]:
            with self.assertRaises(ValueError):
                gb.Parameters(*values)
        for dt in [0, -1, math.nan, math.inf, True]:
            with self.assertRaises(ValueError):
                gb.step(35, self.u, self.p, dt)

    def test_simulation_transition_index_and_initialization(self):
        states = gb.simulate(35, [self.u, self.u], self.p)
        self.assertEqual(len(states), 3)
        self.assertEqual(states[0], 35)
        self.assertEqual(states[1], gb.step(35, self.u, self.p))
        self.assertEqual(states[2], gb.step(states[1], self.u, self.p))
        self.assertEqual(gb.simulate(10, [], self.p), [10])

    def test_segment_initial_states_are_independent_and_no_output_feedback(self):
        document = {"schema": "greybox-segments-v1", "sampling_seconds": 60, "segments": [
            {"id": "a", "initial_temperature_C": 35, "inputs": [self.u, self.u]},
            {"id": "b", "initial_temperature_C": 20, "inputs": [self.u]},
        ]}
        before = gb.simulate_document(document, self.p)
        document["segments"][0]["observed_temperatures_C"] = [35, 1000, 2000]
        document["segments"][0]["initial_temperature_C"] = 40
        after = gb.simulate_document(document, self.p)
        self.assertEqual([r for r in before if r["segment"] == "b"], [r for r in after if r["segment"] == "b"])
        copy_doc = copy.deepcopy(document)
        copy_doc["segments"][0]["observed_temperatures_C"] = [0, 0, 0]
        self.assertEqual(after, gb.simulate_document(copy_doc, self.p))

    def test_invalid_segment_documents(self):
        for doc in [{"schema": "wrong"}, {"schema": "greybox-segments-v1", "sampling_seconds": 60, "segments": []}]:
            with self.assertRaises(ValueError):
                gb.simulate_document(doc, self.p)
        doc = {"schema": "greybox-segments-v1", "sampling_seconds": 60, "segments": [{"id": "a", "initial_temperature_C": 35, "inputs": [self.u]}] * 2}
        with self.assertRaises(ValueError):
            gb.simulate_document(doc, self.p)

    def test_no_temperature_clipping(self):
        self.assertGreater(gb.step(200, self.u, gb.load_parameters()), 120)

    def test_exact_update_matches_independent_RK4_same_equation(self):
        def rate(T):
            return (0.75 * 0.55 * 800 - 8 * (T - 20) - 15 * (T - 25) - 50) / 10000
        T = 35
        for _ in range(60):
            a = rate(T)
            b = rate(T + a / 2)
            c = rate(T + b / 2)
            d = rate(T + c)
            T += (a + 2 * b + 2 * c + d) / 6
        self.assertAlmostEqual(gb.step(35, self.u, self.p), T, places=10)

    def test_cli_provenance_and_output_protection(self):
        source = ROOT / "data/examples/greybox_synthetic_segments.json"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            args = ["frozen_greybox", "--input", str(source), "--output-dir", str(output)]
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                gb.main()
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["fit_calls"], 0)
            self.assertFalse(manifest["prediction_scoring_performed"])
            self.assertEqual(manifest["input_sha256"], gb.digest(source))
            with patch.object(sys, "argv", args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    gb.main()


if __name__ == "__main__":
    unittest.main()
