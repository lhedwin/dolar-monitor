#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Binance P2P Provider
Obtiene precios de USDT/VES y USDT/USD de Binance P2P
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
import requests
import sys
import os

# Agregar ruta del src al path para importar utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import calculate_price_stats, format_currency


class BinanceP2PProvider:
    """Proveedor de precios de Binance P2P"""
    
    def __init__(self, config=None):
        """
        Inicializa el proveedor Binance P2P
        
        Args:
            config: ConfigManager opcional. Si es None, usa valores por defecto
        """
        self.config = config
        self.last_update = None
        
        # Cargar configuración
        if config:
            self.base_url = config.get("binance_p2p.base_url", "https://p2p.binance.com")
            self.p2p_endpoint = config.get("binance_p2p.endpoint", "/bapi/c2c/v2/friendly/c2c/adv/search")
            self.default_limit = config.get("binance_p2p.default_limit", 20)
            self.timeout = config.get("binance_p2p.timeout", 20)
            self.user_agent = config.get("binance_p2p.user_agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
        else:
            self.base_url = "https://p2p.binance.com"
            self.p2p_endpoint = "/bapi/c2c/v2/friendly/c2c/adv/search"
            self.default_limit = 20
            self.timeout = 20
            self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    
    def get_ads(
        self,
        fiat: str,
        trade_type: str = "BUY",
        limit: int = 20,
        payment_method: Optional[str] = None,
        filter_merchant: bool = True,
        trans_amount: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Obtiene anuncios de Binance P2P

        trans_amount: cuando se especifica, se envía en el payload como transAmount
        para que la API filtre anuncios que aceptan esa cantidad.
        """
        
        payload: Dict[str, Any] = {
            "asset": "USDT",
            "fiat": fiat,
            "tradeType": trade_type,
            "page": 1,
            "rows": limit,
            "payTypes": [payment_method] if payment_method else [],
            "publisherType": "merchant" if filter_merchant else None,
            "transAmount": str(trans_amount) if trans_amount is not None else "",
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        
        try:
            response = requests.post(
                f"{self.base_url}{self.p2p_endpoint}",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def parse_ads(self, ads_data: Dict, trade_type: str, filter_merchant: bool = True) -> List[Dict]:
        """Normaliza anuncios en formato simplificado"""
        if "error" in ads_data:
            return []
        
        ads = ads_data.get("data", [])
        parsed: List[Dict] = []
        
        for ad in ads:
            adv = ad.get("adv", {})
            advertiser = ad.get("advertiser", {})
            
            # Filtro por tipo de usuario
            if filter_merchant:
                if trade_type == "BUY":
                    if advertiser.get("userType") != "merchant":
                        continue
                else:  # "SELL"
                    if advertiser.get("userType") not in ("merchant", "user"):
                        continue
            
            try:
                parsed_ad: Dict[str, Any] = {
                    "price": float(adv.get("price", 0)),
                    "min_amount": float(adv.get("minSingleTransAmount", 0)),
                    "max_amount": float(adv.get("maxSingleTransAmount", 0)),
                    "available_amount": float(adv.get("tradableQuantity", 0)),
                    "payment_methods": [
                        pm.get("identifier") for pm in adv.get("tradeMethods", [])
                    ],
                    "merchant_name": advertiser.get("nickName", ""),
                    "order_count": int(advertiser.get("monthOrderCount", 0) or 0),
                    "completion_rate": float(advertiser.get("monthFinishRate", 0) or 0) * 100,
                    "trade_type": trade_type,
                    "user_type": advertiser.get("userType", None),
                }
                parsed.append(parsed_ad)
            except (TypeError, ValueError):
                continue
        
        return parsed
    
    def calculate_stats(self, ads: List[Dict]) -> Dict[str, Any]:
        """Calcula estadísticas de precios usando función de utilidad"""
        if not ads:
            return {"error": "No ads available"}
        
        prices = [float(ad["price"]) for ad in ads if "price" in ad]
        return calculate_price_stats(prices)
    
    def get_price_summary(
        self,
        fiat: str,
        payment_method: Optional[str] = None,
        limit: int = 20,
        filter_merchant: bool = True
    ) -> Dict[str, Any]:
        """Obtiene resumen de precios para un par de monedas

        Ahora devuelve también 'filter_applied' y 'trans_amount' para exponer el
        comportamiento de filtrado a capas superiores.
        """
        
        buy_ads_data = self.get_ads(
            fiat=fiat,
            trade_type="BUY",
            limit=limit,
            payment_method=payment_method,
            filter_merchant=filter_merchant
        )
        buy_ads = self.parse_ads(buy_ads_data, "BUY", filter_merchant)
        
        sell_ads_data = self.get_ads(
            fiat=fiat,
            trade_type="SELL",
            limit=limit,
            payment_method=payment_method,
            filter_merchant=filter_merchant
        )
        sell_ads = self.parse_ads(sell_ads_data, "SELL", filter_merchant)
        
        # Nueva lógica: consulta preliminar para obtener una tasa de referencia y usar transAmount
        filter_applied = False
        filtered_buy_ads = []
        filtered_sell_ads = []
        trans_amount = None

        try:
            # Intentar obtener precio de referencia consultando merchants rápido
            ref_data = self.get_ads(fiat=fiat, trade_type="BUY", limit=5, payment_method=payment_method, filter_merchant=True)
            current_rate = None
            if isinstance(ref_data, dict) and ref_data.get("data"):
                try:
                    current_rate = float(ref_data["data"][0]["adv"]["price"])
                except Exception:
                    current_rate = None

            # Si obtenemos current_rate, pedir anuncios que acepten transAmount = current_rate * 10
            if current_rate:
                trans_amount = str(int(current_rate * 10))
                # Call API with transAmount to get merchant ads that accept that exact amount
                buy_with_amount = self.get_ads(fiat=fiat, trade_type="BUY", limit=limit, payment_method=payment_method, filter_merchant=True, trans_amount=trans_amount)
                sell_with_amount = self.get_ads(fiat=fiat, trade_type="SELL", limit=limit, payment_method=payment_method, filter_merchant=True, trans_amount=trans_amount)

                # Parse the responses (merchant-only)
                filtered_buy_ads = self.parse_ads(buy_with_amount, "BUY", True) if buy_with_amount else []
                filtered_sell_ads = self.parse_ads(sell_with_amount, "SELL", True) if sell_with_amount else []

                # If filtering produced no merchant ads for a side, fallback to the original merchant lists (without transAmount)
                if not filtered_buy_ads:
                    filtered_buy_ads = buy_ads
                if not filtered_sell_ads:
                    filtered_sell_ads = sell_ads

                if filtered_buy_ads or filtered_sell_ads:
                    filter_applied = True
            else:
                # Fallback: use existing parsed lists
                filtered_buy_ads = buy_ads
                filtered_sell_ads = sell_ads
        except Exception:
            filtered_buy_ads = buy_ads
            filtered_sell_ads = sell_ads

        self.last_update = datetime.now()
        
        return {
            "timestamp": self.last_update.isoformat(),
            "fiat": fiat,
            "payment_method": payment_method,
            "filter_applied": filter_applied,
            "trans_amount": trans_amount,
            "buy": {
                "stats": self.calculate_stats(filtered_buy_ads),
                "top_ads": filtered_buy_ads[:5] if filtered_buy_ads else [],
            "all_ads": filtered_buy_ads,
            },
            "sell": {
            "stats": self.calculate_stats(filtered_sell_ads),
            "top_ads": filtered_sell_ads[:5] if filtered_sell_ads else [],
            "all_ads": filtered_sell_ads,
            },
        }
    
    def get_ves_info(self, limit: int = None) -> Dict:
        """Obtiene información de USDT/VES"""
        if limit is None:
            limit = self.config.get("binance_p2p.ves.limit", 20) if self.config else 20
        
        filter_merchant = self.config.get("binance_p2p.ves.filter_merchant", True) if self.config else True
        
        summary = self.get_price_summary(
            fiat="VES", 
            limit=limit,
            filter_merchant=filter_merchant
        )
        return {
            "source": "Binance P2P",
            "pair": "USDT/VES",
            "timestamp": summary.get("timestamp"),
            "filter_applied": summary.get("filter_applied"),
            "trans_amount": summary.get("trans_amount"),
            "buy_stats": summary["buy"]["stats"],
            "sell_stats": summary["sell"]["stats"],
            "top_buy_ads": summary["buy"]["top_ads"],
            "top_sell_ads": summary["sell"]["top_ads"],
        }
    
    def get_usd_zinli_info(self, limit: int = None) -> Dict:
        """Obtiene información de USDT/USD con método Zinli"""
        if limit is None:
            limit = self.config.get("binance_p2p.usd_zinli.limit", 20) if self.config else 20
        
        payment_method = self.config.get("binance_p2p.usd_zinli.payment_method", "zinli") if self.config else "zinli"
        filter_merchant = self.config.get("binance_p2p.usd_zinli.filter_merchant", True) if self.config else True
        
        summary = self.get_price_summary(
            fiat="USD",
            payment_method=payment_method,
            limit=limit,
            filter_merchant=filter_merchant
        )

        # Aplicar filtro adicional: solo anuncios cuyo min_amount >= 10 USD (merchant-only already garantizado por filter_merchant)
        MIN_USD = 10.0
        buy_all = summary["buy"].get("all_ads", [])
        sell_all = summary["sell"].get("all_ads", [])

        # Filtrar por min_amount
        filtered_buy = [ad for ad in buy_all if ad.get("min_amount", 0) >= MIN_USD]
        filtered_sell = [ad for ad in sell_all if ad.get("min_amount", 0) >= MIN_USD]

        # Recalcular estadísticas y top_ads basadas en el filtrado por mínimo
        buy_stats = self.calculate_stats(filtered_buy) if filtered_buy else {"error": "No ads available"}
        sell_stats = self.calculate_stats(filtered_sell) if filtered_sell else {"error": "No ads available"}

        return {
            "source": "Binance P2P",
            "pair": "USDT/USD",
            "payment_method": "zinli",
            "timestamp": summary.get("timestamp"),
            "filter_applied": summary.get("filter_applied"),
            "trans_amount": summary.get("trans_amount"),
            "min_usd_filter": MIN_USD,
            "buy_stats": buy_stats,
            "sell_stats": sell_stats,
            "top_buy_ads": filtered_buy[:5],
            "top_sell_ads": filtered_sell[:5],
        }
    
    def formatear_salida(self, info: Dict) -> str:
        """Formatea la salida de forma elegante usando utilidades"""
        lines = []
        lines.append("=" * 90)
        
        if info.get("pair") == "USDT/VES":
            lines.append("RESUMEN DE PRECIOS USDT/VES EN EL MERCADO BINANCE P2P")
        else:
            lines.append(f"RESUMEN DE PRECIOS {info.get('pair', 'USDT/USD')} EN BINANCE P2P. MÉTODO: {info.get('payment_method', 'ALL').upper()}")
        
        lines.append("=" * 90)
        lines.append(f"Última Actualización: {info.get('timestamp', '')}")
        lines.append("")
        
        for side in ["buy_stats", "sell_stats"]:
            side_name = "BUY" if "buy" in side else "SELL"
            lines.append(f"{side_name} USDT PRICES:")
            lines.append("-" * 30)
            
            stats = info.get(side, {})
            if "error" in stats:
                lines.append(f"  {stats['error']}")
            else:
                fiat = "VES" if info.get("pair") == "USDT/VES" else "USD"
                lines.append(f"  Count: {stats['count']} ads")
                lines.append(f"  Min: {format_currency(stats['min_price'], fiat)}")
                lines.append(f"  Max: {format_currency(stats['max_price'], fiat)}")
                lines.append(f"  Average: {format_currency(stats['avg_price'], fiat)}")
                lines.append(f"  Median: {format_currency(stats['median_price'], fiat)}")
            
            lines.append("")
            
            top_ads_key = "top_buy_ads" if "buy" in side else "top_sell_ads"
            top_ads = info.get(top_ads_key, [])
            if top_ads:
                lines.append("  Top 5 Ofertas:")
                for i, ad in enumerate(top_ads[:5], 1):
                    fiat = "VES" if info.get("pair") == "USDT/VES" else "USD"
                    lines.append(f"    {i}. {format_currency(ad['price'], fiat)} - {ad.get('merchant_name', '')}")
            lines.append("")
        
        return "\n".join(lines)
