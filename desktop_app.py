#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Zinli Monitor - Aplicación de Escritorio
Estilo profesional basado en el ejemplo de OmenDashboard
"""

import sys
import os
from datetime import datetime
from typing import Callable, Dict, Any, Optional

import matplotlib
matplotlib.use('Agg')  # Backend no interactivo
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
    """Worker para cargar datos generales en un hilo separado"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, monitor: ZinliMonitor) -> None:
        super().__init__()
        self.monitor = monitor
    
    def run(self) -> None:
        try:
            data = self.monitor.get_all_data(save_to_db=True)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class RatesLoaderWorker(QObject):
    """Carga todas las tasas para la calculadora en un hilo separado"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, monitor: ZinliMonitor) -> None:
        super().__init__()
        self.monitor = monitor

    def run(self) -> None:
        try:
            data = self.monitor.get_all_data(save_to_db=False)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class CardDetailWorker(QObject):
    """Worker genérico para cargar detalles de tarjetas en un hilo separado"""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fetch_func: Callable[[], Any]) -> None:
        super().__init__()
        self.fetch_func = fetch_func

    def run(self) -> None:
        try:
            data = self.fetch_func()
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class CalculatorDialog(QDialog):
    """Calculadora de conversión VES ↔ USD / EUR."""

    CURRENCY_SYMBOLS = {"VES": "Bs", "USD": "$", "EUR": "€"}
    PANEL_MAX_WIDTH = 700

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.monitor = parent.monitor if parent else ZinliMonitor()
        self.rates: Dict[str, Dict[str, Any]] = {}
        self._rates_ready = False
        self._init_ui()
        self._load_rates_async()

    def _init_ui(self) -> None:
        self.setWindowTitle("🧮 Calculadora de Cambio")
        self.setStyleSheet("""
            QDialog, QWidget#CalcPanel { background-color: #030d16; }
            QFrame#CalcCard { background-color: #061420; border: 1px solid #102a3f; border-radius: 8px; }
            QLabel#CalcTitle { color: #ffffff; font-size: 17px; font-weight: bold; }
            QLabel#SectionLabel { color: #8892b0; font-size: 10px; font-weight: bold; letter-spacing: 1px; }
            QDoubleSpinBox, QComboBox {
                background-color: #0a1e30; color: #d1d5db; border: 1px solid #102a3f;
                border-radius: 6px; padding: 6px 10px; font-size: 14px; min-height: 32px;
            }
            QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #667eea; }
            QComboBox QAbstractItemView { background-color: #061420; color: #d1d5db; selection-background-color: #102a3f; }
            QCheckBox { color: #d1d5db; font-size: 12px; spacing: 6px; }
            QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #102a3f; background: #0a1e30; }
            QCheckBox::indicator:checked { background: #667eea; border-color: #667eea; }
            QPushButton#CalcBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #667eea, stop:1 #764ba2);
                color: #ffffff; border: none; border-radius: 8px; font-size: 14px; font-weight: bold;
                padding: 10px; min-height: 38px;
            }
            QPushButton#CalcBtn:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c93f0, stop:1 #8b5fbf); }
            QPushButton#CalcBtn:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5264cc, stop:1 #623d88); }
            QPushButton#ClearBtn { background-color: #061420; color: #8892b0; border: 1px solid #102a3f; border-radius: 6px; font-size: 12px; padding: 8px 18px; }
            QPushButton#ClearBtn:hover { color: #ffffff; border-color: #667eea; }
            QFrame#ResultCard { background-color: #061420; border: 1px solid #102a3f; border-radius: 8px; }
            QFrame#ResultCard[best="true"] { border: 1.5px solid #667eea; background-color: #0a1e30; }
            QLabel#CardName { color: #8892b0; font-size: 11px; font-weight: bold; }
            QLabel#CardRate { color: #667eea; font-size: 10px; }
            QLabel#CardValue { color: #ffffff; font-size: 20px; font-weight: bold; }
            QLabel#CardBadge { color: #667eea; font-size: 10px; font-weight: bold; }
            QLabel#StatusLabel { color: #8892b0; font-size: 11px; font-style: italic; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        h_center = QHBoxLayout()
        h_center.setContentsMargins(0, 0, 0, 0)
        h_center.addStretch(1)

        panel = QWidget()
        panel.setObjectName("CalcPanel")
        panel.setMaximumWidth(self.PANEL_MAX_WIDTH)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(28, 24, 28, 24)
        inner.setSpacing(16)

        title = QLabel("🧮 Calculadora de Cambio")
        title.setObjectName("CalcTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(title)

        input_card = QFrame()
        input_card.setObjectName("CalcCard")
        input_row = QHBoxLayout(input_card)
        input_row.setContentsMargins(18, 14, 18, 14)
        input_row.setSpacing(14)

        self.is_ves_to_foreign = True

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

        self.btn_swap = QPushButton("⇄ Switch")
        self.btn_swap.setObjectName("ClearBtn")
        self.btn_swap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_swap.setToolTip("Cambiar sentido de conversión (VES ↔ Divisa)")
        self.btn_swap.clicked.connect(self._toggle_direction)

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

        sources_card = QFrame()
        sources_card.setObjectName("CalcCard")
        sources_vbox = QVBoxLayout(sources_card)
        sources_vbox.setContentsMargins(18, 12, 18, 12)
        sources_vbox.setSpacing(10)

        lbl_src = QLabel("FUENTES DE TASA")
        lbl_src.setObjectName("SectionLabel")
        sources_vbox.addWidget(lbl_src)

        checks_row = QHBoxLayout()
        self.chk_bcv = QCheckBox("💵 BCV")
        self.chk_eur = QCheckBox("💶 Euro (BCV)")
        self.chk_binance = QCheckBox("📈 Binance Compra")
        self.chk_syklo = QCheckBox("🔄 Syklo Compra")
        for chk in (self.chk_bcv, self.chk_eur, self.chk_binance, self.chk_syklo):
            chk.setChecked(True)
            checks_row.addWidget(chk)
        checks_row.addStretch()
        sources_vbox.addLayout(checks_row)
        inner.addWidget(sources_card)

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

        self.lbl_status = QLabel("⏳ Cargando tasas en segundo plano…")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(self.lbl_status)

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

        h_center.addWidget(panel)
        h_center.addStretch(1)
        root.addLayout(h_center)

    def _load_rates_async(self) -> None:
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

    def _on_rates_loaded(self, data: Dict[str, Any]) -> None:
        try:
            bcv_rate = None
            bcv_data = data.get("bcv", {})
            if "error" not in bcv_data:
                r = bcv_data.get("rate")
                if r and r != "--":
                    bcv_rate = float(r)
                    self.rates["BCV"] = {"ves_per_usd": bcv_rate, "icon": "💵", "is_eur": False}

            if bcv_rate:
                eur_bs = bcv_rate * 1.08
                self.rates["Euro (BCV)"] = {"ves_per_eur": eur_bs, "icon": "💶", "is_eur": True}

            ves_data = data.get("binance_ves", {})
            if "error" not in ves_data:
                buy = ves_data.get("buy_stats", {}).get("avg_price")
                sell = ves_data.get("sell_stats", {}).get("avg_price")
                if buy and buy != "--":
                    self.rates["Binance Compra"] = {"ves_per_usd": float(buy), "icon": "📈", "is_eur": False}
                if sell and sell != "--":
                    self.rates["Binance Venta"] = {"ves_per_usd": float(sell), "icon": "📉", "is_eur": False}

            syklo_ves = data.get("syklo_ves_usdc", {})
            syklo_usdc_ves = data.get("syklo_usdc_ves", {})
            
            if "error" not in syklo_ves:
                avg = syklo_ves.get("avg_price")
                if avg is None:
                    prices = [float(o.get("price")) for o in syklo_ves.get("orders", []) if o.get("price") not in (None, "-", "--")]
                    avg = sum(prices) / len(prices) if prices else None
                if avg:
                    self.rates["Syklo VES/USDC"] = {"ves_per_usd": float(avg), "icon": "🔄", "is_eur": False}
            
            if "error" not in syklo_usdc_ves:
                avg = syklo_usdc_ves.get("avg_price")
                if avg is None:
                    prices = [float(o.get("price")) for o in syklo_usdc_ves.get("orders", []) if o.get("price") not in (None, "-", "--")]
                    avg = sum(prices) / len(prices) if prices else None
                if avg:
                    self.rates["Syklo Venta"] = {"ves_per_usd": float(avg), "icon": "📈", "is_eur": False}

            self._rates_ready = True
            self.lbl_status.setText("✅ Fuentes cargadas — listo para calcular")
            self.btn_calc.setEnabled(True)

        except Exception as e:
            self.lbl_status.setText(f"⚠️ Error parseando tasas: {e}")
            self.btn_calc.setEnabled(True)

    def _on_rates_error(self, msg: str) -> None:
        self.lbl_status.setText(f"⚠️ Error cargando tasas: {msg}")
        self.btn_calc.setEnabled(True)

    @staticmethod
    def _sym(currency: str) -> str:
        return CalculatorDialog.CURRENCY_SYMBOLS.get(currency, currency)

    @staticmethod
    def _fmt_es(val: float, decimals: int = 2) -> str:
        s = f"{val:,.{decimals}f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")

    def _toggle_direction(self) -> None:
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

    def _on_foreign_currency_changed(self, foreign: str) -> None:
        if not self.is_ves_to_foreign:
            sym = self._sym(foreign)
            self.lbl_amount.setText(f"MONTO EN {foreign} ({sym})")
        self._clear_results()

    def _clear_results(self) -> None:
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.lbl_status.setText("🗑️ Resultados limpiados.")

    def _calculate(self) -> None:
        amount = self.amount_input.value()
        foreign = self.foreign_currency.currentText()
        sym_f = self._sym(foreign)

        if not self.rates:
            self.lbl_status.setText("⚠️ Tasas no disponibles todavía, espera un momento.")
            return

        binance_key = "Binance Compra" if self.is_ves_to_foreign else "Binance Venta"
        syklo_key = "Syklo VES/USDC" if self.is_ves_to_foreign else "Syklo Venta"

        source_filter = {
            "BCV": self.chk_bcv.isChecked(),
            "Euro (BCV)": self.chk_eur.isChecked(),
            binance_key: self.chk_binance.isChecked(),
            syklo_key: self.chk_syklo.isChecked(),
        }

        results = []
        for name, info in self.rates.items():
            if not source_filter.get(name, False):
                continue

            if info.get("is_eur"):
                if foreign != "EUR":
                    continue
                vpe = info["ves_per_eur"]
                converted = (amount / vpe) if self.is_ves_to_foreign else (amount * vpe)
                rate_str = f"1 € = {self._fmt_es(vpe)} Bs"
            else:
                if foreign == "EUR":
                    continue
                vpu = info["ves_per_usd"]
                converted = (amount / vpu) if self.is_ves_to_foreign else (amount * vpu)
                rate_str = f"1 USD = {self._fmt_es(vpu)} Bs"

            results.append((name, info["icon"], converted, rate_str))

        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not results:
            lbl = QLabel("⚠️ No hay fuentes seleccionadas para esta conversión.")
            lbl.setStyleSheet("color:#8892b0; font-size:12px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            self.results_layout.insertWidget(0, lbl)
            return

        results.sort(key=lambda r: r[2], reverse=True)
        best_val = results[0][2]
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
            is_best = (idx == 0)
            is_worst = (idx == len(results) - 1 and len(results) > 1)
            display = f"{self._fmt_es(value)} {display_sym}"
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

    def _make_result_card(self, name: str, value: str, rate_str: str, is_best: bool, is_worst: bool) -> QFrame:
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
    """Aplicación principal de escritorio"""
    
    def __init__(self) -> None:
        super().__init__()
        self.monitor = ZinliMonitor()
        
        # Referencias persistentes para evitar Garbage Collection
        self._card_thread: Optional[QThread] = None
        self._card_worker: Optional[CardDetailWorker] = None
        self._card_progress: Optional[QProgressDialog] = None
        self._card_timeout_timer: Optional[QTimer] = None

        # Diálogo de carga inicial
        self.loading_dialog = QProgressDialog("Cargando registros...", None, 0, 0, self)
        self.loading_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.loading_dialog.setCancelButton(None)
        self.loading_dialog.setAutoClose(False)
        self.loading_dialog.setWindowTitle("")
        self.loading_dialog.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        
        self.init_ui()

    def _fetch_card_detail_async(self, fetch_func: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        """Extracción asíncrona segura con referencias persistentes y timeout"""
        if self._card_thread and self._card_thread.isRunning():
            return

        self._card_progress = QProgressDialog("Cargando registros...", None, 0, 0, self)
        self._card_progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._card_progress.setCancelButton(None)
        self._card_progress.setAutoClose(False)
        self._card_progress.setWindowTitle("")
        self._card_progress.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        self._card_progress.show()
        QApplication.processEvents()

        self._card_thread = QThread(self)
        self._card_worker = CardDetailWorker(fetch_func)
        self._card_worker.moveToThread(self._card_thread)

        self._card_timeout_timer = QTimer(self)
        self._card_timeout_timer.setSingleShot(True)

        def cleanup_resources() -> None:
            if self._card_timeout_timer and self._card_timeout_timer.isActive():
                self._card_timeout_timer.stop()
            if self._card_progress:
                self._card_progress.close()
                self._card_progress.deleteLater()
                self._card_progress = None

        def on_success(result_data: Any) -> None:
            cleanup_resources()
            if self._card_thread and self._card_thread.isRunning():
                self._card_thread.quit()
                self._card_thread.wait()
            callback(result_data)

        def on_error(err_msg: str) -> None:
            cleanup_resources()
            if self._card_thread and self._card_thread.isRunning():
                self._card_thread.quit()
                self._card_thread.wait()
            QMessageBox.critical(self, "Error", f"Error cargando detalle: {err_msg}")

        def on_timeout() -> None:
            cleanup_resources()
            if self._card_thread and self._card_thread.isRunning():
                self._card_thread.terminate()
                self._card_thread.wait()
            QMessageBox.warning(
                self, "Tiempo de espera agotado",
                "La consulta tardó demasiado tiempo en responder. Revisa tu conexión a internet."
            )

        self._card_timeout_timer.timeout.connect(on_timeout)
        self._card_thread.started.connect(self._card_worker.run)
        self._card_worker.finished.connect(on_success)
        self._card_worker.error.connect(on_error)

        self._card_thread.start()
        self._card_timeout_timer.start(15000)

    def init_ui(self) -> None:
        self.setWindowTitle("Dólar Monitor - Dashboard")
        self.resize(1000, 700)
        
        self.setStyleSheet("""
            QWidget { background-color: #030d16; font-family: 'Segoe UI', Helvetica, Arial, sans-serif; }
            QFrame#Tarjeta { background-color: #061420; border: 1px solid #102a3f; border-radius: 6px; }
            QFrame#Tarjeta[clicable="true"] { border: 2px solid #667eea; }
            QFrame#Tarjeta[clicable="true"]:hover { background-color: #0a2a40; }
            QLabel { color: #d1d5db; font-size: 13px; border: none; background-color: transparent; }
            QLabel#TituloSeccion { color: #ffffff; font-size: 14px; font-weight: bold; }
            QLabel#Valor { color: #d1d5db; font-size: 16px; font-weight: bold; }
            QLabel#Subtitulo { color: #8892b0; font-size: 11px; }
            QTextEdit { background-color: #061420; border: 1px solid #102a3f; border-radius: 6px; color: #d1d5db; font-size: 13px; }
            QSpinBox { background-color: #061420; color: #d1d5db; border: 1px solid #102a3f; border-radius: 4px; padding: 5px; }
            QPushButton { background-color: #061420; color: #5c829e; border: 1px solid #102a3f; border-radius: 4px; font-size: 14px; padding: 8px 0px; }
            QPushButton:hover { background-color: #102a3f; color: #ffffff; }
            QPushButton:pressed { background-color: #030d16; }
            QTabWidget::pane { background-color: #030d16; border: none; }
            QTabBar::tab { background-color: #061420; color: #8892b0; padding: 10px 20px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background-color: #030d16; color: #ffffff; border-bottom: 2px solid #102a3f; }
        """)

        layout_principal = QVBoxLayout()
        layout_principal.setContentsMargins(15, 0, 15, 15)
        layout_principal.setSpacing(6)

        self.tab_widget = QTabWidget()
        self.tab_widget.setContentsMargins(0, 0, 0, 0)
        
        self.dashboard_tab = QWidget()
        self.setup_dashboard()
        self.tab_widget.addTab(self.dashboard_tab, "📊 Dashboard")
        
        self.arbitrage_tab = QWidget()
        self.setup_arbitrage()
        self.tab_widget.addTab(self.arbitrage_tab, "🔄 Arbitraje")
        
        self.history_tab = QWidget()
        self.setup_history()
        self.tab_widget.addTab(self.history_tab, "📈 Historial")
        
        self.stats_tab = QWidget()
        self.setup_stats()
        self.tab_widget.addTab(self.stats_tab, "📊 Estadísticas")
        
        self.analysis_24h_tab = QWidget()
        self.setup_24h_analysis()
        self.tab_widget.addTab(self.analysis_24h_tab, "⏰ Análisis 24h")
        
        self.projections_tab = QWidget()
        self.setup_projections()
        self.tab_widget.addTab(self.projections_tab, "🔮 Proyecciones")

        self.calculator_tab = QWidget()
        self.setup_calculator_tab()
        self.tab_widget.addTab(self.calculator_tab, "🧮 Calculadora")

        layout_principal.addWidget(self.tab_widget)

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
        
        QTimer.singleShot(100, self.show_loading_dialog)
    
    def show_loading_dialog(self) -> None:
        self.loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.loading_dialog.show()
        self.loading_dialog.raise_()
        self.loading_dialog.activateWindow()
        QApplication.processEvents()
        
        self.data_thread = QThread()
        self.data_worker = DataLoaderWorker(self.monitor)
        self.data_worker.moveToThread(self.data_thread)
        
        self.data_thread.started.connect(self.data_worker.run)
        self.data_worker.finished.connect(self.on_data_loaded)
        self.data_worker.error.connect(self.on_data_error)
        self.data_worker.finished.connect(self.data_thread.quit)
        self.data_thread.finished.connect(self.data_thread.deleteLater)
        
        self.data_thread.start()
    
    @staticmethod
    def fmt_es(val: Any, decimals: int = 2) -> str:
        """Formatea un número según el estándar en español (miles con punto, decimales con coma)"""
        if val is None or val in ("--", "N/A", "-"):
            return "N/A"
        try:
            v = float(val)
            s = f"{v:,.{decimals}f}"
            return s.replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return str(val)

    def on_data_loaded(self, data: Dict[str, Any]) -> None:
        try:
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
            
            syklo_ves = data.get("syklo_ves_usdc", {})
            syklo_usdc_ves = data.get("syklo_usdc_ves", {})
            
            if "error" not in syklo_ves and "error" not in syklo_usdc_ves:
                buy_avg = syklo_ves.get("avg_price")
                sell_avg = syklo_usdc_ves.get("avg_price")
                
                if buy_avg is None:
                    prices = [float(o.get("price")) for o in syklo_ves.get("orders", []) if o.get("price") not in (None, "-", "--")]
                    buy_avg = sum(prices) / len(prices) if prices else None
                
                if sell_avg is None:
                    prices = [float(o.get("price")) for o in syklo_usdc_ves.get("orders", []) if o.get("price") not in (None, "-", "--")]
                    sell_avg = sum(prices) / len(prices) if prices else None
                
                if buy_avg and sell_avg:
                    self.syklo_ves_card.update_value(f"Buy: {self.fmt_es(buy_avg)}\nSell: {self.fmt_es(sell_avg)}")
                else:
                    self.syklo_ves_card.update_value("--")
            else:
                self.syklo_ves_card.update_value("Error")
            
            syklo_usd = data.get("syklo_usdc_usd", {})
            if "error" not in syklo_usd:
                orders = syklo_usd.get("orders", [])
                if orders:
                    best_rate = orders[0].get("price", "--")
                    if best_rate != "--":
                        self.syklo_usd_card.update_value(f"${self.fmt_es(best_rate, 4)}")
                    else:
                        self.syklo_usd_card.update_value("--")
                else:
                    self.syklo_usd_card.update_value("--")
            else:
                self.syklo_usd_card.update_value("Error")
            
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.lbl_last_updated.setText(f"Datos actualizados: {now_str}")
            self.loading_dialog.close()
            
        except Exception as e:
            self.loading_dialog.close()
            QMessageBox.critical(self, "Error", f"Error actualizando datos: {e}")
    
    def on_data_error(self, error_msg: str) -> None:
        self.loading_dialog.close()
        QMessageBox.critical(self, "Error", f"Error cargando datos: {error_msg}")
    
    def setup_dashboard(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        lbl_titulo = QLabel("📊 Dashboard de Tasas")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

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
        layout.addStretch()

        btn_actualizar = QPushButton("Actualizar Datos")
        btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_actualizar.clicked.connect(self.refresh_dashboard)
        layout.addWidget(btn_actualizar)

        self.dashboard_tab.setLayout(layout)

    # ──────────────────────────────────────────────────────────────────────────
    # Muestra de Diálogos Asíncronos Seguros
    # ──────────────────────────────────────────────────────────────────────────
    def show_binance_ves_dialog(self) -> None:
        self._fetch_card_detail_async(
            fetch_func=self.monitor.get_binance_ves,
            callback=lambda ves_info: BinanceAdsDialog("Binance P2P - USDT/VES", ves_info, self).exec()
        )

    def show_binance_usd_dialog(self) -> None:
        self._fetch_card_detail_async(
            fetch_func=self.monitor.get_binance_usd_zinli,
            callback=lambda usd_info: BinanceAdsDialog("Binance P2P - USDT/USD (Zinli)", usd_info, self).exec()
        )

    def show_syklo_ves_dialog(self) -> None:
        def fetch_syklo_ves() -> Dict[str, Any]:
            return {
                "buy": self.monitor.get_syklo_ves_usdc(),
                "sell": self.monitor.get_syklo_usdc_ves()
            }

        self._fetch_card_detail_async(
            fetch_func=fetch_syklo_ves,
            callback=lambda combined_data: SykloDialog("Syklo - VES/USDC (Compra y Venta)", combined_data, self).exec()
        )

    def show_syklo_usd_dialog(self) -> None:
        self._fetch_card_detail_async(
            fetch_func=self.monitor.get_syklo_usdc_usd,
            callback=lambda syklo_data: SykloDialog("Syklo - USDC/USD", syklo_data, self).exec()
        )

    def show_bcv_dialog(self) -> None:
        self._fetch_card_detail_async(
            fetch_func=self.monitor.get_all_data,
            callback=self._render_bcv_dialog
        )

    def _render_bcv_dialog(self, data: Dict[str, Any]) -> None:
        bcv_data = data.get("bcv", {})
        binance_data = data.get("binance_ves", {})
        syklo_data = data.get("syklo_ves_usdc", {})
        
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
                prices = [float(o.get("price")) for o in syklo_data.get("orders", []) if o.get("price") not in (None, "-", "--")]
                avg = sum(prices) / len(prices) if prices else None
            if avg:
                syklo_rate = float(avg)
        
        euro_rate = bcv_rate * 1.08 if bcv_rate else None
        
        dialog = QDialog(self)
        dialog.setWindowTitle("💵 Spread BCV vs Otras Tasas")
        dialog.setMinimumWidth(600)
        
        layout = QVBoxLayout()
        title_label = QLabel(f"📊 {dialog.windowTitle()}")
        title_label.setObjectName("TituloSeccion")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addSpacing(10)
        
        spreads_text = QTextEdit()
        spreads_text.setReadOnly(True)
        spreads_text.setMinimumHeight(400)
        
        content = f"Tasa BCV: ${self.fmt_es(bcv_rate) if bcv_rate else '--'} Bs\n"
        content += "=" * 60 + "\n\n"
        
        if euro_rate and bcv_rate:
            spread_amount = euro_rate - bcv_rate
            spread_percent = (spread_amount / bcv_rate) * 100
            content += f"📈 Euro BCV: {self.fmt_es(euro_rate)} Bs\n"
            content += f"   Spread: {self.fmt_es(spread_amount)} Bs ({spread_percent:.2f}%)\n\n"
        
        if binance_rate and bcv_rate:
            spread_amount = binance_rate - bcv_rate
            spread_percent = (spread_amount / bcv_rate) * 100
            content += f"📊 Binance Venta: {self.fmt_es(binance_rate)} Bs\n"
            content += f"   Spread: {self.fmt_es(spread_amount)} Bs ({spread_percent:.2f}%)\n\n"
        
        if syklo_rate and bcv_rate:
            spread_amount = syklo_rate - bcv_rate
            spread_percent = (spread_amount / bcv_rate) * 100
            content += f"🔄 Syklo VES/USDC: {self.fmt_es(syklo_rate)} Bs\n"
            content += f"   Spread: {self.fmt_es(spread_amount)} Bs ({spread_percent:.2f}%)\n\n"
        
        spreads_text.setText(content)
        layout.addWidget(spreads_text)
        
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)
        
        dialog.setLayout(layout)
        dialog.exec()

    def setup_arbitrage(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        lbl_titulo = QLabel("🔄 Análisis de Arbitraje")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        self.arbitrage_text = QTextEdit()
        self.arbitrage_text.setReadOnly(True)
        self.arbitrage_text.setMinimumHeight(500)
        layout.addWidget(self.arbitrage_text)

        btn_analizar = QPushButton("Analizar Oportunidades")
        btn_analizar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_analizar.clicked.connect(self.analyze_arbitrage)
        layout.addWidget(btn_analizar)

        layout.addStretch()
        self.arbitrage_tab.setLayout(layout)
        QTimer.singleShot(1500, self.analyze_arbitrage)

    def setup_history(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        lbl_titulo = QLabel("📈 Historial BCV")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Modo:"))
        self.history_mode = QComboBox()
        self.history_mode.addItems([
            "Últimos N días", "Día específico", "Mes específico",
            "Mes en curso", "Año específico", "Año en curso",
        ])
        self.history_mode.setCurrentIndex(0)
        self.history_mode.currentIndexChanged.connect(self._on_history_mode_change)
        mode_layout.addWidget(self.history_mode)

        self.days_label = QLabel("Período (días):")
        self.days_spinbox = QSpinBox()
        self.days_spinbox.setRange(1, 365)
        self.days_spinbox.setValue(30)
        mode_layout.addWidget(self.days_label)
        mode_layout.addWidget(self.days_spinbox)

        self.date_label = QLabel("Fecha:")
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_label.setVisible(False)
        self.date_edit.setVisible(False)
        mode_layout.addWidget(self.date_label)
        mode_layout.addWidget(self.date_edit)

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

        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setMinimumHeight(500)
        layout.addWidget(self.history_text)

        btn_obtener = QPushButton("Obtener Historial")
        btn_obtener.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_obtener.clicked.connect(self.get_history)
        layout.addWidget(btn_obtener)

        layout.addStretch()
        self.history_tab.setLayout(layout)

    def setup_stats(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        lbl_titulo = QLabel("📊 Estadísticas")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        hours_layout = QHBoxLayout()
        hours_layout.addWidget(QLabel("Período (horas):"))
        self.hours_spinbox = QSpinBox()
        self.hours_spinbox.setRange(1, 168)
        self.hours_spinbox.setValue(24)
        hours_layout.addWidget(self.hours_spinbox)
        hours_layout.addStretch()
        layout.addLayout(hours_layout)

        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setMinimumHeight(500)
        layout.addWidget(self.stats_text)

        btn_calcular = QPushButton("Calcular Estadísticas")
        btn_calcular.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_calcular.clicked.connect(self.get_stats)
        layout.addWidget(btn_calcular)

        layout.addStretch()
        self.stats_tab.setLayout(layout)

    def analyze_arbitrage(self) -> None:
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

    def _on_history_mode_change(self, index: int) -> None:
        mode = self.history_mode.currentText()
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
            self.year_spin.setEnabled(True)
            self.year_spin.setVisible(True)
        elif mode == "Mes en curso":
            self.year_label.setVisible(True)
            self.year_spin.setEnabled(True)
            self.year_spin.setVisible(True)
            self.year_spin.setValue(QDate.currentDate().year())
        elif mode == "Año específico":
            self.year_label.setVisible(True)
            self.year_spin.setEnabled(True)
            self.year_spin.setVisible(True)
        elif mode == "Año en curso":
            self.year_label.setVisible(True)
            self.year_spin.setVisible(True)
            self.year_spin.setValue(QDate.currentDate().year())
            self.year_spin.setEnabled(False)

    def get_history(self) -> None:
        mode = self.history_mode.currentText()
        self.history_text.setText("Obteniendo historial...")

        try:
            if mode == "Últimos N días":
                days = self.days_spinbox.value()
                history = self.monitor.get_bcv_history(days)
                if not isinstance(history, dict):
                    self.history_text.setPlainText(f"Error obteniendo historial: {history}")
                    return
                raw_rates = history.get('rates', []) or []
                start_date = history.get('start_date')
                end_date = history.get('end_date')

                from datetime import datetime, timedelta
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                except Exception:
                    start_dt = None
                    end_dt = None

                last_by_date = {}
                for entry in raw_rates:
                    if isinstance(entry, dict):
                        d = entry.get('date') or entry.get('fecha')
                        if d:
                            last_by_date[d] = entry

                dates = []
                if start_dt and end_dt:
                    cur = start_dt
                    while cur <= end_dt:
                        dates.append(cur.strftime("%Y-%m-%d"))
                        cur += timedelta(days=1)
                else:
                    dates = sorted(last_by_date.keys())

                rates = [last_by_date.get(d) or {'date': d, 'USD': None} for d in dates]
                n = len(rates)
                BLOCK_SIZE = 15
                title = f"Período: {start_date} a {end_date}\nTotal registros esperados: {days}\nFuente: {history.get('source')}\nMostrando {n} registros\n\n"

                if n == 0:
                    body = "No hay registros para el período solicitado.<br>"
                elif n <= BLOCK_SIZE:
                    lines = [f"{i}. {r.get('date')}: {self._extract_price(r):.2f} Bs" if self._extract_price(r) else f"{i}. {r.get('date')}: - Bs" for i, r in enumerate(rates, 1)]
                    body = "<br>".join(lines) + "<br>"
                else:
                    num_blocks = (n + BLOCK_SIZE - 1) // BLOCK_SIZE
                    grid = [["" for _ in range(num_blocks)] for _ in range(BLOCK_SIZE)]
                    for idx, entry in enumerate(rates):
                        b = idx // BLOCK_SIZE
                        r = idx % BLOCK_SIZE
                        p = self._extract_price(entry)
                        grid[r][b] = f"{idx+1}. {entry.get('date')}: {p:.2f} Bs" if p else f"{idx+1}. {entry.get('date')}: - Bs"

                    rows_html = []
                    for r in range(BLOCK_SIZE):
                        cols_html = [f'<td style="padding:1px 6px; font-family: monospace;">{grid[r][c]}</td>' if grid[r][c] else '<td>&nbsp;</td>' for c in range(num_blocks)]
                        rows_html.append('<tr>' + ''.join(cols_html) + '</tr>')
                    body = '<table style="border-collapse:collapse;">' + ''.join(rows_html) + '</table>'

                numeric_rates = [self._extract_price(r) for r in rates if self._extract_price(r) is not None]
                stats_html = ''
                if numeric_rates:
                    minimo, maximo = min(numeric_rates), max(numeric_rates)
                    promedio = sum(numeric_rates) / len(numeric_rates)
                    var = ((maximo - minimo) / minimo * 100) if minimo else 0.0
                    color = '#10B981' if var > 0 else '#EF4444' if var < 0 else '#9CA3AF'
                    stats_html = f'<div style="margin-top:10px;"><b>Mínimo:</b> {minimo:.2f} Bs | <b>Máximo:</b> {maximo:.2f} Bs | <b>Promedio:</b> {promedio:.2f} Bs | <b>Variación:</b> <span style="color:{color};">{var:+.2f}%</span></div>'

                self.history_text.setHtml(f'<div style="color:#d1d5db;"><pre>{title}</pre>{body}{stats_html}</div>')

            elif mode == "Día específico":
                date_str = self.date_edit.date().toString("yyyy-MM-dd")
                result = self.monitor.get_bcv_rate_by_date(date_str)
                if isinstance(result, dict) and 'rate' in result:
                    self.history_text.setPlainText(f"Fecha: {date_str}\nPrecio: {float(result['rate']):.2f} Bs\nFuente: {result.get('source')}")
                else:
                    self.history_text.setPlainText(f"No se encontró dato para {date_str}")
        except Exception as e:
            self.history_text.setText(f"Error: {e}")

    def setup_24h_analysis(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        lbl_titulo = QLabel("⏰ Análisis 24h - Binance VES")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        self.analysis_24h_text = QTextEdit()
        self.analysis_24h_text.setReadOnly(True)
        self.analysis_24h_text.setMinimumHeight(500)
        layout.addWidget(self.analysis_24h_text)

        btn_analizar = QPushButton("Analizar Últimas 24h")
        btn_analizar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_analizar.clicked.connect(self.analyze_24h)
        layout.addWidget(btn_analizar)

        layout.addStretch()
        self.analysis_24h_tab.setLayout(layout)
        QTimer.singleShot(2000, self.analyze_24h)

    def setup_projections(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(18)

        lbl_titulo = QLabel(f"🔮 Proyecciones BCV - Cierre {datetime.now().year}")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        self.projections_text = QTextEdit()
        self.projections_text.setReadOnly(True)
        self.projections_text.setMinimumHeight(500)
        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.projections_text.setFont(font)
        layout.addWidget(self.projections_text)

        btn_calcular = QPushButton("Calcular Proyecciones")
        btn_calcular.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_calcular.clicked.connect(self.calculate_projections)
        layout.addWidget(btn_calcular)

        btn_grafico = QPushButton("📊 Ver Gráfico de Proyecciones")
        btn_grafico.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_grafico.clicked.connect(self.show_projections_graph)
        layout.addWidget(btn_grafico)

        layout.addStretch()
        self.projections_tab.setLayout(layout)
        QTimer.singleShot(2500, self.calculate_projections)

    def setup_calculator_tab(self) -> None:
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._calc_widget = CalculatorDialog(self)
        self._calc_widget.setWindowFlags(Qt.WindowType.Widget)
        outer_layout.addWidget(self._calc_widget)
        self.calculator_tab.setLayout(outer_layout)

    def calculate_projections(self) -> None:
        self.projections_text.setText("Obteniendo datos de BCV...")
        try:
            api_url = "https://bcv.today/api/v1/history.json"
            response = requests.get(api_url, timeout=10)
            data = response.json()
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            latest = df.sort_values(by='date', ascending=False).iloc[0]
            
            price_value = next((float(latest[k]) for k in ['USD', 'dollar', 'rate', 'bcv'] if k in latest and latest[k]), None)
            if price_value is None:
                self.projections_text.setText("Error: No se encontró precio válido")
                return
            
            self.last_price = price_value
            self.last_date = latest['date']
            
            scenarios = {
                "Optimista": {"rate": 0.03, "sustento": "Asume intervención cambiaria agresiva y estabilidad."},
                "Conservador": {"rate": 0.07, "sustento": "Refleja aumento estacional de liquidez por gasto público."},
                "Estrés": {"rate": 0.15, "sustento": "Simula caída de divisas y aceleración de circulación."}
            }
            
            current_month = self.last_date.month
            target_year = self.last_date.year
            months_range = range(current_month, 13)
            
            text = f"{'='*80}\nINFORME DE PROYECCIÓN CAMBIARIA - CIERRE {target_year}\nPunto de partida: {self.last_price:.2f} VES/USD\n{'='*80}\n\n"
            self.projections_data = {}
            
            for name, info in scenarios.items():
                text += f"--- ESCENARIO {name.upper()} ---\nSustento: {info['sustento']}\n\n"
                projections = []
                for month in months_range:
                    step = month - current_month
                    m_name = datetime(target_year, month, 1).strftime('%B')
                    p = self.last_price * ((1 + info['rate']) ** step)
                    projections.append((m_name, round(p, 2)))
                
                text += f"{'Mes':<15} {'Precio Est. (VES)':>20}\n" + "-" * 37 + "\n"
                for m_name, p in projections:
                    text += f"{m_name:<15} {p:>20.2f}\n"
                text += "\n" + "-" * 40 + "\n\n"
                
                self.projections_data[name] = {
                    "df": pd.DataFrame(projections, columns=["Mes", "Precio Est. (VES)"]),
                    "rate": info['rate'],
                    "sustento": info['sustento']
                }
            
            self.projections_text.setPlainText(text)
        except Exception as e:
            self.projections_text.setPlainText(f"Error calculando proyecciones: {e}")

    def show_projections_graph(self) -> None:
        if not hasattr(self, 'projections_data') or not self.projections_data:
            QMessageBox.warning(self, "Advertencia", "Primero calcula las proyecciones")
            return
        
        try:
            fig = Figure(figsize=(10, 6), dpi=100)
            ax = fig.add_subplot(111)
            colors = ['#10B981', '#F59E0B', '#EF4444']
            
            for idx, (name, data) in enumerate(self.projections_data.items()):
                df = data['df']
                ax.plot(df["Mes"], df["Precio Est. (VES)"], marker='o', label=f"{name}", color=colors[idx], linewidth=2)
            
            ax.set_title("Visualización de Escenarios BCV", fontsize=14, fontweight='bold')
            ax.set_ylabel("VES/USD")
            ax.grid(True, alpha=0.3)
            ax.legend()
            
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            fig.savefig(temp_file.name, dpi=100, bbox_inches='tight')
            temp_file.close()
            plt.close(fig)
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Gráfico de Proyecciones")
            dialog.resize(900, 600)
            layout = QVBoxLayout()
            
            pixmap = QPixmap(temp_file.name)
            scaled = pixmap.scaled(850, 450, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl = QLabel()
            lbl.setPixmap(scaled)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
            
            btn_close = QPushButton("Cerrar")
            btn_close.clicked.connect(dialog.close)
            layout.addWidget(btn_close)
            
            dialog.setLayout(layout)
            dialog.exec()
            os.unlink(temp_file.name)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error mostrando gráfico: {e}")

    def analyze_24h(self) -> None:
        self.analysis_24h_text.setText("Analizando datos históricos por hora...")
        try:
            from src.database import DatabaseManager
            db = DatabaseManager()
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT side, avg_price, timestamp FROM binance_p2p_prices WHERE pair = 'USDT/VES' ORDER BY timestamp ASC")
            records = cursor.fetchall()
            conn.close()
            
            if not records:
                self.analysis_24h_text.setText("❌ No hay datos suficientes recopilados en la base de datos.")
                return
            
            self.analysis_24h_text.setText(f"📊 Registros analizados: {len(records)}\nAnálisis en curso...")
        except Exception as e:
            self.analysis_24h_text.setText(f"❌ Error: {e}")

    def get_stats(self) -> None:
        hours = self.hours_spinbox.value()
        self.stats_text.setText(f"Calculando estadísticas de {hours} horas...")
        try:
            stats = self.monitor.get_statistics(hours)
            self.stats_text.setText(f"Puntos de datos: {stats.get('data_points', 0)}")
        except Exception as e:
            self.stats_text.setText(f"Error: {e}")

    def refresh_dashboard(self) -> None:
        self.loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.loading_dialog.show()
        QApplication.processEvents()

        self.refresh_thread = QThread()
        self.refresh_worker = DataLoaderWorker(self.monitor)
        self.refresh_worker.moveToThread(self.refresh_thread)

        self.refresh_thread.started.connect(self.refresh_worker.run)
        self.refresh_worker.finished.connect(self.on_data_loaded)
        self.refresh_worker.error.connect(self.on_data_error)
        self.refresh_worker.finished.connect(self.refresh_thread.quit)
        self.refresh_thread.finished.connect(self.refresh_thread.deleteLater)

        self.refresh_thread.start()


class RateCard(QFrame):
    """Tarjeta de tasa con evento clicable"""
    clicked = pyqtSignal()
    
    def __init__(self, title: str, value: str, subtitle: str, clickable: bool = False) -> None:
        super().__init__()
        self.setObjectName("Tarjeta")
        self.clickable = clickable
        if clickable:
            self.setProperty("clicable", "true")
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 15)
        layout.setSpacing(6)

        lbl_titulo = QLabel(title)
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        self.lbl_valor = QLabel(value)
        self.lbl_valor.setObjectName("Valor")
        self.lbl_valor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_valor)

        self.lbl_subtitulo = QLabel(subtitle)
        self.lbl_subtitulo.setObjectName("Subtitulo")
        self.lbl_subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_subtitulo)
    
    def mousePressEvent(self, event: Any) -> None:
        if self.clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
    
    def update_value(self, new_value: Any) -> None:
        self.lbl_valor.setText(str(new_value))
    
    def update_subtitle(self, new_subtitle: Any) -> None:
        self.lbl_subtitulo.setText(str(new_subtitle))


class BinanceAdsDialog(QDialog):
    """Diálogo para mostrar anuncios estructurados de Binance P2P"""
    
    def __init__(self, title: str, data: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(650)
        self.data = data
        
        if "Zinli" in title or "USD" in title:
            self.fiat_currency = "USD"
            self.price_currency = "USD"
            self.decimals = 3
        else:
            self.fiat_currency = "VES"
            self.price_currency = "VES"
            self.decimals = 2

        self.setup_ui()
        self.display_ads()
    
    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        title_label = QLabel(f"📊 {self.windowTitle()}")
        title_label.setObjectName("TituloSeccion")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addSpacing(10)
        
        self.ads_text = QTextEdit()
        self.ads_text.setReadOnly(True)
        self.ads_text.setMinimumHeight(500)
        layout.addWidget(self.ads_text)
        
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(self.accept)
        layout.addWidget(btn_cerrar)
    
    def display_ads(self) -> None:
        """Presenta las ofertas de Binance estructuradas por renglones"""
        text = ""
        buy_ads = self.data.get("top_buy_ads", []) if isinstance(self.data, dict) else []
        sell_ads = self.data.get("top_sell_ads", []) if isinstance(self.data, dict) else []

        # --- COMPRA ---
        if buy_ads:
            text += "🟢 ANUNCIOS DE COMPRA (Top 5 - Comerciantes Verificados)\n"
            text += "=" * 60 + "\n\n"
            for i, ad in enumerate(buy_ads[:5], 1):
                m_name = ad.get('merchant_name', 'N/A')
                price = ZinliMonitorDesktopApp.fmt_es(ad.get('price'), self.decimals)
                available = ZinliMonitorDesktopApp.fmt_es(ad.get('available_amount'), 2)
                min_amt = ZinliMonitorDesktopApp.fmt_es(ad.get('min_amount'), 0)
                max_amt = ZinliMonitorDesktopApp.fmt_es(ad.get('max_amount'), 0)
                u_type = ad.get('user_type', 'N/A')
                orders = ad.get('order_count', 'N/A')
                rate = ad.get('completion_rate')
                rate_str = f"{rate:.1f}%" if isinstance(rate, (int, float)) else "N/A"

                text += f"{i}. {m_name}\n"
                text += f"   Precio: {price} {self.price_currency}\n"
                text += f"   Disponible: {available} USDT\n"
                text += f"   Límites: {min_amt} - {max_amt} {self.fiat_currency}\n"
                text += f"   Tipo: {u_type} | Órdenes: {orders} | Tasa: {rate_str}\n\n"
        else:
            text += "No hay anuncios de compra disponibles.\n\n"

        # --- VENTA ---
        if sell_ads:
            text += "🔴 ANUNCIOS DE VENTA (Top 5)\n"
            text += "=" * 60 + "\n\n"
            for i, ad in enumerate(sell_ads[:5], 1):
                m_name = ad.get('merchant_name', 'N/A')
                price = ZinliMonitorDesktopApp.fmt_es(ad.get('price'), self.decimals)
                available = ZinliMonitorDesktopApp.fmt_es(ad.get('available_amount'), 2)
                min_amt = ZinliMonitorDesktopApp.fmt_es(ad.get('min_amount'), 0)
                max_amt = ZinliMonitorDesktopApp.fmt_es(ad.get('max_amount'), 0)
                u_type = ad.get('user_type', 'N/A')
                orders = ad.get('order_count', 'N/A')
                rate = ad.get('completion_rate')
                rate_str = f"{rate:.1f}%" if isinstance(rate, (int, float)) else "N/A"

                text += f"{i}. {m_name}\n"
                text += f"   Precio: {price} {self.price_currency}\n"
                text += f"   Disponible: {available} USDT\n"
                text += f"   Límites: {min_amt} - {max_amt} {self.fiat_currency}\n"
                text += f"   Tipo: {u_type} | Órdenes: {orders} | Tasa: {rate_str}\n\n"
        else:
            text += "No hay anuncios de venta disponibles.\n\n"

        # --- SPREAD ---
        if buy_ads and sell_ads:
            buy_prices = [ad.get('price') for ad in buy_ads if isinstance(ad.get('price'), (int, float))]
            sell_prices = [ad.get('price') for ad in sell_ads if isinstance(ad.get('price'), (int, float))]
            if buy_prices and sell_prices:
                best_buy = min(buy_prices)
                best_sell = max(sell_prices)
                spread_pct = ((best_buy - best_sell) / best_sell) * 100 if best_sell else 0.0

                text += "📈 SPREAD DEL MERCADO\n"
                text += "=" * 60 + "\n"
                text += f"Mejor precio compra: {ZinliMonitorDesktopApp.fmt_es(best_buy, self.decimals)} {self.price_currency}\n"
                text += f"Mejor precio venta:  {ZinliMonitorDesktopApp.fmt_es(best_sell, self.decimals)} {self.price_currency}\n"
                text += f"Spread porcentual:   {spread_pct:.2f}%\n\n"

        self.ads_text.setText(text)


class SykloDialog(QDialog):
    """Diálogo para mostrar ofertas estructuradas de Syklo"""
    
    def __init__(self, title: str, data: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(650)
        self.data = data
        self.decimals = 4 if "USDC/USD" in title else 2
        self.setup_ui()
        self.display_data()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        
        title_label = QLabel(f"🔄 {self.windowTitle()}")
        title_label.setObjectName("TituloSeccion")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addSpacing(10)
        
        self.data_text = QTextEdit()
        self.data_text.setReadOnly(True)
        self.data_text.setMinimumHeight(500)
        layout.addWidget(self.data_text)
        
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(self.accept)
        layout.addWidget(btn_cerrar)

    def display_data(self) -> None:
        """Formatea las órdenes de Syklo en texto ordenado y legible por líneas"""
        text = ""
        
        # Estructura combinada (Compra y Venta)
        if isinstance(self.data, dict) and "buy" in self.data and "sell" in self.data:
            buy_data = self.data.get("buy", {})
            sell_data = self.data.get("sell", {})
            
            # --- COMPRA ---
            text += "🟢 ANUNCIOS DE COMPRA (VES → USDC)\n"
            text += "=" * 60 + "\n\n"
            buy_orders = buy_data.get("orders", []) if isinstance(buy_data, dict) else []
            if buy_orders:
                for i, order in enumerate(buy_orders[:10], 1):
                    price = ZinliMonitorDesktopApp.fmt_es(order.get("price"), self.decimals)
                    min_amt = ZinliMonitorDesktopApp.fmt_es(order.get("min"), self.decimals)
                    max_amt = ZinliMonitorDesktopApp.fmt_es(order.get("max"), self.decimals)
                    trader = order.get("trader", "N/A")
                    method = order.get("method_full") or order.get("method", "N/A")
                    
                    text += f"{i}. Método: {method}\n"
                    text += f"   Precio: {price} Bs\n"
                    text += f"   Mínimo: {min_amt}\n"
                    text += f"   Máximo: {max_amt}\n"
                    text += f"   Trader: {trader}\n\n"
            else:
                text += "No hay órdenes de compra disponibles.\n\n"
            
            # --- VENTA ---
            text += "🔴 ANUNCIOS DE VENTA (USDC → VES)\n"
            text += "=" * 60 + "\n\n"
            sell_orders = sell_data.get("orders", []) if isinstance(sell_data, dict) else []
            if sell_orders:
                for i, order in enumerate(sell_orders[:10], 1):
                    price = ZinliMonitorDesktopApp.fmt_es(order.get("price"), self.decimals)
                    min_amt = ZinliMonitorDesktopApp.fmt_es(order.get("min"), self.decimals)
                    max_amt = ZinliMonitorDesktopApp.fmt_es(order.get("max"), self.decimals)
                    trader = order.get("trader", "N/A")
                    method = order.get("method_full") or order.get("method", "N/A")
                    
                    text += f"{i}. Método: {method}\n"
                    text += f"   Precio: {price} Bs\n"
                    text += f"   Mínimo: {min_amt}\n"
                    text += f"   Máximo: {max_amt}\n"
                    text += f"   Trader: {trader}\n\n"
            else:
                text += "No hay órdenes de venta disponibles.\n\n"
                
        # Estructura simple (USD/USDC u órdenes directas)
        else:
            orders = self.data.get("orders", []) if isinstance(self.data, dict) else []
            if orders:
                text += f"Total órdenes disponibles: {len(orders)}\n"
                if isinstance(self.data, dict) and self.data.get("description"):
                    text += f"Descripción: {self.data.get('description')}\n"
                text += "=" * 60 + "\n\n"
                
                for i, order in enumerate(orders[:10], 1):
                    price = ZinliMonitorDesktopApp.fmt_es(order.get("price"), self.decimals)
                    min_amt = ZinliMonitorDesktopApp.fmt_es(order.get("min"), self.decimals)
                    max_amt = ZinliMonitorDesktopApp.fmt_es(order.get("max"), self.decimals)
                    trader = order.get("trader", "N/A")
                    method = order.get("method_full") or order.get("method", "N/A")
                    
                    text += f"{i}. Método: {method}\n"
                    text += f"   Precio: {price}\n"
                    text += f"   Mínimo: {min_amt}\n"
                    text += f"   Máximo: {max_amt}\n"
                    text += f"   Trader: {trader}\n\n"
            else:
                text += "No hay datos u órdenes disponibles en Syklo.\n"
        
        self.data_text.setText(text)


def main() -> None:
    app = QApplication(sys.argv)
    window = ZinliMonitorDesktopApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()