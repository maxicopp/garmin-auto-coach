"""Transparent, reproducible training analysis; no invented physiological thresholds."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median
from typing import Any

from .core import as_number, is_running

WEEKLY_COLUMNS = [
    'week_start', 'complete', 'sessions', 'distance_km', 'duration_min',
    'ascent_m', 'longest_km', 'long_run_share_pct', 'km_change_vs_previous_pct',
]


def parse_date(row: dict) -> date | None:
    try:
        return date.fromisoformat(str(row.get('date', '')))
    except ValueError:
        return None


def avg(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def get_weekly(rows: list[dict], today: date, weeks: int = 14) -> list[dict]:
    runs = [r for r in rows if is_running(r) and (d := parse_date(r)) and d <= today]
    byweek: dict[date, list[dict]] = defaultdict(list)
    for r in runs:
        d = parse_date(r)
        assert d
        byweek[d - timedelta(days=d.weekday())].append(r)
    this_monday = today - timedelta(days=today.weekday())
    result = []
    for index in reversed(range(weeks)):
        mon = this_monday - timedelta(days=7 * index)
        w = byweek.get(mon, [])
        km = sum(as_number(r.get('distance_km')) or 0 for r in w)
        minutes = sum(as_number(r.get('duration_min')) or 0 for r in w)
        ascent = sum(as_number(r.get('ascent_m')) or 0 for r in w)
        longest = max([as_number(r.get('distance_km')) or 0 for r in w], default=0)
        result.append({
            'week_start': mon.isoformat(), 'complete': mon + timedelta(days=6) < today,
            'sessions': len(w), 'distance_km': round(km, 2), 'duration_min': round(minutes, 1),
            'ascent_m': round(ascent, 0), 'longest_km': round(longest, 2),
            'long_run_share_pct': round(100 * longest / km, 1) if km else None,
            'km_change_vs_previous_pct': None,
        })
    for i in range(1, len(result)):
        current, prev = result[i], result[i - 1]
        if current['complete'] and prev['complete'] and prev['distance_km'] > 0:
            current['km_change_vs_previous_pct'] = round(100 * (current['distance_km'] / prev['distance_km'] - 1), 1)
    return result


def _range_sum(rows: list[dict], start: date, end: date, key: str) -> float:
    return round(sum(as_number(r.get(key)) or 0 for r in rows if is_running(r) and (d := parse_date(r)) and start <= d <= end), 2)


def compute(activities: list[dict], wellness: list[dict], fit_data: list[dict], today: date) -> dict:
    runs = [r for r in activities if is_running(r) and (d := parse_date(r)) and d <= today]
    runs.sort(key=lambda r: (r.get('date') or '', str(r.get('activity_id') or '')))
    weekly = get_weekly(activities, today)
    complete = [r for r in weekly if r['complete']]
    # 4+4 complete weeks, always disclose fewer available historical weeks.
    recent4 = complete[-4:]
    previous4 = complete[-8:-4]
    hist_complete = complete[-8:]
    recent_km = [r['distance_km'] for r in recent4]
    previous_km = [r['distance_km'] for r in previous4]
    recent_long_pct = [r['long_run_share_pct'] for r in recent4 if r['long_run_share_pct'] is not None]
    steep_share_weeks = [r['week_start'] for r in recent4 if r['long_run_share_pct'] is not None and r['long_run_share_pct'] >= 45]
    large_increases = [r['week_start'] for r in hist_complete if r['km_change_vs_previous_pct'] is not None and r['km_change_vs_previous_pct'] > 25]
    weeks_since_start = (today - parse_date(runs[0])).days / 7 if runs else None
    last_7 = today - timedelta(days=6)
    last_28 = today - timedelta(days=27)
    raw_sleep = [as_number(r.get('sleep_hours')) for r in wellness if (d := parse_date(r)) and last_28 <= d <= today]
    sleep = [x for x in raw_sleep if x is not None and x > 0]
    score = [x for r in wellness if (d := parse_date(r)) and last_28 <= d <= today and (x := as_number(r.get('sleep_score'))) is not None]
    hrv = [x for r in wellness if (d := parse_date(r)) and last_28 <= d <= today and (x := as_number(r.get('hrv_last_night_ms'))) is not None]
    statuses = [str(r.get('hrv_status')).upper() for r in wellness if (d := parse_date(r)) and last_28 <= d <= today and r.get('hrv_status')]
    fit_status = defaultdict(int)
    for row in fit_data:
        fit_status[row.get('fit_status') or 'unknown'] += 1
    drift = [r for r in fit_data if as_number(r.get('fit_drift_pct')) is not None]
    best5 = min((r for r in runs if 4.8 <= (as_number(r.get('distance_km')) or 0) <= 5.3 and as_number(r.get('duration_min'))), key=lambda r: as_number(r.get('duration_min')), default=None)
    best10 = min((r for r in runs if 9.8 <= (as_number(r.get('distance_km')) or 0) <= 10.4 and as_number(r.get('duration_min'))), key=lambda r: as_number(r.get('duration_min')), default=None)
    return {
        'reference_date': today.isoformat(), 'activity_count': len(activities), 'run_count': len(runs),
        'total_run_km': round(sum(as_number(r.get('distance_km')) or 0 for r in runs), 2),
        'first_run': parse_date(runs[0]).isoformat() if runs else None,
        'longest_run_km': round(max((as_number(r.get('distance_km')) or 0 for r in runs), default=0), 2),
        'recent7_km': _range_sum(runs, last_7, today, 'distance_km'),
        'recent28_km': _range_sum(runs, last_28, today, 'distance_km'),
        'recent28_ascent_m': _range_sum(runs, last_28, today, 'ascent_m'),
        'weekly': weekly,
        'last4_complete_weeks_count': len(recent4), 'prev4_complete_weeks_count': len(previous4),
        'last4_weekly_avg_km': avg(recent_km), 'previous4_weekly_avg_km': avg(previous_km),
        'last4_weekly_ascent_m': round(sum(r['ascent_m'] for r in recent4), 1),
        'last4_weekly_long_share_avg_pct': avg(recent_long_pct),
        'high_long_run_share_weeks': steep_share_weeks,
        'weekly_jump_gt25_weeks': large_increases,
        'sleep_nights_available_28d': len(sleep), 'sleep_avg_hours_28d': avg(sleep),
        'sleep_below6_nights_28d': sum(1 for x in sleep if x < 6),
        'sleep_score_avg_28d': avg(score), 'hrv_nights_available_28d': len(hrv),
        'hrv_avg_ms_28d': avg(hrv), 'hrv_statuses_28d': dict((s, statuses.count(s)) for s in sorted(set(statuses))),
        'fit_status_counts': dict(fit_status), 'fit_drift_activities': len(drift),
        'fit_drift_values': [{'activity_id': x['activity_id'], 'drift_pct': x['fit_drift_pct']} for x in drift],
        'sample_best_5k': {'date': best5['date'], 'distance_km': as_number(best5['distance_km']), 'minutes': as_number(best5['duration_min'])} if best5 else None,
        'sample_best_10k': {'date': best10['date'], 'distance_km': as_number(best10['distance_km']), 'minutes': as_number(best10['duration_min'])} if best10 else None,
        'caveats': [
            'Kilometraje sólo de running/trail; otras actividades no cuentan como carrera.',
            'La semana actual es parcial y se excluye de comparaciones entre semanas completas.',
            'Los cambios de kilometraje y porcentaje de fondo NO diagnostican riesgo de lesión.',
            'Un resumen de sesión no permite atribuir mejoras de ritmo/FC a eficiencia: terreno, clima y esfuerzo difieren.',
            'HRV se interpreta frente a la línea base personal; no se diagnostica recuperación con un valor aislado.',
            'Deriva FIT sólo se estima con cobertura y terreno suficientes; no equivale a umbral aeróbico.',
            'Sin zonas de FC individuales confirmadas no se asignan zonas de entrenamiento.',
        ],
    }


def md_num(value: Any, digits=1):
    if value is None: return 's/d'
    if isinstance(value, float): return f'{value:.{digits}f}'
    return str(value)


def make_report(m: dict, goals: str) -> str:
    w = m['weekly']
    lines = [
        '# Informe de entrenamiento — Garmin Auto Coach v0.2', '',
        f'**Fecha de corte:** {m["reference_date"]} (Argentina). **Objetivos:** {goals or "No indicados"}.', '',
        '## Resumen', '',
        f'- **{m["run_count"]} sesiones de running/trail**, {m["total_run_km"]:.1f} km acumulados en el período disponible; fondo máximo {m["longest_run_km"]:.2f} km.',
        f'- Últimos 7 días naturales (incluido hoy): **{m["recent7_km"]:.1f} km**; últimos 28 días: **{m["recent28_km"]:.1f} km** y {m["recent28_ascent_m"]:.0f} m D+.',
        f'- Últimas {m["last4_complete_weeks_count"]} semanas completas: **{md_num(m["last4_weekly_avg_km"])} km/semana**; previas {m["prev4_complete_weeks_count"]}: {md_num(m["previous4_weekly_avg_km"])} km/semana.',
        f'- Fondo más largo como fracción del volumen semanal, promedio de últimas semanas completas con kilómetros: {md_num(m["last4_weekly_long_share_avg_pct"])}%.',
        '', '## Volumen, tiempo, desnivel y concentración de fondos', '',
        '| Semana | Estado | Sesiones | km | Min | D+ m | Fondo km | Fondo % | Δ km vs semana anterior |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in w[-10:]:
        lines.append(f'| {r["week_start"]} | {"Completa" if r["complete"] else "PARCIAL"} | {r["sessions"]} | {r["distance_km"]:.1f} | {r["duration_min"]:.0f} | {r["ascent_m"]:.0f} | {r["longest_km"]:.1f} | {md_num(r["long_run_share_pct"])} | {md_num(r["km_change_vs_previous_pct"])} |')
    lines += ['', '## Observaciones verificables', '']
    if m['high_long_run_share_weeks']:
        lines.append('- En semanas recientes el fondo representó al menos **45%** del kilometraje: ' + ', '.join(m['high_long_run_share_weeks']) + '. Esto sugiere distribuir mejor el volumen, no constituye un diagnóstico.')
    if m['weekly_jump_gt25_weeks']:
        lines.append('- Aumentos semanales descriptivos superiores a 25% en: ' + ', '.join(m['weekly_jump_gt25_weeks']) + '. El porcentaje depende mucho de cuán baja fue la semana anterior.')
    if m['recent28_ascent_m'] == 0:
        lines.append('- No hay desnivel positivo registrado en los últimos 28 días; revisar cobertura del dato antes de interpretarlo.')
    elif m['recent28_ascent_m'] < 500:
        lines.append(f'- En 28 días se registran {m["recent28_ascent_m"]:.0f} m D+; para trail es útil incorporar terreno similar a la carrera progresivamente, sujeto a recuperación y acceso a cuestas.')
    if not (m['high_long_run_share_weeks'] or m['weekly_jump_gt25_weeks']):
        lines.append('- Sin alertas descriptivas de distribución de volumen con los criterios de este reporte.')
    lines += [
        '', '## Recuperación y cobertura de datos (últimos 28 días)', '',
        f'- Sueño: **{m["sleep_nights_available_28d"]} noches** con duración registrada (de 28 posibles); media {md_num(m["sleep_avg_hours_28d"])} h; {m["sleep_below6_nights_28d"]} noches con menos de 6 h.',
        f'- Puntaje de sueño medio registrado: {md_num(m["sleep_score_avg_28d"])}.',
        f'- HRV: **{m["hrv_nights_available_28d"]} noches**; media {md_num(m["hrv_avg_ms_28d"])} ms, estados Garmin: {json.dumps(m["hrv_statuses_28d"], ensure_ascii=False)}.',
        'No asumir que noches sin datos equivalen a noches sin dormir; no interpretar HRV con umbrales poblacionales.',
        '', '## Archivos FIT detallados', '',
        'Estado de los FIT: ' + ', '.join(f'{name}: {count}' for name, count in sorted(m['fit_status_counts'].items())) + '.',
    ]
    if m['fit_drift_activities']:
        lines.append(f'- Se calculó deriva estimada Pa:HR en {m["fit_drift_activities"]} sesiones con series suficientemente completas; valores en fit_metrics.csv.')
    else:
        lines.append('- Todavía no hay sesiones elegibles para estimar deriva de pulso/ritmo. No inventar este indicador.')
    lines += [
        '', '## Referencias de rendimiento en este historial (no récords oficiales)', '',
    ]
    for label, key in [('~5 km', 'sample_best_5k'), ('~10 km', 'sample_best_10k')]:
        run = m[key]
        if run:
            lines.append(f'- {label}: {run["distance_km"]:.2f} km en {run["minutes"]:.1f} min ({run["date"]}); no comparable sin nivel de esfuerzo/recorrido.')
        else:
            lines.append(f'- {label}: sin sesión en rango en el historial disponible.')
    lines += ['', '## Reglas para ajustar entrenamientos', '',
              'Evaluar sensaciones (RPE), síntomas, superficies, pendiente, descanso y carga global antes de modificar el plan.',
              'No aumentar volumen/intensidad basándose únicamente en métricas de reloj.',
              'No inferir zona 2 de promedios de FC; se requieren umbrales personales y/o la configuración de zonas.',
              '', '## Limitaciones', '']
    lines += [f'- {c}' for c in m['caveats']]
    return '\n'.join(lines) + '\n'
