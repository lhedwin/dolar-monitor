#!/usr/bin/env python3
"""Script para actualizar la tabla bcv_rates desde la API histórica de BCV.
Uso: ejecutar periódicamente (cron) para mantener la base local sincronizada.
"""
import requests
import json
import os
import sys
from datetime import datetime

# Asegurar import de DatabaseManager desde src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from database import DatabaseManager

API_URL = 'https://bcv.today/api/v1/history.json'

def fetch_history():
    r = requests.get(API_URL, timeout=30)
    r.raise_for_status()
    return r.json()


def update_db():
    hist = fetch_history()
    db = DatabaseManager()
    conn = db._get_connection()
    cursor = conn.cursor()

    inserted = 0
    skipped = 0
    for item in hist:
        date = item.get('date')
        if not date:
            skipped += 1
            continue
        # extract rate
        rate = None
        for k in ('USD','dollar','rate'):
            if k in item and item.get(k) is not None:
                try:
                    rate = float(item.get(k))
                    break
                except Exception:
                    continue
        if rate is None:
            skipped += 1
            continue
        cursor.execute('SELECT 1 FROM bcv_rates WHERE date = ?', (date,))
        if cursor.fetchone():
            skipped += 1
            continue
        cursor.execute("INSERT INTO bcv_rates (date, rate, source, raw_data) VALUES (?, ?, ?, ?)", (
            date,
            rate,
            item.get('source', 'BCV (history.json)'),
            json.dumps(item, ensure_ascii=False)
        ))
        inserted += 1

    if inserted:
        conn.commit()
    conn.close()
    print(f"Inserted: {inserted}, Skipped: {skipped}")

if __name__ == '__main__':
    try:
        update_db()
    except Exception as e:
        print('ERROR', e)
        raise
