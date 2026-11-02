"""Report-rendering architecture tests using synthetic training data only."""
from __future__ import annotations

import ast
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from garmin_auto_coach import core, reporting

DAY = date(2026, 10, 29)
ACTIVITY = {"date": "2026-10-28", "type": "trail_running", "distance_km": 12.5,
            "duration_min": 90, "ascent_m": 450, "pace_min_km": 7.2, "average_hr_bpm": 145}
WELLNESS = {"date": "2026-10-28", "sleep_hours": 7.25,
            "sleep_score": 81, "hrv_last_night_ms": 50, "hrv_status": "BALANCED"}


class ReportingBoundaryTests(unittest.TestCase):
    def test_compatibility_of_explicit_date(self):
        rows = [ACTIVITY]
        self.assertEqual(core.fmt(12.345, 2), reporting.fmt(12.345, 2))
        self.assertEqual(core.week_summary(rows, weeks=1, today=DAY),
                         reporting.week_summary(rows, weeks=1, today=DAY))
        self.assertEqual(core.coach_context(rows, [WELLNESS], "Synthetic goal", DAY),
                         reporting.coach_context(rows, [WELLNESS], "Synthetic goal", DAY))

    def test_legacy_defaults_use_original_core_clock(self):
        with patch.object(core, "local_today", return_value=DAY):
            self.assertEqual(core.week_summary([ACTIVITY], weeks=1),
                             reporting.week_summary([ACTIVITY], weeks=1, today=DAY))
            self.assertEqual(core.coach_context([ACTIVITY], [WELLNESS], "Synthetic"),
                             reporting.coach_context([ACTIVITY], [WELLNESS], "Synthetic", DAY))

    def test_reporting_layer_requires_an_explicit_date(self):
        with self.assertRaises(ValueError):
            reporting.week_summary([], weeks=1)
        with self.assertRaises(ValueError):
            reporting.coach_context([], [], "Synthetic")

    def test_reporting_does_not_depend_on_core_or_storage(self):
        tree = ast.parse(Path(reporting.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                self.assertEqual(node.module, "normalization")

    def test_synthetic_report_preserves_running_filter_and_privacy(self):
        hike = dict(ACTIVITY, type="hiking", distance_km=30, ascent_m=1800)
        summary = core.week_summary([ACTIVITY, hike], weeks=1, today=DAY)
        self.assertIn("| 2026-10-26 | 1 | 12.50 | 90 | 450 | 12.50 |", summary)
        context = core.coach_context([ACTIVITY], [WELLNESS], "Synthetic goal", DAY)
        self.assertIn("Synthetic goal", context)
        self.assertNotIn("latitude", context)
        self.assertNotIn("longitude", context)


if __name__ == "__main__":
    unittest.main()
