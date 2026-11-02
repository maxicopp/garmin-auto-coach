"""Golden regression tests for the legacy Garmin Auto Coach behavior.

Golden outputs are created ONCE from synthetic input by the installer. They are
reviewed and committed, and must never be updated automatically during tests.
Only synthetic records are used. No Garmin API calls, credentials or private
activity data are loaded.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from garmin_auto_coach import core

TODAY = date(2026, 10, 29)
FREEZE_TIME = datetime(2026, 10, 29, 12, 0, 0)
SNAPSHOTS = Path(__file__).resolve().parent / "fixtures" / "regression_baseline"
EXPECTED_REPORTS = (
    "activities.csv", "wellness.csv", "weekly_metrics.csv", "fit_metrics.csv",
    "laps.csv", "training_metrics.json", "training_analysis.md",
    "weekly_summary.md", "coach_context.md", "latest_sync.json",
)
GOALS = "Synthetic trail running goal (test fixture only)"


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 29, 12, 0, 0, tzinfo=tz)


def encode_json(data):
    return (json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def create_synthetic_input(private: Path):
    """All training records are made-up; no Garmin or local private data read."""
    activities = private / "activities"
    activities.mkdir(parents=True)
    records = [
        (10001, "2026-08-24", "running", 6500, 2400, 30, 141),
        (10002, "2026-08-31", "running", 8200, 3100, 50, 145),
        (10003, "2026-09-07", "running", 10500, 4200, 70, 148),
        (10004, "2026-09-14", "running", 9500, 3800, 40, 147),
        (10005, "2026-09-21", "trail_running", 14000, 6300, 500, 153),
        (10006, "2026-09-28", "running", 12500, 4900, 80, 147),
        (10007, "2026-10-05", "running", 16000, 6200, 65, 149),
        (10008, "2026-10-12", "trail_running", 18500, 8200, 820, 155),
        (10009, "2026-10-19", "running", 11000, 4300, 45, 146),
        (10010, "2026-10-27", "running", 5000, 1710, 20, 158),
        (10011, "2026-10-22", "hiking", 20000, 14000, 1000, 110),
    ]
    for activity_id, day, kind, distance, duration, ascent, hr in records:
        search = {
            "activityId": activity_id,
            "activityName": f"Synthetic activity {activity_id}",
            "activityType": {"typeKey": kind},
            "startTimeLocal": day + " 08:00:00",
            "distance": float(distance),
            "duration": float(duration),
            "movingDuration": float(duration - 30),
            "averageSpeed": float(distance / duration),
            "averageHR": hr,
            "elevationGain": float(ascent),
        }
        detail = {
            "activityId": activity_id,
            "summaryDTO": {
                "maxHR": hr + 20,
                "aerobicTrainingEffect": 3.1,
                "anaerobicTrainingEffect": 0.4,
            },
            # These fake coordinates must never appear in public exports.
            "gps_private_test_marker": "SYNTHETIC_GPS_SHOULD_NOT_EXPORT",
            "latitude": -99.123456,
            "longitude": -99.654321,
        }
        (activities / f"{activity_id}.json").write_bytes(
            encode_json({"search": search, "detail": detail, "search_digest": "synthetic"})
        )

    wellness = private / "wellness"
    wellness.mkdir()
    wellness_rows = [
        ("2026-10-26", 27000, 82, 51.2, "BALANCED", 65, 50),
        ("2026-10-27", 21600, 70, 48.0, "BALANCED", 47, 60),
        ("2026-10-28", None, None, None, "", 52, 41),
    ]
    for day, seconds, score, hrv, status, charged, drained in wellness_rows:
        record = {
            "date": day,
            "sleep": {"dailySleepDTO": {
                **({"sleepTimeSeconds": seconds} if seconds is not None else {}),
                **({"sleepScores": {"overall": {"value": score}}} if score is not None else {}),
            }},
            "hrv": {"hrvSummary": {
                **({"lastNightAvg": hrv, "weeklyAvg": hrv - 1} if hrv is not None else {}),
                "status": status,
            }},
            "body_battery": [{"chargedValue": charged, "drainedValue": drained}],
        }
        (wellness / f"{day}.json").write_bytes(encode_json(record))

    # Seed a synthetic FIT cache for a realistic, reproducible fit_metrics/laps
    # snapshot. The placeholder ZIP is never parsed: the cache signature matches.
    # Existing FIT-parser tests separately exercise parsing/error behavior.
    original = private / "originals" / "10007.zip"
    original.parent.mkdir()
    original.write_bytes(b"synthetic cached FIT placeholder - NOT real training data\n")
    fixed_ns = 1_600_000_000_000_000_000
    os.utime(original, ns=(fixed_ns, fixed_ns))
    cache = private / "fit-cache-v02"
    cache.mkdir()
    synthetic = {
        "signature": f"{original.stat().st_size}:{original.stat().st_mtime_ns}:running:65.0",
        "summary": {
            "activity_id": "10007", "fit_status": "ok", "fit_records": 2500,
            "fit_duration_min": 103.3, "fit_hr_coverage_pct": 99.2,
            "fit_moving_hr_samples": 2480, "fit_laps": 1,
            "fit_mean_hr_bpm": 149.0, "fit_median_cadence_spm": 82.0,
            "fit_drift_pct": 3.2, "fit_drift_note": "Synthetic cache only",
        },
        "laps": [{
            "activity_id": "10007", "lap_index": 1, "duration_min": 103.3,
            "distance_km": 16.0, "average_hr_bpm": 149,
            "max_hr_bpm": 170, "ascent_m": 65, "pace_min_km": 6.46,
        }],
    }
    (cache / "10007.json").write_bytes(encode_json(synthetic))


def render(private: Path, exports: Path):
    with patch.object(core, "datetime", FrozenDateTime):
        return core.generate_exports(private, exports, goals=GOALS, today=TODAY)


def render_in_temporary_directory():
    """Returns bytes, never references to files that outlive the temp folder."""
    with tempfile.TemporaryDirectory(prefix="garmin-synthetic-regression-") as tmp:
        root = Path(tmp)
        private = root / "private"
        exports = root / "exports"
        create_synthetic_input(private)
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (private / "activities").glob("*.json")}
        render(private, exports)
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (private / "activities").glob("*.json")}
        if before != after:
            raise AssertionError("Report generation modified raw synthetic activities")
        return {p.name: p.read_bytes() for p in exports.iterdir() if p.is_file()}


def record_baseline():
    """Run only once when adding snapshots; tests never update baselines."""
    if SNAPSHOTS.exists():
        raise SystemExit(f"Refusing to overwrite existing golden snapshots: {SNAPSHOTS}")
    reports = render_in_temporary_directory()
    if set(reports) != set(EXPECTED_REPORTS):
        raise SystemExit(f"Unexpected report names: {sorted(set(reports) ^ set(EXPECTED_REPORTS))}")
    SNAPSHOTS.mkdir(parents=True)
    for name, content in sorted(reports.items()):
        (SNAPSHOTS / name).write_bytes(content)
    manifest = {
        "description": "Synthetic Garmin Auto Coach baseline. Generated once; review before updating.",
        "reference_date": TODAY.isoformat(),
        "files": {name: hashlib.sha256(value).hexdigest() for name, value in sorted(reports.items())},
    }
    (SNAPSHOTS / "manifest.json").write_bytes(encode_json(manifest))
    print(f"Recorded {len(reports)} synthetic golden outputs at {SNAPSHOTS}")


class GoldenRegressionTests(unittest.TestCase):
    def test_full_report_bytes_match_approved_baseline(self):
        self.assertTrue((SNAPSHOTS / "manifest.json").is_file(),
                        "Missing committed golden fixtures: run the installer once")
        expected = json.loads((SNAPSHOTS / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(expected["files"]), set(EXPECTED_REPORTS))
        actual = render_in_temporary_directory()
        self.assertEqual(set(actual), set(EXPECTED_REPORTS))
        for name in EXPECTED_REPORTS:
            with self.subTest(file=name):
                baseline = (SNAPSHOTS / name).read_bytes()
                self.assertEqual(hashlib.sha256(baseline).hexdigest(), expected["files"][name],
                                 f"Committed golden fixture was edited: {name}")
                self.assertEqual(actual[name], baseline,
                                 f"Behavior changed in {name}; review before approving a baseline update")

    def test_repeated_reports_are_byte_identical(self):
        with tempfile.TemporaryDirectory(prefix="garmin-idempotence-") as tmp:
            root = Path(tmp)
            private, exports = root / "private", root / "exports"
            create_synthetic_input(private)
            render(private, exports)
            before = {p.name: p.read_bytes() for p in exports.iterdir() if p.is_file()}
            render(private, exports)
            after = {p.name: p.read_bytes() for p in exports.iterdir() if p.is_file()}
            self.assertEqual(before, after)

    def test_export_privacy_and_csv_contracts(self):
        reports = render_in_temporary_directory()
        all_text = "\n".join(data.decode("utf-8") for data in reports.values())
        self.assertNotIn("SYNTHETIC_GPS_SHOULD_NOT_EXPORT", all_text)
        self.assertNotIn("-99.123456", all_text)
        self.assertNotIn("-99.654321", all_text)
        activity_csv = list(csv.DictReader(reports["activities.csv"].decode().splitlines()))
        self.assertEqual(len(activity_csv), 11)
        self.assertEqual([r["activity_id"] for r in activity_csv],
                         [str(x) for x in (10001, 10002, 10003, 10004, 10005, 10006, 10007, 10008, 10009, 10011, 10010)])
        metrics = json.loads(reports["training_metrics.json"])
        self.assertEqual(metrics["run_count"], 10)
        self.assertEqual(metrics["activity_count"], 11)
        self.assertFalse(metrics["weekly"][-1]["complete"])
        self.assertEqual(metrics["fit_status_counts"].get("ok"), 1)
        self.assertEqual(len(list(csv.DictReader(reports["laps.csv"].decode().splitlines()))), 1)


if __name__ == "__main__":
    if sys.argv[1:] == ["--record-baseline"]:
        record_baseline()
    else:
        unittest.main()
