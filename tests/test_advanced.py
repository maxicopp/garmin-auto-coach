from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from garmin_auto_coach.analytics import compute, get_weekly, make_report
from garmin_auto_coach.fit_analysis import _analyze_points, summarize_fit
from garmin_auto_coach.sync import backfill_originals, run_sync
from test_core import FakeClient


class AdvancedTests(unittest.TestCase):
    def test_partial_week_excluded_and_long_share(self):
        activities = [
            {'date': '2026-10-19', 'type': 'running', 'distance_km': 20, 'duration_min': 120, 'ascent_m': 40},
            {'date': '2026-10-21', 'type': 'running', 'distance_km': 10, 'duration_min': 70, 'ascent_m': 30},
            {'date': '2026-10-28', 'type': 'running', 'distance_km': 8, 'duration_min': 55, 'ascent_m': 10},
            {'date': '2026-10-22', 'type': 'hiking', 'distance_km': 18, 'duration_min': 300, 'ascent_m': 750},
        ]
        w = get_weekly(activities, date(2026, 10, 29), weeks=3)
        self.assertEqual(w[-2]['distance_km'], 30)
        self.assertEqual(w[-2]['long_run_share_pct'], 66.7)
        self.assertEqual(w[-2]['ascent_m'], 70)
        self.assertEqual(w[-1]['distance_km'], 8)
        self.assertFalse(w[-1]['complete'])
        self.assertIsNone(w[-1]['km_change_vs_previous_pct'])
        metrics = compute(activities, [], [], date(2026, 10, 29))
        self.assertNotIn('PARCIAL', str(metrics['last4_weekly_avg_km']))
        self.assertIn('PARCIAL', make_report(metrics, 'trail'))

    def test_drift_on_steady_run_and_short_run_exclusion(self):
        start = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)
        points = []
        for i in range(90 * 60):
            points.append({'time': start + timedelta(seconds=i), 'hr': 135 if i < 2700 else 150, 'speed': 2.8})
        result = _analyze_points(points)
        self.assertIsNotNone(result['drift'])
        self.assertGreater(result['drift'], 5)
        self.assertIsNone(_analyze_points(points[: 20 * 60])['drift'])

    def test_backfill_skips_existing_and_survives_failure(self):
        class Client(FakeClient):
            def download_activity(self, activity_id):
                if activity_id == 2:
                    raise RuntimeError('no ZIP available')
                data = io.BytesIO()
                with zipfile.ZipFile(data, 'w') as z:
                    z.writestr('record.fit', b'fake fit')
                return data.getvalue()

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / 'activities'
            root.mkdir()
            (root / '1.json').write_text('{}')
            (root / '2.json').write_text('{}')
            r = backfill_originals(Client(), base, pause=0)
            self.assertEqual(r['downloaded'], 1)
            self.assertEqual(r['failed'], 1)
            self.assertTrue((base / 'originals' / '1.zip').exists())
            r2 = backfill_originals(Client(), base, pause=0)
            self.assertEqual(r2['existing'], 1)
            self.assertEqual(r2['downloaded'], 0)

    def test_zip_contains_fit_but_bad_fit_never_crashes_report(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / '1.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('test.fit', b'bad fit data')
            report, laps = summarize_fit(p, 1)
            self.assertIn(report['fit_status'], ('missing_fitdecode', 'parse_error'))
            self.assertEqual(laps, [])

    def test_daily_with_download_failure_continues(self):
        class Client(FakeClient):
            def download_activity(self, activity_id):
                raise RuntimeError('Garmin download unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            ret = run_sync(Client(), p / 'private', p / 'exports', initial_days=2,
                           wellness_days=1, today=date(2026, 10, 29),
                           originals=True, pause=0)
            self.assertEqual(ret['activities'], 1)
            self.assertTrue((p / 'exports' / 'training_analysis.md').exists())
            self.assertFalse(list((p / 'private').rglob('*.zip')))


if __name__ == '__main__':
    unittest.main()
