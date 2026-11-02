"""Pure normalization of Garmin activities and wellness responses.

The numeric conversions, fallback order, and output schemas are unchanged.
"""
from __future__ import annotations

import re
from typing import Any


def find_key(obj: Any, *keys: str) -> Any:
    """Case-sensitive lookup on a limited tree; never invent a metric."""
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] is not None:
                return obj[key]
        for value in obj.values():
            if isinstance(value, dict):
                found = find_key(value, *keys)
                if found is not None:
                    return found
    return None


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
        if out == float('inf') or out == float('-inf') or out != out:
            return None
        return out
    except (ValueError, TypeError):
        return None


def rounded(value: Any, digits: int = 1) -> float | None:
    val = as_number(value)
    return round(val, digits) if val is not None else None


def iso_date(value: Any) -> str:
    if isinstance(value, str):
        m = re.match(r'^\d{4}-\d{2}-\d{2}', value)
        if m:
            return m.group()
    return ''


def activity_kind(summary: dict, detail: dict) -> str:
    tp = summary.get('activityType') or detail.get('activityType') or {}
    if isinstance(tp, dict):
        return str(tp.get('typeKey') or tp.get('typeName') or 'unknown')
    return str(tp)


def activity_row(item: dict) -> dict:
    summary = item.get('search') or {}
    detail = item.get('detail') or {}
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(detail, dict):
        detail = {}
    # Search endpoint returns summary DTO, detail usually holds summaryDTO.
    dt_summary = detail.get('summaryDTO') if isinstance(detail.get('summaryDTO'), dict) else {}
    merged = {**summary, **dt_summary}
    activity_id = summary.get('activityId') or detail.get('activityId') or ''
    seconds = as_number(find_key(merged, 'duration', 'elapsedDuration'))
    moving = as_number(find_key(merged, 'movingDuration'))
    distance = as_number(find_key(merged, 'distance'))
    speed = as_number(find_key(merged, 'averageSpeed'))
    pace = 1000 / speed / 60 if speed and speed > 0 else (
        (moving or seconds) / (distance / 1000) / 60 if distance and distance > 0 and (moving or seconds) else None
    )
    timestamp = summary.get('startTimeLocal') or detail.get('startTimeLocal') or summary.get('startTimeGMT') or ''
    return {
        'date': iso_date(timestamp),
        'activity_id': activity_id,
        'name': summary.get('activityName') or detail.get('activityName') or '',
        'type': activity_kind(summary, detail),
        'distance_km': rounded(distance / 1000, 3) if distance is not None else None,
        'duration_min': rounded(seconds / 60, 1) if seconds is not None else None,
        'moving_min': rounded(moving / 60, 1) if moving is not None else None,
        'pace_min_km': rounded(pace, 2),
        'average_hr_bpm': rounded(find_key(merged, 'averageHR', 'averageHeartRate'), 0),
        'max_hr_bpm': rounded(find_key(merged, 'maxHR', 'maxHeartRate'), 0),
        'ascent_m': rounded(find_key(merged, 'elevationGain', 'totalAscent'), 0),
        'descent_m': rounded(find_key(merged, 'elevationLoss', 'totalDescent'), 0),
        'average_cadence_spm': rounded(find_key(merged, 'avgRunningCadenceInStepsPerMinute', 'averageRunningCadenceInStepsPerMinute', 'averageRunCadence'), 0),
        'aerobic_te': rounded(find_key(merged, 'aerobicTrainingEffect'), 1),
        'anaerobic_te': rounded(find_key(merged, 'anaerobicTrainingEffect'), 1),
        'average_power_w': rounded(find_key(merged, 'avgPower', 'averagePower'), 0),
    }


def wellness_row(item: dict) -> dict:
    sleep = item.get('sleep') or {}
    hrv = item.get('hrv') or {}
    battery = item.get('body_battery') or {}
    sleep_dto = sleep.get('dailySleepDTO', sleep) if isinstance(sleep, dict) else {}
    if not isinstance(sleep_dto, dict):
        sleep_dto = {}
    hrv_summary = hrv.get('hrvSummary', hrv) if isinstance(hrv, dict) else {}
    if not isinstance(hrv_summary, dict):
        hrv_summary = {}
    score = find_key(sleep_dto, 'overallSleepScore', 'sleepScore')
    sleep_scores = sleep.get('sleepScores') if isinstance(sleep, dict) else None
    if not isinstance(sleep_scores, dict):
        sleep_scores = sleep_dto.get('sleepScores')
    if score is None and isinstance(sleep_scores, dict):
        overall = sleep_scores.get('overall') or sleep_scores.get('overallScore')
        score = overall.get('value', overall.get('score')) if isinstance(overall, dict) else overall
    if isinstance(score, dict):
        score = score.get('value') or score.get('score')
    if score is None and isinstance(sleep, dict):
        score = find_key(sleep, 'overallSleepScore', 'sleepScore')
        if isinstance(score, dict):
            score = score.get('value') or score.get('score')
    total_seconds = as_number(find_key(sleep_dto, 'sleepTimeSeconds', 'totalSleepSeconds'))
    # No fallback to time in bed: it is not equivalent to sleep duration.
    bb = battery[0] if isinstance(battery, list) and battery and isinstance(battery[0], dict) else battery
    return {
        'date': item.get('date', ''),
        'sleep_hours': rounded(total_seconds / 3600, 2) if total_seconds is not None else None,
        'sleep_score': rounded(score, 0),
        'hrv_last_night_ms': rounded(find_key(hrv_summary, 'lastNightAvg'), 1),
        'hrv_weekly_avg_ms': rounded(find_key(hrv_summary, 'weeklyAvg'), 1),
        'hrv_status': hrv_summary.get('status') or '',
        'body_battery_charged': rounded(find_key(bb, 'chargedValue'), 0),
        'body_battery_drained': rounded(find_key(bb, 'drainedValue'), 0),
    }


def is_running(row: dict) -> bool:
    kind = str(row.get('type') or '').lower()
    return 'running' in kind or kind in {'run', 'trail_run', 'trailrunning'}
