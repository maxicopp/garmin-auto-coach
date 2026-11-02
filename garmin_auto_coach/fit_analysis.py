"""GPS-free summary extraction from official Garmin ZIP exports containing .FIT files.

Never extracts members to filesystem. Only aggregated HR/speed/cadence/laps are exported.
The original ZIP stays in the private directory. Do not treat these as medical data.
"""
from __future__ import annotations

import io
import math
import zipfile
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

# Guard against unexpectedly large or malicious ZIP members.
MAX_ZIP_BYTES = 80 * 1024 * 1024
MAX_FIT_BYTES = 60 * 1024 * 1024
MAX_MEMBERS = 30

FIT_FIELDS = [
    'activity_id', 'fit_status', 'fit_records', 'fit_duration_min',
    'fit_hr_coverage_pct', 'fit_moving_hr_samples', 'fit_laps',
    'fit_mean_hr_bpm', 'fit_median_cadence_spm',
    'fit_drift_pct', 'fit_drift_note',
]
LAP_FIELDS = ['activity_id', 'lap_index', 'duration_min', 'distance_km',
              'average_hr_bpm', 'max_hr_bpm', 'ascent_m', 'pace_min_km']


def valid_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _field(frame: Any, name: str) -> Any:
    try:
        return frame.get_value(name)
    except (KeyError, ValueError, AttributeError, TypeError):
        return None


def _fit_bytes(archive: Path) -> bytes | None:
    if archive.stat().st_size > MAX_ZIP_BYTES:
        raise ValueError('ZIP demasiado grande')
    with zipfile.ZipFile(archive, 'r') as zf:
        members = zf.infolist()
        if len(members) > MAX_MEMBERS:
            raise ValueError('Demasiados elementos en ZIP')
        for member in members:
            if not member.is_dir() and member.filename.lower().endswith('.fit'):
                if member.file_size > MAX_FIT_BYTES:
                    raise ValueError('FIT demasiado grande')
                # no extract(); bounded read, no untrusted path use
                with zf.open(member) as fh:
                    data = fh.read(MAX_FIT_BYTES + 1)
                if len(data) > MAX_FIT_BYTES:
                    raise ValueError('FIT excede máximo permitido')
                return data
    return None


def _analyze_points(points: list[dict]) -> dict:
    """Return conservative Pa:HR drift for steady, continuous road runs.

    Positive drift = lower velocity/heart-rate ratio in the second half.
    Exclude slow/walking/stopped periods and sampling gaps > 10 s.
    This is a *description* not a fitness or risk diagnosis.
    """
    clean = sorted((p for p in points if isinstance(p.get('time'), datetime)), key=lambda p: p['time'])
    if len(clean) < 60:
        return {'drift': None, 'note': 'Datos temporales insuficientes'}
    samples: list[tuple[float, float, float, float]] = []
    start = clean[0]['time']
    for i, p in enumerate(clean[:-1]):
        try:
            dt = (clean[i + 1]['time'] - p['time']).total_seconds()
            t = (p['time'] - start).total_seconds()
        except (TypeError, ValueError):
            continue
        hr = valid_float(p.get('hr'))
        speed = valid_float(p.get('speed'))
        if not 0 < dt <= 10 or hr is None or speed is None:
            continue
        if 75 <= hr <= 210 and 1.35 <= speed <= 6.5:
            samples.append((t, dt, hr, speed))
    if not samples:
        return {'drift': None, 'note': 'Sin pares válidos de FC y velocidad'}
    total_duration = (clean[-1]['time'] - start).total_seconds()
    # All activity samples; ignore initial 10 min for warm-up, require >= 45m thereafter.
    if total_duration < 55 * 60:
        return {'drift': None, 'note': 'Sesión menor a 55 min'}
    after = [s for s in samples if s[0] >= 600]
    if sum(s[1] for s in after) < 0.7 * (total_duration - 600):
        return {'drift': None, 'note': 'FC/velocidad o movimiento insuficiente'}
    midpoint = (total_duration + 600) / 2
    first, second = [s for s in after if s[0] < midpoint], [s for s in after if s[0] >= midpoint]

    def ratio(xs):
        weight = sum(x[1] for x in xs)
        if weight < 15 * 60:
            return None
        hr = sum(x[1] * x[2] for x in xs) / weight
        speed = sum(x[1] * x[3] for x in xs) / weight
        return speed / hr if hr else None

    a, b = ratio(first), ratio(second)
    if not a or not b:
        return {'drift': None, 'note': 'Mitades incompletas'}
    return {'drift': round(100 * (a - b) / a, 1), 'note': 'Estimación Pa:HR; interpretar solo en terreno estable'}


