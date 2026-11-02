"""Read-only runtime health tests, with synthetic files and mocked launchctl."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "healthcheck.py"
spec = importlib.util.spec_from_file_location("garmin_runtime_healthcheck", MODULE)
healthcheck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(healthcheck)
DAY = date(2026, 11, 2)


class RuntimeHealthcheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="garmin-runtime-health-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "run_daily.sh").touch()
        (self.root / ".venv" / "bin").mkdir(parents=True)
        (self.root / ".venv" / "bin" / "python").touch()

    def metadata(self, private: Path, exports: Path):
        private.mkdir(parents=True, exist_ok=True)
        exports.mkdir(parents=True, exist_ok=True)
        (private / "state.json").write_text('{"last_success":"2026-11-02"}')
        (exports / "latest_sync.json").write_text('{"generated_at":"2026-11-02T07:00:00-03:00"}')

    def test_dotenv_data_paths_are_honored_without_exposing_secrets(self):
        (self.root / ".env").write_text(
            "GARMIN_PRIVATE_DIR=alternate-private\nGARMIN_EXPORT_DIR=alternate-exports\nGARMIN_API_KEY=SECRET_NOT_FOR_OUTPUT\n"
        )
        self.metadata(self.root / "alternate-private", self.root / "alternate-exports")
        with patch.dict(os.environ, {}, clear=True):
            checks = healthcheck.audit(self.root, today=DAY, check_launchd=False)
        self.assertTrue(all(c["status"] == "ok" for c in checks))
        self.assertNotIn("SECRET_NOT_FOR_OUTPUT", json.dumps(checks))
        self.assertNotIn(str(self.root), json.dumps(checks))

    def test_environment_overrides_dotenv_for_both_paths(self):
        (self.root / ".env").write_text("GARMIN_PRIVATE_DIR=missing-private\nGARMIN_EXPORT_DIR=missing-exports\n")
        self.metadata(self.root / "env-private", self.root / "env-exports")
        with patch.dict(os.environ, {
            "GARMIN_PRIVATE_DIR": str(self.root / "env-private"),
            "GARMIN_EXPORT_DIR": str(self.root / "env-exports"),
        }):
            checks = healthcheck.audit(self.root, today=DAY, check_launchd=False)
        self.assertEqual([c["status"] for c in checks if c["check"] in ("sync_state", "exports")], ["ok", "ok"])

    def test_default_data_paths_remain_compatible(self):
        (self.root / ".env").write_text("FAKE_TOKEN=DO_NOT_PRINT\n")
        self.metadata(self.root / "private-data", self.root / "exports")
        with patch.dict(os.environ, {}, clear=True):
            paths = healthcheck.configured_data_directories(self.root)
        self.assertEqual(paths, (self.root / "private-data", self.root / "exports"))

    def test_loaded_launchd_registration_and_silent_output(self):
        success = subprocess.CompletedProcess(args=[], returncode=0, stdout="TOKEN=SECRET", stderr="")
        with patch.object(healthcheck.subprocess, "run", return_value=success) as call:
            with patch.object(healthcheck.os, "getuid", return_value=501):
                result = healthcheck.check_agent_loaded()
        self.assertEqual(result["status"], "ok")
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(call.call_args.args[0], ["launchctl", "print", "gui/501/com.local.garmin-auto-coach"])
        self.assertTrue(call.call_args.kwargs["capture_output"])

    def test_unloaded_or_unavailable_launchd_is_warning(self):
        not_loaded = subprocess.CompletedProcess(args=[], returncode=113, stdout="", stderr="not found")
        with patch.object(healthcheck.subprocess, "run", return_value=not_loaded):
            self.assertEqual(healthcheck.check_agent_loaded()["status"], "warning")
        with patch.object(healthcheck.subprocess, "run", side_effect=FileNotFoundError()):
            self.assertEqual(healthcheck.check_agent_loaded()["status"], "warning")

    def test_explicit_test_agent_does_not_query_real_launchd(self):
        import plistlib
        runner = self.root / "scripts" / "run_daily.sh"
        config = {"Label": "com.local.garmin-auto-coach", "StartCalendarInterval": {"Hour": 7, "Minute": 0},
                  "ProgramArguments": ["/bin/bash", str(runner)]}
        agent = self.root / "test-agent.plist"
        agent.write_bytes(plistlib.dumps(config))
        self.metadata(self.root / "private-data", self.root / "exports")
        (self.root / ".env").touch()
        with patch.dict(os.environ, {}, clear=True), patch.object(healthcheck.sys, "platform", "darwin"):
            with patch.object(healthcheck, "check_agent_loaded") as live:
                checks = healthcheck.audit(self.root, agent, today=DAY)
        live.assert_not_called()
        self.assertEqual(checks[-1]["check"], "launchd")


if __name__ == "__main__":
    unittest.main()
