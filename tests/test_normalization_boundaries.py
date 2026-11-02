"""Backward compatibility and domain-boundary tests; synthetic data only."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from garmin_auto_coach import core, normalization


class NormalizationBoundaryTests(unittest.TestCase):
    def test_public_helpers_remain_available_from_core(self):
        names = (
            "find_key", "as_number", "rounded", "iso_date", "activity_kind",
            "activity_row", "wellness_row", "is_running",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIs(getattr(core, name), getattr(normalization, name))

    def test_synthetic_activity_normalization(self):
        activity = {
            "search": {
                "activityId": 999001, "startTimeLocal": "2026-10-28 08:30:00",
                "activityName": "Synthetic trail run",
                "activityType": {"typeKey": "trail_running"},
                "distance": 10000.0, "duration": 3600.0,
                "averageHR": 146, "elevationGain": 230,
            },
            "detail": {"summaryDTO": {"maxHR": 165}, "latitude": -99.0},
        }
        row = normalization.activity_row(activity)
        self.assertEqual(row["activity_id"], 999001)
        self.assertEqual(row["distance_km"], 10)
        self.assertEqual(row["date"], "2026-10-28")
        self.assertTrue(normalization.is_running(row))
        self.assertEqual(row["ascent_m"], 230)
        self.assertNotIn("latitude", row)
        self.assertEqual(row, core.activity_row(activity))

    def test_missing_and_nested_wellness_are_stable(self):
        record = {
            "date": "2026-10-28",
            "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 25200}},
            "hrv": {"hrvSummary": {"lastNightAvg": 46.2}},
            "body_battery": [{"chargedValue": 60}],
        }
        result = normalization.wellness_row(record)
        self.assertEqual(result["sleep_hours"], 7)
        self.assertEqual(result["hrv_last_night_ms"], 46.2)
        self.assertIsNone(result["sleep_score"])
        self.assertEqual(result, core.wellness_row(record))
        self.assertIsNone(normalization.as_number(None))
        self.assertIsNone(normalization.as_number(True))
        self.assertEqual(normalization.find_key({"outer": {"value": 5}}, "value"), 5)

    def test_normalization_has_no_application_imports(self):
        tree = ast.parse(Path(normalization.__file__).read_text(encoding="utf-8"))
        self.assertFalse([
            node for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level > 0
        ])


if __name__ == "__main__":
    unittest.main()
