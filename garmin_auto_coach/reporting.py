"""Pure Markdown rendering for Garmin training reports.

The reference date is required to avoid hidden clock-dependent output.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from .normalization import as_number, is_running


def fmt(value: Any, decimals: int = 1) -> str:
    n = as_number(value)
    return f'{n:.{decimals}f}' if n is not None else 's/d'


def week_summary(rows: list[dict], weeks: int = 8, today: date | None = None) -> str:
    if today is None:
        raise ValueError('reporting.week_summary requires an explicit reference date')
    by_week: dict[date, list[dict]] = defaultdict(list)
    for row in rows:
        if not is_running(row):
            continue
        try:
            d = date.fromisoformat(row['date'])
        except (ValueError, KeyError, TypeError):
            continue
        start = d.fromordinal(d.toordinal() - d.weekday())
        by_week[start].append(row)
    this_monday = date.fromordinal(today.toordinal() - today.weekday())
    lines = [
        '# Resumen de entrenamiento de Garmin',
        '',
        f'Generado el {today.isoformat()}. Semanas: lunes a domingo. Solo actividades de running/trail.',
        'Los datos reflejan únicamente lo registrado y descargado; s/d significa sin datos.',
        '',
        '| Semana (lunes) | Salidas | Kilómetros | Minutos | Desnivel positivo (m) | Fondo máximo (km) |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for idx in reversed(range(weeks)):
        week = date.fromordinal(this_monday.toordinal() - idx * 7)
        w = by_week.get(week, [])
        km = sum(as_number(r.get('distance_km')) or 0 for r in w)
        mins = sum(as_number(r.get('duration_min')) or 0 for r in w)
        climb = sum(as_number(r.get('ascent_m')) or 0 for r in w)
        longest = max((as_number(r.get('distance_km')) or 0 for r in w), default=0)
        lines.append(f'| {week.isoformat()} | {len(w)} | {km:.2f} | {mins:.0f} | {climb:.0f} | {longest:.2f} |')
    lines += ['', '## Notas', '- La semana en curso puede estar incompleta.', '- Sin interpretación médica ni diagnóstico de sobreentrenamiento.', '']
    return '\n'.join(lines)


def coach_context(activities: list[dict], wellness: list[dict], goals: str, today: date | None = None) -> str:
    if today is None:
        raise ValueError('reporting.coach_context requires an explicit reference date')
    last_activities = [r for r in activities if r.get('date') and r['date'] <= today.isoformat()]
    last_activities.sort(key=lambda r: (r.get('date',''), str(r.get('activity_id',''))), reverse=True)
    well = sorted((r for r in wellness if r.get('date')), key=lambda r: r['date'], reverse=True)
    text = [
        '# Contexto para análisis de entrenamientos', '',
        f'Fecha de referencia: {today.isoformat()} (America/Argentina/Buenos_Aires)',
        f'Objetivos declarados: {goals or "No definidos"}', '',
        '## Últimas 12 actividades',
        '| Fecha | Tipo | Distancia km | Minutos | Ritmo min/km | FC media | Desnivel + m |',
        '|---|---|---:|---:|---:|---:|---:|',
    ]
    for a in last_activities[:12]:
        text.append(f"| {a['date']} | {a.get('type','')} | {fmt(a.get('distance_km'),2)} | {fmt(a.get('duration_min'),0)} | {fmt(a.get('pace_min_km'),2)} | {fmt(a.get('average_hr_bpm'),0)} | {fmt(a.get('ascent_m'),0)} |")
    text += ['', '## Recuperación reciente', '| Fecha | Sueño h | Puntuación sueño | HRV anoche ms | HRV estado |', '|---|---:|---:|---:|---|']
    for r in well[:10]:
        text.append(f"| {r['date']} | {fmt(r.get('sleep_hours'),2)} | {fmt(r.get('sleep_score'),0)} | {fmt(r.get('hrv_last_night_ms'),1)} | {r.get('hrv_status') or 's/d'} |")
    text += [
        '', '## Instrucciones sugeridas para el análisis',
        'Evaluá progresión semanal, carga de running, desnivel y recuperación.',
        'No inferir zonas de entrenamiento sin umbrales individuales confirmados.',
        'No diagnosticar lesión ni sobreentrenamiento solo a partir de estas métricas.',
        'Si faltan datos, indicarlo expresamente. Considerar terreno, sensaciones y objetivos.',
        '',
    ]
    return '\n'.join(text)
