#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Dólar Monitor - Agente de Bandeja de Sistema (Tray Agent)
Se ejecuta en segundo plano recopilando datos cada 10 minutos y guardándolos en la BD SQLite.
Muestra información de BCV (USD/EUR) y Binance (USDT/VES) en el tooltip y menú contextual.
"""

import sys
import os
import subprocess
from datetime import datetime

# Forzar directorio de trabajo al directorio del proyecto para rutas relativas correctas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Logging removed per user request

# Rutas del proyecto
SRC_DIR = os.path.join(BASE_DIR, 'src')
sys.path.insert(0, SRC_DIR)

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QTimer, Qt
from zinli_monitor import ZinliMonitor


def create_tray_icon():
    """Genera un icono dinámico de 64x64 en memoria con un diseño elegante de dólar ($)"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Fondo circular verde oscuro / esmeralda
    painter.setBrush(QColor("#0a382c"))
    painter.setPen(QColor("#00ff88"))
    painter.drawEllipse(2, 2, 60, 60)
    
    # Texto '$' en el centro
    font = QFont("Segoe UI", 34, QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "$")
    
    painter.end()
    return QIcon(pixmap)


class DolarMonitorTrayAgent:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        self.monitor = ZinliMonitor()
        
        # Crear la bandeja de sistema
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(create_tray_icon())
        self.tray.setToolTip("Dólar Monitor - Iniciando...")
        
        # Crear Menú Contextual
        self.menu = QMenu()
        
        self.header_action = self.menu.addAction("💵 Dólar Monitor - Agente")
        self.header_action.setEnabled(False)
        self.menu.addSeparator()
        
        self.bcv_usd_action = self.menu.addAction("💵 BCV USD: --")
        self.bcv_usd_action.setEnabled(False)
        
        self.bcv_eur_action = self.menu.addAction("💶 BCV EUR: --")
        self.bcv_eur_action.setEnabled(False)
        
        self.menu.addSeparator()
        
        self.binance_buy_action = self.menu.addAction("🟢 Binance Comprar: --")
        self.binance_buy_action.setEnabled(False)
        
        self.binance_sell_action = self.menu.addAction("🔴 Binance Vender: --")
        self.binance_sell_action.setEnabled(False)
        
        self.last_update_action = self.menu.addAction("⏱ Última actualización: --")
        self.last_update_action.setEnabled(False)
        
        self.menu.addSeparator()
        
        # Acciones interactivas
        self.refresh_action = self.menu.addAction("🔄 Actualizar Ahora")
        self.refresh_action.triggered.connect(self.collect_data)
        
        self.open_app_action = self.menu.addAction("📊 Abrir App Principal")
        self.open_app_action.triggered.connect(self.open_main_app)
        
        self.menu.addSeparator()
        
        self.quit_action = self.menu.addAction("❌ Salir")
        self.quit_action.triggered.connect(self.app.quit)
        
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray_icon_activated)
        self.tray.show()
        
        # Timer de 10 minutos (10 * 60 * 1000 ms)
        self.timer = QTimer()
        self.timer.setInterval(10 * 60 * 1000)
        self.timer.timeout.connect(self.collect_data)
        self.timer.start()
        
        # Recopilación inicial
        self.collect_data()

    def on_tray_icon_activated(self, reason):
        """Al hacer doble clic en el icono de la bandeja, abre la app principal"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_main_app()

    def open_main_app(self):
        """Abre desktop_app.py como proceso independiente"""
        desktop_app_path = os.path.join(BASE_DIR, "desktop_app.py")
        subprocess.Popen([sys.executable, desktop_app_path])

    def collect_data(self):
        """Obtiene datos de BCV y Binance VES, actualizando el menú y guardando en BD"""
        # logging disabled: iniciando recopilación de datos
        try:
            data = self.monitor.get_all_data(save_to_db=True)
            # logging disabled: datos obtenidos y guardados en BD
            now_str = datetime.now().strftime("%H:%M:%S")
            
            # BCV
            bcv_data = data.get("bcv", {})
            bcv_usd_str = "--"
            bcv_eur_str = "--"
            if "error" not in bcv_data:
                rate = bcv_data.get("rate", "--")
                if rate != "--":
                    r_val = float(rate)
                    bcv_usd_str = f"{r_val:.2f} Bs"
                    # Usar el valor real del euro de la API si está disponible
                    if "euro" in bcv_data and bcv_data.get("euro"):
                        eur_val = float(bcv_data.get("euro"))
                        bcv_eur_str = f"{eur_val:.2f} Bs"
                    else:
                        # Fallback al cálculo aproximado
                        bcv_eur_str = f"{r_val * 1.08:.2f} Bs"
            
            # Binance VES
            binance_data = data.get("binance_ves", {})
            buy_str = "--"
            sell_str = "--"
            if "error" not in binance_data:
                buy_avg = binance_data.get("buy_stats", {}).get("avg_price", "--")
                sell_avg = binance_data.get("sell_stats", {}).get("avg_price", "--")
                if buy_avg != "--":
                    buy_str = f"{float(buy_avg):.2f} VES"
                if sell_avg != "--":
                    sell_str = f"{float(sell_avg):.2f} VES"
            
            # Actualizar textos del menú
            self.bcv_usd_action.setText(f"💵 BCV USD: {bcv_usd_str}")
            self.bcv_eur_action.setText(f"💶 BCV EUR: {bcv_eur_str}")
            self.binance_buy_action.setText(f"🟢 Binance Comprar: {buy_str}")
            self.binance_sell_action.setText(f"🔴 Binance Vender: {sell_str}")
            self.last_update_action.setText(f"⏱ Actualizado: {now_str}")
            
            # Tooltip al pasar el mouse por el icono de la bandeja
            tooltip_text = (
                f"Dólar Monitor\n"
                f"BCV USD: {bcv_usd_str} | EUR: {bcv_eur_str}\n"
                f"Binance Compra: {buy_str}\n"
                f"Binance Venta: {sell_str}\n"
                f"Última act.: {now_str}"
            )
            self.tray.setToolTip(tooltip_text)
            # logging disabled: menú actualizado correctamente
            
        except Exception as e:
            # logging disabled: error en collect_data
            self.tray.setToolTip(f"Dólar Monitor - Error actualizando: {e}")

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    agent = DolarMonitorTrayAgent()
    agent.run()
