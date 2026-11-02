"""Offline resilience contracts for Garmin synchronization (synthetic data only)."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from garmin_auto_coach.core import digest
from garmin_auto_coach.sync import (
    extract_activities, fetch_activities, sync_activities,
    sync_wellness, run_sync,
)

DAY = date(2026, 10, 29)


def summary(activity_id=123, *, distance=7000):
    return {
        "activityId": activity_id,
        "activityName": "Synthetic training activity",
        "activityType": {"typeKey": "running"},
        "startTimeLocal": "2026-10-29 09:00:00",
        "distance": distance,
        "duration": 2600,
        "averageSpeed": distance / 2600,
    }


class Client:
    def __init__(self, activities=None):
        self.activities = list(activities if activities is not None else [summary()])
        self.details_called = 0
        self.download_calls = 0

    def search_activities(self, *, start, limit, start_date, end_date):
        return self.activities[start:start + limit]

    def get_activity(self, activity_id):
        self.details_called += 1
        return {"activityId": activity_id, "summaryDTO": {"maxHR": 170}}

    def download_activity(self, activity_id):
        self.download_calls += 1
        return b"invalid ZIP content"

    def get_daily_sleep(self, day):
        return {"dailySleepDTO": {"sleepTimeSeconds": 25200}}

    def get_daily_hrv(self, day):
        return {"hrvSummary": {"lastNightAvg": 49}}

    def get_daily_body_battery(self, start, end):
        return [{"chargedValue": 45, "drainedValue": 55}]


class SyncResilienceTests(unittest.TestCase):
    def test_response_shapes_and_invalid_payload(self):
        record = summary()
        self.assertEqual(extract_activities([record]), [record])
        for key in ("activities", "results", "data"):
            with self.subTest(key=key):
                self.assertEqual(extract_activities({key: [record]}), [record])
        with self.assertRaises(ValueError):
            extract_activities({"unexpected": [record]})

    def test_activity_pagination_does_not_lose_records(self):
        client = Client([summary(i) for i in range(1, 6)])
        found = list(fetch_activities(client, DAY, DAY, page_size=2, pause=0))
        self.assertEqual([x["activityId"] for x in found], [1, 2, 3, 4, 5])

    def test_invalid_activity_ids_are_ignored_without_detail_calls(self):
        client = Client([summary("bad"), summary(0), summary(-1), summary(None)])
        with tempfile.TemporaryDirectory(prefix="garmin-invalid-id-") as tmp:
            total, changed, originals = sync_activities(client, Path(tmp), DAY, DAY, False, pause=0)
            self.assertEqual((total, changed, originals), (0, 0, 0))
            self.assertEqual(client.details_called, 0)
            self.assertFalse(list((Path(tmp) / "activities").glob("*.json")))

    def test_unchanged_activity_does_not_refetch_detail(self):
        client = Client()
        with tempfile.TemporaryDirectory(prefix="garmin-idempotent-sync-") as tmp:
            root = Path(tmp)
            self.assertEqual(sync_activities(client, root, DAY, DAY, False, pause=0), (1, 1, 0))
            cached = (root / "activities" / "123.json").read_bytes()
            self.assertEqual(sync_activities(client, root, DAY, DAY, False, pause=0), (1, 0, 0))
            self.assertEqual(client.details_called, 1)
            self.assertEqual((root / "activities" / "123.json").read_bytes(), cached)

    def test_detail_failure_preserves_previous_activity_and_checkpoint(self):
        class FailingClient(Client):
            def get_activity(self, activity_id):
                raise RuntimeError("synthetic Garmin API failure")

        with tempfile.TemporaryDirectory(prefix="garmin-failed-detail-") as tmp:
            private = Path(tmp) / "private"
            activities = private / "activities"
            activities.mkdir(parents=True)
            previous_summary = summary(distance=6000)
            existing = {
                "search": previous_summary, "detail": {"synthetic": "retain"},
                "search_digest": digest(previous_summary),
            }
            cached_path = activities / "123.json"
            cached_path.write_text(json.dumps(existing), encoding="utf-8")
            state_path = private / "state.json"
            state_path.write_text('{"last_success": "2026-10-28"}', encoding="utf-8")
            cached_bytes = cached_path.read_bytes()
            state_bytes = state_path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "synthetic Garmin"):
                run_sync(FailingClient(), private, Path(tmp) / "exports", today=DAY, pause=0)
            self.assertEqual(cached_path.read_bytes(), cached_bytes)
            self.assertEqual(state_path.read_bytes(), state_bytes)

    def test_invalid_download_does_not_cache_zip_or_stop_activity_sync(self):
        client = Client()
        with tempfile.TemporaryDirectory(prefix="garmin-invalid-download-") as tmp:
            root = Path(tmp)
            self.assertEqual(sync_activities(client, root, DAY, DAY, True, pause=0), (1, 1, 0))
            self.assertEqual(client.download_calls, 1)
            self.assertTrue((root / "activities" / "123.json").is_file())
            self.assertFalse((root / "originals" / "123.zip").exists())
            self.assertFalse(list(root.rglob("*.zip.tmp")))

    def test_wellness_failure_preserves_previously_cached_field(self):
        class PartialFailure(Client):
            def get_daily_sleep(self, day):
                raise RuntimeError("synthetic sleep API failure")

        with tempfile.TemporaryDirectory(prefix="garmin-wellness-failure-") as tmp:
            private = Path(tmp)
            directory = private / "wellness"
            directory.mkdir()
            previous_sleep = {"dailySleepDTO": {"sleepTimeSeconds": 28800}}
            target = directory / "2026-10-29.json"
            target.write_text(json.dumps({"date": "2026-10-29", "sleep": previous_sleep}), encoding="utf-8")
            self.assertEqual(sync_wellness(PartialFailure(), private, DAY, DAY, pause=0), 1)
            stored = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(stored["sleep"], previous_sleep)
            self.assertEqual(stored["hrv"]["hrvSummary"]["lastNightAvg"], 49)
            self.assertEqual(stored["body_battery"][0]["chargedValue"], 45)

    def test_fatal_wellness_failure_does_not_advance_checkpoint(self):
        with tempfile.TemporaryDirectory(prefix="garmin-checkpoint-failure-") as tmp:
            private = Path(tmp) / "private"
            private.mkdir()
            state = private / "state.json"
            state.write_text('{"last_success":"2026-10-28"}', encoding="utf-8")
            before = state.read_bytes()
            with patch("garmin_auto_coach.sync.sync_wellness", side_effect=RuntimeError("synthetic interruption")):
                with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
                    run_sync(Client(), private, Path(tmp) / "exports", today=DAY, pause=0)
            self.assertEqual(state.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
