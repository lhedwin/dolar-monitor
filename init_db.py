#!/usr/bin/env python3
"""
init_db.py
Crea la base de datos SQLite usada por Dólar Monitor y opcionalmente inserta datos de ejemplo.

Uso:
  python3 init_db.py --path ./zinli_monitor.db --sample-size 8 --force
"""
from pathlib import Path
import sqlite3
import argparse
from datetime import datetime, timedelta
import random

DDL = {
    "bcv_rates": """
    CREATE TABLE IF NOT EXISTS bcv_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        USD REAL,
        source TEXT
    );
    """,

    "binance_p2p_prices": """
    CREATE TABLE IF NOT EXISTS binance_p2p_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        pair TEXT NOT NULL,
        side TEXT NOT NULL,
        avg_price REAL,
        rate REAL
    );
    """,

    "consolidated_data": """
    CREATE TABLE IF NOT EXISTS consolidated_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        metric TEXT,
        value REAL
    );
    """,

    "syklo_orderbook": """
    CREATE TABLE IF NOT EXISTS syklo_orderbook (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        pair TEXT,
        bid REAL,
        ask REAL
    );
    """
}

INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_binance_ts ON binance_p2p_prices(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_bcv_ts ON bcv_rates(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_consol_ts ON consolidated_data(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_syklo_ts ON syklo_orderbook(timestamp);",
]


def insert_sample(conn, sample_size: int):
    now = datetime.utcnow()
    cur = conn.cursor()
    # Distribute sample rows across tables
    for i in range(sample_size):
        ts = (now - timedelta(hours=(sample_size - i))).isoformat()
        # bcv_rates
        usd = round(4.0 + random.uniform(-0.5, 0.5), 2)
        cur.execute("INSERT INTO bcv_rates (timestamp, USD, source) VALUES (?, ?, ?)",
                    (ts, usd, 'BCV'))
        # binance_p2p_prices (simulate buy/sell alternation)
        pair = 'USDT/VES'
        side = 'buy' if i % 2 == 0 else 'sell'
        avg_price = round(usd * (1 + random.uniform(-0.02, 0.02)), 2)
        cur.execute("INSERT INTO binance_p2p_prices (timestamp, pair, side, avg_price, rate) VALUES (?, ?, ?, ?, ?)",
                    (ts, pair, side, avg_price, avg_price))
        # consolidated_data
        cur.execute("INSERT INTO consolidated_data (timestamp, metric, value) VALUES (?, ?, ?)",
                    (ts, 'example_metric', round(random.uniform(0, 100), 2)))
        # syklo_orderbook
        bid = round(avg_price - random.uniform(0.1, 0.5), 2)
        ask = round(avg_price + random.uniform(0.1, 0.5), 2)
        cur.execute("INSERT INTO syklo_orderbook (timestamp, pair, bid, ask) VALUES (?, ?, ?, ?)",
                    (ts, 'VES/USDC', bid, ask))
    conn.commit()


def create_db(path: Path, sample_size: int = 0, force: bool = False):
    if path.exists() and not force:
        print(f"ERROR: {path} already exists. Use --force to overwrite or choose a different --path.")
        return 1
    if path.exists() and force:
        bak = path.with_suffix(path.suffix + '.bak') if path.suffix else Path(str(path) + '.bak')
        print(f"Backing up existing DB to {bak}")
        path.replace(bak)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    # Create tables
    for name, ddl in DDL.items():
        cur.executescript(ddl)
    for idx in INDICES:
        cur.execute(idx)
    conn.commit()
    if sample_size and sample_size > 0:
        insert_sample(conn, sample_size)
    conn.close()
    print(f"Database created at: {path} (sample_size={sample_size})")
    return 0


def main():
    parser = argparse.ArgumentParser(description='Inicializar la base de datos SQLite para Dólar Monitor.')
    parser.add_argument('--path', '-p', default='zinli_monitor.db', help='Ruta al archivo SQLite a crear.')
    parser.add_argument('--sample-size', '-s', type=int, default=8, help='Número de filas de ejemplo por tabla (default: 8).')
    parser.add_argument('--force', '-f', action='store_true', help='Sobrescribir DB existente (se hace backup).')
    parser.add_argument('--no-sample', action='store_true', help='No insertar datos de ejemplo.')
    args = parser.parse_args()

    path = Path(args.path)
    sample_size = 0 if args.no_sample else args.sample_size
    return create_db(path, sample_size=sample_size, force=args.force)


if __name__ == '__main__':
    raise SystemExit(main())
