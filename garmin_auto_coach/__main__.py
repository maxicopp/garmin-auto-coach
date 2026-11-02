"""CLI: python -m garmin_auto_coach [doctor|sync|report]."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from .core import generate_exports
from .sync import run_sync, backfill_originals


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    try:
        from dotenv import load_dotenv
    except ImportError:
        print('Falta python-dotenv. Ejecutá: pip install -r requirements.txt', file=sys.stderr)
        return 2
    load_dotenv(root / '.env', override=False)
    parser = argparse.ArgumentParser(description='Garmin Personal API → reportes para análisis de running')
    command = parser.add_subparsers(dest='command', required=True)
    doctor = command.add_parser('doctor', help='Revisar configuración sin consultar datos personales')
    doctor.add_argument('--test-api', action='store_true', help='Realiza una consulta autenticada')
    sync = command.add_parser('sync', help='Sincronizar de Garmin y actualizar reportes')
    sync.add_argument('--initial-days', type=int, default=90)
    sync.add_argument('--lookback-days', type=int, default=14)
    sync.add_argument('--wellness-days', type=int, default=14)
    sync.add_argument('--since', type=date.fromisoformat, help='YYYY-MM-DD, sobrescribe la fecha inicial')
    sync.add_argument('--download-originals', action='store_true', help='ZIP original (GPS potencialmente incluido), solo almacenamiento local privado')
    sync.add_argument('--pause', type=float, default=0.15, help='Segundos entre solicitudes para reducir carga API')
    backfill = command.add_parser('backfill-originals', help='Descargar ZIP/FIT de todas las actividades ya guardadas')
    backfill.add_argument('--limit', type=int, default=500, help='Máximo de descargas nuevas en esta ejecución')
    backfill.add_argument('--pause', type=float, default=0.25)
    command.add_parser('report', help='Regenerar CSV, métricas e informes sin utilizar Garmin')
    args = parser.parse_args(argv)
    os.umask(0o077)
    private_dir = Path(os.environ.get('GARMIN_PRIVATE_DIR', str(root / 'private-data'))).expanduser()
    export_dir = Path(os.environ.get('GARMIN_EXPORT_DIR', str(root / 'exports'))).expanduser()
    goals = os.environ.get('GARMIN_COACH_GOALS', 'Trail running, ultradistancia de montaña y maratón de Buenos Aires 2027')
    if args.command == 'report':
        print(generate_exports(private_dir, export_dir, goals))
        return 0
    from garmin_personal_api import PersonalApiAuthenticator, GarminPersonalApiClient, resolve_api_key
    if args.command == 'doctor':
        print(f'Ruta privada: {private_dir.resolve()}')
        print(f'Ruta de exportación: {export_dir.resolve()}')
        try:
            key = resolve_api_key()
        except Exception as err:
            print(f'Clave no configurada: {err}', file=sys.stderr)
            return 1
        if 'REEMPLAZAR_POR_TU_CLAVE' in key:
            print('Debés reemplazar el valor de ejemplo por tu API key real.', file=sys.stderr)
            return 1
        print('Clave de Garmin: configurada (no se muestra)')
        if args.test_api:
            with PersonalApiAuthenticator() as authenticator:
                token = authenticator.obtain_token(key)
            with GarminPersonalApiClient(token.access_token) as client:
                # Avoid printing private profile information.
                client.search_activities(start=0, limit=1)
            print('Conexión con Garmin: OK')
        return 0
    if args.pause < 0 or args.pause > 10:
        parser.error('--pause debe estar entre 0 y 10')
    if args.command == 'backfill-originals' and not (1 <= args.limit <= 10000):
        parser.error('--limit debe estar entre 1 y 10000')
    try:
        key = resolve_api_key()
        if 'REEMPLAZAR_POR_TU_CLAVE' in key:
            raise ValueError('Reemplazá la clave de ejemplo en .env por tu clave real de Garmin')
        with PersonalApiAuthenticator() as authenticator:
            token = authenticator.obtain_token(key)
        with GarminPersonalApiClient(token.access_token) as client:
            if args.command == 'backfill-originals':
                progress = backfill_originals(client, private_dir, limit=args.limit, pause=args.pause)
                report = generate_exports(private_dir, export_dir, goals)
                print(f'ZIP originales almacenados: {progress["downloaded"]} nuevos. Reportes regenerados.')
                return 0
            report = run_sync(
                client, private_dir, export_dir,
                initial_days=args.initial_days, lookback_days=args.lookback_days,
                wellness_days=args.wellness_days, originals=args.download_originals,
                goals=goals, since=args.since, pause=args.pause,
            )
        print(f'Listo. {report["activities"]} actividades disponibles para análisis.')
        return 0
    except Exception as err:
        print(f'Error de sincronización: {type(err).__name__}: {err}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
