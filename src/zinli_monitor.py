#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Zinli Monitor - Sistema Unificado de Monitoreo de Tasas
Integra todos los proveedores de datos en un solo sistema cohesivo
"""

import sys
import os
from datetime import datetime
from typing import Dict, List, Optional

# Agregar ruta del src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from providers import BCVProvider, BinanceP2PProvider, SykloProvider
from config_manager import ConfigManager, get_config
from database import DatabaseManager


class ZinliMonitor:
    """Sistema unificado de monitoreo de tasas"""
    
    def __init__(self, config_path: Optional[str] = None, enable_db: bool = True):
        """
        Inicializa el sistema de monitoreo
        
        Args:
            config_path: Ruta opcional al archivo de configuración
            enable_db: Habilitar sistema de persistencia
        """
        self.config = get_config(config_path)
        self.bcv_provider = BCVProvider(self.config)
        self.binance_provider = BinanceP2PProvider(self.config)
        self.syklo_provider = SykloProvider(self.config)
        self.last_update = None
        
        # Sistema de persistencia
        self.enable_db = enable_db
        if enable_db:
            self.db = DatabaseManager()
        else:
            self.db = None
    
    def get_all_data(self, save_to_db: bool = True) -> Dict:
        """Obtiene datos de todos los proveedores"""
        self.last_update = datetime.now()
        
        data = {
            "timestamp": self.last_update.isoformat(),
            "bcv": self.bcv_provider.get_rate_info(),
            "binance_ves": self.binance_provider.get_ves_info(),
            "binance_usd_zinli": self.binance_provider.get_usd_zinli_info(),
            "syklo_ves_usdc": self.syklo_provider.get_ves_usdc_info(),
            "syklo_usdc_usd": self.syklo_provider.get_usdc_usd_info(),
        }
        
        # Guardar en base de datos si está habilitado
        if save_to_db and self.db:
            self._save_all_data(data)
        
        return data
    
    def _save_all_data(self, data: Dict) -> None:
        """Guarda todos los datos en la base de datos"""
        try:
            # Guardar BCV
            if isinstance(data.get("bcv"), dict) and "error" not in data["bcv"]:
                self.db.save_bcv_rate(data["bcv"])
            
            # Guardar Binance VES
            if isinstance(data.get("binance_ves"), dict) and "error" not in data["binance_ves"]:
                self.db.save_binance_p2p_data(data["binance_ves"])
            
            # Guardar Binance USD Zinli
            if isinstance(data.get("binance_usd_zinli"), dict) and "error" not in data["binance_usd_zinli"]:
                self.db.save_binance_p2p_data(data["binance_usd_zinli"])
            
            # Guardar Syklo VES/USDC
            if isinstance(data.get("syklo_ves_usdc"), dict) and "error" not in data["syklo_ves_usdc"]:
                self.db.save_syklo_data(data["syklo_ves_usdc"])
            
            # Guardar Syklo USDC/USD
            if isinstance(data.get("syklo_usdc_usd"), dict) and "error" not in data["syklo_usdc_usd"]:
                self.db.save_syklo_data(data["syklo_usdc_usd"])
            
            # Guardar datos consolidados
            self.db.save_consolidated_data(data)
            
        except Exception as e:
            print(f"Error saving data to database: {e}")
    
    def get_bcv_rate(self) -> Dict:
        """Obtiene solo la tasa del BCV"""
        return self.bcv_provider.get_rate_info()
    
    def get_bcv_history(self, days: int = 30, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Union[Dict, str]:
        """Obtiene historial de tasas del BCV"""
        return self.bcv_provider.get_historical_rates(days, start_date, end_date)
    
    def get_bcv_rate_by_date(self, date_str: str) -> Union[Dict, str]:
        """Obtiene la tasa del BCV de una fecha específica"""
        return self.bcv_provider.get_rate_by_date(date_str)
    
    def get_binance_ves(self) -> Dict:
        """Obtiene solo precios USDT/VES"""
        return self.binance_provider.get_ves_info()
    
    def get_binance_usd_zinli(self) -> Dict:
        """Obtiene solo precios USDT/USD Zinli"""
        return self.binance_provider.get_usd_zinli_info()
    
    def get_syklo_ves_usdc(self) -> Dict:
        """Obtiene solo orderbook VES/USDC"""
        return self.syklo_provider.get_ves_usdc_info()
    
    def get_syklo_usdc_usd(self) -> Dict:
        """Obtiene solo orderbook USDC/USD"""
        return self.syklo_provider.get_usdc_usd_info()
    
    # Métodos de análisis y persistencia
    def get_history(self, hours: int = 24) -> Dict:
        """Obtiene historial de datos de la base de datos"""
        if not self.db:
            return {"error": "Database not enabled"}
        
        return {
            "bcv": self.db.get_bcv_history(hours),
            "binance_ves": self.db.get_binance_history("USDT/VES", hours),
            "binance_usd": self.db.get_binance_history("USDT/USD", hours),
            "consolidated": self.db.get_consolidated_history(hours),
        }
    
    def get_statistics(self, hours: int = 24) -> Dict:
        """Obtiene estadísticas del período especificado"""
        if not self.db:
            return {"error": "Database not enabled"}
        
        return self.db.get_statistics(hours)
    
    def get_arbitrage_opportunities(self, hours: int = 1) -> List[Dict]:
        """Analiza oportunidades de arbitraje"""
        if not self.db:
            return []
        
        return self.db.get_arbitrage_opportunities(hours)
    
    def analyze_current_arbitrage(self) -> Dict:
        """Analiza oportunidades de arbitraje con datos actuales"""
        data = self.get_all_data(save_to_db=False)
        
        opportunities = []
        
        # Extraer datos relevantes
        bcv_data = data.get("bcv", {})
        binance_ves = data.get("binance_ves", {})
        binance_usd = data.get("binance_usd_zinli", {})
        syklo_ves = data.get("syklo_ves_usdc", {})
        
        # Análisis BCV vs Binance P2P VES
        if isinstance(bcv_data, dict) and isinstance(binance_ves, dict):
            bcv_rate = bcv_data.get("rate")
            ves_buy_avg = binance_ves.get("buy_stats", {}).get("avg_price")
            ves_sell_avg = binance_ves.get("sell_stats", {}).get("avg_price")
            
            if bcv_rate and ves_buy_avg and ves_sell_avg:
                spread_to_bcv = ((ves_buy_avg - bcv_rate) / bcv_rate) * 100
                binance_spread = ((ves_buy_avg - ves_sell_avg) / ves_sell_avg) * 100
                
                if abs(spread_to_bcv) > 5:
                    opportunities.append({
                        "type": "bcv_vs_binance_ves",
                        "description": f"Diferencia significativa entre BCV ({bcv_rate:.2f}) y Binance P2P Buy ({ves_buy_avg:.2f})",
                        "spread_percent": spread_to_bcv,
                        "bcv_rate": bcv_rate,
                        "binance_buy": ves_buy_avg,
                        "binance_sell": ves_sell_avg,
                        "recommendation": "buy" if spread_to_bcv > 0 else "sell",
                    })
                
                if abs(binance_spread) > 2:
                    opportunities.append({
                        "type": "binance_ves_spread",
                        "description": f"Spread significativo en Binance P2P VES: {binance_spread:.2f}%",
                        "spread_percent": binance_spread,
                        "buy_price": ves_buy_avg,
                        "sell_price": ves_sell_avg,
                        "recommendation": "arbitrage" if binance_spread > 2 else "wait",
                    })
        
        # Análisis Binance P2P USD vs Zinli
        if isinstance(binance_usd, dict):
            usd_buy_avg = binance_usd.get("buy_stats", {}).get("avg_price")
            usd_sell_avg = binance_usd.get("sell_stats", {}).get("avg_price")
            
            if usd_buy_avg and usd_sell_avg:
                usd_spread = ((usd_buy_avg - usd_sell_avg) / usd_sell_avg) * 100
                
                if abs(usd_spread) > 1:
                    opportunities.append({
                        "type": "binance_usd_zinli_spread",
                        "description": f"Spread en Binance P2P USD/Zinli: {usd_spread:.2f}%",
                        "spread_percent": usd_spread,
                        "buy_price": usd_buy_avg,
                        "sell_price": usd_sell_avg,
                        "recommendation": "arbitrage" if usd_spread > 1 else "wait",
                    })
        
        # Análisis Syklo VES/USDC
        if isinstance(syklo_ves, dict) and isinstance(binance_ves, dict):
            syklo_orders = syklo_ves.get("orders", [])
            if syklo_orders:
                syklo_avg = sum([float(o.get("price", 0)) for o in syklo_orders if o.get("price") != "-"]) / len(syklo_orders)
                ves_sell_avg = binance_ves.get("sell_stats", {}).get("avg_price")
                
                if syklo_avg and ves_sell_avg:
                    syklo_spread = ((syklo_avg - ves_sell_avg) / ves_sell_avg) * 100
                    
                    if abs(syklo_spread) > 3:
                        opportunities.append({
                            "type": "syklo_vs_binance_ves",
                            "description": f"Diferencia entre Syklo ({syklo_avg:.2f}) y Binance P2P Sell ({ves_sell_avg:.2f})",
                            "spread_percent": syklo_spread,
                            "syklo_avg": syklo_avg,
                            "binance_sell": ves_sell_avg,
                            "recommendation": "use_syklo" if syklo_spread < 0 else "use_binance",
                        })
        
        return {
            "timestamp": data.get("timestamp"),
            "opportunities": opportunities,
            "total_opportunities": len(opportunities),
        }
    
    def display_all(self):
        """Muestra todos los datos en formato estructurado"""
        data = self.get_all_data()
        
        print("\n" + "=" * 100)
        print("ZINLI MONITOR - SISTEMA UNIFICADO DE MONITOREO DE TASAS")
        print(f"Última actualización: {data['timestamp']}")
        print("=" * 100)
        
        # BCV
        print("\n" + "=" * 50)
        print("TASA OFICIAL BCV")
        print("=" * 50)
        if "formatted" in data["bcv"]:
            print(data["bcv"]["formatted"])
        else:
            print(f"Error: {data['bcv'].get('error', 'Unknown error')}")
        
        # Binance VES
        print("\n" + "=" * 90)
        print("BINANCE P2P - USDT/VES")
        print("=" * 90)
        if "error" not in data["binance_ves"]:
            print(self.binance_provider.formatear_salida(data["binance_ves"]))
        else:
            print(f"Error: {data['binance_ves'].get('error', 'Unknown error')}")
        
        # Binance USD Zinli
        print("\n" + "=" * 90)
        print("BINANCE P2P - USDT/USD (ZINLI)")
        print("=" * 90)
        if "error" not in data["binance_usd_zinli"]:
            print(self.binance_provider.formatear_salida(data["binance_usd_zinli"]))
        else:
            print(f"Error: {data['binance_usd_zinli'].get('error', 'Unknown error')}")
        
        # Syklo VES/USDC
        print("\n" + "=" * 100)
        print("SYKLO SWAP - VES/USDC")
        print("=" * 100)
        if "error" not in data["syklo_ves_usdc"]:
            print(self.syklo_provider.formatear_salida(data["syklo_ves_usdc"]))
        else:
            print(f"Error: {data['syklo_ves_usdc'].get('error', 'Unknown error')}")
        
        # Syklo USDC/USD
        print("\n" + "=" * 100)
        print("SYKLO SWAP - USDC/USD")
        print("=" * 100)
        if "error" not in data["syklo_usdc_usd"]:
            print(self.syklo_provider.formatear_salida(data["syklo_usdc_usd"]))
        else:
            print(f"Error: {data['syklo_usdc_usd'].get('error', 'Unknown error')}")
        
        print("\n" + "=" * 100)
        print("FIN DEL REPORTE")
        print("=" * 100 + "\n")
    
    def display_menu(self):
        """Muestra menú interactivo"""
        while True:
            print("\n" + "=" * 60)
            print("ZINLI MONITOR - MENÚ PRINCIPAL")
            print("=" * 60)
            print("1. Mostrar todos los datos")
            print("2. Mostrar solo tasa BCV")
            print("3. Mostrar solo Binance P2P USDT/VES")
            print("4. Mostrar solo Binance P2P USDT/USD (Zinli)")
            print("5. Mostrar solo Syklo Swap VES/USDC")
            print("6. Mostrar solo Syklo Swap USDC/USD")
            print("7. Analizar oportunidades de arbitraje (tiempo real)")
            print("8. Ver historial de datos (últimas 24h)")
            print("9. Ver estadísticas del período")
            print("10. Ver historial BCV (últimos 30 días)")
            print("11. Ver tasa BCV por fecha específica")
            print("12. Salir")
            print("=" * 60)
            
            try:
                choice = int(input("Selecciona una opción (1-12): "))
                
                if choice == 1:
                    self.display_all()
                elif choice == 2:
                    data = self.get_bcv_rate()
                    if "formatted" in data:
                        print(data["formatted"])
                    else:
                        print(f"Error: {data.get('error', 'Unknown error')}")
                elif choice == 3:
                    data = self.get_binance_ves()
                    if "error" not in data:
                        print(self.binance_provider.formatear_salida(data))
                    else:
                        print(f"Error: {data.get('error', 'Unknown error')}")
                elif choice == 4:
                    data = self.get_binance_usd_zinli()
                    if "error" not in data:
                        print(self.binance_provider.formatear_salida(data))
                    else:
                        print(f"Error: {data.get('error', 'Unknown error')}")
                elif choice == 5:
                    data = self.get_syklo_ves_usdc()
                    if "error" not in data:
                        print(self.syklo_provider.formatear_salida(data))
                    else:
                        print(f"Error: {data.get('error', 'Unknown error')}")
                elif choice == 6:
                    data = self.get_syklo_usdc_usd()
                    if "error" not in data:
                        print(self.syklo_provider.formatear_salida(data))
                    else:
                        print(f"Error: {data.get('error', 'Unknown error')}")
                elif choice == 7:
                    analysis = self.analyze_current_arbitrage()
                    print("\n" + "=" * 80)
                    print("ANÁLISIS DE OPORTUNIDADES DE ARBITRAJE")
                    print("=" * 80)
                    print(f"Timestamp: {analysis['timestamp']}")
                    print(f"Total oportunidades: {analysis['total_opportunities']}")
                    print()
                    
                    if analysis['opportunities']:
                        for i, opp in enumerate(analysis['opportunities'], 1):
                            print(f"{i}. {opp['type'].upper()}")
                            print(f"   Descripción: {opp['description']}")
                            print(f"   Spread: {opp['spread_percent']:.2f}%")
                            print(f"   Recomendación: {opp['recommendation']}")
                            print()
                    else:
                        print("No se detectaron oportunidades de arbitraje significativas.")
                    
                    print("=" * 80)
                elif choice == 8:
                    history = self.get_history(24)
                    if "error" in history:
                        print(f"Error: {history['error']}")
                    else:
                        print("\n" + "=" * 80)
                        print("HISTORIAL DE DATOS (ÚLTIMAS 24 HORAS)")
                        print("=" * 80)
                        print(f"Registros BCV: {len(history['bcv'])}")
                        print(f"Registros Binance VES: {len(history['binance_ves'])}")
                        print(f"Registros Binance USD: {len(history['binance_usd'])}")
                        print(f"Registros Consolidados: {len(history['consolidated'])}")
                        print()
                        
                        if history['consolidated']:
                            print("Últimos 5 registros consolidados:")
                            for i, record in enumerate(history['consolidated'][:5], 1):
                                print(f"{i}. {record['timestamp']}")
                                print(f"   BCV: {record.get('bcv_rate', 'N/A')}")
                                print(f"   Binance VES Buy: {record.get('binance_ves_buy_avg', 'N/A')}")
                                print(f"   Binance VES Sell: {record.get('binance_ves_sell_avg', 'N/A')}")
                        
                        print("=" * 80)
                elif choice == 9:
                    stats = self.get_statistics(24)
                    if "error" in stats:
                        print(f"Error: {stats['error']}")
                    else:
                        print("\n" + "=" * 80)
                        print("ESTADÍSTICAS DEL PERÍODO (ÚLTIMAS 24 HORAS)")
                        print("=" * 80)
                        print(f"Puntos de datos: {stats['data_points']}")
                        print()
                        
                        print("TASA BCV:")
                        bcv = stats['bcv']
                        print(f"  Mín: {bcv['min']:.2f}" if bcv['min'] else "  Mín: N/A")
                        print(f"  Máx: {bcv['max']:.2f}" if bcv['max'] else "  Máx: N/A")
                        print(f"  Prom: {bcv['avg']:.2f}" if bcv['avg'] else "  Prom: N/A")
                        print()
                        
                        print("BINANCE P2P VES BUY:")
                        ves_buy = stats['binance_ves_buy']
                        print(f"  Mín: {ves_buy['min']:.2f}" if ves_buy['min'] else "  Mín: N/A")
                        print(f"  Máx: {ves_buy['max']:.2f}" if ves_buy['max'] else "  Máx: N/A")
                        print(f"  Prom: {ves_buy['avg']:.2f}" if ves_buy['avg'] else "  Prom: N/A")
                        print()
                        
                        print("BINANCE P2P VES SELL:")
                        ves_sell = stats['binance_ves_sell']
                        print(f"  Mín: {ves_sell['min']:.2f}" if ves_sell['min'] else "  Mín: N/A")
                        print(f"  Máx: {ves_sell['max']:.2f}" if ves_sell['max'] else "  Máx: N/A")
                        print(f"  Prom: {ves_sell['avg']:.2f}" if ves_sell['avg'] else "  Prom: N/A")
                        
                        print("=" * 80)
                elif choice == 10:
                    history = self.get_bcv_history(30)
                    if isinstance(history, dict) and "rates" in history:
                        print("\n" + "=" * 80)
                        print(f"HISTORIAL BCV - ÚLTIMOS 30 DÍAS")
                        print("=" * 80)
                        print(f"Período: {history.get('start_date')} a {history.get('end_date')}")
                        print(f"Total registros: {history.get('count')}")
                        print(f"Fuente: {history.get('source')}")
                        print()
                        
                        if history['rates']:
                            print("Últimos 10 registros:")
                            for i, rate in enumerate(history['rates'][-10:], 1):
                                # BCV Today usa "USD" en lugar de "dollar"
                                rate_value = rate.get("USD", rate.get("dollar", "N/A"))
                                print(f"{i}. {rate.get('date')}: {rate_value} Bs")
                            
                            # Estadísticas básicas
                            rates = [float(r.get("USD", r.get("dollar", 0))) for r in history['rates']]
                            if rates:
                                print()
                                print("Estadísticas:")
                                print(f"  Mínimo: {min(rates):.2f} Bs")
                                print(f"  Máximo: {max(rates):.2f} Bs")
                                print(f"  Promedio: {sum(rates)/len(rates):.2f} Bs")
                                print(f"  Variación: {((max(rates) - min(rates)) / min(rates) * 100):.2f}%")
                        else:
                            print("No hay datos disponibles")
                        
                        print("=" * 80)
                    else:
                        print(f"Error: {history}")
                elif choice == 11:
                    date_str = input("Ingresa la fecha (YYYY-MM-DD): ")
                    rate = self.get_bcv_rate_by_date(date_str)
                    if isinstance(rate, dict) and "rate" in rate:
                        print("\n" + "=" * 80)
                        print(f"TASA BCV - {rate.get('date')}")
                        print("=" * 80)
                        print(f"Fecha: {rate.get('date')}")
                        print(f"Tasa: {rate.get('rate'):.2f} Bs")
                        print("=" * 80)
                    else:
                        print(f"Error: {rate}")
                elif choice == 12:
                    print("Saliendo del programa...")
                    break
                else:
                    print("Opción inválida. Por favor selecciona un número entre 1 y 12.")
                
                input("\nPresiona Enter para continuar...")
                
            except ValueError:
                print("Error: Por favor ingresa un número válido.")
                input("\nPresiona Enter para continuar...")
            except KeyboardInterrupt:
                print("\nSaliendo del programa...")
                break


def main():
    """Función principal"""
    monitor = ZinliMonitor()
    
    # Si hay argumentos de línea de comandos, ejecutar directamente
    if len(sys.argv) > 1:
        option = sys.argv[1].lower()
        if option == "all":
            monitor.display_all()
        elif option == "bcv":
            data = monitor.get_bcv_rate()
            if "formatted" in data:
                print(data["formatted"])
        elif option == "ves":
            data = monitor.get_binance_ves()
            if "error" not in data:
                print(monitor.binance_provider.formatear_salida(data))
        elif option == "zinli":
            data = monitor.get_binance_usd_zinli()
            if "error" not in data:
                print(monitor.binance_provider.formatear_salida(data))
        elif option == "syklo_ves":
            data = monitor.get_syklo_ves_usdc()
            if "error" not in data:
                print(monitor.syklo_provider.formatear_salida(data))
        elif option == "syklo_usd":
            data = monitor.get_syklo_usdc_usd()
            if "error" not in data:
                print(monitor.syklo_provider.formatear_salida(data))
        else:
            print(f"Opción desconocida: {option}")
            print("Opciones disponibles: all, bcv, ves, zinli, syklo_ves, syklo_usd")
    else:
        # Modo interactivo
        monitor.display_menu()


if __name__ == "__main__":
    main()
