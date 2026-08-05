#!/usr/bin/env python3
"""Wrapper para inicializar la base de datos en la raíz del proyecto.
Este script está pensado para usarse al configurar el proyecto por primera vez.
Crea ./zinli_monitor.db (en la raíz del repo) y opcionalmente inserta datos de ejemplo.

Uso:
  python3 scripts/init_db.py --sample-size 8 --force
"""
import sys
import os
from pathlib import Path

# Asegurar que el directorio raíz del proyecto está en sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import init_db as root_init
except Exception as e:
    print('Error importando init_db.py desde la raíz:', e)
    raise

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Inicializar la base de datos SQLite en la raíz del proyecto')
    parser.add_argument('--sample-size', '-s', type=int, default=8, help='Número de filas de ejemplo por tabla (default: 8)')
    parser.add_argument('--force', '-f', action='store_true', help='Sobrescribir DB existente (se hace backup)')
    parser.add_argument('--no-sample', action='store_true', help='No insertar datos de ejemplo')
    parser.add_argument('--path', '-p', default=str(ROOT / 'zinli_monitor.db'), help='Ruta destino para la base de datos (por defecto: ./zinli_monitor.db)')

    args = parser.parse_args()
    path = Path(args.path)
    sample_size = 0 if args.no_sample else args.sample_size

    # Llamar a la función create_db del init_db.py raíz
    rc = root_init.create_db(path, sample_size=sample_size, force=args.force)
    raise SystemExit(rc)
