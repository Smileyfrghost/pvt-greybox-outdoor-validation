from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_electrical_dataset import build_electrical_dataset, load_power_markdown


def _table(current_header: str, rows: list[str]) -> str:
    return "\n".join(
        [
            "| instrument export | | | | | | | | | | | | | |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            f"| sequence | product | ambient temperature | timestamp | | voltage(V) | current({current_header}) | | active power(W) | power factor | frequency(Hz) | apparent power(W) | reactive power(W) | average |",
            *rows,
        ]
    )


class ElectricalDatasetTests(unittest.TestCase):
    def test_header_milliamps_is_overridden_when_physics_requires_amperes(self):
        text = _table(
            "mA",
            [
                "| 1 | test | 25 | 2026-03-21 08:00:00 | | 14 | 2.0 | | 28 | 0 | 0 | 28 | 0 | 0 |",
                "| 2 | test | 25 | 2026-03-21 08:00:06 | | 15 | 2.0 | | 30 | 0 | 0 | 30 | 0 | 0 |",
                "| 3 | test | 25 | 2026-03-21 08:00:12 | | 16 | 2.0 | | 32 | 0 | 0 | 32 | 0 | 0 |",
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "power.md"
            path.write_text(text, encoding="utf-8")
            raw, unit = load_power_markdown(path)
            self.assertEqual(unit, "mA")
            power_dir = Path(temp_dir)
            dataset, qc = build_electrical_dataset(power_dir)
            self.assertEqual(dataset["current_scale_to_A"].iloc[0], 1.0)
            self.assertTrue(qc["days"]["2026-03-21"]["current_header_conflict"])

    def test_true_milliamps_are_scaled_to_amperes(self):
        text = _table(
            "mA",
            [
                "| 1 | test | 25 | 2026-03-22 08:00:00 | | 14 | 2000 | | 28 | 0 | 0 | 28 | 0 | 0 |",
                "| 2 | test | 25 | 2026-03-22 08:00:06 | | 15 | 2000 | | 30 | 0 | 0 | 30 | 0 | 0 |",
                "| 3 | test | 25 | 2026-03-22 08:00:12 | | 16 | 2000 | | 32 | 0 | 0 | 32 | 0 | 0 |",
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "power.md"
            path.write_text(text, encoding="utf-8")
            dataset, qc = build_electrical_dataset(Path(temp_dir))
            self.assertEqual(dataset["current_scale_to_A"].iloc[0], 0.001)
            self.assertFalse(qc["days"]["2026-03-22"]["current_header_conflict"])
            self.assertAlmostEqual(dataset["current_A"].iloc[0], 2.0)

    def test_duplicate_timestamps_are_preserved_and_flagged(self):
        text = _table(
            "A",
            [
                "| 1 | test | 25 | 2026-03-23 08:00:00 | | 14 | 2 | | 28 | 0 | 0 | 28 | 0 | 0 |",
                "| 2 | test | 25 | 2026-03-23 08:00:00 | | 14 | 2 | | 28 | 0 | 0 | 28 | 0 | 0 |",
                "| 3 | test | 25 | 2026-03-23 08:00:06 | | 15 | 2 | | 30 | 0 | 0 | 30 | 0 | 0 |",
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "power.md"
            path.write_text(text, encoding="utf-8")
            dataset, qc = build_electrical_dataset(Path(temp_dir))
            self.assertEqual(len(dataset), 3)
            self.assertEqual(int(dataset["duplicate_timestamp"].sum()), 2)
            self.assertEqual(qc["days"]["2026-03-23"]["duplicate_timestamp_extra_rows"], 1)
            self.assertEqual(qc["days"]["2026-03-23"]["raw_order_duplicate_time_steps"], 1)
            self.assertEqual(qc["days"]["2026-03-23"]["raw_order_negative_time_steps"], 0)
            self.assertTrue(qc["days"]["2026-03-23"]["raw_order_is_monotonic"])

    def test_raw_timestamp_disorder_is_reported_before_sorting(self):
        text = _table(
            "A",
            [
                "| 1 | test | 25 | 2026-03-24 08:00:06 | | 10 | 2 | | 20 | 0 | 0 | 20 | 0 | 0 |",
                "| 2 | test | 25 | 2026-03-24 08:00:00 | | 10 | 2 | | 20 | 0 | 0 | 20 | 0 | 0 |",
                "| 3 | test | 25 | 2026-03-24 08:00:12 | | 10 | 2 | | 20 | 0 | 0 | 20 | 0 | 0 |",
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "power.md"
            path.write_text(text, encoding="utf-8")
            dataset, qc = build_electrical_dataset(Path(temp_dir))
            day = qc["days"]["2026-03-24"]
            self.assertEqual(day["raw_order_negative_time_steps"], 1)
            self.assertFalse(day["raw_order_is_monotonic"])
            self.assertTrue(dataset["timestamp"].is_monotonic_increasing)
            self.assertEqual(dataset["source_row_order"].tolist(), [1, 0, 2])


if __name__ == "__main__":
    unittest.main()
