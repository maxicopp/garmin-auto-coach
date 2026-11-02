# Garmin Auto Coach

Python application for synchronizing Garmin Connect data, analyzing running and trail-running performance, and generating training reports.

## Features

- Garmin Connect activity synchronization
- Heart rate, HRV, sleep, and Body Battery tracking
- FIT file analysis
- Running and trail-running performance metrics
- Weekly training summaries
- CSV, JSON, and Markdown reports
- Automated daily synchronization on macOS

## Installation

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Configure Garmin API credentials in a local `.env` file.

## Configuration

- `GARMIN_PRIVATE_DIR`: Private activity data directory
- `GARMIN_EXPORT_DIR`: Generated reports directory
- `GARMIN_COACH_GOALS`: Training objectives

## Usage

Check Garmin API connectivity:

    python -m garmin_auto_coach doctor --test-api

Synchronize activities:

    python -m garmin_auto_coach sync --download-originals

Download historical FIT files:

    python -m garmin_auto_coach backfill-originals --limit 50

Generate reports:

    python -m garmin_auto_coach report

Run tests:

    python -m unittest discover -s tests -v

## Generated Reports

- activities.csv
- wellness.csv
- weekly_metrics.csv
- fit_metrics.csv
- laps.csv
- training_metrics.json
- training_analysis.md
- weekly_summary.md
- coach_context.md
- latest_sync.json

## macOS Automation

Install daily synchronization:

    python scripts/install_launchd.py install

Remove daily synchronization:

    python scripts/install_launchd.py uninstall

## Privacy

Credentials, private Garmin data, and generated exports are excluded from Git. Original activity files may contain sensitive GPS information.

## Technologies

- Python
- Garmin Connect Personal API
- fitdecode
- python-dotenv
- macOS launchd
