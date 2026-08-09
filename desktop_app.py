#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Zinli Monitor - Aplicación de Escritorio
Estilo profesional basado en el ejemplo de OmenDashboard
"""

import sys
import os
from datetime import datetime
import matplotlib
matplotlib.use('Agg')  # Backend no interactivo para evitar problemas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import pandas as pd
import requests
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QGridLayout, QTabWidget, QMessageBox,
    QTextEdit, QSpinBox, QDoubleSpinBox, QDialog, QComboBox, QDateEdit,
    QProgressDialog, QScrollArea, QCheckBox, QSizePolicy
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QDate, QThread, QObject
from PyQt6.QtGui import QFont, QPixmap

# Agregar ruta del src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from zinli_monitor import ZinliMonitor


class DataLoaderWorker(QObject):
    """Worker para cargar datos en un hilo separado"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
    
    def run(self):
        """Carga los datos en el hilo separado"""
        try:
            data = self.monitor.get_all_data(save_to_db=True)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Worker para cargar tasas en background desde la calculadora
# ──────────────────────────────────────────────────────────────────────────────
class RatesLoaderWorker(QObject):
    """Carga todas las tasas en un hilo separado"""
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor

    def run(self):
        try:
            data = self.monitor.get_all_data(save_to_db=False)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Calculadora de Cambio
