#!/usr/bin/env python3
"""Read-only health diagnostics for a local Garmin Auto Coach installation.

Reads configured data-directory values from .env without printing credentials.
Never reads Garmin activity files, FIT archives, or private workout content.
Does not access Garmin, change any files, or print activity identifiers.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
AGENT_NAME = "com.local.garmin-auto-coach.plist"


def result(name: str, status: str, message: str) -> dict[str, str]:
    return {"check": name, "status": status, "message": message}


def check_recent_date(path: Path, field: str, label: str, today: date, *, is_timestamp: bool = False) -> dict[str, str]:
    if not path.is_file():
        return result(label, "warning", "No synchronization metadata found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get(field), str):
            raise ValueError("Expected timestamp field missing")
        raw = payload[field]
        if is_timestamp:
            instant = datetime.fromisoformat(raw)
            if instant.tzinfo is None:
                raise ValueError("Timestamp has no timezone")
            stamp = instant.astimezone(LOCAL_TZ).date()
        else:
            stamp = date.fromisoformat(raw)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return result(label, "error", "Invalid synchronization metadata")
    if stamp > today:
        return result(label, "warning", "Last recorded date is in the future")
    if (today - stamp).days > 2:
        return result(label, "warning", "Last recorded update is older than two days")
    return result(label, "ok", "Recent synchronization metadata available")


def check_agent(agent_path: Path, expected_runner: Path) -> dict[str, str]:
    if not agent_path.is_file():
        return result("launchd", "warning", "Scheduled job is not installed")
    try:
        with agent_path.open("rb") as stream:
            payload = plistlib.load(stream)
        calendar = payload.get("StartCalendarInterval")
        args = payload.get("ProgramArguments")
        valid = (
            payload.get("Label") == "com.local.garmin-auto-coach"
            and isinstance(calendar, dict)
            and calendar.get("Hour") == 7
            and calendar.get("Minute") == 0
            and isinstance(args, list)
            and len(args) == 2
            and args[0] == "/bin/bash"
            and Path(args[1]).expanduser().resolve() == expected_runner.resolve()
        )
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException):
        return result("launchd", "error", "Scheduled job file could not be parsed")
    if not valid:
        return result("launchd", "warning", "Scheduled job differs from the expected 07:00 runner")
    return result("launchd", "ok", "07:00 scheduled job points to this project")



def configured_data_directories(root: Path) -> tuple[Path, Path]:
    """Resolve the same directory settings used by the CLI without printing values.

    The runner changes the working directory to the repository root. Relative
    values from .env are therefore resolved against that root.
    """
    import os
    from dotenv import dotenv_values

    settings = dotenv_values(root / ".env") if (root / ".env").is_file() else {}

    def directory(name: str, fallback: str) -> Path:
        value = os.environ[name] if name in os.environ else settings.get(name)
        path = Path(fallback if value is None else value).expanduser()
        return path if path.is_absolute() else root / path

    return directory("GARMIN_PRIVATE_DIR", "private-data"), directory("GARMIN_EXPORT_DIR", "exports")


def check_agent_loaded() -> dict[str, str]:
    """Query the user's launchd registry, without displaying command output."""
    try:
        completed = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/com.local.garmin-auto-coach"],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return result("launchd_loaded", "warning", "Could not inspect active launchd registration")
    if completed.returncode:
        return result("launchd_loaded", "warning", "Scheduled job is not loaded in this user session")
    return result("launchd_loaded", "ok", "Scheduled job is registered with launchd")


def audit(root: Path, agent_path: Path | None = None, today: date | None = None, *, check_launchd: bool = True) -> list[dict[str, str]]:
    root = root.expanduser().resolve()
    today = today or datetime.now(LOCAL_TZ).date()
    private_dir, export_dir = configured_data_directories(root)
    checks = [
        result("credentials_file", "ok" if (root / ".env").is_file() else "warning",
               "Local configuration file is present" if (root / ".env").is_file() else "Local configuration file is missing"),
        result("python_environment", "ok" if (root / ".venv" / "bin" / "python").is_file() else "warning",
               "Python environment is present" if (root / ".venv" / "bin" / "python").is_file() else "Python environment is missing"),
        result("daily_runner", "ok" if (root / "scripts" / "run_daily.sh").is_file() else "error",
               "Daily runner is present" if (root / "scripts" / "run_daily.sh").is_file() else "Daily runner is missing"),
        check_recent_date(private_dir / "state.json", "last_success", "sync_state", today),
        check_recent_date(export_dir / "latest_sync.json", "generated_at", "exports", today, is_timestamp=True),
    ]
    if check_launchd:
        agent = agent_path or Path.home() / "Library" / "LaunchAgents" / AGENT_NAME
        checks.append(check_agent(agent, root / "scripts" / "run_daily.sh"))
        if sys.platform == "darwin" and agent_path is None:
            checks.append(check_agent_loaded())
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect local Garmin Auto Coach health without accessing Garmin")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--launch-agent", type=Path, default=None)
    parser.add_argument("--skip-launchd", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable status report")
    args = parser.parse_args(argv)
    check_launchd = not args.skip_launchd and (sys.platform == "darwin" or args.launch_agent is not None)
    checks = audit(args.project_root, args.launch_agent, check_launchd=check_launchd)
    if args.json:
        print(json.dumps({"checks": checks}, indent=2, sort_keys=True))
    else:
        for check in checks:
            print(f"{check['status'].upper():7} {check['check']}: {check['message']}")
    if any(c["status"] == "error" for c in checks):
        return 2
    return 1 if any(c["status"] == "warning" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