def summarize_fit(archive: Path, activity_id: str | int, *, is_road_run: bool = False,
                  ascent_m: float | None = None) -> tuple[dict, list[dict]]:
    base = {k: None for k in FIT_FIELDS}
    base.update(activity_id=str(activity_id), fit_status='unknown', fit_laps=0)
    try:
        raw = _fit_bytes(archive)
        if raw is None:
            base.update(fit_status='no_fit', fit_drift_note='ZIP sin archivo FIT')
            return base, []
        try:
            import fitdecode
        except ImportError:
            base.update(fit_status='missing_fitdecode', fit_drift_note='Instalar fitdecode')
            return base, []
        points: list[dict] = []
        laps: list[dict] = []
        hr_count = 0
        cadences = []
        with fitdecode.FitReader(io.BytesIO(raw)) as reader:
            for frame in reader:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                    continue
                if frame.name == 'record':
                    if len(points) >= 250000:
                        raise ValueError('Demasiados registros FIT')
                    timestamp = _field(frame, 'timestamp')
                    hr = valid_float(_field(frame, 'heart_rate'))
                    speed = valid_float(_field(frame, 'enhanced_speed'))
                    if speed is None:
                        speed = valid_float(_field(frame, 'speed'))
                    cad = valid_float(_field(frame, 'cadence'))
                    # FIT may encode running cadence as strides/min. Manufacturer varies;
                    # do not multiply until proven whether field means steps or strides.
                    if cad is not None and 0 < cad < 300:
                        cadences.append(cad)
                    if hr is not None:
                        hr_count += 1
                    points.append({'time': timestamp, 'hr': hr, 'speed': speed})
                elif frame.name == 'lap':
                    elapsed = valid_float(_field(frame, 'total_timer_time'))
                    dist = valid_float(_field(frame, 'total_distance'))
                    sp = valid_float(_field(frame, 'avg_speed'))
                    if sp is None:
                        sp = valid_float(_field(frame, 'enhanced_avg_speed'))
                    laps.append({
                        'activity_id': str(activity_id), 'lap_index': len(laps) + 1,
                        'duration_min': round(elapsed / 60, 2) if elapsed is not None else None,
                        'distance_km': round(dist / 1000, 3) if dist is not None else None,
                        'average_hr_bpm': valid_float(_field(frame, 'avg_heart_rate')),
                        'max_hr_bpm': valid_float(_field(frame, 'max_heart_rate')),
                        'ascent_m': valid_float(_field(frame, 'total_ascent')),
                        'pace_min_km': round(1000 / (sp * 60), 2) if sp and sp > 0 else None,
                    })
        times = sorted(p['time'] for p in points if isinstance(p['time'], datetime))
        duration = (times[-1] - times[0]).total_seconds() / 60 if len(times) > 1 else None
        drift_info = {'drift': None, 'note': 'Requiere running en terreno relativamente llano'}
        if is_road_run and (ascent_m is not None and ascent_m <= 12 * (duration / 10 if duration else 0)):
            drift_info = _analyze_points(points)
        elif is_road_run:
            drift_info['note'] = 'Desnivel alto o no disponible; no comparar Pa:HR'
        hr_values = [p['hr'] for p in points if p['hr'] is not None]
        base.update(
            fit_status='ok', fit_records=len(points), fit_duration_min=round(duration, 1) if duration else None,
            fit_hr_coverage_pct=round(100 * hr_count / len(points), 1) if points else None,
            fit_moving_hr_samples=sum(1 for p in points if p['hr'] is not None and p['speed'] and p['speed'] > 1.35),
            fit_laps=len(laps), fit_mean_hr_bpm=round(sum(hr_values) / len(hr_values), 1) if hr_values else None,
            fit_median_cadence_spm=round(median(cadences), 1) if cadences else None,
            fit_drift_pct=drift_info['drift'], fit_drift_note=drift_info['note'],
        )
        return base, laps
    except Exception as exc:
        base.update(fit_status='parse_error', fit_drift_note=f'{type(exc).__name__}: no se pudo analizar FIT')
        return base, []


def fit_reports(private_dir: Path, activities: list[dict]) -> tuple[list[dict], list[dict]]:
    # Cache aggregate FIT findings across daily runs; version increment invalidates it.
    import json
    from .core import atomic_json
    cache_dir = private_dir / 'fit-cache-v02'
    cache_dir.mkdir(parents=True, exist_ok=True)
    results, laps = [], []
    for row in activities:
        activity_id = str(row.get('activity_id') or '')
        archive = private_dir / 'originals' / f'{activity_id}.zip'
        if not archive.exists():
            results.append({'activity_id': activity_id, 'fit_status': 'not_downloaded'})
            continue
        sig = f'{archive.stat().st_size}:{archive.stat().st_mtime_ns}:{row.get("type")}:{row.get("ascent_m")}'
        cache = cache_dir / f'{activity_id}.json'
        cached = None
        if cache.exists():
            try:
                cached = json.loads(cache.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
        if cached and cached.get('signature') == sig:
            out, lap_rows = cached['summary'], cached['laps']
        else:
            kind = str(row.get('type') or '').lower()
            is_road = kind in {'running', 'run'}
            out, lap_rows = summarize_fit(archive, activity_id, is_road_run=is_road, ascent_m=valid_float(row.get('ascent_m')))
            if out['fit_status'] != 'missing_fitdecode':
                atomic_json(cache, {'signature': sig, 'summary': out, 'laps': lap_rows})
        results.append(out)
        laps.extend(lap_rows)
    return results, laps
