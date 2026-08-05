#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Zinli Monitor - Aplicación de Escritorio
Estilo profesional basado en el ejemplo de OmenDashboard
"""

import sys
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QGridLayout, QTabWidget, QMessageBox,
    QTextEdit, QSpinBox, QDialog, QComboBox, QDateEdit
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QDate
from PyQt6.QtGui import QFont

# Agregar ruta del src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from zinli_monitor import ZinliMonitor


class ZinliMonitorDesktopApp(QWidget):
    """Aplicación principal de escritorio usando QWidget como el ejemplo"""
    
    def __init__(self):
        super().__init__()
        self.monitor = ZinliMonitor()
        self.init_ui()
        
    def init_ui(self):
        """Configura la interfaz de usuario usando el patrón del ejemplo"""
        # 1. Configuración de la Ventana Principal
        self.setWindowTitle("Dólar Monitor - Dashboard")
        self.resize(1000, 700)
        
        # Paleta de colores aplicada mediante QSS (Estilos tipo CSS)
        self.setStyleSheet("""
            QWidget {
                background-color: #030d16;  /* Azul oscuro profundo */
                font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
            }
            QFrame#Tarjeta {
                background-color: #061420;  /* Azul marino mate */
                border: 1px solid #102a3f;   /* Borde azul acero */
                border-radius: 6px;         /* Esquinas redondeadas */
            }
            QFrame#Tarjeta[clicable="true"] {
                border: 2px solid #667eea;   /* Borde más destacado para clickeables */
            }
            QFrame#Tarjeta[clicable="true"]:hover {
                background-color: #0a2a40;  /* Un poco más claro al hover */
            }
            QLabel {
                color: #d1d5db;             /* Gris claro para texto general */
                font-size: 13px;
                border: none;               /* Evita que hereden el borde del Frame */
                background-color: transparent;
            }
            QLabel#TituloSeccion {
                color: #ffffff;             /* Blanco para títulos */
                font-size: 14px;
                font-weight: bold;
            }
            QLabel#Valor {
                color: #d1d5db;
                font-size: 16px;
                font-weight: bold;
            }
            QLabel#Subtitulo {
                color: #8892b0;
                font-size: 11px;
            }
            QTextEdit {
                background-color: #061420;
                border: 1px solid #102a3f;
                border-radius: 6px;
                color: #d1d5db;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QSpinBox {
                background-color: #061420;
                color: #d1d5db;
                border: 1px solid #102a3f;
                border-radius: 4px;
                padding: 5px;
            }
            QPushButton {
                background-color: #061420;  /* Azul marino muy oscuro mate */
                color: #5c829e;             /* Azul celeste grisáceo/desaturado */
                border: 1px solid #102a3f; /* Azul acero opaco */
                border-radius: 4px;
                font-size: 14px;
                padding: 8px 0px;
            }
            QPushButton:hover {
                background-color: #102a3f;  /* Azul acero - aclara al borde */
                color: #ffffff;             /* Blanco puro al hover */
            }
            QPushButton:pressed {
                background-color: #030d16;  /* Azul oscuro profundo - efecto hundimiento */
            }
            QTabWidget::pane {
                background-color: #030d16;
                border: none;
            }
            QTabBar::tab {
                background-color: #061420;
                color: #8892b0;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #030d16;
                color: #ffffff;
                border-bottom: 2px solid #102a3f;
            }
        """)

        # Layout Principal (Vertical)
        layout_principal = QVBoxLayout()
        layout_principal.setContentsMargins(15, 0, 15, 15)  # Margen superior 0
        layout_principal.setSpacing(6)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setContentsMargins(0, 0, 0, 0)  # Sin márgenes
        
        # Tab Dashboard
        self.dashboard_tab = QWidget()
        self.setup_dashboard()
        self.tab_widget.addTab(self.dashboard_tab, "📊 Dashboard")
        
        # Tab Arbitraje
        self.arbitrage_tab = QWidget()
        self.setup_arbitrage()
        self.tab_widget.addTab(self.arbitrage_tab, "🔄 Arbitraje")
        
        # Tab Historial
        self.history_tab = QWidget()
        self.setup_history()
        self.tab_widget.addTab(self.history_tab, "📈 Historial")
        
        # Tab Estadísticas
        self.stats_tab = QWidget()
        self.setup_stats()
        self.tab_widget.addTab(self.stats_tab, "📊 Estadísticas")
        
        # Tab Análisis 24h
        self.analysis_24h_tab = QWidget()
        self.setup_24h_analysis()
        self.tab_widget.addTab(self.analysis_24h_tab, "⏰ Análisis 24h")
        
        layout_principal.addWidget(self.tab_widget)
        layout_principal.setSpacing(6)  # Reducir spacing entre tab widget y otros elementos

        # Footer global (siempre visible incluso al cambiar de pestañas)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(15, 5, 15, 5)

        self.lbl_last_updated = QLabel("Datos actualizados: --/--/----:--:--:--")
        self.lbl_last_updated.setObjectName("Subtitulo")

        lbl_copyright = QLabel("© 2026 Edwin López — Licensed under GNU GPL v3")
        lbl_copyright.setObjectName("Subtitulo")
        lbl_copyright.setAlignment(Qt.AlignmentFlag.AlignRight)

        footer_layout.addWidget(self.lbl_last_updated)
        footer_layout.addStretch()
        footer_layout.addWidget(lbl_copyright)

        layout_principal.addLayout(footer_layout)

        self.setLayout(layout_principal)
        
        # Cargar datos iniciales
        QTimer.singleShot(1000, self.refresh_dashboard)
    
    def setup_dashboard(self):
        """Configura el dashboard usando QFrame como el ejemplo"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)  # Margen superior reducido a 5px
        layout.setSpacing(18)  # Ajustado a 18px para separación limpia entre título y tarjetas

        # Título Centrado
        lbl_titulo = QLabel("📊 Dashboard de Tasas")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Grid de tarjetas usando QFrame
        cards_layout = QGridLayout()
        cards_layout.setSpacing(12)
        
        self.bcv_card = RateCard("💵 Tasa BCV", "--", "--")
        self.binance_ves_card = RateCard("📊 Binance VES", "--", "USDT/VES", clickable=True)
        self.binance_ves_card.clicked.connect(self.show_binance_ves_dialog)
        self.binance_usd_card = RateCard("💱 Binance USD (Zinli)", "--", "USDT/USD", clickable=True)
        self.binance_usd_card.clicked.connect(self.show_binance_usd_dialog)
        self.syklo_ves_card = RateCard("🔄 Syklo VES/USDC", "--", "VES → USDC", clickable=True)
        self.syklo_ves_card.clicked.connect(self.show_syklo_ves_dialog)
        self.syklo_usd_card = RateCard("💲 Syklo USDC/USD", "--", "USDC → USD", clickable=True)
        self.syklo_usd_card.clicked.connect(self.show_syklo_usd_dialog)
        
        cards_layout.addWidget(self.bcv_card, 0, 0)
        cards_layout.addWidget(self.binance_ves_card, 0, 1)
        cards_layout.addWidget(self.binance_usd_card, 0, 2)
        cards_layout.addWidget(self.syklo_ves_card, 1, 0)
        cards_layout.addWidget(self.syklo_usd_card, 1, 1)
        
        layout.addLayout(cards_layout)
        
        # Espaciador flexible para empujar todo hacia arriba
        layout.addStretch()

        # Botón de actualización (subido)
        btn_actualizar = QPushButton("Actualizar Datos")
        btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_actualizar.clicked.connect(self.refresh_dashboard)
        layout.addWidget(btn_actualizar)


        self.dashboard_tab.setLayout(layout)
    
    def setup_arbitrage(self):
        """Configura la pestaña de Arbitraje"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        # Título Centrado
        lbl_titulo = QLabel("🔄 Análisis de Arbitraje")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Área de texto para mostrar resultados
        self.arbitrage_text = QTextEdit()
        self.arbitrage_text.setReadOnly(True)
        self.arbitrage_text.setMinimumHeight(500)  # Altura aumentada para más líneas
        layout.addWidget(self.arbitrage_text)

        # Botón de análisis
        btn_analizar = QPushButton("Analizar Oportunidades")
        btn_analizar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_analizar.clicked.connect(self.analyze_arbitrage)
        layout.addWidget(btn_analizar)

        layout.addStretch()
        self.arbitrage_tab.setLayout(layout)
        
        # Cargar datos iniciales
        QTimer.singleShot(1500, self.analyze_arbitrage)
    
    def setup_history(self):
        """Configura la pestaña de Historial"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        # Título Centrado
        lbl_titulo = QLabel("📈 Historial BCV")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Selector de modo de búsqueda y controles dinámicos
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Modo:"))
        self.history_mode = QComboBox()
        self.history_mode.addItems([
            "Últimos N días",
            "Día específico",
            "Mes específico",
            "Mes en curso",
            "Año específico",
            "Año en curso",
        ])
        self.history_mode.setCurrentIndex(0)
        self.history_mode.currentIndexChanged.connect(self._on_history_mode_change)
        mode_layout.addWidget(self.history_mode)

        # Controles auxiliares (se muestran/ocultan según modo)
        # 1) SpinBox para N días
        self.days_label = QLabel("Período (días):")
        self.days_spinbox = QSpinBox()
        self.days_spinbox.setRange(1, 365)
        self.days_spinbox.setValue(30)
        mode_layout.addWidget(self.days_label)
        mode_layout.addWidget(self.days_spinbox)

        # 2) DateEdit para día específico
        self.date_label = QLabel("Fecha:")
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_label.setVisible(False)
        self.date_edit.setVisible(False)
        mode_layout.addWidget(self.date_label)
        mode_layout.addWidget(self.date_edit)

        # 3) Month/Year selectors para mes específico y año
        self.month_label = QLabel("Mes:")
        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setValue(QDate.currentDate().month())
        self.month_label.setVisible(False)
        self.month_spin.setVisible(False)
        mode_layout.addWidget(self.month_label)
        mode_layout.addWidget(self.month_spin)

        self.year_label = QLabel("Año:")
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(QDate.currentDate().year())
        self.year_label.setVisible(False)
        self.year_spin.setVisible(False)
        mode_layout.addWidget(self.year_label)
        mode_layout.addWidget(self.year_spin)

        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # Área de texto para mostrar historial
        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setMinimumHeight(500)  # Altura aumentada para más líneas
        layout.addWidget(self.history_text)

        # Botón de obtención
        btn_obtener = QPushButton("Obtener Historial")
        btn_obtener.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_obtener.clicked.connect(self.get_history)
        layout.addWidget(btn_obtener)

        layout.addStretch()
        self.history_tab.setLayout(layout)
    
    def setup_stats(self):
        """Configura la pestaña de Estadísticas"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        # Título Centrado
        lbl_titulo = QLabel("📊 Estadísticas")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Selector de horas
        hours_layout = QHBoxLayout()
        hours_layout.addWidget(QLabel("Período (horas):"))
        self.hours_spinbox = QSpinBox()
        self.hours_spinbox.setRange(1, 168)
        self.hours_spinbox.setValue(24)
        hours_layout.addWidget(self.hours_spinbox)
        hours_layout.addStretch()
        layout.addLayout(hours_layout)

        # Área de texto para mostrar estadísticas
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setMinimumHeight(500)  # Altura aumentada para más líneas
        layout.addWidget(self.stats_text)

        # Botón de cálculo
        btn_calcular = QPushButton("Calcular Estadísticas")
        btn_calcular.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_calcular.clicked.connect(self.get_stats)
        layout.addWidget(btn_calcular)

        layout.addStretch()
        self.stats_tab.setLayout(layout)
    
    def analyze_arbitrage(self):
        """Analiza oportunidades de arbitraje"""
        self.arbitrage_text.setText("Analizando oportunidades...")
        
        try:
            analysis = self.monitor.analyze_current_arbitrage()
            
            text = f"Timestamp: {analysis.get('timestamp', 'N/A')}\n"
            text += f"Total oportunidades: {analysis.get('total_opportunities', 0)}\n\n"
            
            if analysis.get('opportunities'):
                for i, opp in enumerate(analysis['opportunities'], 1):
                    text += f"{i}. {opp.get('type', '').upper()}\n"
                    text += f"   Descripción: {opp.get('description', 'N/A')}\n"
                    text += f"   Spread: {opp.get('spread_percent', 0):.2f}%\n"
                    text += f"   Recomendación: {opp.get('recommendation', 'N/A')}\n\n"
            else:
                text += "No se detectaron oportunidades de arbitraje significativas."
            
            self.arbitrage_text.setText(text)
        except Exception as e:
            self.arbitrage_text.setText(f"Error: {e}")
    
    def _extract_price(self, item: dict) -> Optional[float]:
        """Extrae el precio de un elemento histórico intentando varias claves conocidas."""
        if not isinstance(item, dict):
            return None
        for k in ("dollar", "USD", "rate", "price"):
            v = item.get(k)
            if v is None:
                continue
            try:
                return float(v)
            except Exception:
                try:
                    return float(str(v).replace(',', '.'))
                except Exception:
                    continue
        return None

    def _on_history_mode_change(self, index: int):
        """Muestra/oculta controles según modo seleccionado."""
        mode = self.history_mode.currentText()
        # Hide all auxiliary controls first
        self.days_label.setVisible(False)
        self.days_spinbox.setVisible(False)
        self.date_label.setVisible(False)
        self.date_edit.setVisible(False)
        self.month_label.setVisible(False)
        self.month_spin.setVisible(False)
        self.year_label.setVisible(False)
        self.year_spin.setVisible(False)

        if mode == "Últimos N días":
            self.days_label.setVisible(True)
            self.days_spinbox.setVisible(True)
        elif mode == "Día específico":
            self.date_label.setVisible(True)
            self.date_edit.setVisible(True)
        elif mode == "Mes específico":
            self.month_label.setVisible(True)
            self.month_spin.setVisible(True)
            self.year_label.setVisible(True)
            self.year_spin.setVisible(True)
        elif mode == "Mes en curso":
            # mostrar solo año/mes (mes fijado al actual)
            self.month_label.setVisible(False)
            self.month_spin.setVisible(False)
            self.year_label.setVisible(True)
            self.year_spin.setVisible(True)
            self.year_spin.setValue(QDate.currentDate().year())
            self.year_spin.setEnabled(False)
        elif mode == "Año específico":
            self.year_label.setVisible(True)
            self.year_spin.setVisible(True)
        elif mode == "Año en curso":
            self.year_label.setVisible(True)
            self.year_spin.setVisible(True)
            # Fijar año al actual y deshabilitar edición
            self.year_spin.setValue(QDate.currentDate().year())
            self.year_spin.setEnabled(False)
        else:
            self.days_label.setVisible(True)
            self.days_spinbox.setVisible(True)

    def get_history(self):
        """Obtiene historial BCV y soporta varios modos de consulta."""
        mode = self.history_mode.currentText()
        self.history_text.setText("Obteniendo historial...")

        try:
            # Preparar parámetros según modo
            if mode == "Últimos N días":
                days = self.days_spinbox.value()
                history = self.monitor.get_bcv_history(days)
                if not isinstance(history, dict):
                    # Muestra el error tal cual provenga del proveedor
                    self.history_text.setPlainText(f"Error obteniendo historial: {history}")
                    return
                rates = history.get('rates', []) or []
                start_date = history.get('start_date')
                end_date = history.get('end_date')
                title = f"Período: {start_date} a {end_date}    Total registros: {history.get('count', 0)}\nFuente: {history.get('source')}\n\n"

                # Reusar visualización previa (bloques horizontales)
                n = len(rates)
                BLOCK_SIZE = 15
                text = title
                if n == 0:
                    text += "No hay registros para el período solicitado.\n"
                elif n <= BLOCK_SIZE:
                    text += "Registros:\n"
                    for i, rate in enumerate(rates, 1):
                        price = self._extract_price(rate)
                        rate_str = f"{price:.2f}" if price is not None else (rate.get('USD', rate.get('dollar', 'N/A')) if isinstance(rate, dict) else str(rate))
                        text += f"{i}. {rate.get('date') if isinstance(rate, dict) else 'N/A'}: {rate_str} Bs\n"
                else:
                    text += f"Mostrando {n} registros.\n\n"
                    num_blocks = (n + BLOCK_SIZE - 1) // BLOCK_SIZE
                    for row in range(BLOCK_SIZE):
                        row_parts = []
                        any_in_row = False
                        for b in range(num_blocks):
                            idx = b * BLOCK_SIZE + row
                            if idx < n:
                                entry = rates[idx]
                                price = self._extract_price(entry)
                                rate_str = f"{price:.2f}" if price is not None else (entry.get('USD', entry.get('dollar', 'N/A')) if isinstance(entry, dict) else str(entry))
                                cell = f"{idx+1}. {entry.get('date') if isinstance(entry, dict) else 'N/A'}: {rate_str}"
                                any_in_row = True
                            else:
                                cell = ""
                            row_parts.append(cell.ljust(32))
                        if not any_in_row:
                            break
                        text += '  '.join(row_parts) + "\n"
                    text += "\n"

                # Estadísticas
                numeric_rates = [self._extract_price(r) for r in rates if self._extract_price(r) is not None]
                stats_html = ""
                if numeric_rates:
                    minimo = min(numeric_rates)
                    maximo = max(numeric_rates)
                    promedio = sum(numeric_rates) / len(numeric_rates)
                    try:
                        variacion = ((maximo - minimo) / minimo * 100)
                    except ZeroDivisionError:
                        variacion = 0.0
                    sign_variacion = f"{variacion:+.2f}%"
                    if variacion > 0:
                        color = "#10B981"
                        bg = "rgba(16,185,129,0.12)"
                    elif variacion < 0:
                        color = "#EF4444"
                        bg = "rgba(239,68,68,0.12)"
                    else:
                        color = "#9CA3AF"
                        bg = "transparent"
                    stats_html += "<br><b>Estadísticas:</b><br>"
                    stats_html += f"&nbsp;&nbsp;Mínimo: {minimo:.2f} Bs<br>"
                    stats_html += f"&nbsp;&nbsp;Máximo: {maximo:.2f} Bs<br>"
                    stats_html += f"&nbsp;&nbsp;Promedio: {promedio:.2f} Bs<br>"
                    stats_html += f"&nbsp;&nbsp;Variación: <span style=\"color:{color}; font-weight:700; background-color:{bg}; padding:2px 6px; border-radius:4px;\">{sign_variacion}</span><br>"

                html = f'<div style="font-family: monospace; color: #d1d5db;">'
                html += f'<pre style="white-space: pre-wrap; font-family: monospace;">{text}</pre>'
                html += stats_html
                html += '</div>'

                self.history_text.setHtml(html)

            elif mode == "Día específico":
                date_q = self.date_edit.date()
                date_str = date_q.toString("yyyy-MM-dd")
                result = self.monitor.get_bcv_rate_by_date(date_str)
                if isinstance(result, dict) and 'rate' in result:
                    price = result.get('rate')
                    src = result.get('source')
                    ts = result.get('timestamp')
                    out = f"Fecha: {date_str}    Precio: {float(price):.2f} Bs\nFuente: {src}\n"
                    self.history_text.setPlainText(out)
                else:
                    self.history_text.setPlainText(f"No se encontró dato para {date_str}: {result}")

            elif mode == "Mes específico":
                month = int(self.month_spin.value())
                year = int(self.year_spin.value())
                from calendar import monthrange
                start_date = f"{year}-{month:02d}-01"
                last_day = monthrange(year, month)[1]
                end_date = f"{year}-{month:02d}-{last_day:02d}"
                history = self.monitor.get_bcv_history(0, start_date, end_date)
                if not isinstance(history, dict):
                    self.history_text.setPlainText(f"Error obteniendo historial: {history}")
                    return
                rates = history.get('rates', []) or []

                # Construir listado y estadísticas
                text = f"Período: {start_date} a {end_date}    Total registros: {history.get('count', 0)}\nFuente: {history.get('source')}\n\n"
                lines = []
                numeric_rates = []
                for i, r in enumerate(rates, 1):
                    price = self._extract_price(r)
                    if price is not None:
                        numeric_rates.append(price)
                        rate_str = f"{price:.2f}"
                    else:
                        rate_str = (r.get('USD', r.get('dollar', 'N/A')) if isinstance(r, dict) else str(r))
                    lines.append(f"{i}. {r.get('date') if isinstance(r, dict) else 'N/A'}: {rate_str} Bs")

                # Estadísticas si hay datos numéricos
                stats_html = ""
                if numeric_rates:
                    minimo = min(numeric_rates)
                    maximo = max(numeric_rates)
                    promedio = sum(numeric_rates) / len(numeric_rates)
                    try:
                        variacion = ((maximo - minimo) / minimo * 100)
                    except ZeroDivisionError:
                        variacion = 0.0
                    sign_variacion = f"{variacion:+.2f}%"
                    if variacion > 0:
                        color = "#10B981"
                        bg = "rgba(16,185,129,0.12)"
                    elif variacion < 0:
                        color = "#EF4444"
                        bg = "rgba(239,68,68,0.12)"
                    else:
                        color = "#9CA3AF"
                        bg = "transparent"
                    stats_html += "<br><b>Estadísticas:</b><br>"
                    stats_html += f"&nbsp;&nbsp;Mínimo: {minimo:.2f} Bs<br>"
                    stats_html += f"&nbsp;&nbsp;Máximo: {maximo:.2f} Bs<br>"
                    stats_html += f"&nbsp;&nbsp;Promedio: {promedio:.2f} Bs<br>"
                    stats_html += f"&nbsp;&nbsp;Variación: <span style=\"color:{color}; font-weight:700; background-color:{bg}; padding:2px 6px; border-radius:4px;\">{sign_variacion}</span><br>"

                html = f'<div style="font-family: monospace; color: #d1d5db;">'
                html += f'<pre style="white-space: pre-wrap; font-family: monospace;">{text}'
                html += "\n".join(lines)
                html += '</pre>'
                html += stats_html
                html += '</div>'

                self.history_text.setHtml(html)

            elif mode == "Mes en curso":
                # Mes actual desde primer día hasta hoy
                today = QDate.currentDate()
                year = today.year()
                month = today.month()
                # Asegurar controles reflejen el mes/año actual para evitar residuos de consultas previas
                try:
                    self.year_spin.setValue(year)
                    self.month_spin.setValue(month)
                except Exception:
                    pass
                from calendar import monthrange
                start_date = f"{year}-{month:02d}-01"
                end_date = today.toString("yyyy-MM-dd")
                history = self.monitor.get_bcv_history(0, start_date, end_date)
                if not isinstance(history, dict):
                    self.history_text.setPlainText(f"Error obteniendo historial: {history}")
                    return
                rates = history.get('rates', []) or []

                text = f"Período: {start_date} a {end_date}    Total registros: {history.get('count', 0)}\nFuente: {history.get('source')}\n\n"
                lines = []
                numeric_rates = []
                for i, r in enumerate(rates, 1):
                    price = self._extract_price(r)
                    if price is not None:
                        numeric_rates.append(price)
                        rate_str = f"{price:.2f}"
                    else:
                        rate_str = (r.get('USD', r.get('dollar', 'N/A')) if isinstance(r, dict) else str(r))
                    lines.append(f"{i}. {r.get('date') if isinstance(r, dict) else 'N/A'}: {rate_str} Bs")

                # Estadísticas si hay datos numéricos
                stats_html = ""
                if numeric_rates:
                    minimo = min(numeric_rates)
                    maximo = max(numeric_rates)
                    promedio = sum(numeric_rates) / len(numeric_rates)
                    try:
                        variacion = ((maximo - minimo) / minimo * 100)
                    except ZeroDivisionError:
                        variacion = 0.0
                    sign_variacion = f"{variacion:+.2f}%"
                    if variacion > 0:
                        color = "#10B981"
                        bg = "rgba(16,185,129,0.12)"
                    elif variacion < 0:
                        color = "#EF4444"
                        bg = "rgba(239,68,68,0.12)"
                    else:
                        color = "#9CA3AF"
                        bg = "transparent"
                    stats_html += "<br><b>Estadísticas:</b><br>"
                    stats_html += f"&nbsp;&nbsp;Mínimo: {minimo:.2f} Bs<br>"
                    stats_html += f"&nbsp;&nbsp;Máximo: {maximo:.2f} Bs<br>"
                    stats_html += f"&nbsp;&nbsp;Promedio: {promedio:.2f} Bs<br>"
                    stats_html += f"&nbsp;&nbsp;Variación: <span style=\"color:{color}; font-weight:700; background-color:{bg}; padding:2px 6px; border-radius:4px;\">{sign_variacion}</span><br>"

                html = f'<div style="font-family: monospace; color: #d1d5db;">'
                html += f'<pre style="white-space: pre-wrap; font-family: monospace;">{text}'
                html += "\n".join(lines)
                html += '</pre>'
                html += stats_html
                html += '</div>'

                self.history_text.setHtml(html)

            elif mode in ("Año específico", "Año en curso"):
                year = int(self.year_spin.value())
                from datetime import datetime
                if mode == "Año en curso":
                    # asegurar selector refleje el año actual
                    current_year = datetime.now().year
                    try:
                        self.year_spin.setValue(current_year)
                    except Exception:
                        pass
                    start_date = f"{current_year}-01-01"
                    end_date = datetime.now().strftime("%Y-%m-%d")
                else:
                    start_date = f"{year}-01-01"
                    end_date = f"{year}-12-31"

                history = self.monitor.get_bcv_history(0, start_date, end_date)
                if not isinstance(history, dict):
                    self.history_text.setPlainText(f"Error obteniendo historial: {history}")
                    return
                rates = history.get('rates', []) or []

                # Agrupar por mes
                from collections import defaultdict
                months = defaultdict(list)
                for r in rates:
                    d = r.get('date') if isinstance(r, dict) else None
                    if not d:
                        continue
                    m = d[:7]  # YYYY-MM
                    months[m].append(r)

                # Construir tabla de estadísticas mensuales: primer día, último día, variación
                rows = []
                all_numeric = []
                for m in sorted(months.keys()):
                    month_rates = months[m]
                    # ordenar por fecha asc
                    month_rates.sort(key=lambda x: x.get('date'))
                    first = month_rates[0]
                    last = month_rates[-1]
                    p_first = self._extract_price(first)
                    p_last = self._extract_price(last)
                    if p_first is None or p_last is None:
                        continue
                    try:
                        var = ((p_last - p_first) / p_first) * 100
                    except ZeroDivisionError:
                        var = 0.0
                    rows.append((m, p_first, p_last, var))
                    all_numeric.extend([p_first, p_last])

                # Mapear nombres de meses en español
                months_es = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

                # Render HTML en tabla para mejor alineación
                html = '<div style="color: #d1d5db; font-family: sans-serif;">'
                display_year = datetime.now().year if mode == "Año en curso" else year
                html += f'<h3>Resumen por mes para {display_year}</h3>'
                html += '<table style="border-collapse: collapse; width: 100%; font-family: monospace; color:#d1d5db;">'
                html += '<tr style="border-bottom:1px solid #102a3f;"><th style="text-align:left; padding:6px 8px;">Mes</th><th style="text-align:right; padding:6px 8px;">Primer día</th><th style="text-align:right; padding:6px 8px;">Último día</th><th style="text-align:right; padding:6px 8px;">Variación</th></tr>'
                for m, p1, p2, var in rows:
                    y, mm = m.split('-')
                    mm_i = int(mm)
                    month_label = f"{months_es[mm_i-1]} de {y}"
                    sign = f"{var:+.2f}%"
                    color = '#10B981' if var>0 else '#EF4444' if var<0 else '#9CA3AF'
                    html += f"<tr><td style='padding:6px 8px;'>{month_label}</td><td style='text-align:right;padding:6px 8px;'>{p1:,.2f}</td><td style='text-align:right;padding:6px 8px;'>{p2:,.2f}</td><td style='text-align:right;padding:6px 8px;'><span style='color:{color}; font-weight:700;'>{sign}</span></td></tr>"
                html += '</table>'

                # Añadir estadísticas generales si hay datos
                if all_numeric:
                    minimo = min(all_numeric)
                    maximo = max(all_numeric)
                    promedio = sum(all_numeric) / len(all_numeric)
                    try:
                        variacion = ((maximo - minimo) / minimo * 100)
                    except ZeroDivisionError:
                        variacion = 0.0
                    sign_variacion = f"{variacion:+.2f}%"
                    if variacion > 0:
                        color = "#10B981"
                        bg = "rgba(16,185,129,0.08)"
                    elif variacion < 0:
                        color = "#EF4444"
                        bg = "rgba(239,68,68,0.08)"
                    else:
                        color = "#9CA3AF"
                        bg = "transparent"
                    html += '<div style="margin-top:12px;">'
                    html += '<b>Estadísticas generales del período:</b><br>'
                    html += f'&nbsp;&nbsp;Mínimo: {minimo:,.2f} Bs<br>'
                    html += f'&nbsp;&nbsp;Máximo: {maximo:,.2f} Bs<br>'
                    html += f'&nbsp;&nbsp;Promedio: {promedio:,.2f} Bs<br>'
                    html += f'&nbsp;&nbsp;Variación: <span style=\"color:{color}; font-weight:700; background-color:{bg}; padding:3px 8px; border-radius:4px;\">{sign_variacion}</span><br>'
                    html += '</div>'

                html += '</div>'
                self.history_text.setHtml(html)

            else:
                self.history_text.setPlainText('Modo no soportado')

        except Exception as e:
            self.history_text.setText(f"Error: {e}")
    
    def setup_24h_analysis(self):
        """Configura la pestaña de Análisis 24h"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        # Título Centrado
        lbl_titulo = QLabel("⏰ Análisis 24h - Binance VES")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Área de texto para mostrar análisis
        self.analysis_24h_text = QTextEdit()
        self.analysis_24h_text.setReadOnly(True)
        self.analysis_24h_text.setMinimumHeight(500)
        layout.addWidget(self.analysis_24h_text)

        # Botón de análisis
        btn_analizar = QPushButton("Analizar Últimas 24h")
        btn_analizar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_analizar.clicked.connect(self.analyze_24h)
        layout.addWidget(btn_analizar)

        layout.addStretch()
        self.analysis_24h_tab.setLayout(layout)
        
        # Cargar datos iniciales
        QTimer.singleShot(2000, self.analyze_24h)
    
    def analyze_24h(self):
        """Analiza las mejores horas para comprar y vender consolidadas por hora del día (00:00 a 23:59)"""
        self.analysis_24h_text.setText("Analizando datos históricos por hora del día...")
        
        try:
            from src.database import DatabaseManager
            db = DatabaseManager()
            
            # Obtener TODOS los registros históricos de Binance USDT/VES acumulados en la BD
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT side, avg_price, timestamp 
                FROM binance_p2p_prices 
                WHERE pair = 'USDT/VES' 
                ORDER BY timestamp ASC
            """)
            history = cursor.fetchall()
            conn.close()
            
            if not history:
                self.analysis_24h_text.setText(
                    "No hay datos históricos registrados aún en la base de datos.\n\n"
                    "Nota: El agente de bandeja de sistema (dolar_monitor_agent.py) recopila y guarda automáticamente "
                    "los precios cada 10 minutos al encender la PC para ir completando todas las horas del día."
                )
                return
            
            # Agrupar precios por hora del día (0 a 23)
            buy_by_hour = {}
            sell_by_hour = {}
            dates_found = set()
            
            from datetime import datetime
            
            for record in history:
                ts_str = record["timestamp"]
                # Formato ISO
                try:
                    dt = datetime.fromisoformat(ts_str)
                except ValueError:
                    continue
                
                hour = dt.hour
                dates_found.add(dt.strftime("%Y-%m-%d"))
                side = record["side"]
                price = record["avg_price"]
                
                if side == "BUY":
                    if hour not in buy_by_hour:
                        buy_by_hour[hour] = []
                    buy_by_hour[hour].append(price)
                elif side == "SELL":
                    if hour not in sell_by_hour:
                        sell_by_hour[hour] = []
                    sell_by_hour[hour].append(price)
            
            # Calcular promedios y conteos por hora
            buy_avg_by_hour = {}
            sell_avg_by_hour = {}
            
            for hour, prices in buy_by_hour.items():
                if prices:
                    buy_avg_by_hour[hour] = (sum(prices) / len(prices), len(prices))
            
            for hour, prices in sell_by_hour.items():
                if prices:
                    sell_avg_by_hour[hour] = (sum(prices) / len(prices), len(prices))
            
            # Cobertura de horas
            hours_covered = len(set(buy_by_hour.keys()).union(set(sell_by_hour.keys())))
            min_date = min(dates_found) if dates_found else "N/A"
            max_date = max(dates_found) if dates_found else "N/A"
            
            text = f"📊 ANÁLISIS DE MERCADO DIARIO (Binance USDT/VES)\n"
            text += f"Período analizado: {min_date} a {max_date} ({len(dates_found)} día(s) registrados)\n"
            text += f"Registros totales: {len(history)} | Horas cubiertas: {hours_covered}/24 h\n"
            text += "=" * 65 + "\n\n"
            
            # Mejores horas para COMPRAR (precio más bajo)
            if buy_avg_by_hour:
                text += "🟢 MEJORES HORAS PARA COMPRAR (Precio Promedio Más Bajo)\n"
                text += "-" * 65 + "\n"
                sorted_buy = sorted(buy_avg_by_hour.items(), key=lambda x: x[1][0])
                for i, (hour, (avg_price, count)) in enumerate(sorted_buy, 1):
                    text += f"{i:2d}. {hour:02d}:00 - {hour:02d}:59 → Promedio: {avg_price:.2f} VES  ({count} muestra(s))\n"
                text += "\n"
            else:
                text += "🟢 No hay datos de compra disponibles\n\n"
            
            # Mejores horas para VENDER (precio más alto)
            if sell_avg_by_hour:
                text += "🔴 MEJORES HORAS PARA VENDER (Precio Promedio Más Alto)\n"
                text += "-" * 65 + "\n"
                sorted_sell = sorted(sell_avg_by_hour.items(), key=lambda x: x[1][0], reverse=True)
                for i, (hour, (avg_price, count)) in enumerate(sorted_sell, 1):
                    text += f"{i:2d}. {hour:02d}:00 - {hour:02d}:59 → Promedio: {avg_price:.2f} VES  ({count} muestra(s))\n"
                text += "\n"
            else:
                text += "🔴 No hay datos de venta disponibles\n\n"
            
            # Calcular spread promedio por hora
            common_hours = set(buy_avg_by_hour.keys()).intersection(set(sell_avg_by_hour.keys()))
            if common_hours:
                text += "📈 MEJORES HORAS POR SPREAD (Margen entre Venta y Compra)\n"
                text += "-" * 65 + "\n"
                spreads = []
                for hour in common_hours:
                    b_avg, _ = buy_avg_by_hour[hour]
                    s_avg, _ = sell_avg_by_hour[hour]
                    spread = s_avg - b_avg
                    spread_pct = (spread / b_avg) * 100 if b_avg > 0 else 0
                    spreads.append((hour, spread, spread_pct))
                
                spreads.sort(key=lambda x: x[1], reverse=True)
                for i, (hour, spread, spread_pct) in enumerate(spreads, 1):
                    text += f"{i:2d}. {hour:02d}:00 - {hour:02d}:59 → Margen: {spread:+.2f} VES ({spread_pct:.2f}%)\n"
            
            self.analysis_24h_text.setText(text)
            
        except Exception as e:
            self.analysis_24h_text.setText(f"Error generando análisis: {e}\n\n{str(e)}")
    
    def get_stats(self):
        """Obtiene estadísticas"""
        hours = self.hours_spinbox.value()
        self.stats_text.setText(f"Calculando estadísticas de {hours} horas...")
        
        try:
            stats = self.monitor.get_statistics(hours)
            
            text = f"Puntos de datos: {stats.get('data_points', 0)}\n\n"
            
            if "error" not in stats:
                bcv = stats.get('bcv', {})
                text += "TASA BCV:\n"
                text += f"  Mín: {bcv.get('min', 'N/A')}\n"
                text += f"  Máx: {bcv.get('max', 'N/A')}\n"
                text += f"  Prom: {bcv.get('avg', 'N/A')}\n\n"
                
                ves_buy = stats.get('binance_ves_buy', {})
                text += "BINANCE VES BUY:\n"
                text += f"  Mín: {ves_buy.get('min', 'N/A')}\n"
                text += f"  Máx: {ves_buy.get('max', 'N/A')}\n"
                text += f"  Prom: {ves_buy.get('avg', 'N/A')}\n\n"
                
                ves_sell = stats.get('binance_ves_sell', {})
                text += "BINANCE VES SELL:\n"
                text += f"  Mín: {ves_sell.get('min', 'N/A')}\n"
                text += f"  Máx: {ves_sell.get('max', 'N/A')}\n"
                text += f"  Prom: {ves_sell.get('avg', 'N/A')}\n"
            else:
                text += f"Error: {stats.get('error', 'Unknown')}"
            
            self.stats_text.setText(text)
        except Exception as e:
            self.stats_text.setText(f"Error: {e}")
    
    def show_binance_ves_dialog(self):
        """Muestra diálogo con anuncios de Binance VES"""
        try:
            ves_info = self.monitor.get_binance_ves()
            dialog = BinanceAdsDialog("Binance P2P - USDT/VES", ves_info, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al obtener anuncios: {e}")
    
    def show_binance_usd_dialog(self):
        """Muestra diálogo con anuncios de Binance USD (Zinli)"""
        try:
            usd_info = self.monitor.get_binance_usd_zinli()
            dialog = BinanceAdsDialog("Binance P2P - USDT/USD (Zinli)", usd_info, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al obtener anuncios: {e}")
    
    def show_syklo_ves_dialog(self):
        """Muestra diálogo con datos de Syklo VES/USDC"""
        try:
            syklo_data = self.monitor.get_syklo_ves_usdc()
            dialog = SykloDialog("Syklo - VES/USDC", syklo_data, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al obtener datos: {e}")
    
    def show_syklo_usd_dialog(self):
        """Muestra diálogo con datos de Syklo USDC/USD"""
        try:
            syklo_data = self.monitor.get_syklo_usdc_usd()
            dialog = SykloDialog("Syklo - USDC/USD", syklo_data, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al obtener datos: {e}")
    
    def refresh_dashboard(self):
        """Actualiza los datos del dashboard"""
        try:
            data = self.monitor.get_all_data(save_to_db=True)
            
            # BCV
            bcv_data = data.get("bcv", {})
            if "error" not in bcv_data:
                bcv_rate = bcv_data.get("rate", "--")
                if bcv_rate != "--":
                    bcv_rate = float(bcv_rate)
                    # Calcular euro (1 EUR ≈ 1.08 USD)
                    euro_rate = bcv_rate * 1.08
                    self.bcv_card.update_value(f"${bcv_rate:.2f} Bs\n€{euro_rate:.2f} Bs")
                else:
                    self.bcv_card.update_value("--")
                self.bcv_card.update_subtitle(bcv_data.get("date", "--"))
            else:
                self.bcv_card.update_value("Error")
            
            # Binance VES
            ves_data = data.get("binance_ves", {})
            if "error" not in ves_data:
                buy_avg = ves_data.get("buy_stats", {}).get("avg_price", "--")
                sell_avg = ves_data.get("sell_stats", {}).get("avg_price", "--")
                if buy_avg != "--" and sell_avg != "--":
                    buy_avg = float(buy_avg)
                    sell_avg = float(sell_avg)
                    self.binance_ves_card.update_value(f"Buy: {buy_avg:.2f}\nSell: {sell_avg:.2f}")
                else:
                    self.binance_ves_card.update_value("--")
            else:
                self.binance_ves_card.update_value("Error")
            
            # Binance USD (Zinli)
            usd_data = data.get("binance_usd_zinli", {})
            if "error" not in usd_data:
                buy_avg = usd_data.get("buy_stats", {}).get("avg_price", "--")
                sell_avg = usd_data.get("sell_stats", {}).get("avg_price", "--")
                if buy_avg != "--" and sell_avg != "--":
                    buy_avg = float(buy_avg)
                    sell_avg = float(sell_avg)
                    self.binance_usd_card.update_value(f"Buy: ${buy_avg:.3f}\nSell: ${sell_avg:.3f}")
                else:
                    self.binance_usd_card.update_value("--")
            else:
                self.binance_usd_card.update_value("Error")
            
            # Syklo VES/USDC
            syklo_ves = data.get("syklo_ves_usdc", {})
            if "error" not in syklo_ves:
                orders = syklo_ves.get("orders", [])
                if orders and len(orders) > 0:
                    # Prefer avg_price returned by provider; fallback to computing average excluding small-range orders
                    best_rate = syklo_ves.get("avg_price") if syklo_ves.get("avg_price") is not None else None
                    if best_rate is None:
                        # compute with same rule: exclude orders with min>5 and max<20
                        def include_order_for_avg(o):
                            try:
                                min_v = float(o.get("min", "-")) if o.get("min", "-") not in (None, "-") else None
                            except Exception:
                                min_v = None
                            try:
                                max_v = float(o.get("max", "-")) if o.get("max", "-") not in (None, "-") else None
                            except Exception:
                                max_v = None
                            if (min_v is not None) and (max_v is not None) and (min_v > 5) and (max_v < 20):
                                return False
                            return True
                        prices = [float(o.get("price")) for o in orders if o.get("price") != "-" and include_order_for_avg(o)]
                        best_rate = (sum(prices) / len(prices)) if prices else None

                    if best_rate is not None:
                        self.syklo_ves_card.update_value(f"{best_rate:.2f} Bs")
                    else:
                        self.syklo_ves_card.update_value("--")
                else:
                    self.syklo_ves_card.update_value("--")
            else:
                self.syklo_ves_card.update_value("Error")
            
            # Syklo USDC/USD
            syklo_usd = data.get("syklo_usdc_usd", {})
            if "error" not in syklo_usd:
                orders = syklo_usd.get("orders", [])
                if orders and len(orders) > 0:
                    best_rate = orders[0].get("price", "--")
                    if best_rate != "--":
                        best_rate = float(best_rate)
                        self.syklo_usd_card.update_value(f"${best_rate:.3f}")
                    else:
                        self.syklo_usd_card.update_value("--")
                else:
                    self.syklo_usd_card.update_value("--")
            # Actualizar timestamp de última actualización
            now_str = datetime.now().strftime("%d/%m/%Y:%H:%M:%S")
            self.lbl_last_updated.setText(f"Datos actualizados: {now_str}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error actualizando: {e}")


class RateCard(QFrame):
    """Tarjeta usando QFrame como el ejemplo de OmenDashboard"""
    
    clicked = pyqtSignal()  # Señal para cuando se hace clic
    
    def __init__(self, title, value, subtitle, clickable=False):
        super().__init__()
        self.setObjectName("Tarjeta")
        self.clickable = clickable
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 15)
        layout.setSpacing(6)

        # Título
        lbl_titulo = QLabel(title)
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)
        layout.addSpacing(4)

        # Valor
        self.lbl_valor = QLabel(value)
        self.lbl_valor.setObjectName("Valor")
        self.lbl_valor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_valor)

        # Subtítulo
        self.lbl_subtitulo = QLabel(subtitle)
        self.lbl_subtitulo.setObjectName("Subtitulo")
        self.lbl_subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_subtitulo)
    
    def mousePressEvent(self, event):
        """Maneja el evento de clic"""
        if self.clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
    
    def update_value(self, new_value):
        """Actualiza el valor de la tarjeta"""
        self.lbl_valor.setText(str(new_value))
    
    def update_subtitle(self, new_subtitle):
        """Actualiza el subtítulo de la tarjeta"""
        self.lbl_subtitulo.setText(str(new_subtitle))


class BinanceAdsDialog(QDialog):
    """Diálogo para mostrar anuncios de Binance P2P"""
    
    def __init__(self, title, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self.data = data
        # Detectar moneda local y símbolo de precio
        if "Zinli" in title or "USD (Zinli)" in title:
            self.fiat_currency = "USD"
            self.price_currency = "USD"
        else:
            self.fiat_currency = "VES"
            self.price_currency = "VES"
        self.setup_ui()
        self.display_ads()
    
    def setup_ui(self):
        """Configura la interfaz del diálogo"""
        layout = QVBoxLayout()
        
        # Título
        title_label = QLabel(f"📊 {self.windowTitle()}")
        title_label.setObjectName("TituloSeccion")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addSpacing(10)
        
        # Área de texto para mostrar anuncios
        self.ads_text = QTextEdit()
        self.ads_text.setReadOnly(True)
        self.ads_text.setMinimumHeight(500)
        layout.addWidget(self.ads_text)
        
        # Botón cerrar
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(self.accept)
        layout.addWidget(btn_cerrar)
        
        self.setLayout(layout)
    
    def display_ads(self):
        """Muestra los anuncios en el diálogo"""
        import statistics
        
        text = ""
        
        # Anuncios de compra
        buy_ads = self.data.get("top_buy_ads", [])
        if buy_ads:
            text += "🟢 ANUNCIOS DE COMPRA (Top 5 - Comerciantes Verificados)\n"
            text += "=" * 60 + "\n\n"
            for i, ad in enumerate(buy_ads[:5], 1):
                merchant_name = ad.get('merchant_name', 'N/A')
                price = ad.get('price', 'N/A')
                available = ad.get('available_amount', 'N/A')
                min_amt = ad.get('min_amount', 'N/A')
                max_amt = ad.get('max_amount', 'N/A')
                user_type = ad.get('user_type', 'N/A')
                order_count = ad.get('order_count', 'N/A')
                completion_rate = ad.get('completion_rate', 'N/A')
                
                # Formatear precio con 2 decimales para VES, 3 para USD
                if price != 'N/A':
                    if self.fiat_currency == "VES":
                        price_str = f"{price:,.2f}"
                    else:
                        price_str = f"{price:,.3f}"
                else:
                    price_str = 'N/A'
                
                # Formatear disponible con 2 decimales
                if available != 'N/A':
                    available_str = f"{available:,.2f}"
                else:
                    available_str = 'N/A'
                
                # Formatear min/max sin decimales (en moneda local)
                if min_amt != 'N/A':
                    min_str = f"{min_amt:,.0f}"
                else:
                    min_str = 'N/A'
                
                if max_amt != 'N/A':
                    max_str = f"{max_amt:,.0f}"
                else:
                    max_str = 'N/A'
                
                text += f"{i}. {merchant_name}\n"
                text += f"   Precio: {price_str} {self.price_currency}\n"
                text += f"   Disponible: {available_str} USDT\n"
                text += f"   Min: {min_str} {self.fiat_currency}\n"
                text += f"   Max: {max_str} {self.fiat_currency}\n"
                text += f"   Tipo: {user_type}\n"
                text += f"   Órdenes/mes: {order_count}\n"
                if completion_rate != 'N/A':
                    text += f"   Tasa completitud: {completion_rate:.1f}%\n"
                else:
                    text += f"   Tasa completitud: N/A\n"
                text += "\n"
        else:
            text += "No hay anuncios de compra disponibles\n\n"
        
        # Anuncios de venta
        sell_ads = self.data.get("top_sell_ads", [])
        if sell_ads:
            # Título dinámico según el par
            if self.fiat_currency == "USD":
                sell_title = "🔴 ANUNCIOS DE VENTA (Top 5 - Todos los usuarios)"
            else:
                sell_title = "🔴 ANUNCIOS DE VENTA (Top 5 - Comerciantes Verificados)"
            text += f"{sell_title}\n"
            text += "=" * 60 + "\n\n"
            for i, ad in enumerate(sell_ads[:5], 1):
                merchant_name = ad.get('merchant_name', 'N/A')
                price = ad.get('price', 'N/A')
                available = ad.get('available_amount', 'N/A')
                min_amt = ad.get('min_amount', 'N/A')
                max_amt = ad.get('max_amount', 'N/A')
                user_type = ad.get('user_type', 'N/A')
                order_count = ad.get('order_count', 'N/A')
                completion_rate = ad.get('completion_rate', 'N/A')
                
                # Formatear precio con 2 decimales para VES, 3 para USD
                if price != 'N/A':
                    if self.fiat_currency == "VES":
                        price_str = f"{price:,.2f}"
                    else:
                        price_str = f"{price:,.3f}"
                else:
                    price_str = 'N/A'
                
                # Formatear disponible con 2 decimales
                if available != 'N/A':
                    available_str = f"{available:,.2f}"
                else:
                    available_str = 'N/A'
                
                # Formatear min/max sin decimales (en moneda local)
                if min_amt != 'N/A':
                    min_str = f"{min_amt:,.0f}"
                else:
                    min_str = 'N/A'
                
                if max_amt != 'N/A':
                    max_str = f"{max_amt:,.0f}"
                else:
                    max_str = 'N/A'
                
                text += f"{i}. {merchant_name}\n"
                text += f"   Precio: {price_str} {self.price_currency}\n"
                text += f"   Disponible: {available_str} USDT\n"
                text += f"   Min: {min_str} {self.fiat_currency}\n"
                text += f"   Max: {max_str} {self.fiat_currency}\n"
                text += f"   Tipo: {user_type}\n"
                text += f"   Órdenes/mes: {order_count}\n"
                if completion_rate != 'N/A':
                    text += f"   Tasa completitud: {completion_rate:.1f}%\n"
                else:
                    text += f"   Tasa completitud: N/A\n"
                text += "\n"
        else:
            text += "No hay anuncios de venta disponibles\n\n"
        
        # Calcular Spread entre mejor compra y mejor venta
        if buy_ads and sell_ads:
            # Mejor precio de compra (el más bajo de los vendedores)
            buy_prices = [ad.get('price', 0) for ad in buy_ads if ad.get('price') != 'N/A']
            # Mejor precio de venta (el más alto de los compradores)
            sell_prices = [ad.get('price', 0) for ad in sell_ads if ad.get('price') != 'N/A']
            
            if buy_prices and sell_prices:
                mejor_compra = min(buy_prices)  # Precio más bajo para comprar
                mejor_venta = max(sell_prices)  # Precio más alto para vender
                
                spread_porcentual = ((mejor_compra - mejor_venta) / mejor_venta) * 100
                
                # Formatear precios según moneda
                if self.fiat_currency == "VES":
                    compra_str = f"{mejor_compra:,.2f}"
                    venta_str = f"{mejor_venta:,.2f}"
                else:
                    compra_str = f"{mejor_compra:,.3f}"
                    venta_str = f"{mejor_venta:,.3f}"
                
                text += "📈 SPREAD DEL MERCADO\n"
                text += "=" * 60 + "\n"
                text += f"Mejor precio de compra: {compra_str} {self.price_currency}\n"
                text += f"Mejor precio de venta: {venta_str} {self.price_currency}\n"
                text += f"Spread porcentual: {spread_porcentual:.2f}%\n\n"
        
        # Estadísticas - Calcular desde los anuncios si el backend no lo hace
        buy_stats = self.data.get("buy_stats", {})
        sell_stats = self.data.get("sell_stats", {})
        
        # Calcular estadísticas de compra desde los anuncios
        if buy_ads:
            buy_prices = [ad.get('price', 0) for ad in buy_ads if ad.get('price') != 'N/A']
            if buy_prices:
                # Formatear según moneda
                if self.fiat_currency == "VES":
                    min_str = f"{min(buy_prices):,.2f}"
                    max_str = f"{max(buy_prices):,.2f}"
                    avg_str = f"{statistics.mean(buy_prices):,.2f}"
                    med_str = f"{statistics.median(buy_prices):,.2f}"
                else:
                    min_str = f"{min(buy_prices):,.3f}"
                    max_str = f"{max(buy_prices):,.3f}"
                    avg_str = f"{statistics.mean(buy_prices):,.3f}"
                    med_str = f"{statistics.median(buy_prices):,.3f}"
                
                text += "📊 ESTADÍSTICAS DE COMPRA\n"
                text += f"  Mínimo: {min_str} {self.price_currency}\n"
                text += f"  Máximo: {max_str} {self.price_currency}\n"
                text += f"  Promedio: {avg_str} {self.price_currency}\n"
                text += f"  Mediana: {med_str} {self.price_currency}\n\n"
            else:
                text += "📊 ESTADÍSTICAS DE COMPRA\n"
                text += "  No hay datos suficientes\n\n"
        elif "error" not in buy_stats:
            text += "📊 ESTADÍSTICAS DE COMPRA\n"
            text += f"  Mínimo: {buy_stats.get('min', 'N/A')}\n"
            text += f"  Máximo: {buy_stats.get('max', 'N/A')}\n"
            text += f"  Promedio: {buy_stats.get('avg', 'N/A')}\n"
            text += f"  Mediana: {buy_stats.get('median', 'N/A')}\n\n"
        
        # Calcular estadísticas de venta desde los anuncios
        if sell_ads:
            sell_prices = [ad.get('price', 0) for ad in sell_ads if ad.get('price') != 'N/A']
            if sell_prices:
                # Formatear según moneda
                if self.fiat_currency == "VES":
                    min_str = f"{min(sell_prices):,.2f}"
                    max_str = f"{max(sell_prices):,.2f}"
                    avg_str = f"{statistics.mean(sell_prices):,.2f}"
                    med_str = f"{statistics.median(sell_prices):,.2f}"
                else:
                    min_str = f"{min(sell_prices):,.3f}"
                    max_str = f"{max(sell_prices):,.3f}"
                    avg_str = f"{statistics.mean(sell_prices):,.3f}"
                    med_str = f"{statistics.median(sell_prices):,.3f}"
                
                text += "📊 ESTADÍSTICAS DE VENTA\n"
                text += f"  Mínimo: {min_str} {self.price_currency}\n"
                text += f"  Máximo: {max_str} {self.price_currency}\n"
                text += f"  Promedio: {avg_str} {self.price_currency}\n"
                text += f"  Mediana: {med_str} {self.price_currency}\n"
            else:
                text += "📊 ESTADÍSTICAS DE VENTA\n"
                text += "  No hay datos suficientes\n"
        elif "error" not in sell_stats:
            text += "📊 ESTADÍSTICAS DE VENTA\n"
            text += f"  Mínimo: {sell_stats.get('min', 'N/A')}\n"
            text += f"  Máximo: {sell_stats.get('max', 'N/A')}\n"
            text += f"  Promedio: {sell_stats.get('avg', 'N/A')}\n"
            text += f"  Mediana: {sell_stats.get('median', 'N/A')}\n"
        
        self.ads_text.setText(text)


class SykloDialog(QDialog):
    """Diálogo para mostrar datos de Syklo"""
    
    def __init__(self, title, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self.data = data
        # Detectar si es USDC/USD para usar 4 decimales
        self.decimals = 4 if "USDC/USD" in title else 2
        self.setup_ui()
        self.display_data()
    
    def setup_ui(self):
        """Configura la interfaz del diálogo"""
        layout = QVBoxLayout()
        
        # Título
        title_label = QLabel(f"🔄 {self.windowTitle()}")
        title_label.setObjectName("TituloSeccion")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addSpacing(10)
        
        # Área de texto para mostrar datos
        self.data_text = QTextEdit()
        self.data_text.setReadOnly(True)
        self.data_text.setMinimumHeight(500)
        layout.addWidget(self.data_text)
        
        # Botón cerrar
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(self.accept)
        layout.addWidget(btn_cerrar)
        
        self.setLayout(layout)
    
    def display_data(self):
        """Muestra los datos de Syklo"""
        text = ""
        
        orders = self.data.get("orders", [])
        if orders:
            text += f"Total órdenes disponibles: {len(orders)}\n"
            if self.data.get("description"):
                text += f"Descripción: {self.data.get('description')}\n"
            text += "=" * 60 + "\n\n"
            
            for i, order in enumerate(orders[:10], 1):  # Mostrar top 10
                price = order.get("price", "N/A")
                min_amount = order.get("min", "N/A")
                max_amount = order.get("max", "N/A")
                trader = order.get("trader", "N/A")
                method = order.get("method_full", order.get("method", "N/A"))
                
                # Formatear con decimales dinámicos
                if price != "N/A" and price != "-":
                    price_str = f"{float(price):,.{self.decimals}f}"
                else:
                    price_str = "N/A"
                
                if min_amount != "N/A" and min_amount != "-":
                    min_str = f"{float(min_amount):,.{self.decimals}f}"
                else:
                    min_str = "N/A"
                
                if max_amount != "N/A" and max_amount != "-":
                    max_str = f"{float(max_amount):,.{self.decimals}f}"
                else:
                    max_str = "N/A"
                
                text += f"{i}. Método: {method}\n"
                text += f"   Precio: {price_str}\n"
                text += f"   Mínimo: {min_str}\n"
                text += f"   Máximo: {max_str}\n"
                text += f"   Trader: {trader}\n"
                text += "\n"
        else:
            text += "No hay datos disponibles\n"
        
        self.data_text.setText(text)


def main():
    """Punto de entrada principal"""
    app = QApplication(sys.argv)
    
    window = ZinliMonitorDesktopApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()