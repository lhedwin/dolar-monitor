#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Database Manager
Sistema de persistencia SQLite para datos históricos de tasas
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path


class DatabaseManager:
    """Gestor de base de datos SQLite para Zinli Monitor"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Inicializa el gestor de base de datos
        
        Args:
            db_path: Ruta al archivo de base de datos. Si es None, usa ubicación por defecto
        """
        if db_path is None:
            # Usar directorio del proyecto (resolver rutas relativas como '..')
            project_dir = Path(__file__).resolve().parent.parent
            db_path = project_dir / "zinli_monitor.db"
        
        self.db_path = str(db_path)
        self._initialize_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexión a la base de datos (timeout y WAL para concurrencia)"""
        # timeout: tiempo máximo (s) que espera SQLite si la DB está bloqueada
        # check_same_thread=False para permitir uso en hilos si se comparte (agente/background)
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Para acceder por nombre de columna
        # Activar pragmas recomendados para concurrencia y resiliencia
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA wal_autocheckpoint=1000;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
        except Exception:
            # Si algo falla, no romper la inicialización; la DB seguirá usable
            pass
        return conn
    
    def _initialize_database(self) -> None:
        """Inicializa las tablas de la base de datos

        Implementa reintentos cuando la base de datos está bloqueada por el agente en background.
        Esto evita fallos de arranque si el agente mantiene transacciones cortas abiertas.
        """
        max_attempts = 6
        delay = 0.5
        for attempt in range(1, max_attempts + 1):
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                # Asegurar modo WAL para permitir lectores concurrentes mientras el agente escribe
                try:
                    cursor.execute("PRAGMA journal_mode=WAL;")
                    cursor.execute("PRAGMA busy_timeout=30000;")
                except Exception:
                    pass

                # Tabla de tasas BCV
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bcv_rates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        date TEXT NOT NULL,
                        rate REAL NOT NULL,
                        source TEXT DEFAULT 'BCV',
                        raw_data TEXT
                    )
                """)

                # Tabla de precios Binance P2P
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS binance_p2p_prices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        pair TEXT NOT NULL,
                        side TEXT NOT NULL,
                        payment_method TEXT,
                        count INTEGER,
                        min_price REAL,
                        max_price REAL,
                        avg_price REAL,
                        median_price REAL,
                        top_ads TEXT,
                        raw_data TEXT
                    )
                """)

                # Tabla de orderbook Syklo
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS syklo_orderbook (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        pair TEXT NOT NULL,
                        description TEXT,
                        total_orders INTEGER,
                        orders TEXT,
                        raw_data TEXT
                    )
                """)

                # Tabla de datos consolidados (para análisis)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS consolidated_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        bcv_rate REAL,
                        binance_ves_buy_avg REAL,
                        binance_ves_sell_avg REAL,
                        binance_usd_zinli_buy_avg REAL,
                        binance_usd_zinli_sell_avg REAL,
                        syklo_ves_usdc_avg REAL,
                        syklo_usdc_usd_avg REAL,
                        metadata TEXT
                    )
                """)

                # Índices para consultas rápidas
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bcv_timestamp ON bcv_rates(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_binance_timestamp ON binance_p2p_prices(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_syklo_timestamp ON syklo_orderbook(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_consolidated_timestamp ON consolidated_data(timestamp)")

                conn.commit()
                conn.close()
                return

            except sqlite3.OperationalError as e:
                # Si la BD está bloqueada, esperar y reintentar
                if 'locked' in str(e).lower() and attempt < max_attempts:
                    time.sleep(delay)
                    delay = min(5.0, delay * 2)
                    continue
                # Si es otro error o agotaron intentos, volver a lanzar
                raise

    
    def save_bcv_rate(self, rate_data: Dict) -> bool:
        """
        Guarda una tasa del BCV
        
        Args:
            rate_data: Diccionario con datos de la tasa
            
        Returns:
            True si se guardó correctamente
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO bcv_rates (date, rate, source, raw_data)
                VALUES (?, ?, ?, ?)
            """, (
                rate_data.get("date"),
                rate_data.get("rate"),
                rate_data.get("source", "BCV"),
                json.dumps(rate_data)
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving BCV rate: {e}")
            return False
    
    def save_binance_p2p_data(self, data: Dict) -> bool:
        """
        Guarda datos de Binance P2P
        
        Args:
            data: Diccionario con datos de Binance P2P
            
        Returns:
            True si se guardó correctamente
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            pair = data.get("pair", "")
            timestamp = data.get("timestamp")
            
            # Guardar datos BUY
            buy_stats = data.get("buy_stats", {})
            if buy_stats and "error" not in buy_stats:
                cursor.execute("""
                    INSERT INTO binance_p2p_prices 
                    (timestamp, pair, side, count, min_price, max_price, avg_price, median_price, top_ads, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    pair,
                    "BUY",
                    buy_stats.get("count"),
                    buy_stats.get("min_price"),
                    buy_stats.get("max_price"),
                    buy_stats.get("avg_price"),
                    buy_stats.get("median_price"),
                    json.dumps(data.get("top_buy_ads", [])),
                    json.dumps(data)
                ))
            
            # Guardar datos SELL
            sell_stats = data.get("sell_stats", {})
            if sell_stats and "error" not in sell_stats:
                cursor.execute("""
                    INSERT INTO binance_p2p_prices 
                    (timestamp, pair, side, count, min_price, max_price, avg_price, median_price, top_ads, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    pair,
                    "SELL",
                    sell_stats.get("count"),
                    sell_stats.get("min_price"),
                    sell_stats.get("max_price"),
                    sell_stats.get("avg_price"),
                    sell_stats.get("median_price"),
                    json.dumps(data.get("top_sell_ads", [])),
                    json.dumps(data)
                ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving Binance P2P data: {e}")
            return False
    
    def save_syklo_data(self, data: Dict) -> bool:
        """
        Guarda datos de Syklo
        
        Args:
            data: Diccionario con datos de Syklo
            
        Returns:
            True si se guardó correctamente
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO syklo_orderbook 
                (timestamp, pair, description, total_orders, orders, raw_data)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                data.get("timestamp"),
                data.get("pair"),
                data.get("description"),
                data.get("total_orders", 0),
                json.dumps(data.get("orders", [])),
                json.dumps(data)
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving Syklo data: {e}")
            return False
    
    def save_consolidated_data(self, all_data: Dict) -> bool:
        """
        Guarda datos consolidados de todas las fuentes
        
        Args:
            all_data: Diccionario con todos los datos
            
        Returns:
            True si se guardó correctamente
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Extraer datos relevantes
            bcv_data = all_data.get("bcv", {})
            binance_ves = all_data.get("binance_ves", {})
            binance_usd = all_data.get("binance_usd_zinli", {})
            syklo_ves = all_data.get("syklo_ves_usdc", {})
            syklo_usd = all_data.get("syklo_usdc_usd", {})
            
            bcv_rate = bcv_data.get("rate") if isinstance(bcv_data, dict) else None
            ves_buy_avg = binance_ves.get("buy_stats", {}).get("avg_price") if isinstance(binance_ves, dict) else None
            ves_sell_avg = binance_ves.get("sell_stats", {}).get("avg_price") if isinstance(binance_ves, dict) else None
            usd_buy_avg = binance_usd.get("buy_stats", {}).get("avg_price") if isinstance(binance_usd, dict) else None
            usd_sell_avg = binance_usd.get("sell_stats", {}).get("avg_price") if isinstance(binance_usd, dict) else None
            
            # Calcular promedios de Syklo
            syklo_ves_orders = syklo_ves.get("orders", []) if isinstance(syklo_ves, dict) else []
            syklo_ves_avg = sum([float(o.get("price", 0)) for o in syklo_ves_orders if o.get("price") != "-"]) / len(syklo_ves_orders) if syklo_ves_orders else None
            
            syklo_usd_orders = syklo_usd.get("orders", []) if isinstance(syklo_usd, dict) else []
            syklo_usd_avg = sum([float(o.get("price", 0)) for o in syklo_usd_orders if o.get("price") != "-"]) / len(syklo_usd_orders) if syklo_usd_orders else None
            
            cursor.execute("""
                INSERT INTO consolidated_data 
                (bcv_rate, binance_ves_buy_avg, binance_ves_sell_avg, 
                 binance_usd_zinli_buy_avg, binance_usd_zinli_sell_avg,
                 syklo_ves_usdc_avg, syklo_usdc_usd_avg, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bcv_rate,
                ves_buy_avg,
                ves_sell_avg,
                usd_buy_avg,
                usd_sell_avg,
                syklo_ves_avg,
                syklo_usd_avg,
                json.dumps(all_data)
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving consolidated data: {e}")
            return False
    
    def get_bcv_history(self, hours: int = 24) -> List[Dict]:
        """
        Obtiene historial de tasas BCV por las últimas N horas

        Args:
            hours: Número de horas de historial

        Returns:
            Lista de diccionarios con datos históricos
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            since = datetime.now() - timedelta(hours=hours)
            
            cursor.execute("""
                SELECT * FROM bcv_rates 
                WHERE timestamp >= ? 
                ORDER BY date ASC
            """, (since.isoformat(),))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting BCV history: {e}")
            return []

    def get_bcv_history_by_date(self, start_date: str, end_date: str) -> Dict:
        """
        Obtiene historial de tasas BCV filtrando por rango de fechas (YYYY-MM-DD)

        Args:
            start_date: Fecha inicial en formato 'YYYY-MM-DD'
            end_date: Fecha final en formato 'YYYY-MM-DD'

        Returns:
            Diccionario con keys: source, start_date, end_date, rates (list), count, timestamp
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT raw_data FROM bcv_rates
                WHERE date >= ? AND date <= ?
                ORDER BY date ASC
            """, (start_date, end_date))
            rows = cursor.fetchall()
            conn.close()

            rates = []
            for r in rows:
                raw = r['raw_data']
                try:
                    parsed = json.loads(raw)
                    rates.append(parsed)
                except Exception:
                    # fallback: try to build minimal dict
                    rates.append({'date': None, 'dollar': None, 'USD': None})

            return {
                'source': 'BCV (local DB)',
                'start_date': start_date,
                'end_date': end_date,
                'rates': rates,
                'count': len(rates),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Error getting BCV history by date: {e}")
            return {'error': str(e)}
    
    def get_binance_history(self, pair: str, hours: int = 24) -> List[Dict]:
        """
        Obtiene historial de Binance P2P
        
        Args:
            pair: Par de monedas (ej: "USDT/VES")
            hours: Número de horas de historial
            
        Returns:
            Lista de diccionarios con datos históricos
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            since = datetime.now() - timedelta(hours=hours)
            
            cursor.execute("""
                SELECT * FROM binance_p2p_prices 
                WHERE pair = ? AND timestamp >= ? 
                ORDER BY timestamp DESC
            """, (pair, since.isoformat(),))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting Binance history: {e}")
            return []
    
    def get_consolidated_history(self, hours: int = 24) -> List[Dict]:
        """
        Obtiene historial consolidado
        
        Args:
            hours: Número de horas de historial
            
        Returns:
            Lista de diccionarios con datos históricos
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            since = datetime.now() - timedelta(hours=hours)
            
            cursor.execute("""
                SELECT * FROM consolidated_data 
                WHERE timestamp >= ? 
                ORDER BY timestamp DESC
            """, (since.isoformat(),))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting consolidated history: {e}")
            return []
    
    def get_arbitrage_opportunities(self, hours: int = 1) -> List[Dict]:
        """
        Analiza oportunidades de arbitraje basadas en datos históricos
        
        Args:
            hours: Período de tiempo a analizar
            
        Returns:
            Lista de oportunidades detectadas
        """
        try:
            history = self.get_consolidated_history(hours)
            opportunities = []
            
            for data in history:
                bcv_rate = data.get("bcv_rate")
                ves_buy_avg = data.get("binance_ves_buy_avg")
                ves_sell_avg = data.get("binance_ves_sell_avg")
                
                if bcv_rate and ves_buy_avg and ves_sell_avg:
                    # Calcular spread
                    spread_to_bcv = ((ves_buy_avg - bcv_rate) / bcv_rate) * 100
                    binance_spread = ((ves_buy_avg - ves_sell_avg) / ves_sell_avg) * 100
                    
                    if abs(spread_to_bcv) > 5 or abs(binance_spread) > 2:
                        opportunities.append({
                            "timestamp": data.get("timestamp"),
                            "type": "price_discrepancy",
                            "bcv_rate": bcv_rate,
                            "binance_buy": ves_buy_avg,
                            "binance_sell": ves_sell_avg,
                            "spread_to_bcv": spread_to_bcv,
                            "binance_spread": binance_spread,
                        })
            
            return opportunities
        except Exception as e:
            print(f"Error getting arbitrage opportunities: {e}")
            return []
    
    def get_statistics(self, hours: int = 24) -> Dict:
        """
        Obtiene estadísticas generales del período
        
        Args:
            hours: Período de tiempo a analizar
            
        Returns:
            Diccionario con estadísticas
        """
        try:
            history = self.get_consolidated_history(hours)
            
            if not history:
                return {"error": "No data available"}
            
            bcv_rates = [h.get("bcv_rate") for h in history if h.get("bcv_rate")]
            ves_buy_rates = [h.get("binance_ves_buy_avg") for h in history if h.get("binance_ves_buy_avg")]
            ves_sell_rates = [h.get("binance_ves_sell_avg") for h in history if h.get("binance_ves_sell_avg")]
            
            return {
                "period_hours": hours,
                "data_points": len(history),
                "bcv": {
                    "min": min(bcv_rates) if bcv_rates else None,
                    "max": max(bcv_rates) if bcv_rates else None,
                    "avg": sum(bcv_rates) / len(bcv_rates) if bcv_rates else None,
                },
                "binance_ves_buy": {
                    "min": min(ves_buy_rates) if ves_buy_rates else None,
                    "max": max(ves_buy_rates) if ves_buy_rates else None,
                    "avg": sum(ves_buy_rates) / len(ves_buy_rates) if ves_buy_rates else None,
                },
                "binance_ves_sell": {
                    "min": min(ves_sell_rates) if ves_sell_rates else None,
                    "max": max(ves_sell_rates) if ves_sell_rates else None,
                    "avg": sum(ves_sell_rates) / len(ves_sell_rates) if ves_sell_rates else None,
                },
            }
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {"error": str(e)}
    
    def cleanup_old_data(self, days: int = 30) -> int:
        """
        Elimina datos antiguos para mantener la base de datos manejable
        
        Args:
            days: Días de datos a mantener
            
        Returns:
            Número de registros eliminados
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            since = datetime.now() - timedelta(days=days)
            
            tables = ["bcv_rates", "binance_p2p_prices", "syklo_orderbook", "consolidated_data"]
            total_deleted = 0
            
            for table in tables:
                cursor.execute(f"""
                    DELETE FROM {table} 
                    WHERE timestamp < ?
                """, (since.isoformat(),))
                total_deleted += cursor.rowcount
            
            conn.commit()
            conn.close()
            
            return total_deleted
        except Exception as e:
            print(f"Error cleaning up old data: {e}")
            return 0
