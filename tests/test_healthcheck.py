"""Offline synthetic tests for the optional read-only health checker."""
from __future__ import annotations

import importlib.util
import json
import plistlib
import tempfile
import unittest
from datetime import date
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "healthcheck.py"
spec = importlib.util.spec_from_file_location("garmin_healthcheck", MODULE)
healthcheck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(healthcheck)
TODAY = date(2026, 11, 2)


class HealthcheckTests(unittest.TestCase):
    def create_fixture(self, root):
        (root / ".env").write_text("SYNTHETIC_PLACEHOLDER_DO_NOT_READ=secret\n")
        (root / ".venv" / "bin").mkdir(parents=True)
        (root / ".venv" / "bin" / "python").touch()
        (root / "scripts").mkdir()
        (root / "scripts" / "run_daily.sh").touch()
        (root / "private-data").mkdir()
        (root / "private-data" / "state.json").write_text('{"last_success":"2026-11-02"}')
        (root / "exports").mkdir()
        (root / "exports" / "latest_sync.json").write_text('{"generated_at":"2026-11-02T07:00:00-03:00"}')

    def test_healthy_project_and_no_file_modifications(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_fixture(root)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            results = healthcheck.audit(root, today=TODAY, check_launchd=False)
            self.assertTrue(all(c["status"] == "ok" for c in results))
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)

    def test_stale_and_missing_metadata_warn_without_leaking_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_fixture(root)
            (root / "private-data" / "state.json").write_text('{"last_success":"2026-10-25"}')
            (root / "exports" / "latest_sync.json").unlink()
            checks = healthcheck.audit(root, today=TODAY, check_launchd=False)
            self.assertEqual([c["status"] for c in checks[-2:]], ["warning", "warning"])
            self.assertNotIn("secret", json.dumps(checks))

    def test_invalid_state_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_fixture(root)
            (root / "private-data" / "state.json").write_text("invalid JSON")
            checks = healthcheck.audit(root, today=TODAY, check_launchd=False)
            self.assertEqual(next(c for c in checks if c["check"] == "sync_state")["status"], "error")

    def test_correct_launchd_schedule(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_fixture(root)
            agent = root / "launchd.plist"
            config = {"Label": "com.local.garmin-auto-coach", "StartCalendarInterval": {"Hour": 7, "Minute": 0},
                      "ProgramArguments": ["/bin/bash", str(root / "scripts" / "run_daily.sh")]}
            agent.write_bytes(plistlib.dumps(config))
            checks = healthcheck.audit(root, agent, today=TODAY)
            self.assertEqual(checks[-1]["status"], "ok")
            config["StartCalendarInterval"]["Hour"] = 8
            agent.write_bytes(plistlib.dumps(config))
            checks = healthcheck.audit(root, agent, today=TODAY)
            self.assertEqual(checks[-1]["status"], "warning")

    def test_future_timestamp_warns(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_fixture(root)
            (root / "exports" / "latest_sync.json").write_text('{"generated_at":"2026-11-07T07:00:00-03:00"}')
            checks = healthcheck.audit(root, today=TODAY, check_launchd=False)
            self.assertEqual(checks[-1]["status"], "warning")

    def test_missing_runner_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.create_fixture(root)
            (root / "scripts" / "run_daily.sh").unlink()
            checks = healthcheck.audit(root, today=TODAY, check_launchd=False)
            self.assertEqual(next(c for c in checks if c["check"] == "daily_runner")["status"], "error")


if __name__ == "__main__":
    unittest.main()
