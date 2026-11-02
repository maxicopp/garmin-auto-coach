# Garmin Auto Coach v0.2 — análisis de running/trail y recuperación

Evolución del proyecto original. Funciona con la **Garmin Connect Personal API** oficial y conserva los datos de entrenamientos y recuperación en el equipo. No accede directamente a ChatGPT: los informes se consultan a través de archivos locales o Google Drive autorizado.

## Actualizar tu instalación existente en Mac (sin perder historial)

El proyecto ya instalado en `~/Projects/garmin-auto-coach` tiene tu clave `.env`, 42 actividades y el job macOS. **No lo reemplaces completo ni copies tu `.env` al chat**.

1. Descomprimí `garmin-auto-coach-v0.2.zip`, por ejemplo en Descargas.
2. Desde Terminal, ingresá en la carpeta descomprimida y ejecutá:

```bash
cd ~/Downloads/garmin-auto-coach-v0.2
bash scripts/upgrade_existing.sh
```

Si tu carpeta está en otro lugar: `bash scripts/upgrade_existing.sh /RUTA/A/tu/garmin-auto-coach`.

El instalador crea una copia del **código** anterior, copia el código actualizado, instala `fitdecode`, corre las pruebas y regenera los reportes usando los datos existentes. **No modifica `.env`, `private-data` ni tu historial original**. La tarea de las 07:00 sigue apuntando al mismo `scripts/run_daily.sh`, ahora con `--download-originals` para nuevos entrenamientos.

## Descargar los FIT históricos (una sola vez)

La exportación anterior tenía 42 actividades pero **cero archivos originales**. Con la API oficial ya autorizada, ejecutá:

```bash
cd ~/Projects/garmin-auto-coach
source .venv/bin/activate
python -m garmin_auto_coach backfill-originals --limit 50
```

Este comando busca las actividades ya guardadas, descarga sus ZIP originales (cuando Garmin los ofrece), los deja exclusivamente en `private-data/originals/`, crea un caché local de métricas sin GPS y actualiza `exports`.

Si alguna descarga falla, deja las demás disponibles y muestra un aviso. Volvé a ejecutar el comando después: salta ZIP existentes. Descargas y parsing de FIT pueden tardar más que la sincronización de promedios.

## Nuevos informes en `exports`

| Archivo | Propósito |
|---|---|
| `training_analysis.md` | Informe completo con hallazgos, cobertura y advertencias |
| `training_metrics.json` | Métricas reproducibles para otros agentes o dashboards |
| `weekly_metrics.csv` | Volumen, frecuencia, minutos, D+, fondos, variación semanal, semanas parciales |
| `fit_metrics.csv` | Por actividad: cobertura FC, cantidad de registros, laps y deriva Pa:HR elegible |
| `laps.csv` | Vueltas detectadas en FIT sin puntos GPS |
| `activities.csv` | Actividades normalizadas (se mantiene) |
| `wellness.csv` | Sueño y HRV (se mantiene) |
| `coach_context.md`, `weekly_summary.md`, `latest_sync.json` | Compatibilidad con análisis anteriores |

**Importante:** `fit_drift_pct` es una *estimación* para carreras en ruta mayormente llanas, con FC y velocidad de calidad y al menos 55 min. Es descriptiva, no estima el umbral, no es válida para rutas onduladas, ni debe usarse sola para decidir intensidad. Si faltan datos, aparece vacío y la causa en `fit_drift_note`. `fit_median_cadence_spm` refleja el campo cadence tal cual FIT, que puede representar pasos o zancadas dependiendo del dispositivo: no debe usarse como cadencia de pasos confirmada sin verificar la escala.

La salida nunca incluye latitud/longitud ni puntos GPS, pero los archivos originales en `private-data` **sí pueden contener rutas sensibles** y no deben subirse a Drive. Las fechas, IDs y títulos de las actividades también son información personal.

## Uso cotidiano

```bash
# Sincronizar y descargar originales nuevos (también lo hace el job de las 07:00)
python -m garmin_auto_coach sync --download-originals

# Recalcular informes sin usar red
python -m garmin_auto_coach report

# Verificar API (no muestra la clave)
python -m garmin_auto_coach doctor --test-api

# Probar sin conexión ni credenciales
python -m unittest discover -s tests -v
```

Las salidas pueden copiarse a Google Drive mediante `GARMIN_EXPORT_DIR`, si el usuario ha configurado Google Drive for desktop; el asistente solo podrá leerlas después de que conecte y autorice Drive. La Mac debe estar encendida y con sesión disponible para la sincronización local; la app de ChatGPT no ejecuta acciones de fondo por leer los informes.

## Alcance y advertencias

- Volúmenes = sesiones running/trail; senderismo no se suma como carrera.
- Última semana identificada como **PARCIAL** y excluida de comparaciones de 4 semanas completas.
- Compara semanas sin diagnosticar sobreentrenamiento ni riesgo de lesión a partir de porcentajes.
- La deriva Pa:HR solo se calcula si el terreno y la calidad de los registros cumplen filtros sencillos. No hay análisis de pendiente avanzada ni zonas de FC personalizadas sin parámetros individualizados.
- Los cambios de promedio de FC/ritmo entre sesiones no demuestran por sí mismos mayor eficiencia.
- HRV se evalúa de forma descriptiva, no con umbrales poblacionales.
- No incorpora estrés, VO₂máx ni Training Readiness hasta integrar fuentes que efectivamente los provean con garantías.

Fuentes: [Garmin Personal API](https://developer.garmin.com/gc-developer-program/personal/swagger-docs), [cliente oficial](https://github.com/garmin/connect-personal-api-python), [fitdecode](https://pypi.org/project/fitdecode/).
