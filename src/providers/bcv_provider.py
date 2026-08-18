#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
BCV Rate Provider
Obtiene la tasa oficial del dólar del BCV
"""

import re
import requests
import urllib3
from datetime import datetime, timezone, timedelta
from typing import Dict, Union, Optional


class BCVProvider:
    """Proveedor de tasas del BCV con múltiples fuentes de datos"""
    
    def __init__(self, config=None):
        """
        Inicializa el proveedor BCV con múltiples fuentes de datos
        
        Args:
            config: ConfigManager opcional. Si es None, usa valores por defecto
        """
        self.config = config
        self.last_rate = None
        self.last_update = None
        
        # Cargar configuración
        if config:
            self.primary_api = config.get("bcv.api_url", "https://bcv.today/api/v1/rate.json")
            self.web_url = config.get("bcv.web_url", "https://bcv.org.ve")
            self.timeout = config.get("bcv.timeout", 10)
            self.fallback_enabled = config.get("bcv.fallback_enabled", True)
        else:
            self.primary_api = "https://bcv.today/api/v1/rate.json"
            self.web_url = "https://bcv.org.ve"
            self.timeout = 10
            self.fallback_enabled = True
        
        # Fuentes alternativas (orden de prioridad)
        self.fallback_apis = [
            {
                "name": "Gisus07 API",
                "url": "https://api.tasabcv.com/v1/rates",
                "type": "json",
                "rate_field": "USD",
                "date_field": "date"
            },
            {
                "name": "Cotizave",
                "url": "https://api.cotizave.com/v1/fx/rates/reference",
                "type": "json",
                "rate_field": "mid",
                "date_field": "updated_at",
                "headers": {"Accept": "application/json"}
            }
        ]
    
    def obtener_tasa(self) -> Union[Dict, str]:
        """Obtiene la tasa del BCV con múltiples fallbacks"""
        
        # Intento 1: API principal (BCV Today)
        try:
            response = requests.get(self.primary_api, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            # BCV Today usa "USD" en lugar de "dollar" y también ofrece "EUR"
            if isinstance(data, dict) and "USD" in data:
                self.last_rate = {
                    "dollar": data["USD"],
                    "euro": data.get("EUR", None),
                    "date": data.get("date", ""),
                    "source": "BCV (BCV Today API)"
                }
                self.last_update = datetime.now()
                return self.last_rate
        except Exception as e:
            print(f"Error con API principal: {e}")
        
        # Intento 2: APIs alternativas
        if self.fallback_enabled:
            for api in self.fallback_apis:
                try:
                    headers = api.get("headers", {})
                    response = requests.get(api["url"], headers=headers, timeout=self.timeout)
                    response.raise_for_status()
                    data = response.json()
                    
                    # Extraer tasa según la estructura de cada API
                    rate_value = self._extract_rate_from_api(data, api)
                    date_value = self._extract_date_from_api(data, api)
                    
                    if rate_value:
                        result = {
                            "dollar": rate_value,
                            "date": date_value,
                            "source": f"BCV ({api['name']} - Fallback)"
                        }
                        self.last_rate = result
                        self.last_update = datetime.now()
                        return result
                        
                except Exception as e:
                    print(f"Error con {api['name']}: {e}")
                    continue
        
        # Intento 3: Web scraping del sitio oficial
        if self.fallback_enabled:
            try:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                response = requests.get(self.web_url, timeout=self.timeout, verify=False)
                response.raise_for_status()
                html = response.text
                
                # Busca patrón de precio del dólar
                m = re.search(
                    r"dolar[\s\S]{0,800}?([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})|[0-9]+[.,][0-9]{1,2})",
                    html,
                    re.IGNORECASE,
                )
                if m:
                    tasa_raw = m.group(1)
                    tasa = tasa_raw.replace(".", "").replace(",", ".")
                    
                    # Fecha actual en Venezuela (UTC-4)
                    tz_ve = timezone(timedelta(hours=-4))
                    fecha_ve = datetime.now(tz_ve).date().strftime("%d/%m/%Y")
                    
                    result = {
                        "dollar": tasa,
                        "date": fecha_ve,
                        "source": "BCV (Web Scraping - Fallback)"
                    }
                    self.last_rate = result
                    self.last_update = datetime.now()
                    return result
                    
            except Exception as e:
                print(f"Error con web scraping: {e}")
        
        # Intento 4: Valor por defecto si todo falla
        return "No se pudo obtener la tasa del BCV de ninguna fuente"
    
    def _extract_rate_from_api(self, data: Dict, api_config: Dict) -> Optional[float]:
        """Extrae la tasa de la respuesta de una API específica"""
        try:
            rate_field = api_config["rate_field"]
            
            # Navegar la estructura según la API
            if api_config["name"] == "Gisus07 API":
                return float(data.get(rate_field, 0))
            elif api_config["name"] == "BCV Today":
                return float(data.get(rate_field, 0))
            elif api_config["name"] == "Cotizave":
                # Cotizave tiene estructura anidada
                if isinstance(data, dict) and "rates" in data:
                    usd_rate = data["rates"].get("USD")
                    if isinstance(usd_rate, dict):
                        return float(usd_rate.get("mid", 0))
            return None
        except (TypeError, ValueError, KeyError):
            return None
    
    def _extract_date_from_api(self, data: Dict, api_config: Dict) -> str:
        """Extrae la fecha de la respuesta de una API específica"""
        try:
            date_field = api_config["date_field"]
            
            if api_config["name"] == "Gisus07 API":
                return data.get(date_field, "")
            elif api_config["name"] == "BCV Today":
                return data.get(date_field, "")
            elif api_config["name"] == "Cotizave":
                # Cotizave usa timestamp
                timestamp = data.get(date_field, "")
                if timestamp:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    return dt.strftime("%d/%m/%Y")
            return ""
        except (TypeError, ValueError, KeyError):
            return ""
    
    def formatear_salida(self, data: Dict) -> str:
        """Formatea la salida de forma elegante"""
        if not isinstance(data, dict):
            return str(data)
        
        keys = ["date", "dollar"]
        labels = {"date": "Fecha", "dollar": "Precio del Dolar BCV"}
        
        max_key_len = max(len(labels[k]) for k in keys)
        max_val_len = max(len(str(data.get(k, ""))) for k in keys)
        
        border = "+" + "-" * (max_key_len + 2) + "+" + "-" * (max_val_len + 2) + "+"
        border_green = "\033[32m" + border + "\033[0m"
        
        framed_output = border_green + "\n"
        for i, k in enumerate(keys):
            row = (
                "\033[32m"
                + f"| {labels[k]:<{max_key_len}} | "
                + "\033[33m"
                + f"{str(data.get(k, '')):<{max_val_len}}"
                + "\033[32m"
                + " |"
                + "\033[0m"
                + "\n"
            )
            framed_output += row
            if i < len(keys) - 1:
                framed_output += border_green + "\n"
        framed_output += border_green
        return framed_output
    
    def get_rate_info(self) -> Dict:
        """Retorna información estructurada de la tasa"""
        rate_data = self.obtener_tasa()
        if isinstance(rate_data, dict):
            result = {
                "source": "BCV",
                "timestamp": self.last_update.isoformat() if self.last_update else None,
                "date": rate_data.get("date"),
                "rate": float(rate_data.get("dollar", 0)),
                "formatted": self.formatear_salida(rate_data)
            }
            # Agregar euro si está disponible
            if rate_data.get("euro"):
                result["euro"] = float(rate_data.get("euro", 0))
            return result
        return {
            "source": "BCV",
            "error": str(rate_data),
            "timestamp": self.last_update.isoformat() if self.last_update else None
        }
    
    def get_historical_rates(self, days: int = 30, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Union[Dict, str]:
        """
        Obtiene tasas históricas del BCV.

        Estrategia:
        1. Intentar usar la base de datos local (si existe) para el rango solicitado.
        2. Si no hay datos suficientes, consultar la API de BCV Today y actualizar la DB local.
        3. Si la API falla, caer a datos simulados como último recurso.
        """
        # Determinar rango de fechas
        from datetime import datetime, timedelta
        if start_date and end_date:
            start = start_date
            end = end_date
        else:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Intentar leer desde la BD local primero
        try:
            try:
                # Import local DatabaseManager
                from database import DatabaseManager
            except Exception:
                from src.database import DatabaseManager

            db = DatabaseManager()
            local = db.get_bcv_history_by_date(start, end)
            if isinstance(local, dict) and local.get('count', 0) > 0:
                # Si la BD tiene entradas para el rango, devolverlas
                return local
        except Exception as e:
            # Si falla el acceso a DB, seguimos y consultamos API
            print(f"Warning: no se pudo leer BD local: {e}")

        # Si no hay datos locales, consultar la API BCV Today
        try:
            url = "https://bcv.today/api/v1/history.json"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list) and len(data) > 0:
                # Filtrar por rango
                filtered_data = [item for item in data if start <= item.get("date", "") <= end]

                # Actualizar BD local con nuevos registros (evitar duplicados)
                try:
                    try:
                        from database import DatabaseManager
                    except Exception:
                        from src.database import DatabaseManager

                    db = DatabaseManager()
                    conn = db._get_connection()
                    cursor = conn.cursor()
                    import json
                    inserted = 0
                    for item in filtered_data:
                        date = item.get('date')
                        if not date:
                            continue
                        # determine rate value
                        rate_val = None
                        for k in ('USD','dollar','rate'):
                            if k in item and item.get(k) is not None:
                                try:
                                    rate_val = float(item.get(k))
                                    break
                                except Exception:
                                    continue
                        if rate_val is None:
                            continue
                        cursor.execute('SELECT 1 FROM bcv_rates WHERE date = ?', (date,))
                        if cursor.fetchone():
                            continue
                        cursor.execute("INSERT INTO bcv_rates (date, rate, source, raw_data) VALUES (?, ?, ?, ?)", (
                            date,
                            rate_val,
                            item.get('source', 'BCV (history.json)'),
                            json.dumps(item, ensure_ascii=False)
                        ))
                        inserted += 1
                    if inserted:
                        conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"Warning: no se pudo actualizar BD local: {e}")

                return {
                    "source": "BCV (BCV Today API - Historical)",
                    "start_date": start,
                    "end_date": end,
                    "rates": filtered_data,
                    "count": len(filtered_data),
                    "timestamp": datetime.now().isoformat()
                }

        except Exception as e:
            print(f"Error con historial BCV Today: {e}")
            # Intento fallback a datos simulados
            return self._generate_mock_historical_rates(days, start_date, end_date)
    
    def _generate_mock_historical_rates(self, days: int = 30, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        """
        Genera datos históricos simulados basados en tendencia cuando la API no está disponible
        
        Args:
            days: Número de días de historial
            start_date: Fecha inicial (opcional)
            end_date: Fecha final (opcional)
            
        Returns:
            Diccionario con datos históricos simulados
        """
        try:
            # Obtener tasa actual como base
            current_rate_data = self.obtener_tasa()
            if isinstance(current_rate_data, str):
                # Si falla la tasa actual, usar un valor base
                base_rate = 752.09  # Valor base aproximado
            else:
                base_rate = float(current_rate_data.get("dollar", 752.09))
            
            # Calcular fechas
            if start_date and end_date:
                from datetime import datetime
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                date_range = (end_dt - start_dt).days
            else:
                from datetime import datetime, timedelta
                end_dt = datetime.now()
                start_dt = end_dt - timedelta(days=days)
                date_range = days
            
            # Generar datos simulados con tendencia realista
            rates = []
            current_date = start_dt
            
            for i in range(date_range + 1):
                # Simular variación aleatoria pequeña (+/- 2%)
                import random
                variation = random.uniform(-0.02, 0.02)
                rate = base_rate * (1 + variation)
                
                rates.append({
                    "date": current_date.strftime("%Y-%m-%d"),
                    "dollar": round(rate, 2)
                })
                
                current_date += timedelta(days=1)
            
            return {
                "source": "BCV (Simulado - API no disponible)",
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": end_dt.strftime("%Y-%m-%d"),
                "rates": rates,
                "count": len(rates),
                "timestamp": datetime.now().isoformat(),
                "note": "Datos simulados debido a que la API del BCV no está disponible temporalmente"
            }
            
        except Exception as e:
            return f"Error generando datos históricos simulados: {e}"
    
    def get_rate_by_date(self, date_str: str) -> Union[Dict, str]:
        """
        Obtiene la tasa de una fecha específica usando BCV Today API
        
        Args:
            date_str: Fecha en formato YYYY-MM-DD
            
        Returns:
            Diccionario con la tasa o mensaje de error
        """
        try:
            # Usar el endpoint de historial por fecha específica de BCV Today
            url = f"https://bcv.today/api/v1/history/{date_str}.json"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, dict) and "USD" in data:
                return {
                    "source": "BCV (BCV Today API)",
                    "date": data.get("date"),
                    "rate": float(data.get("USD", 0)),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return f"No se encontró tasa para la fecha {date_str}"
                
        except requests.exceptions.RequestException as e:
            # Fallback: buscar en el historial completo
            try:
                url = "https://bcv.today/api/v1/history.json"
                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                
                if isinstance(data, list):
                    for item in data:
                        if item.get("date") == date_str:
                            return {
                                "source": "BCV (BCV Today API - History)",
                                "date": item.get("date"),
                                "rate": float(item.get("USD", 0)),
                                "timestamp": datetime.now().isoformat()
                            }
                    return f"No se encontró tasa para la fecha {date_str}"
                else:
                    return f"No se encontró tasa para la fecha {date_str}"
            except Exception as e2:
                return f"Error al obtener tasa para fecha {date_str}: {e}"
        except Exception as e:
            return f"Error inesperado: {e}"
