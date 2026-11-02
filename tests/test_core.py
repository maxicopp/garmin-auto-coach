from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from garmin_auto_coach.core import activity_row, wellness_row, week_summary, generate_exports
from garmin_auto_coach.sync import run_sync


class FakeClient:
    def __init__(self):
        self.details_called = 0
        self.searches = 0

    def search_activities(self, *, start, limit, start_date, end_date):
        self.searches += 1
        if start:
            return []
        return [{
            'activityId': 987654, 'startTimeLocal': '2026-10-28 08:30:00',
            'activityName': 'Rodaje Z2', 'activityType': {'typeKey': 'running'},
            'distance': 7000.0, 'duration': 2700.0, 'averageSpeed': 2.5926,
            'averageHR': 140, 'elevationGain': 52.0,
        }]

    def get_activity(self, activity_id):
        self.details_called += 1
        return {'activityId': activity_id, 'summaryDTO': {'maxHR': 166}}

    def get_daily_sleep(self, day):
        return {'dailySleepDTO': {'sleepTimeSeconds': 27000, 'sleepScores': {'overall': {'value': 80}}}}

    def get_daily_hrv(self, day):
        return {'hrvSummary': {'lastNightAvg': 49, 'weeklyAvg': 47, 'status': 'BALANCED'}}

    def get_daily_body_battery(self, first, last):
        return [{'chargedValue': 62, 'drainedValue': 55}]

    def download_activity(self, activity_id):
        return b'PK\x03\x04fakezip'


class TestReport(unittest.TestCase):
    def test_activity_row_conversions(self):
        row = activity_row({'search': FakeClient().search_activities(start=0, limit=50, start_date='', end_date='')[0], 'detail': {'summaryDTO': {'maxHR': 166}}})
        self.assertEqual(row['distance_km'], 7)
        self.assertAlmostEqual(row['pace_min_km'], 6.43, places=2)
        self.assertEqual(row['max_hr_bpm'], 166)
        self.assertEqual(row['type'], 'running')
        self.assertEqual(row['date'], '2026-10-28')

    def test_wellness(self):
        wellness = wellness_row({'date': '2026-10-28', 'sleep': {'dailySleepDTO': {'sleepTimeSeconds': 27000}}, 'hrv': {'hrvSummary': {'lastNightAvg': 49}}, 'body_battery': [{'chargedValue': 62}]})
        self.assertEqual(wellness['sleep_hours'], 7.5)
        self.assertEqual(wellness['hrv_last_night_ms'], 49)
        self.assertEqual(wellness['body_battery_charged'], 62)

    def test_sleep_score_nested(self):
        row = wellness_row({'date': '2026-10-29', 'sleep': {'dailySleepDTO': {'sleepTimeSeconds': 27000, 'sleepScores': {'overall': {'value': 80}}}}})
        self.assertEqual(row['sleep_score'], 80)

    def test_week_summary_excludes_hiking(self):
        rows = [{'date': '2026-10-28', 'type': 'trail_running', 'distance_km': 7, 'duration_min': 40, 'ascent_m': 100}, {'date': '2026-10-28', 'type': 'hiking', 'distance_km': 18, 'duration_min': 200, 'ascent_m': 900}]
        summary = week_summary(rows, weeks=1, today=date(2026,10,29))
        self.assertIn('| 2026-10-26 | 1 | 7.00 | 40 | 100 | 7.00 |', summary)

    def test_end_to_end_idempotence(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            client = FakeClient()
            result = run_sync(client, base/'private', base/'drive', initial_days=2, wellness_days=2, today=date(2026,10,29), pause=0)
            self.assertEqual(result['activities'], 1)
            self.assertEqual(client.details_called, 1)
            result2 = run_sync(client, base/'private', base/'drive', initial_days=2, wellness_days=2, today=date(2026,10,29), pause=0)
            self.assertEqual(result2['new_or_changed'], 0)
            self.assertEqual(client.details_called, 1)
            with (base/'drive'/'activities.csv').open(newline='') as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['activity_id'], '987654')
            self.assertEqual(len(list((base/'private'/'wellness').glob('*.json'))), 2)
            self.assertIn('Rodaje Z2', (base/'private'/'activities'/'987654.json').read_text())
            self.assertNotIn('Rodaje Z2', (base/'drive'/'coach_context.md').read_text())  # export only summary without name

    def test_no_raw_location_in_export(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            client = FakeClient()
            run_sync(client, base/'private', base/'drive', initial_days=2, wellness_days=1, today=date(2026,10,29), pause=0)
            data = '\n'.join(p.read_text() for p in (base/'drive').iterdir() if p.suffix in {'.csv','.md','.json'})
            self.assertNotIn('latitude', data)
            self.assertNotIn('longitude', data)


if __name__ == '__main__':
    unittest.main()
