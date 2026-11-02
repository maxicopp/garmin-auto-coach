"""Install/uninstall a per-user daily launchd job for macOS (07:00 local)."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = 'com.local.garmin-auto-coach'
AGENT = Path.home() / 'Library' / 'LaunchAgents' / (LABEL + '.plist')
LOGS = Path.home() / 'Library' / 'Logs'
RUN = Path(__file__).resolve().parent / 'run_daily.sh'
TARGET = f'gui/{os.getuid()}'


def launchctl(*args: str):
    return subprocess.run(['launchctl', *args], check=False)


def main():
    if sys.platform != 'darwin':
        print('Este instalador es exclusivo de macOS.')
        return 2
    action = sys.argv[1] if len(sys.argv) > 1 else 'install'
    if action not in {'install', 'uninstall'}:
        print('Uso: python scripts/install_launchd.py [install|uninstall]')
        return 2
    if AGENT.exists():
        launchctl('bootout', TARGET, str(AGENT))
    if action == 'uninstall':
        AGENT.unlink(missing_ok=True)
        print('Tarea programada eliminada.')
        return 0
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    payload = {
        'Label': LABEL,
        'ProgramArguments': ['/bin/bash', str(RUN)],
        'WorkingDirectory': str(RUN.parent.parent),
        'StartCalendarInterval': {'Hour': 7, 'Minute': 0},
        'RunAtLoad': False,
        'StandardOutPath': str(LOGS / 'garmin-auto-coach.log'),
        'StandardErrorPath': str(LOGS / 'garmin-auto-coach.error.log'),
        'ProcessType': 'Background',
    }
    AGENT.write_bytes(plistlib.dumps(payload))
    os.chmod(AGENT, 0o600)
    result = launchctl('bootstrap', TARGET, str(AGENT))
    if result.returncode:
        print('No se pudo activar la tarea. Revisá permisos y launchctl.', file=sys.stderr)
        return result.returncode
    print('Sincronización diaria instalada para las 07:00 (hora local de macOS).')
    print('El equipo debe estar encendido y tu sesión disponible. Ejecutá manualmente después de instalar.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