# ──────────────────────────────────────────────────────────────────────────────
class CalculatorDialog(QDialog):
    """
    Calculadora de conversión VES → USD / EUR.
    Fuentes: BCV, EUR (BCV×1.08), Binance Compra, Syklo VES/USDC.
    Diseñada para embeberse como widget en una pestaña (no popup).
    """

    CURRENCY_SYMBOLS = {"VES": "Bs", "USD": "$", "EUR": "€"}

    # Ancho máximo del panel central (para centrado lateral)
    PANEL_MAX_WIDTH = 700

    def __init__(self, parent=None):
        super().__init__(parent)
        self.monitor      = parent.monitor
        self.rates        = {}   # { label: {"ves_per_usd"|"ves_per_eur": float, "icon": str, ...} }
        self._rates_ready = False
        self._init_ui()
        self._load_rates_async()

    # ──────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle("🧮 Calculadora de Cambio")

        self.setStyleSheet("""
            QDialog, QWidget#CalcPanel {
                background-color: #030d16;
            }
            QFrame#CalcCard {
                background-color: #061420;
                border: 1px solid #102a3f;
                border-radius: 8px;
            }
            QLabel#CalcTitle {
                color: #ffffff;
                font-size: 17px;
                font-weight: bold;
            }
            QLabel#SectionLabel {
                color: #8892b0;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QDoubleSpinBox, QComboBox {
                background-color: #0a1e30;
                color: #d1d5db;
                border: 1px solid #102a3f;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 14px;
                min-height: 32px;
            }
            QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid #667eea;
            }
            QComboBox QAbstractItemView {
                background-color: #061420;
                color: #d1d5db;
                selection-background-color: #102a3f;
            }
            QCheckBox {
                color: #d1d5db;
                font-size: 12px;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #102a3f;
                background: #0a1e30;
            }
            QCheckBox::indicator:checked {
                background: #667eea;
                border-color: #667eea;
            }
            QPushButton#CalcBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                min-height: 38px;
            }
            QPushButton#CalcBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7c93f0, stop:1 #8b5fbf);
            }
            QPushButton#CalcBtn:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5264cc, stop:1 #623d88);
            }
            QPushButton#ClearBtn {
                background-color: #061420;
                color: #8892b0;
                border: 1px solid #102a3f;
                border-radius: 6px;
                font-size: 12px;
                padding: 8px 18px;
            }
            QPushButton#ClearBtn:hover {
                color: #ffffff;
                border-color: #667eea;
            }
            QFrame#ResultCard {
                background-color: #061420;
                border: 1px solid #102a3f;
                border-radius: 8px;
            }
            QFrame#ResultCard[best="true"] {
                border: 1.5px solid #667eea;
                background-color: #0a1e30;
            }
            QLabel#CardName  { color: #8892b0; font-size: 11px; font-weight: bold; }
            QLabel#CardRate  { color: #667eea; font-size: 10px; }
            QLabel#CardValue { color: #ffffff;  font-size: 20px; font-weight: bold; }
            QLabel#CardBadge { color: #667eea;  font-size: 10px; font-weight: bold; }
            QLabel#StatusLabel {
                color: #8892b0;
                font-size: 11px;
                font-style: italic;
            }
        """)

        # ── Layout raiz: centra el panel horizontalmente ──────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        h_center = QHBoxLayout()
        h_center.setContentsMargins(0, 0, 0, 0)
        h_center.addStretch(1)

        # ── Panel central ──────────────────────────────────────────────
        panel = QWidget()
        panel.setObjectName("CalcPanel")
        panel.setMaximumWidth(self.PANEL_MAX_WIDTH)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(28, 24, 28, 24)
        inner.setSpacing(16)

        # Título
        title = QLabel("🧮 Calculadora de Cambio")
        title.setObjectName("CalcTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(title)

        # ── Fila de entrada ───────────────────────────────────────
        input_card = QFrame()
        input_card.setObjectName("CalcCard")
        input_row = QHBoxLayout(input_card)
        input_row.setContentsMargins(18, 14, 18, 14)
        input_row.setSpacing(14)

        # Modo de conversión
        self.is_ves_to_foreign = True  # True: VES -> USD/EUR | False: USD/EUR -> VES

        # Monto
        amount_col = QVBoxLayout()
        self.lbl_amount = QLabel("MONTO EN VES (Bs)")
        self.lbl_amount.setObjectName("SectionLabel")
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0.01, 1_000_000_000)
        self.amount_input.setValue(1000.0)
        self.amount_input.setDecimals(2)
        self.amount_input.setSingleStep(100)
        self.amount_input.setGroupSeparatorShown(True)
        self.amount_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        amount_col.addWidget(self.lbl_amount)
        amount_col.addWidget(self.amount_input)

        # Botón Switch / Swap
        self.btn_swap = QPushButton("⇄ Switch")
        self.btn_swap.setObjectName("ClearBtn")
        self.btn_swap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_swap.setToolTip("Cambiar sentido de conversión (VES ↔ Divisa)")
        self.btn_swap.clicked.connect(self._toggle_direction)

        # Moneda divisa: USD o EUR
        target_col = QVBoxLayout()
        self.lbl_target = QLabel("DIVISA (DESTINO)")
        self.lbl_target.setObjectName("SectionLabel")
        self.foreign_currency = QComboBox()
        self.foreign_currency.addItems(["USD", "EUR"])
        self.foreign_currency.currentTextChanged.connect(self._on_foreign_currency_changed)
        target_col.addWidget(self.lbl_target)
        target_col.addWidget(self.foreign_currency)

        input_row.addLayout(amount_col, 4)
        input_row.addWidget(self.btn_swap)
        input_row.addLayout(target_col, 2)
        inner.addWidget(input_card)

        # ── Fuentes de tasas ──────────────────────────────────────
        sources_card = QFrame()
        sources_card.setObjectName("CalcCard")
        sources_vbox = QVBoxLayout(sources_card)
        sources_vbox.setContentsMargins(18, 12, 18, 12)
        sources_vbox.setSpacing(10)

        lbl_src = QLabel("FUENTES DE TASA")
        lbl_src.setObjectName("SectionLabel")
        sources_vbox.addWidget(lbl_src)

        checks_row = QHBoxLayout()
        self.chk_bcv       = QCheckBox("💵 BCV")
        self.chk_eur       = QCheckBox("💶 Euro (BCV)")
        self.chk_binance   = QCheckBox("📈 Binance Compra")
        self.chk_syklo     = QCheckBox("🔄 Syklo Compra")
        for chk in (self.chk_bcv, self.chk_eur, self.chk_binance, self.chk_syklo):
            chk.setChecked(True)
            checks_row.addWidget(chk)
        checks_row.addStretch()
        sources_vbox.addLayout(checks_row)
        inner.addWidget(sources_card)

        # ── Botones ─────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.btn_calc = QPushButton("⚡ CALCULAR")
        self.btn_calc.setObjectName("CalcBtn")
        self.btn_calc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_calc.clicked.connect(self._calculate)

        btn_clear = QPushButton("🗑️ Limpiar")
        btn_clear.setObjectName("ClearBtn")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_results)

        btn_row.addWidget(self.btn_calc, 3)
        btn_row.addWidget(btn_clear, 1)
        inner.addLayout(btn_row)

        # ── Status ─────────────────────────────────────────────
        self.lbl_status = QLabel("⏳ Cargando tasas en segundo plano…")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(self.lbl_status)

        # ── Área de resultados (scroll) ──────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.results_container = QWidget()
        self.results_container.setStyleSheet("background: transparent;")
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(8)
        self.results_layout.addStretch()
        scroll.setWidget(self.results_container)
        inner.addWidget(scroll, 1)

        # Ensamblar centrándolo
        h_center.addWidget(panel)
        h_center.addStretch(1)
        root.addLayout(h_center)

    # ──────────────────────────────────────────────
    # Carga de tasas en background
    # ──────────────────────────────────────────────
    def _load_rates_async(self):
        self.btn_calc.setEnabled(False)
        self._rates_thread = QThread()
        self._rates_worker = RatesLoaderWorker(self.monitor)
        self._rates_worker.moveToThread(self._rates_thread)
        self._rates_thread.started.connect(self._rates_worker.run)
        self._rates_worker.finished.connect(self._on_rates_loaded)
        self._rates_worker.error.connect(self._on_rates_error)
        self._rates_worker.finished.connect(self._rates_thread.quit)
        self._rates_thread.finished.connect(self._rates_thread.deleteLater)
        self._rates_thread.start()

    def _on_rates_loaded(self, data):
        """Parsea las fuentes requeridas."""
        try:
            # 1. BCV → Bs/USD
            bcv_rate = None
            bcv_data = data.get("bcv", {})
            if "error" not in bcv_data:
                r = bcv_data.get("rate")
                if r and r != "--":
                    bcv_rate = float(r)
                    self.rates["BCV"] = {"ves_per_usd": bcv_rate, "icon": "💵", "is_eur": False}

            # 2. EUR: BCV × 1.08 → Bs/EUR
            if bcv_rate:
                eur_bs = bcv_rate * 1.08
                self.rates["Euro (BCV)"] = {"ves_per_eur": eur_bs, "icon": "💶", "is_eur": True}

            # 3. Binance Compra y Venta → Bs/USD
            ves_data = data.get("binance_ves", {})
            if "error" not in ves_data:
                buy = ves_data.get("buy_stats", {}).get("avg_price")
                sell = ves_data.get("sell_stats", {}).get("avg_price")
                if buy and buy != "--":
                    self.rates["Binance Compra"] = {"ves_per_usd": float(buy), "icon": "📈", "is_eur": False}
                if sell and sell != "--":
                    self.rates["Binance Venta"] = {"ves_per_usd": float(sell), "icon": "📉", "is_eur": False}

            # 4. Syklo VES/USDC → Bs/USDC (≈ Bs/USD)
            syklo_ves = data.get("syklo_ves_usdc", {})
            syklo_usdc_ves = data.get("syklo_usdc_ves", {})
            
            if "error" not in syklo_ves:
                avg = syklo_ves.get("avg_price")
                if avg is None:
                    prices = []
                    for o in syklo_ves.get("orders", []):
                        p = o.get("price")
                        if p and p not in ("-", "--"):
                            try:
                                prices.append(float(p))
                            except Exception:
                                pass
                    avg = sum(prices) / len(prices) if prices else None
                if avg:
                    self.rates["Syklo VES/USDC"] = {"ves_per_usd": float(avg), "icon": "🔄", "is_eur": False}
            
            if "error" not in syklo_usdc_ves:
                avg = syklo_usdc_ves.get("avg_price")
                if avg is None:
                    prices = []
                    for o in syklo_usdc_ves.get("orders", []):
                        p = o.get("price")
                        if p and p not in ("-", "--"):
                            try:
                                prices.append(float(p))
                            except Exception:
                                pass
                    avg = sum(prices) / len(prices) if prices else None
                if avg:
                    self.rates["Syklo Venta"] = {"ves_per_usd": float(avg), "icon": "📈", "is_eur": False}

            self._rates_ready = True
            self.lbl_status.setText(f"✅ Fuentes cargadas — listo para calcular")
            self.btn_calc.setEnabled(True)

        except Exception as e:
            self.lbl_status.setText(f"⚠️ Error parseando tasas: {e}")
            self.btn_calc.setEnabled(True)

    def _on_rates_error(self, msg):
        self.lbl_status.setText(f"⚠️ Error cargando tasas: {msg}")
        self.btn_calc.setEnabled(True)

    # ──────────────────────────────────────────────
    # Cálculo
    # ──────────────────────────────────────────────
    @staticmethod
    def _sym(currency):
        return CalculatorDialog.CURRENCY_SYMBOLS.get(currency, currency)

    @staticmethod
    def _fmt_es(val, decimals=2):
        """Formatea un número según el estándar en español (miles con punto, decimales con coma)."""
        s = f"{val:,.{decimals}f}"
        # Se intercambian las comas y los puntos usando una sustitución temporal
        return s.replace(",", "X").replace(".", ",").replace("X", ".")

    def _toggle_direction(self):
        """Alterna el sentido de conversión (VES -> Divisa <-> Divisa -> VES)."""
        self.is_ves_to_foreign = not self.is_ves_to_foreign
        foreign = self.foreign_currency.currentText()
        sym = self._sym(foreign)

        if self.is_ves_to_foreign:
            self.lbl_amount.setText("MONTO EN VES (Bs)")
            self.lbl_target.setText("DIVISA (DESTINO)")
            self.chk_binance.setText("📈 Binance Compra")
            self.chk_syklo.setText("🔄 Syklo Compra")
            if self.amount_input.value() < 100:
                self.amount_input.setValue(1000.0)
        else:
            self.lbl_amount.setText(f"MONTO EN {foreign} ({sym})")
            self.lbl_target.setText("CONVERTIR A: VES (Bs)")
            self.chk_binance.setText("📈 Binance Venta")
            self.chk_syklo.setText("🔄 Syklo Venta")
            if self.amount_input.value() >= 1000:
                self.amount_input.setValue(100.0)

        self._clear_results()

    def _on_foreign_currency_changed(self, foreign):
        if not self.is_ves_to_foreign:
            sym = self._sym(foreign)
            self.lbl_amount.setText(f"MONTO EN {foreign} ({sym})")
        self._clear_results()

    def _clear_results(self):
        """Limpia el área de resultados sin cerrar la calculadora."""
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.lbl_status.setText("🗑️ Resultados limpiados.")

    def _calculate(self):
        """Convierte VES ↔ Divisa (USD/EUR) según la dirección activa y las fuentes seleccionadas."""
        amount  = self.amount_input.value()
        foreign = self.foreign_currency.currentText()  # "USD" o "EUR"
        sym_f   = self._sym(foreign)

        if not self.rates:
            self.lbl_status.setText("⚠️ Tasas no disponibles todavía, espera un momento.")
            return

        binance_key = "Binance Compra" if self.is_ves_to_foreign else "Binance Venta"
        syklo_key = "Syklo VES/USDC" if self.is_ves_to_foreign else "Syklo Venta"

        # Filtro de fuentes activas
        source_filter = {
            "BCV":            self.chk_bcv.isChecked(),
            "Euro (BCV)":     self.chk_eur.isChecked(),
            binance_key:      self.chk_binance.isChecked(),
            syklo_key:        self.chk_syklo.isChecked(),
        }

        results = []  # [(nombre, icono, valor_convertido, tasa_str)]
        for name, info in self.rates.items():
            if not source_filter.get(name, False):
                continue

            if info.get("is_eur"):
                if foreign != "EUR":
                    continue
                vpe = info["ves_per_eur"]
                if self.is_ves_to_foreign:
                    converted = amount / vpe
                else:
                    converted = amount * vpe
                rate_str = f"1 € = {self._fmt_es(vpe)} Bs"
            else:
                if foreign == "EUR":
                    continue
                vpu = info["ves_per_usd"]
                if self.is_ves_to_foreign:
                    converted = amount / vpu
                else:
                    converted = amount * vpu
                rate_str = f"1 USD = {self._fmt_es(vpu)} Bs"

            results.append((name, info["icon"], converted, rate_str))

        # Limpiar resultados anteriores
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not results:
            lbl = QLabel(f"⚠️ No hay fuentes seleccionadas para esta conversión.")
            lbl.setStyleSheet("color:#8892b0; font-size:12px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            self.results_layout.insertWidget(0, lbl)
            return

        # Ordenamiento:
        # - VES -> Divisa: mayor resultado primero (más divisa por los Bs)
        # - Divisa -> VES: menor resultado si vas a pagar/vender o mayor si recibes Bs.
        #   Normalmente se busca obtener la mayor cantidad de Bs posibles por la divisa.
        results.sort(key=lambda r: r[2], reverse=True)

        best_val  = results[0][2]
        worst_val = results[-1][2]

        if self.is_ves_to_foreign:
            header_text = f"Convirtiendo {self._fmt_es(amount)} Bs → {foreign}"
            display_sym = sym_f
        else:
            header_text = f"Convirtiendo {self._fmt_es(amount)} {sym_f} → VES (Bs)"
            display_sym = "Bs"

        header = QLabel(header_text)
        header.setStyleSheet("color:#8892b0; font-size:11px; padding-bottom:4px;")
        self.results_layout.insertWidget(0, header)

        for idx, (name, icon, value, rate_str) in enumerate(results):
            is_best  = (idx == 0)
            is_worst = (idx == len(results) - 1 and len(results) > 1)
            display  = f"{self._fmt_es(value)} {display_sym}"
            card = self._make_result_card(
                name=f"{icon}  {name}",
                value=display,
                rate_str=rate_str,
                is_best=is_best,
                is_worst=is_worst,
            )
            self.results_layout.insertWidget(idx + 1, card)

        if len(results) >= 2 and worst_val and worst_val != 0:
            spread = abs((best_val - worst_val) / worst_val) * 100
            lbl_spread = QLabel(f"📐 Spread mejor/peor: {self._fmt_es(spread)}%")
            lbl_spread.setStyleSheet("color:#8892b0; font-size:11px; padding-top:4px;")
            self.results_layout.insertWidget(len(results) + 1, lbl_spread)

        self.lbl_status.setText(f"✅ Conversión completada: {header_text}")

    # ──────────────────────────────────────────────
    # Tarjeta de resultado
    # ──────────────────────────────────────────────
    def _make_result_card(self, name, value, rate_str, is_best, is_worst):
        card = QFrame()
        card.setObjectName("ResultCard")
        if is_best:
            card.setProperty("best", "true")
            card.style().unpolish(card)
            card.style().polish(card)

        row = QHBoxLayout(card)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(14)

        left = QVBoxLayout()
        lbl_name = QLabel(name)
        lbl_name.setObjectName("CardName")
        lbl_rate = QLabel(rate_str)
        lbl_rate.setObjectName("CardRate")
        left.addWidget(lbl_name)
        left.addWidget(lbl_rate)
        row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_value = QLabel(value)
        lbl_value.setObjectName("CardValue")
        lbl_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(lbl_value)

        badges = QHBoxLayout()
        badges.setAlignment(Qt.AlignmentFlag.AlignRight)
        if is_best:
            b = QLabel("⭐ MEJOR")
            b.setObjectName("CardBadge")
            badges.addWidget(b)
        elif is_worst:
            b = QLabel("⬇ PEOR")
            b.setStyleSheet("color:#8892b0; font-size:10px; font-weight:bold;")
            badges.addWidget(b)
        right.addLayout(badges)
        row.addLayout(right)

        return card



class ZinliMonitorDesktopApp(QWidget):
    """Aplicación principal de escritorio usando QWidget como el ejemplo"""
    
    def __init__(self):
        super().__init__()
        self.monitor = ZinliMonitor()
        
        # Diálogo de carga
        self.loading_dialog = QProgressDialog("Cargando registros...", None, 0, 0, self)
        self.loading_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.loading_dialog.setCancelButton(None)
        self.loading_dialog.setAutoClose(False)
        self.loading_dialog.setWindowTitle("")
        self.loading_dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        
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
        
        # Tab Proyecciones
        self.projections_tab = QWidget()
        self.setup_projections()
        self.tab_widget.addTab(self.projections_tab, "🔮 Proyecciones")

        # Tab Calculadora
        self.calculator_tab = QWidget()
        self.setup_calculator_tab()
        self.tab_widget.addTab(self.calculator_tab, "🧮 Calculadora")

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
        
        # Cargar datos iniciales con un pequeño delay para asegurar que la ventana esté visible
        QTimer.singleShot(100, self.show_loading_dialog)
    
    def show_loading_dialog(self):
        """Muestra el diálogo de carga y carga los datos en un hilo separado"""
        # Usar un método diferente para asegurar que aparezca en primer plano
        self.loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.loading_dialog.show()
        self.loading_dialog.raise_()
        self.loading_dialog.activateWindow()
        # Procesar eventos para asegurar que se muestre
        QApplication.processEvents()
        
        # Crear worker y thread para cargar datos en background
        self.data_thread = QThread()
        self.data_worker = DataLoaderWorker(self.monitor)
        self.data_worker.moveToThread(self.data_thread)
        
        # Conectar señales
        self.data_thread.started.connect(self.data_worker.run)
        self.data_worker.finished.connect(self.on_data_loaded)
        self.data_worker.error.connect(self.on_data_error)
        self.data_worker.finished.connect(self.data_thread.quit)
        self.data_thread.finished.connect(self.data_thread.deleteLater)
        
        # Iniciar el thread
        self.data_thread.start()
    
    @staticmethod
    def fmt_es(val, decimals=2):
        """Formatea un número según el estándar en español (miles con punto, decimales con coma)."""
        if val is None or val == "--":
            return "--"
        try:
            v = float(val)
            s = f"{v:,.{decimals}f}"
            return s.replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return str(val)

    def on_data_loaded(self, data):
        """Callback cuando los datos se cargan exitosamente"""
        try:
            # BCV
            bcv_data = data.get("bcv", {})
            if "error" not in bcv_data:
                bcv_rate = bcv_data.get("rate", "--")
                if bcv_rate != "--":
                    bcv_rate = float(bcv_rate)
                    euro_rate = bcv_rate * 1.08
                    self.bcv_card.update_value(f"${self.fmt_es(bcv_rate)} Bs\n€{self.fmt_es(euro_rate)} Bs")
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
                    self.binance_ves_card.update_value(f"Buy: {self.fmt_es(buy_avg)}\nSell: {self.fmt_es(sell_avg)}")
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
                    self.binance_usd_card.update_value(f"Buy: ${self.fmt_es(buy_avg, 3)}\nSell: ${self.fmt_es(sell_avg, 3)}")
                else:
                    self.binance_usd_card.update_value("--")
            else:
                self.binance_usd_card.update_value("Error")
            
            # Syklo VES/USDC - mostrar compra y venta
            syklo_ves = data.get("syklo_ves_usdc", {})
            syklo_usdc_ves = data.get("syklo_usdc_ves", {})
            
            if "error" not in syklo_ves and "error" not in syklo_usdc_ves:
                buy_avg = syklo_ves.get("avg_price")
                sell_avg = syklo_usdc_ves.get("avg_price")
                
                if buy_avg is None:
                    prices = []
                    for o in syklo_ves.get("orders", []):
                        p = o.get("price")
                        if p and p not in ("-", "--"):
                            try:
                                prices.append(float(p))
                            except Exception:
                                pass
                    buy_avg = sum(prices) / len(prices) if prices else None
                
                if sell_avg is None:
                    prices = []
                    for o in syklo_usdc_ves.get("orders", []):
                        p = o.get("price")
                        if p and p not in ("-", "--"):
                            try:
                                prices.append(float(p))
                            except Exception:
                                pass
                    sell_avg = sum(prices) / len(prices) if prices else None
                
                if buy_avg and sell_avg:
                    self.syklo_ves_card.update_value(f"Buy: {self.fmt_es(buy_avg)}\nSell: {self.fmt_es(sell_avg)}")
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
                        self.syklo_usd_card.update_value(f"${self.fmt_es(best_rate, 4)}")
                    else:
                        self.syklo_usd_card.update_value("--")
                else:
                    self.syklo_usd_card.update_value("--")
            else:
                self.syklo_usd_card.update_value("Error")
            
            # Actualizar timestamp de última actualización
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.lbl_last_updated.setText(f"Datos actualizados: {now_str}")
            
            # Cerrar diálogo de carga
            self.loading_dialog.close()
            
        except Exception as e:
            self.loading_dialog.close()
            QMessageBox.critical(self, "Error", f"Error actualizando datos: {e}")
    
    def on_data_error(self, error_msg):
        """Callback cuando hay un error cargando datos"""
        self.loading_dialog.close()
        QMessageBox.critical(self, "Error", f"Error cargando datos: {error_msg}")
    
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
        
        self.bcv_card = RateCard("💵 Tasa BCV", "--", "--", clickable=True)
        self.bcv_card.clicked.connect(self.show_bcv_dialog)
        self.binance_ves_card = RateCard("📊 Binance VES", "--", "USDT/VES", clickable=True)
        self.binance_ves_card.clicked.connect(self.show_binance_ves_dialog)
        self.binance_usd_card = RateCard("💱 Binance USD (Zinli)", "--", "USDT/USD", clickable=True)
        self.binance_usd_card.clicked.connect(self.show_binance_usd_dialog)
        self.syklo_ves_card = RateCard("🔄 Syklo VES/USDC", "--", "VES ↔ USDC", clickable=True)
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
            self.year_spin.setEnabled(True)  # siempre re-habilitar
            self.year_spin.setVisible(True)
        elif mode == "Mes en curso":
            # mostrar solo año (mes fijado al actual)
            self.month_label.setVisible(False)
            self.month_spin.setVisible(False)
            self.year_label.setVisible(True)
            self.year_spin.setEnabled(True)  # siempre re-habilitar
            self.year_spin.setVisible(True)
            self.year_spin.setValue(QDate.currentDate().year())
        elif mode == "Año específico":
            self.year_label.setVisible(True)
            self.year_spin.setEnabled(True)  # siempre re-habilitar
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
                    self.history_text.setPlainText(f"Error obteniendo historial: {history}")
                    return
                raw_rates = history.get('rates', []) or []
                start_date = history.get('start_date')
                end_date = history.get('end_date')

                # Normalizar: construir un único registro por fecha en el rango (más reciente por fecha)
                from datetime import datetime, timedelta
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                except Exception:
                    # si no vienen fechas, usar última N fechas encontradas
                    start_dt = None
                    end_dt = None

                # Map date -> last entry
                last_by_date = {}
                for entry in raw_rates:
                    d = None
                    if isinstance(entry, dict):
                        d = entry.get('date') or entry.get('fecha')
                    if not d:
                        continue
                    last_by_date[d] = entry  # override: keeps last occurrence

                # Build ordered list of dates in range
                dates = []
                if start_dt and end_dt:
                    cur = start_dt
                    while cur <= end_dt:
                        dates.append(cur.strftime("%Y-%m-%d"))
                        cur += timedelta(days=1)
                else:
                    # fallback: unique sorted dates present
                    dates = sorted(last_by_date.keys())

                # Create list of one entry per date (may be missing)
                rates = []
                for d in dates:
                    e = last_by_date.get(d)
                    if e:
                        rates.append(e)
                    else:
                        rates.append({'date': d, 'USD': None})

                n = len(rates)
                BLOCK_SIZE = 15
                title = f"Período: {start_date} a {end_date}\n"
                title += f"Total registros esperados: {days}\n"
                title += f"Fuente: {history.get('source')}\n"
                title += f"Mostrando {n} registros (uno por fecha del rango)\n\n"

                # Si pocos registros, mostrar línea por línea (usar HTML <br> para evitar interlineado)
                if n == 0:
                    body = "No hay registros para el período solicitado.<br>"
                elif n <= BLOCK_SIZE:
                    lines = []
                    for i, rate in enumerate(rates, 1):
                        price = self._extract_price(rate)
                        rate_str = f"{price:.2f}" if price is not None else "-"
                        lines.append(f"{i}. {rate.get('date')}: {rate_str} Bs")
                    body = "<br>".join(lines) + "<br>"
                else:
                    # Renderizar en una tabla HTML con columnas = num_blocks para garantizar alineación
                    num_blocks = (n + BLOCK_SIZE - 1) // BLOCK_SIZE
                    grid = [["" for _ in range(num_blocks)] for _ in range(BLOCK_SIZE)]
                    for idx, entry in enumerate(rates):
                        b = idx // BLOCK_SIZE
                        r = idx % BLOCK_SIZE
                        price = self._extract_price(entry)
                        rate_str = f"{price:.2f}" if price is not None else "-"
                        grid[r][b] = f"{idx+1}. {entry.get('date')}: {rate_str} Bs"

                    rows_html = []
                    for r in range(BLOCK_SIZE):
                        cols_html = []
                        any_in_row = False
                        for c in range(num_blocks):
                            cell = grid[r][c]
                            if cell:
                                any_in_row = True
                                cols_html.append(f'<td style="padding:1px 6px; vertical-align:top; font-family: monospace; white-space:nowrap;">{cell}</td>')
                            else:
                                cols_html.append('<td style="padding:1px 6px; vertical-align:top;">&nbsp;</td>')
                            # separador horizontal entre columnas (excepto tras la última)
                            if c < num_blocks - 1:
                                cols_html.append('<td style="width:100px;"></td>')
                        if not any_in_row:
                            break
                        rows_html.append('<tr style="line-height:1.1;">' + ''.join(cols_html) + '</tr>')

                    body = f'<table style="border-collapse:collapse;">' + ''.join(rows_html) + '</table>'

                # Estadísticas con los valores numéricos disponibles
                numeric_rates = [self._extract_price(r) for r in rates if self._extract_price(r) is not None]
                stats_html = ''
                if numeric_rates:
                    minimo = min(numeric_rates)
                    maximo = max(numeric_rates)
                    promedio = sum(numeric_rates) / len(numeric_rates)
                    try:
                        variacion = ((maximo - minimo) / minimo * 100)
                    except ZeroDivisionError:
                        variacion = 0.0
                    sign_variacion = f'{variacion:+.2f}%'
                    if variacion > 0:
                        color = '#10B981'
                        bg = 'rgba(16,185,129,0.12)'
                    elif variacion < 0:
                        color = '#EF4444'
                        bg = 'rgba(239,68,68,0.12)'
                    else:
                        color = '#9CA3AF'
                        bg = 'transparent'
                    stats_html = (
                        '<div style="margin-top:10px; line-height:1.6;">'
                        '<b>Estadísticas:</b><br>'
                        f'&nbsp;&nbsp;Mínimo: {minimo:.2f} Bs<br>'
                        f'&nbsp;&nbsp;Máximo: {maximo:.2f} Bs<br>'
                        f'&nbsp;&nbsp;Promedio: {promedio:.2f} Bs<br>'
                        f'&nbsp;&nbsp;Variación: <span style="color:{color}; font-weight:700; background-color:{bg}; padding:2px 7px; border-radius:4px;">{sign_variacion}</span><br>'
                        '</div>'
                    )

                html = '<div style="color:#d1d5db; font-family: sans-serif; line-height:1.1;">'
                html += f'<pre style="font-family: monospace; color:#d1d5db; background:transparent; border:none; line-height:1.4;">{title}</pre>'
                html += body
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
                raw_rates = history.get('rates', []) or []

                # Agrupar por fecha (usar la última entrada por fecha)
                last_by_date = {}
                for entry in raw_rates:
                    if not isinstance(entry, dict):
                        continue
                    d = entry.get('date')
                    if not d:
                        continue
                    last_by_date[d] = entry

                # Generar lista de fechas del mes
                from datetime import datetime, timedelta
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                dates = []
                cur = start_dt
                while cur <= end_dt:
                    dates.append(cur.strftime("%Y-%m-%d"))
                    cur += timedelta(days=1)

                # Construir lista de un registro por fecha (None si faltante)
                rates = [last_by_date.get(d) or {'date': d, 'USD': None} for d in dates]

                # Render en bloques horizontales (BLOCK_SIZE = 15)
                n = len(rates)
                BLOCK_SIZE = 15
                title_html = f'<div style="color:#d1d5db; font-family: sans-serif;"><b>Período: {start_date} a {end_date}</b><br>Fuente: {history.get("source")}<br>Total fechas: {n} — Registros encontrados: {history.get("count", 0)}<br><br>'

                if n == 0:
                    body_html = "No hay registros para el período solicitado."
                elif n <= BLOCK_SIZE:
                    lines = []
                    for i, rate in enumerate(rates, 1):
                        price = self._extract_price(rate)
                        rate_str = f"{price:.2f}" if price is not None else "-"
                        lines.append(f"{i}. {rate.get('date')}: {rate_str} Bs")
                    body_html = "<br>".join(lines)
                else:
                    num_blocks = (n + BLOCK_SIZE - 1) // BLOCK_SIZE
                    grid = [["" for _ in range(num_blocks)] for _ in range(BLOCK_SIZE)]
                    for idx, entry in enumerate(rates):
                        b = idx // BLOCK_SIZE
                        r = idx % BLOCK_SIZE
                        price = self._extract_price(entry)
                        rate_str = f"{price:.2f}" if price is not None else "-"
                        grid[r][b] = f"{idx+1}. {entry.get('date')}: {rate_str} Bs"

                    rows_html = []
                    for r in range(BLOCK_SIZE):
                        cols_html = []
                        any_in_row = False
                        for c in range(num_blocks):
                            cell = grid[r][c]
                            if cell:
                                any_in_row = True
                                cols_html.append(f'<td style="padding:1px 6px; vertical-align:top; font-family: monospace; white-space:nowrap;">{cell}</td>')
                            else:
                                cols_html.append('<td style="padding:1px 6px; vertical-align:top;">&nbsp;</td>')
                            if c < num_blocks - 1:
                                cols_html.append('<td style="width:24px;"></td>')
                        if not any_in_row:
                            break
                        rows_html.append('<tr style="line-height:1.1;">' + ''.join(cols_html) + '</tr>')

                    body_html = f'Mostrando {n} fechas.<br><table style="border-collapse:collapse;">' + ''.join(rows_html) + '</table>'

                # Estadísticas
                numeric_rates = [self._extract_price(r) for r in rates if self._extract_price(r) is not None]
                stats_html = ''
                if numeric_rates:
                    minimo = min(numeric_rates)
                    maximo = max(numeric_rates)
                    promedio = sum(numeric_rates) / len(numeric_rates)
                    try:
                        variacion = ((maximo - minimo) / minimo * 100)
                    except ZeroDivisionError:
                        variacion = 0.0
                    sign_variacion = f'{variacion:+.2f}%'
                    if variacion > 0:
                        color = '#10B981'
                        bg = 'rgba(16,185,129,0.12)'
                    elif variacion < 0:
                        color = '#EF4444'
                        bg = 'rgba(239,68,68,0.12)'
                    else:
                        color = '#9CA3AF'
                        bg = 'transparent'
                    stats_html = (
                        '<div style="margin-top:10px; line-height:1.6;">'
                        '<b>Estadísticas:</b><br>'
                        f'&nbsp;&nbsp;Mínimo: {minimo:.2f} Bs<br>'
                        f'&nbsp;&nbsp;Máximo: {maximo:.2f} Bs<br>'
                        f'&nbsp;&nbsp;Promedio: {promedio:.2f} Bs<br>'
                        f'&nbsp;&nbsp;Variación: <span style="color:{color}; font-weight:700; background-color:{bg}; padding:2px 7px; border-radius:4px;">{sign_variacion}</span><br>'
                        '</div>'
                    )

                html = title_html.replace(
                    '<div style="color:#d1d5db; font-family: sans-serif;">',
                    '<div style="color:#d1d5db; font-family: sans-serif; line-height:1.1;">'
                ) + body_html + stats_html + '</div>'
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
                raw_rates = history.get('rates', []) or []

                # Agrupar por fecha (usar la última entrada por fecha)
                last_by_date = {}
                for entry in raw_rates:
                    if not isinstance(entry, dict):
                        continue
                    d = entry.get('date')
                    if not d:
                        continue
                    last_by_date[d] = entry

                # Generar lista de fechas desde primer día del mes hasta hoy
                from datetime import datetime, timedelta
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                dates = []
                cur = start_dt
                while cur <= end_dt:
                    dates.append(cur.strftime("%Y-%m-%d"))
                    cur += timedelta(days=1)

                rates = [last_by_date.get(d) or {'date': d, 'USD': None} for d in dates]

                # Render en bloques horizontales (BLOCK_SIZE = 15)
                n = len(rates)
                BLOCK_SIZE = 15
                title_html = f'<div style="color:#d1d5db; font-family: sans-serif;"><b>Período: {start_date} a {end_date}</b><br>Fuente: {history.get("source")}<br>Total fechas: {n} — Registros encontrados: {history.get("count", 0)}<br><br>'

                if n == 0:
                    body_html = "No hay registros para el período solicitado."
                elif n <= BLOCK_SIZE:
                    lines = []
                    for i, rate in enumerate(rates, 1):
                        price = self._extract_price(rate)
                        rate_str = f"{price:.2f}" if price is not None else "-"
                        lines.append(f"{i}. {rate.get('date')}: {rate_str} Bs")
                    body_html = "<br>".join(lines)
                else:
                    num_blocks = (n + BLOCK_SIZE - 1) // BLOCK_SIZE
                    grid = [["" for _ in range(num_blocks)] for _ in range(BLOCK_SIZE)]
                    for idx, entry in enumerate(rates):
                        b = idx // BLOCK_SIZE
                        r = idx % BLOCK_SIZE
                        price = self._extract_price(entry)
                        rate_str = f"{price:.2f}" if price is not None else "-"
                        grid[r][b] = f"{idx+1}. {entry.get('date')}: {rate_str} Bs"

                    rows_html = []
                    for r in range(BLOCK_SIZE):
                        cols_html = []
                        any_in_row = False
                        for c in range(num_blocks):
                            cell = grid[r][c]
                            if cell:
                                any_in_row = True
                                cols_html.append(f'<td style="padding:1px 6px; vertical-align:top; font-family: monospace; white-space:nowrap;">{cell}</td>')
                            else:
                                cols_html.append('<td style="padding:1px 6px; vertical-align:top;">&nbsp;</td>')
                            if c < num_blocks - 1:
                                cols_html.append('<td style="width:24px;"></td>')
                        if not any_in_row:
                            break
                        rows_html.append('<tr style="line-height:1.1;">' + ''.join(cols_html) + '</tr>')

                    body_html = f'Mostrando {n} fechas.<br><table style="border-collapse:collapse;">' + ''.join(rows_html) + '</table>'

                # Estadísticas
                numeric_rates = [self._extract_price(r) for r in rates if self._extract_price(r) is not None]
                stats_html = ''
                if numeric_rates:
                    minimo = min(numeric_rates)
                    maximo = max(numeric_rates)
                    promedio = sum(numeric_rates) / len(numeric_rates)
                    try:
                        variacion = ((maximo - minimo) / minimo * 100)
                    except ZeroDivisionError:
                        variacion = 0.0
                    sign_variacion = f'{variacion:+.2f}%'
                    if variacion > 0:
                        color = '#10B981'
                        bg = 'rgba(16,185,129,0.12)'
                    elif variacion < 0:
                        color = '#EF4444'
                        bg = 'rgba(239,68,68,0.12)'
                    else:
                        color = '#9CA3AF'
                        bg = 'transparent'
                    stats_html = (
                        '<div style="margin-top:10px; line-height:1.6;">'
                        '<b>Estadísticas:</b><br>'
                        f'&nbsp;&nbsp;Mínimo: {minimo:.2f} Bs<br>'
                        f'&nbsp;&nbsp;Máximo: {maximo:.2f} Bs<br>'
                        f'&nbsp;&nbsp;Promedio: {promedio:.2f} Bs<br>'
                        f'&nbsp;&nbsp;Variación: <span style="color:{color}; font-weight:700; background-color:{bg}; padding:2px 7px; border-radius:4px;">{sign_variacion}</span><br>'
                        '</div>'
                    )

                html = title_html.replace(
                    '<div style="color:#d1d5db; font-family: sans-serif;">',
                    '<div style="color:#d1d5db; font-family: sans-serif; line-height:1.1;">'
                ) + body_html + stats_html + '</div>'
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
    
    def setup_projections(self):
        """Configura la pestaña de Proyecciones BCV"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        # Título Centrado
        lbl_titulo = QLabel(f"🔮 Proyecciones BCV - Cierre {datetime.now().year}")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Área de texto para mostrar escenarios
        self.projections_text = QTextEdit()
        self.projections_text.setReadOnly(True)
        self.projections_text.setMinimumHeight(500)
        # Usar fuente monoespaciada para alineación perfecta
        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.projections_text.setFont(font)
        layout.addWidget(self.projections_text)

        # Botón de cálculo
        btn_calcular = QPushButton("Calcular Proyecciones")
        btn_calcular.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_calcular.clicked.connect(self.calculate_projections)
        layout.addWidget(btn_calcular)

        # Botón de gráfico
        btn_grafico = QPushButton("📊 Ver Gráfico de Proyecciones")
        btn_grafico.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_grafico.clicked.connect(self.show_projections_graph)
        layout.addWidget(btn_grafico)

        layout.addStretch()
        self.projections_tab.setLayout(layout)
        
        # Cargar datos iniciales
        QTimer.singleShot(2500, self.calculate_projections)
    
    def setup_calculator_tab(self):
        """Configura la pestaña de calculadora embebiendo el widget de CalculatorDialog"""
        # Usamos un QVBoxLayout con un scroll para hospedar el contenido
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Creamos el widget de la calculadora directamente (sin abrir como diálogo)
        self._calc_widget = CalculatorDialog(self)
        # Quitamos los botones de ventana modal y lo integramos como widget normal
        self._calc_widget.setWindowFlags(Qt.WindowType.Widget)
        outer_layout.addWidget(self._calc_widget)

        self.calculator_tab.setLayout(outer_layout)


    def calculate_projections(self):
        """Calcula y muestra los tres escenarios de proyección BCV"""
        self.projections_text.setText("Obteniendo datos de BCV...")
        
        try:
            # Obtener datos de la API BCV Today
            api_url = "https://bcv.today/api/v1/history.json"
            response = requests.get(api_url, timeout=10)
            data = response.json()
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            latest = df.sort_values(by='date', ascending=False).iloc[0]
            
            # Obtener precio actual
            price_value = None
            for key in ['USD', 'dollar', 'rate', 'bcv']:
                if key in latest and latest[key] is not None:
                    price_value = float(latest[key])
                    break
            
            if price_value is None:
                self.projections_text.setText("Error: No se encontró precio válido en la API")
                return
            
            self.last_price = price_value
            self.last_date = latest['date']
            
            # Definición de escenarios
            scenarios = {
                "Optimista": {
                    "rate": 0.03,
                    "sustento": "Asume una intervención cambiaria agresiva (> $500M mensuales) y estabilidad en ingresos petroleros."
                },
                "Conservador": {
                    "rate": 0.07,
                    "sustento": "Refleja el aumento estacional de liquidez (M2) por gasto público y bonos de fin de año."
                },
                "Estrés": {
                    "rate": 0.15,
                    "sustento": "Simula una caída en la oferta de divisas y una aceleración en la velocidad de circulación del dinero."
                }
            }
            
            current_month = self.last_date.month
            current_year = self.last_date.year
            target_year = current_year  # Usar el año actual
            months_range = range(current_month, 13)
            
            text = f"{'='*80}\n"
            text += f"INFORME DE PROYECCIÓN CAMBIARIA - CIERRE {target_year}\n"
            text += f"Punto de partida: {self.last_price:.2f} VES/USD (Fecha: {self.last_date.date()})\n"
            text += f"{'='*80}\n\n"
            
            # Guardar datos para el gráfico
            self.projections_data = {}
            
            for name, info in scenarios.items():
                text += f"--- ESCENARIO {name.upper()} ---\n"
                text += f"Sustento: {info['sustento']}\n\n"
                
                # Crear tabla para este escenario con alineación perfecta
                projections = []
                for month in months_range:
                    step = month - current_month
                    month_name = datetime(target_year, month, 1).strftime('%B')
                    price = self.last_price * ((1 + info['rate']) ** step)
                    projections.append((month_name, round(price, 2)))
                
                # Formatear tabla con alineación perfecta
                text += f"{'Mes':<15} {'Precio Est. (VES)':>20}\n"
                text += "-" * 37 + "\n"
                for month_name, price in projections:
                    text += f"{month_name:<15} {price:>20.2f}\n"
                
                text += "\n" + "-" * 40 + "\n\n"
                
                self.projections_data[name] = {
                    "df": pd.DataFrame(projections, columns=["Mes", "Precio Est. (VES)"]),
                    "rate": info['rate'],
                    "sustento": info['sustento']
                }
            
            self.projections_text.setPlainText(text)
            
        except Exception as e:
            self.projections_text.setPlainText(f"Error calculando proyecciones: {e}")
    
    def show_projections_graph(self):
        """Muestra el gráfico de proyecciones en un diálogo"""
        if not hasattr(self, 'projections_data') or not self.projections_data:
            QMessageBox.warning(self, "Advertencia", "Primero calcula las proyecciones")
            return
        
        try:
            # Generar gráfico como imagen
            fig = Figure(figsize=(10, 6), dpi=100)
            ax = fig.add_subplot(111)
            
            # Dibujar cada escenario
            colors = ['#10B981', '#F59E0B', '#EF4444']  # Verde, Naranja, Rojo
            color_idx = 0
            
            for name, data in self.projections_data.items():
                df = data['df']
                rate = data['rate']
                sustento = data['sustento']
                
                ax.plot(df["Mes"], df["Precio Est. (VES)"], 
                       marker='o', 
                       label=f"{name} ({rate*100:.0f}% mensual)",
                       color=colors[color_idx],
                       linewidth=2)
                
                # Etiquetas en TODOS los puntos
                for i, (month, price) in enumerate(zip(df["Mes"], df["Precio Est. (VES)"])):
                    ax.annotate(f'{price:.2f}', 
                               xy=(month, price),
                               textcoords="offset points", 
                               xytext=(0,8 if i % 2 == 0 else -12),  # Alternar posición vertical
                               ha='center',
                               fontsize=8,
                               color=colors[color_idx],
                               fontweight='bold')
                
                color_idx += 1
            
            ax.set_title(f"Visualización de Escenarios BCV - Cierre {self.last_date.year}", fontsize=14, fontweight='bold')
            ax.set_ylabel("Bolívares por Dólar (VES/USD)")
            ax.set_xlabel("Meses")
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper left')
            
            # Ajustar márgenes para evitar que se corte el texto superior
            fig.tight_layout(rect=[0, 0, 1, 0.95])
            
            # Guardar gráfico como imagen temporal
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            fig.savefig(temp_file.name, dpi=100, bbox_inches='tight')
            temp_file.close()
            plt.close(fig)
            
            # Crear diálogo
            dialog = QDialog(self)
            dialog.setWindowTitle("Gráfico de Proyecciones BCV")
            dialog.resize(900, 700)
            
            layout = QVBoxLayout()
            
            # Cargar imagen y escalarla al tamaño del diálogo
            pixmap = QPixmap(temp_file.name)
            scaled_pixmap = pixmap.scaled(850, 450, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            label = QLabel()
            label.setPixmap(scaled_pixmap)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            
            # Agregar sustentos como footer debajo del gráfico
            sustento_text = ""
            for name, data in self.projections_data.items():
                sustento_text += f"{name}: {data['sustento']}\n\n"
            
            sustento_label = QLabel(sustento_text.strip())
            sustento_label.setWordWrap(True)
            sustento_label.setStyleSheet("background-color: #e8e8e8; padding: 15px; border-radius: 5px; color: #000000;")
            layout.addWidget(sustento_label)
            
            btn_close = QPushButton("Cerrar")
            btn_close.clicked.connect(dialog.close)
            layout.addWidget(btn_close)
            
            dialog.setLayout(layout)
            dialog.exec()
            
            # Limpiar archivo temporal
            import os
            os.unlink(temp_file.name)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error mostrando gráfico: {e}")
    
    def analyze_24h(self):
        """Analiza las mejores horas para comprar y vendiendo todos los datos disponibles"""
        self.analysis_24h_text.setText("Analizando datos históricos por hora del día...")
        
        try:
            from src.database import DatabaseManager
            db = DatabaseManager()
            
            # Obtener datos de Binance P2P
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT side, avg_price, timestamp 
                FROM binance_p2p_prices 
                WHERE pair = 'USDT/VES' 
                ORDER BY timestamp ASC
            """)
            binance_history = cursor.fetchall()
            
            conn.close()
            
            if not binance_history:
                self.analysis_24h_text.setText(
                    "❌ No hay datos históricos registrados aún en la base de datos.\n\n"
                    "📝 El agente de bandeja (dolar_monitor_agent.py) recopila datos cada 10 minutos.\n"
                    "   Deja la aplicación corriendo por lo menos 24-48 horas para obtener análisis completo.\n\n"
                    "💡 Alternativa: Usa el botón 'Actualizar Dashboard' para ver datos en tiempo real."
                )
                return
            
            # Agrupar precios por hora del día
            buy_by_hour = {}
            sell_by_hour = {}
            dates_found = set()
            
            from datetime import datetime
            
            # Procesar datos de Binance
            for record in binance_history:
                ts_str = record["timestamp"]
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
            
            # Calcular promedios por hora
            buy_avg_by_hour = {}
            sell_avg_by_hour = {}
            
            for hour, prices in buy_by_hour.items():
                if prices:
                    buy_avg_by_hour[hour] = (sum(prices) / len(prices), len(prices))
            
            for hour, prices in sell_by_hour.items():
                if prices:
                    sell_avg_by_hour[hour] = (sum(prices) / len(prices), len(prices))
            
            # Calcular horas cubiertas
            hours_covered = len(set(buy_by_hour.keys()).union(set(sell_by_hour.keys())))
            min_date = min(dates_found) if dates_found else "N/A"
            max_date = max(dates_found) if dates_found else "N/A"
            
            text = f"📊 ANÁLISIS DE MERCADO DIARIO (Binance P2P USDT/VES)\n"
            text += f"📅 Período: {min_date} a {max_date} ({len(dates_found)} día(s))\n"
            text += f"📈 Registros totales: {len(binance_history)}\n"
            text += f"⏰ Horas cubiertas: {hours_covered}/24 h\n"
            text += "=" * 70 + "\n\n"
            
            # RECOMENDACIONES DE COMPRA
            if buy_avg_by_hour:
                text += "🟢 MEJORES HORAS PARA COMPRAR USDT (Precio más bajo)\n"
                text += "-" * 70 + "\n"
                sorted_buy = sorted(buy_avg_by_hour.items(), key=lambda x: x[1][0])
                best_buy_hour = sorted_buy[0][0] if sorted_buy else None
                best_buy_price = sorted_buy[0][1][0] if sorted_buy else None
                
                for i, (hour, (avg_price, count)) in enumerate(sorted_buy[:5], 1):
                    marker = "⭐ " if hour == best_buy_hour else "   "
                    text += f"{marker}{i}. {hour:02d}:00-{hour:02d}:59 → {avg_price:.2f} VES ({count} registros)\n"
                
                if best_buy_hour is not None:
                    text += f"\n💡 RECOMENDACIÓN: Comprar alrededor de las {best_buy_hour:02d}:00 para mejor precio\n\n"
            else:
                text += "🟢 No hay suficientes datos de compra (necesitas más datos históricos)\n\n"
            
            # RECOMENDACIONES DE VENTA
            if sell_avg_by_hour:
                text += "🔴 MEJORES HORAS PARA VENDER USDT (Precio más alto)\n"
                text += "-" * 70 + "\n"
                sorted_sell = sorted(sell_avg_by_hour.items(), key=lambda x: x[1][0], reverse=True)
                best_sell_hour = sorted_sell[0][0] if sorted_sell else None
                best_sell_price = sorted_sell[0][1][0] if sorted_sell else None
                
                for i, (hour, (avg_price, count)) in enumerate(sorted_sell[:5], 1):
                    marker = "⭐ " if hour == best_sell_hour else "   "
                    text += f"{marker}{i}. {hour:02d}:00-{hour:02d}:59 → {avg_price:.2f} VES ({count} registros)\n"
                
                if best_sell_hour is not None:
                    text += f"\n💡 RECOMENDACIÓN: Vender alrededor de las {best_sell_hour:02d}:00 para mejor precio\n\n"
            else:
                text += "🔴 No hay suficientes datos de venta (necesitas más datos históricos)\n\n"
            
            # RESUMEN EJECUTIVO
            text += "📋 RESUMEN EJECUTIVO\n"
            text += "-" * 70 + "\n"
            
            if best_buy_hour is not None and best_sell_hour is not None:
                if best_buy_price and best_sell_price:
                    profit_potential = ((best_sell_price - best_buy_price) / best_buy_price) * 100
                    text += f"🎯 Estrategia óptima: Comprar {best_buy_hour:02d}:00, Vender {best_sell_hour:02d}:00\n"
                    text += f"💰 Potencial de ganancia: {profit_potential:.1f}%\n"
            
            text += f"📊 Cobertura de datos: {hours_covered}/24 horas del día\n"
            
            if hours_covered < 12:
                text += f"⚠️  ADVERTENCIA: Solo tienes {hours_covered} horas cubiertas.\n"
                text += f"   Deja el agente corriendo más tiempo para análisis completo.\n"
            
            self.analysis_24h_text.setText(text)
            
        except Exception as e:
            self.analysis_24h_text.setText(f"❌ Error generando análisis: {e}\n\n{str(e)}")
    
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
        """Muestra diálogo con datos de Syklo VES/USDC (compra y venta)"""
        try:
            syklo_buy_data = self.monitor.get_syklo_ves_usdc()
            syklo_sell_data = self.monitor.get_syklo_usdc_ves()
            
            # Combinar datos en un solo diccionario para el diálogo
            combined_data = {
                "buy": syklo_buy_data,
                "sell": syklo_sell_data
            }
            
            dialog = SykloDialog("Syklo - VES/USDC (Compra y Venta)", combined_data, self)
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
    
    def show_bcv_dialog(self):
        """Muestra diálogo con spread entre BCV y otras tasas"""
        try:
            # Obtener datos actuales
            data = self.monitor.get_all_data()
            
            bcv_data = data.get("bcv", {})
            binance_data = data.get("binance_ves", {})
            syklo_data = data.get("syklo_ves_usdc", {})
            
            # Obtener tasas
            bcv_rate = None
            if "error" not in bcv_data:
                r = bcv_data.get("rate")
                if r and r != "--":
                    bcv_rate = float(r)
            
            binance_rate = None
            if "error" not in binance_data:
                sell = binance_data.get("sell_stats", {}).get("avg_price")
                if sell and sell != "--":
                    binance_rate = float(sell)
            
            syklo_rate = None
            if "error" not in syklo_data:
                avg = syklo_data.get("avg_price")
                if avg is None:
                    prices = []
                    for o in syklo_data.get("orders", []):
                        p = o.get("price")
                        if p and p not in ("-", "--"):
                            try:
                                prices.append(float(p))
                            except Exception:
                                pass
                    avg = sum(prices) / len(prices) if prices else None
                if avg:
                    syklo_rate = float(avg)
            
            # Calcular Euro BCV
            euro_rate = bcv_rate * 1.08 if bcv_rate else None
            
            # Crear diálogo con spreads
            dialog = QDialog(self)
            dialog.setWindowTitle("💵 Spread BCV vs Otras Tasas")
            dialog.setMinimumWidth(600)
            
            layout = QVBoxLayout()
            
            # Título
            title_label = QLabel(f"📊 {dialog.windowTitle()}")
            title_label.setObjectName("TituloSeccion")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title_label)
            layout.addSpacing(10)
            
            # Área de texto para mostrar spreads
            spreads_text = QTextEdit()
            spreads_text.setReadOnly(True)
            spreads_text.setMinimumHeight(400)
            
            # Construir contenido
            content = f"Tasa BCV: ${self.fmt_es(bcv_rate) if bcv_rate else '--'} Bs\n"
            content += "=" * 60 + "\n\n"
            
            if euro_rate:
                spread_amount = euro_rate - bcv_rate
                spread_percent = (spread_amount / bcv_rate) * 100 if bcv_rate else 0
                content += f"📈 Euro BCV: {self.fmt_es(euro_rate)} Bs\n"
                content += f"   Spread: {self.fmt_es(spread_amount)} Bs ({spread_percent:.2f}%)\n\n"
            
            if binance_rate:
                spread_amount = binance_rate - bcv_rate
                spread_percent = (spread_amount / bcv_rate) * 100 if bcv_rate else 0
                content += f"📊 Binance Venta: {self.fmt_es(binance_rate)} Bs\n"
                content += f"   Spread: {self.fmt_es(spread_amount)} Bs ({spread_percent:.2f}%)\n\n"
            
            if syklo_rate:
                spread_amount = syklo_rate - bcv_rate
                spread_percent = (spread_amount / bcv_rate) * 100 if bcv_rate else 0
                content += f"🔄 Syklo VES/USDC: {self.fmt_es(syklo_rate)} Bs\n"
                content += f"   Spread: {self.fmt_es(spread_amount)} Bs ({spread_percent:.2f}%)\n\n"
            
            spreads_text.setText(content)
            layout.addWidget(spreads_text)
            
            # Botón cerrar
            btn_cerrar = QPushButton("Cerrar")
            btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_cerrar.clicked.connect(dialog.accept)
            layout.addWidget(btn_cerrar)
            
            dialog.setLayout(layout)
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al obtener datos: {e}")
    
    def refresh_dashboard(self):
        """Actualiza los datos del dashboard usando un hilo separado para no bloquear la UI"""
        # Mostrar diálogo de carga
        self.loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.loading_dialog.show()
        self.loading_dialog.raise_()
        self.loading_dialog.activateWindow()
        QApplication.processEvents()

        # Crear worker y thread
        self.refresh_thread = QThread()
        self.refresh_worker = DataLoaderWorker(self.monitor)
        self.refresh_worker.moveToThread(self.refresh_thread)

        self.refresh_thread.started.connect(self.refresh_worker.run)
        self.refresh_worker.finished.connect(self._on_refresh_done)
        self.refresh_worker.error.connect(self._on_refresh_error)
        self.refresh_worker.finished.connect(self.refresh_thread.quit)
        self.refresh_thread.finished.connect(self.refresh_thread.deleteLater)

        self.refresh_thread.start()

    def _on_refresh_done(self, data):
        """Callback cuando el refresco de datos termina exitosamente"""
        self.loading_dialog.close()
        try:
            
            # BCV
            bcv_data = data.get("bcv", {})
            if "error" not in bcv_data:
                bcv_rate = bcv_data.get("rate", "--")
                if bcv_rate != "--":
                    bcv_rate = float(bcv_rate)
                    # Calcular euro (1 EUR ≈ 1.08 USD)
                    euro_rate = bcv_rate * 1.08
                    self.bcv_card.update_value(f"${self.fmt_es(bcv_rate)} Bs\n€{self.fmt_es(euro_rate)} Bs")
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
                    self.binance_ves_card.update_value(f"Buy: {self.fmt_es(buy_avg)}\nSell: {self.fmt_es(sell_avg)}")
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
                    self.binance_usd_card.update_value(f"Buy: ${self.fmt_es(buy_avg, 3)}\nSell: ${self.fmt_es(sell_avg, 3)}")
                else:
                    self.binance_usd_card.update_value("--")
            else:
                self.binance_usd_card.update_value("Error")
            
            # Syklo VES/USDC - mostrar compra y venta
            syklo_ves = data.get("syklo_ves_usdc", {})
            syklo_usdc_ves = data.get("syklo_usdc_ves", {})
            
            if "error" not in syklo_ves and "error" not in syklo_usdc_ves:
                buy_avg = syklo_ves.get("avg_price")
                sell_avg = syklo_usdc_ves.get("avg_price")
                
                if buy_avg is None:
                    prices = []
                    for o in syklo_ves.get("orders", []):
                        p = o.get("price")
                        if p and p not in ("-", "--"):
                            try:
                                prices.append(float(p))
                            except Exception:
                                pass
                    buy_avg = sum(prices) / len(prices) if prices else None
                
                if sell_avg is None:
                    prices = []
                    for o in syklo_usdc_ves.get("orders", []):
                        p = o.get("price")
                        if p and p not in ("-", "--"):
                            try:
                                prices.append(float(p))
                            except Exception:
                                pass
                    sell_avg = sum(prices) / len(prices) if prices else None
                
                if buy_avg and sell_avg:
                    self.syklo_ves_card.update_value(f"Buy: {self.fmt_es(buy_avg)}\nSell: {self.fmt_es(sell_avg)}")
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
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.lbl_last_updated.setText(f"Datos actualizados: {now_str}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error actualizando: {e}")

    def _on_refresh_error(self, error_msg):
        """Callback cuando el refresco de datos falla"""
        self.loading_dialog.close()
        QMessageBox.critical(self, "Error", f"Error actualizando datos: {error_msg}")

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
        
        # Verificar si es formato combinado (compra y venta)
        if "buy" in self.data and "sell" in self.data:
            # Formato combinado
            buy_data = self.data["buy"]
            sell_data = self.data["sell"]
            
            # Compra
            text += "🟢 ANUNCIOS DE COMPRA (VES → USDC)\n"
            text += "=" * 60 + "\n\n"
            
            buy_orders = buy_data.get("orders", [])
            if buy_orders:
                for i, order in enumerate(buy_orders[:10], 1):
                    price = order.get("price", "N/A")
                    min_amount = order.get("min", "N/A")
                    max_amount = order.get("max", "N/A")
                    trader = order.get("trader", "N/A")
                    method = order.get("method_full", order.get("method", "N/A"))
                    
                    if price != "N/A" and price != "-":
                        price_str = f"{float(price):,.2f}"
                    else:
                        price_str = "N/A"
                    
                    if min_amount != "N/A" and min_amount != "-":
                        min_str = f"{float(min_amount):,.2f}"
                    else:
                        min_str = "N/A"
                    
                    if max_amount != "N/A" and max_amount != "-":
                        max_str = f"{float(max_amount):,.2f}"
                    else:
                        max_str = "N/A"
                    
                    text += f"{i}. Método: {method}\n"
                    text += f"   Precio: {price_str} Bs\n"
                    text += f"   Mínimo: {min_str}\n"
                    text += f"   Máximo: {max_str}\n"
                    text += f"   Trader: {trader}\n"
                    text += "\n"
            else:
                text += "No hay órdenes de compra disponibles.\n\n"
            
            # Venta
            text += "🔴 ANUNCIOS DE VENTA (USDC → VES)\n"
            text += "=" * 60 + "\n\n"
            
            sell_orders = sell_data.get("orders", [])
            if sell_orders:
                for i, order in enumerate(sell_orders[:10], 1):
                    price = order.get("price", "N/A")
                    min_amount = order.get("min", "N/A")
                    max_amount = order.get("max", "N/A")
                    trader = order.get("trader", "N/A")
                    method = order.get("method_full", order.get("method", "N/A"))
                    
                    if price != "N/A" and price != "-":
                        price_str = f"{float(price):,.2f}"
                    else:
                        price_str = "N/A"
                    
                    if min_amount != "N/A" and min_amount != "-":
                        min_str = f"{float(min_amount):,.2f}"
                    else:
                        min_str = "N/A"
                    
                    if max_amount != "N/A" and max_amount != "-":
                        max_str = f"{float(max_amount):,.2f}"
                    else:
                        max_str = "N/A"
                    
                    text += f"{i}. Método: {method}\n"
                    text += f"   Precio: {price_str} Bs\n"
                    text += f"   Mínimo: {min_str}\n"
                    text += f"   Máximo: {max_str}\n"
                    text += f"   Trader: {trader}\n"
                    text += "\n"
            else:
                text += "No hay órdenes de venta disponibles.\n\n"
                
        else:
            # Formato simple (original)
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