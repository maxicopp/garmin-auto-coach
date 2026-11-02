"""Incremental sync against Garmin's official Personal API Python client."""
from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .core import atomic_json, digest, generate_exports, json_file, local_today


def extract_activities(response: Any) -> list[dict]:
    if isinstance(response, list):
        return [x for x in response if isinstance(x, dict)]
    if isinstance(response, dict):
        for field in ('activities', 'results', 'data'):
            if isinstance(response.get(field), list):
                return [x for x in response[field] if isinstance(x, dict)]
    raise ValueError('Garmin devolvió un formato inesperado al consultar actividades')


def fetch_activities(client: Any, start_date: date, end_date: date, page_size: int = 50, pause: float = 0.15):
    offset = 0
    while True:
        response = client.search_activities(
            start=offset, limit=page_size,
            start_date=start_date.isoformat(), end_date=end_date.isoformat(),
        )
        page = extract_activities(response)
        for item in page:
            yield item
        if len(page) < page_size:
            break
        offset += len(page)
        if offset > 10000:
            raise RuntimeError('Más de 10.000 actividades en la ventana: reducí --initial-days')
        if pause:
            time.sleep(pause)


def sync_activities(client: Any, private_dir: Path, start_date: date, end_date: date,
                    originals: bool, pause: float = 0.15) -> tuple[int, int, int]:
    directory = private_dir / 'activities'
    directory.mkdir(parents=True, exist_ok=True)
    total = new_or_changed = originals_count = 0
    for summary in fetch_activities(client, start_date, end_date, pause=pause):
        activity_id = summary.get('activityId')
        if not isinstance(activity_id, int) or activity_id <= 0:
            print(f'Advertencia: actividad sin ID numérico válido: {activity_id!r}; se omite')
            continue
        total += 1
        path = directory / f'{activity_id}.json'
        summary_digest = digest(summary)
        old = json_file(path) if path.exists() else None
        if old is None or old.get('search_digest') != summary_digest:
            if pause:
                time.sleep(pause)
            detail = client.get_activity(activity_id)
            atomic_json(path, {'search': summary, 'detail': detail, 'search_digest': summary_digest})
            new_or_changed += 1
        if originals:
            originals_dir = private_dir / 'originals'
            original_path = originals_dir / f'{activity_id}.zip'
            if not original_path.exists():
                if pause:
                    time.sleep(pause)
                try:
                    import io
                    import zipfile
                    from .fit_analysis import MAX_ZIP_BYTES
                    raw = client.download_activity(activity_id)
                    if not isinstance(raw, bytes) or len(raw) > MAX_ZIP_BYTES or not zipfile.is_zipfile(io.BytesIO(raw)):
                        raise ValueError('ZIP no válido')
                    originals_dir.mkdir(parents=True, exist_ok=True)
                    temp = original_path.with_suffix('.zip.tmp')
                    try:
                        temp.write_bytes(raw)
                        temp.replace(original_path)
                    finally:
                        temp.unlink(missing_ok=True)
                    originals_count += 1
                except Exception as err:
                    print(f'Advertencia: no se pudo descargar ZIP de actividad {activity_id}: {type(err).__name__}')
    return total, new_or_changed, originals_count



