#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Syklo Swap Provider
Obtiene datos del orderbook de Syklo Swap
"""

import requests
import time
from datetime import datetime
from typing import Dict, List, Optional


class SykloProvider:
    """Proveedor de datos de Syklo Swap"""
    
    def __init__(self, config=None):
        """
        Inicializa el proveedor Syklo
        
        Args:
            config: ConfigManager opcional. Si es None, usa valores por defecto
        """
        self.config = config
        self.last_update = None
        
        # Cargar configuración
        if config:
            self.base_url = config.get("syklo.base_url", "https://syklo-orderbook.ddns.net")
            self.timeout = config.get("syklo.timeout", 100)
            self.retries = config.get("syklo.retries", 3)
            self.user_agent = config.get("syklo.user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        else:
            self.base_url = "https://syklo-orderbook.ddns.net"
            self.timeout = 100
            self.retries = 3
            self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    def fetch_orderbook_data(self, url: str, retries: int = None, timeout: int = None) -> Dict:
        """Obtiene datos del orderbook con reintentos"""
        if retries is None:
            retries = self.retries
        if timeout is None:
            timeout = self.timeout
            
        headers = {
            "User-Agent": self.user_agent
        }
        
        for attempt in range(retries):
            try:
                response = requests.get(url, timeout=timeout, headers=headers)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(5)
                else:
                    return {}
    
    def fetch_usernames(self, user_ids: List[int]) -> Dict[int, str]:
        """Obtiene nombres de usuario para IDs dados"""
        if not user_ids:
            return {}
        
        url = f"{self.base_url}/maker_stats?user_ids={','.join(map(str, user_ids))}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            usernames = {}
            for user_id_str, details in data.items():
                user_id = int(user_id_str)
                username = details.get("user_name", f"user_{user_id}")
                usernames[user_id] = username
            return usernames
        except Exception as e:
            print(f"Error fetching usernames: {e}")
            return {}
    
    def parse_orderbook_data(self, data: Dict, method_aliases: Dict = None) -> List[Dict]:
        """Parsea datos del orderbook en lista de órdenes"""
        if method_aliases is None:
            method_aliases = {}
        
        orders = []
        user_ids_set = set()
        
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            
            pms = value.get("pm", [])
            if not pms:
                continue
            
            method_short = pms[0].split(":")[-1] if ":" in pms[0] else pms[0]
            method_full = method_aliases.get(method_short, pms[0])
            
            r_prices = value.get("r_price", [])
            mins = value.get("min", [])
            maxs = value.get("max", [])
            user_ids = value.get("user_id", [])
            scores = value.get("score", [])
            sides = value.get("side", [])
            
            for i in range(len(r_prices)):
                user_id = user_ids[i] if i < len(user_ids) else None
                if user_id is not None:
                    user_ids_set.add(user_id)
                
                order = {
                    "method_full": method_full,
                    "method": method_short,
                    "price": r_prices[i] if i < len(r_prices) else "-",
                    "min": mins[i] if i < len(mins) else "-",
                    "max": maxs[i] if i < len(maxs) else "-",
                    "trader_id": user_id,
                    "score": scores[i] if i < len(scores) else "-",
                    "side": sides[0] if sides else "-",
                }
                orders.append(order)
        
        # Obtener nombres de usuario
        usernames = self.fetch_usernames(list(user_ids_set))
        
        # Mapear nombres a órdenes
        for order in orders:
            trader_id = order.get("trader_id")
            order["trader"] = usernames.get(
                trader_id, f"user_{trader_id}" if trader_id else "-"
            )
        
        return orders
    
    def filter_orders(self, orders: List[Dict], send_methods: List[str]) -> List[Dict]:
        """Filtra órdenes por métodos de envío"""
        return [order for order in orders if order.get("method") in send_methods]
    
    def get_ves_usdc_info(self) -> Dict:
        """Obtiene información de VES→USDC (bancos venezolanos)"""
        if self.config:
            send_pms = self.config.get("syklo.ves_usdc.send_pms", "VES:VE:VEBN1,VES:VE:VEBN2,VES:VE:VEBN29")
            receive_pms = self.config.get("syklo.ves_usdc.receive_pms", "USDC:ALL:SYKLO")
            method_aliases = self.config.get("syklo.ves_usdc.method_aliases", {
                "VEBN1": "Banco de Venezuela",
                "VEBN2": "Banesco",
                "VEBN29": "BNC",
            })
            send_methods = self.config.get("syklo.ves_usdc.send_methods", ["VEBN1", "VEBN2", "VEBN29"])
        else:
            send_pms = "VES:VE:VEBN1,VES:VE:VEBN2,VES:VE:VEBN29"
            receive_pms = "USDC:ALL:SYKLO"
            method_aliases = {
                "VEBN1": "Banco de Venezuela",
                "VEBN2": "Banesco",
                "VEBN29": "BNC",
            }
            send_methods = ["VEBN1", "VEBN2", "VEBN29"]
        
        url = f"{self.base_url}/book?send_pms={send_pms}&receive_pms={receive_pms}"
        
        data = self.fetch_orderbook_data(url)
        if not data:
            return {
                "source": "Syklo Swap",
                "pair": "VES/USDC",
                "error": "No se pudieron obtener datos",
                "timestamp": None
            }
        
        orders = self.parse_orderbook_data(data, method_aliases)
        filtered_orders = self.filter_orders(orders, send_methods)
        filtered_orders.sort(key=lambda x: float(x.get("price", 0) if x.get("price") != "-" else 0), reverse=True)
        
        self.last_update = datetime.now()
        
        return {
            "source": "Syklo Swap",
            "pair": "VES/USDC",
            "description": "Envías Bolívares desde Banesco, Banco de Venezuela, o BNC, para recibir USDC",
            "timestamp": self.last_update.isoformat(),
            "orders": filtered_orders[:20],
            "total_orders": len(filtered_orders),
        }
    
    def get_usdc_usd_info(self) -> Dict:
        """Obtiene información de USDC→USD/ZI"""
        if self.config:
            send_pms = self.config.get("syklo.usdc_usd.send_pms", "USDC:ALL:SYKLO")
            receive_pms = self.config.get("syklo.usdc_usd.receive_pms", "USD:ALL:ZI")
            send_methods = self.config.get("syklo.usdc_usd.send_methods", ["USD", "ZI"])
        else:
            send_pms = "USDC:ALL:SYKLO"
            receive_pms = "USD:ALL:ZI"
            send_methods = ["USD", "ZI"]
        
        url = f"{self.base_url}/book?send_pms={send_pms}&receive_pms={receive_pms}"
        
        data = self.fetch_orderbook_data(url)
        if not data:
            return {
                "source": "Syklo Swap",
                "pair": "USDC/USD",
                "error": "No se pudieron obtener datos",
                "timestamp": None
            }
        
        orders = self.parse_orderbook_data(data)
        filtered_orders = self.filter_orders(orders, send_methods)
        filtered_orders.sort(key=lambda x: float(x.get("price", 0) if x.get("price") != "-" else 0), reverse=True)
        
        self.last_update = datetime.now()
        
        return {
            "source": "Syklo Swap",
            "pair": "USDC/USD",
            "description": "Envías USDC y recibes Zinli",
            "timestamp": self.last_update.isoformat(),
            "orders": filtered_orders[:20],
            "total_orders": len(filtered_orders),
        }
    
    def formatear_salida(self, info: Dict) -> str:
        """Formatea la salida de forma elegante"""
        lines = []
        lines.append("=" * 100)
        lines.append(f"SYKLO SWAP ORDERBOOK - {info.get('pair', 'SWAP')}")
        
        if info.get("description"):
            lines.append(f"Parámetros: {info['description']}")
        
        lines.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Desarrollado por Edwin Lopez.")
        lines.append("=" * 100)
        
        if "error" in info:
            lines.append(f"Error: {info['error']}")
            return "\n".join(lines)
        
        lines.append(f"{'Method':<20} {'Price':<15} {'Min':<15} {'Max':<15} {'Trader':<25}")
        lines.append("-" * 100)
        
        orders = info.get("orders", [])
        if not orders:
            lines.append("No matching orders found for the swap parameters.")
        else:
            for order in orders[:20]:
                method_full = order.get("method_full", "-")
                price = order.get("price", "-")
                min_amount = order.get("min", "-")
                max_amount = order.get("max", "-")
                trader = order.get("trader", "-")
                
                lines.append(
                    f"{str(method_full):<20} {str(price):<15} {str(min_amount):<15} {str(max_amount):<15} {str(trader):<25}"
                )
        
        lines.append("=" * 100)
        return "\n".join(lines)
