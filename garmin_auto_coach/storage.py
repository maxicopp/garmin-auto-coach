"""Local persistence utilities for the Garmin Auto Coach application.

This module has no dependencies on Garmin, analytics, or CLI code.
Data encoding and atomic-write behavior are preserved from core.py.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    try:
        tmp.write_text(text, encoding='utf-8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def load_rows(directory: Path, transform) -> list[dict]:
    rows = []
    if directory.exists():
        for path in directory.glob('*.json'):
            try:
                rows.append(transform(json_file(path)))
            except (ValueError, TypeError, OSError, KeyError) as exc:
                print(f'Advertencia: no se pudo leer {path.name}: {exc}')
    return rows


def csv_output(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    try:
        with tmp.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow({key: '' if row.get(key) is None else row.get(key) for key in columns})
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