def backfill_originals(client: Any, private_dir: Path, *, limit: int = 500,
                       pause: float = 0.2) -> dict:
    """Fetch original ZIP for cached activities (without re-querying their summaries).

    Per-activity failures remain private and do not block others. No raw data
    is sent to export_dir. Existing downloads are left untouched.
    """
    import zipfile
    import io
    from .fit_analysis import MAX_ZIP_BYTES
    entries = sorted((private_dir / 'activities').glob('*.json'))
    if not entries:
        raise ValueError('No hay actividades almacenadas. Ejecutá sync antes.')
    originals_dir = private_dir / 'originals'
    originals_dir.mkdir(parents=True, exist_ok=True)
    attempted = success = already = 0
    failed_ids: list[str] = []
    for path in entries:
        if not path.stem.isdecimal():
            continue
        target = originals_dir / f'{path.stem}.zip'
        if target.exists():
            already += 1
            continue
        if attempted >= limit:
            break
        attempted += 1
        try:
            raw = client.download_activity(int(path.stem))
            if not isinstance(raw, bytes) or len(raw) > MAX_ZIP_BYTES or not zipfile.is_zipfile(io.BytesIO(raw)):
                raise ValueError('Descarga sin ZIP válido')
            # Atomic write of potentially sensitive GPS data.
            target_tmp = target.with_suffix('.zip.tmp')
            try:
                target_tmp.write_bytes(raw)
                target_tmp.replace(target)
            finally:
                target_tmp.unlink(missing_ok=True)
            success += 1
        except Exception as error:
            failed_ids.append(path.stem)
            print(f'Advertencia: FIT original no disponible para ID {path.stem} ({type(error).__name__})')
        if pause:
            time.sleep(pause)
    print(f'Backfill ZIP: nuevos {success}, existentes {already}, fallidos {len(failed_ids)}')
    return {'downloaded': success, 'existing': already, 'attempted': attempted, 'failed': len(failed_ids)}


def sync_wellness(client: Any, private_dir: Path, start_date: date, end_date: date,
                  pause: float = 0.15) -> int:
    wellness_dir = private_dir / 'wellness'
    wellness_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    day = start_date
    while day <= end_date:
        path = wellness_dir / f'{day.isoformat()}.json'
        record = {'date': day.isoformat()}
        tasks = (
            ('sleep', lambda: client.get_daily_sleep(day.isoformat())),
            ('hrv', lambda: client.get_daily_hrv(day.isoformat())),
            ('body_battery', lambda: client.get_daily_body_battery(day.isoformat(), day.isoformat())),
        )
        for field, operation in tasks:
            try:
                record[field] = operation()
            except Exception as error:
                # Preserve previously fetched data instead of overwriting it with an error.
                if path.exists():
                    record[field] = json_file(path).get(field)
                print(f'Advertencia [{day.isoformat()} / {field}]: {type(error).__name__}: {error}')
            if pause:
                time.sleep(pause)
        atomic_json(path, record)
        count += 1
        day += timedelta(days=1)
    return count


def run_sync(client: Any, private_dir: Path, export_dir: Path, *,
             initial_days: int = 90, lookback_days: int = 14, wellness_days: int = 14,
             originals: bool = False, goals: str = '', since: date | None = None,
             today: date | None = None, pause: float = 0.15) -> dict:
    if any(x < 1 for x in (initial_days, lookback_days, wellness_days)):
        raise ValueError('Los períodos deben ser mayores a cero')
    today = today or local_today()
    private_dir.mkdir(parents=True, exist_ok=True)
    state_path = private_dir / 'state.json'
    state = json_file(state_path) if state_path.exists() else {}
    if since:
        activities_start = since
    elif state.get('last_success'):
        last = date.fromisoformat(state['last_success'])
        # Revisit a few days for activities updated after first upload.
        activities_start = min(last - timedelta(days=lookback_days - 1), today)
    else:
        activities_start = today - timedelta(days=initial_days - 1)
    wellness_start = today - timedelta(days=wellness_days - 1)
    print(f'Actividades: {activities_start} → {today}')
    total, changed, downloaded = sync_activities(client, private_dir, activities_start, today, originals, pause)
    print(f'Actividades encontradas: {total}; nuevas/modificadas: {changed}; ZIP originales: {downloaded}')
    print(f'Recuperación: {wellness_start} → {today}')
    health_count = sync_wellness(client, private_dir, wellness_start, today, pause)
    report = generate_exports(private_dir, export_dir, goals=goals, today=today)
    atomic_json(state_path, {'last_success': today.isoformat(), 'last_activity_window_start': activities_start.isoformat()})
    print(f'Exportación generada en: {export_dir.resolve()}')
    return {**report, 'wellness_days_checked': health_count, 'new_or_changed': changed}
