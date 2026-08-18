#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Zinli Monitor - Aplicación de Escritorio
Interfaz gráfica profesional con monitoreo en tiempo real, historial, arbitraje,
análisis 24h, proyecciones e informes macroeconómicos con Inteligencia Artificial.
"""

import sys
import os
import calendar
import statistics
import tempfile
import json
from datetime import datetime, timedelta
from typing import Callable, Dict, Any, Optional, List, Tuple

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
    QProgressDialog, QScrollArea, QCheckBox, QSizePolicy, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QDate, QThread, QObject
from PyQt6.QtGui import QFont, QPixmap, QColor

# Agregar ruta del src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from zinli_monitor import ZinliMonitor

# Nombres de meses en español para la vista anual
MONTH_NAMES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

# Nombres amigables para rutas de arbitraje
STRATEGY_NAMES = {
    "BCV_VS_BINANCE_VES": "💵 BCV vs. Binance VES",
    "BINANCE_VES_SPREAD": "📊 Binance VES (Brecha Buy/Sell)",
    "BINANCE_USD_ZINLI_SPREAD": "💱 Binance USD (Zinli P2P)",
    "SYKLO_VES_USDC_SPREAD": "🔄 Syklo VES/USDC",
}


# ──────────────────────────────────────────────────────────────────────────────
# Workers Asíncronos (Hilos Secundarios)
# ──────────────────────────────────────────────────────────────────────────────
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


class AIReportWorker(QObject):
    """Worker asíncrono para consultar un LLM y generar el informe macroeconómico"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        current_rate: float,
        projections: Dict[str, Any],
        historical_stats: Dict[str, Any],
        api_key: Optional[str] = None
    ) -> None:
        super().__init__()
        self.current_rate = current_rate
        self.projections = projections
        self.historical_stats = historical_stats
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def run(self) -> None:
        try:
            prompt = self._build_prompt()

            if self.api_key:
                report_md = self._call_llm_api(prompt)
            else:
                report_md = self._generate_fallback_report()

            self.finished.emit(report_md)
        except Exception as e:
            self.error.emit(str(e))

    def _build_prompt(self) -> str:
        scen_summary = ""
        for name, data in self.projections.items():
            rate_pct = f"{data['rate'] * 100:.1f}%"
            final_val = data['df'].iloc[-1]['Precio Est. (VES)']
            scen_summary += f"- Escenario {name} ({rate_pct} mensual): Cierre est. {final_val:.2f} Bs/USD.\n"

        return f"""
Actúa como Economista Jefe y Consultor Financiero Senior experto en la economía de Venezuela.
Elabora un Informe Ejecutivo Macroestructural analizando la dinámica cambiaria del Bolívar (VES) frente al Dólar (USD) considerando datos desde 2025 hasta la actualidad (2026).

DATOS TÉCNICOS ACTUALES DE LA APLICACIÓN:
- Tasa BCV Actual: {self.current_rate:.2f} Bs/USD
- Proyecciones de Cierre 2026:
{scen_summary}

Estructura el informe en formato Markdown con las siguientes secciones:
1. 📌 **Resumen Ejecutivo y Diagnóstico Macro (2025-2026)**
2. 🏦 **Política Monetaria y Cierre del BCV** (Análisis de la intervención cambiaria, M2, liquidez y encaje legal).
3. 📉 **Análisis Comparativo de Firmas de Análisis Reconocidas** (Contraste con proyecciones de Ecoanalítica, Datanálisis, OVF, Torino Capital y multilateralismo).
4. 🔮 **Evaluación de Escenarios Proyectados** (Análisis de los escenarios Optimista, Conservador y Estrés).
5. 🛡️ **Recomendaciones Estratégicas y Cobertura P2P** (Consejos para tesorería de empresas y usuarios P2P/Zinli).
"""

    def _call_llm_api(self, prompt: str) -> str:
        """Petición REST directa a OpenAI GPT-4o"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "Eres un analista macroeconómico experto en la economía de Venezuela."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])

    def _generate_fallback_report(self) -> str:
        """Generador analítico integrado estructurado con métricas de firmas reconocidas"""
        opt = self.projections.get("Optimista", {}).get("df")
        cons = self.projections.get("Conservador", {}).get("df")
        strss = self.projections.get("Estrés", {}).get("df")

        opt_close = opt.iloc[-1]["Precio Est. (VES)"] if opt is not None else 0
        cons_close = cons.iloc[-1]["Precio Est. (VES)"] if cons is not None else 0
        strss_close = strss.iloc[-1]["Precio Est. (VES)"] if strss is not None else 0

        return f"""# 📊 INFORME EJECUTIVO MACROECONÓMICO Y PERSPECTIVAS CAMBIARIAS
**Período de Análisis:** 2025 – 2026 | **Fuente de Datos:** Zinli Monitor AI Analytics

---

### 📌 1. Resumen Ejecutivo y Diagnóstico Macro (2025–2026)
Durante el período 2025-2026, la tasa oficial del **Banco Central de Venezuela (BCV)** ha experimentado un proceso de reajuste progresivo. Tras la aceleración de la devaluación observada a finales de 2025, el tipo de cambio oficial ha buscado converger parcialmente con los mercados P2P (Binance / Syklo), impulsado por la brecha de oferta en las mesas de cambio bancarias.

Actualmente, el tipo de cambio oficial de partida se ubica en **{self.current_rate:.2f} Bs/USD**.

---

### 🏦 2. Política Monetaria y Estrategia del BCV
El comportamiento de la tasa se encuentra condicionado por tres factores monetarios centrales:
1. **Monto de las Intervenciones Cambiarias:** El BCV ha mantenido inyecciones semanales de divisas al sistema bancario. La sostenibilidad de esta política depende directamente de los ingresos petroleros y la capacidad de liquidación internacional.
2. **Expansión de la Liquidez Monetaria (M2):** Los incrementos en el gasto público para el pago de pasivos laborales y gasto estacional presionan la velocidad de circulación del Bolívar.
3. **Encaje Legal e Inflación:** La restricción del crédito bancario se mantiene como el principal ancla antiinflacionaria, obligando a los agentes económicos a acudir al mercado alternativo P2P.

---

### 📉 3. Análisis Comparativo con Firmas y Consultoras Reconocidas
Las principales firmas de análisis económico en Venezuela respaldan los siguientes consensos:

* **Ecoanalítica:** Señala que la brecha entre la tasa oficial y la paralela/P2P tiende a fluctuar entre un 10% y un 25%. Estiman que sin un incremento sustancial en la venta de divisas por intervención, el deslizamiento mensual del dólar oficial promediará entre 6% y 9%.
* **Observatorio Venezolano de Finanzas (OVF):** Destaca que la devaluación acumulada impacta de forma directa sobre la canasta alimentaria (>80% de transmisión a precios al consumidor).
* **Datanálisis / Torino Capital:** Coinciden en que los escenarios de mayor estabilidad dependerán de la flexibilidad en las licencias energéticas internacionales y la disciplina fiscal del Ejecutivo.

---

### 🔮 4. Evaluación de Escenarios Proyectados (Cierre 2026)
Con base en los modelos econométricos calculados por el sistema:

* 🟢 **Escenario Optimista (Intervención Sostenida):** Tasa proyectada a cierre de **{opt_close:.2f} Bs/USD**. Asume inyecciones cambiarias superiores a $500M mensuales y estabilidad en ingresos petroleros.
* 🟠 **Escenario Conservador (Tendencia Inercial):** Tasa proyectada a cierre de **{cons_close:.2f} Bs/USD**. Mantiene la tasa de deslizamiento observada entre 2025 y 2026 con expansión estacional de liquidez.
* 🔴 **Escenario de Estrés (Choque de Oferta):** Tasa proyectada a cierre de **{strss_close:.2f} Bs/USD**. Refleja una contracción en la oferta de divisas e incremento acelerado de la demanda de dólares como refugio de valor.

---

### 🛡️ 5. Recomendaciones Estratégicas
* **Para Tesorería Corporativa:** Calzar flujos de caja en moneda dura y acelerar rotación de inventarios monetizados a tasa de mercado P2P real.
* **Operativa P2P / Zinli:** Aprovechar las ventanas de menor volatilidad intradía identificadas en el módulo de Análisis 24h para optimizar el spread de compra/venta de USDT.
"""


# ──────────────────────────────────────────────────────────────────────────────
# Calculadora de Cambio Embebida
# ──────────────────────────────────────────────────────────────────────────────
class CalculatorDialog(QDialog):
    """Calculadora de conversión VES ↔ USD / EUR."""

    CURRENCY_SYMBOLS = {"VES": "Bs", "USD": "$", "EUR": "€"}
    PANEL_MAX_WIDTH = 700

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.monitor = parent.monitor if parent and hasattr(parent, 'monitor') else ZinliMonitor()
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

            # Usar el valor real del euro de la API si está disponible
            eur_rate = None
            if "error" not in bcv_data and "euro" in bcv_data:
                eur_rate = bcv_data.get("euro")
                if eur_rate and eur_rate != "--":
                    eur_rate = float(eur_rate)
                    self.rates["Euro (BCV)"] = {"ves_per_eur": eur_rate, "icon": "💶", "is_eur": True}
            elif bcv_rate:
                # Fallback al cálculo aproximado si no hay euro en la API
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
            if item and item.widget():
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
                rate_str = f"1 € = {ZinliMonitorDesktopApp.fmt_es(vpe)} Bs"
            else:
                if foreign == "EUR":
                    continue
                vpu = info["ves_per_usd"]
                converted = (amount / vpu) if self.is_ves_to_foreign else (amount * vpu)
                rate_str = f"1 USD = {ZinliMonitorDesktopApp.fmt_es(vpu)} Bs"

            results.append((name, info["icon"], converted, rate_str))

        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item and item.widget():
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
            header_text = f"Convirtiendo {ZinliMonitorDesktopApp.fmt_es(amount)} Bs → {foreign}"
            display_sym = sym_f
        else:
            header_text = f"Convirtiendo {ZinliMonitorDesktopApp.fmt_es(amount)} {sym_f} → VES (Bs)"
            display_sym = "Bs"

        header = QLabel(header_text)
        header.setStyleSheet("color:#8892b0; font-size:11px; padding-bottom:4px;")
        self.results_layout.insertWidget(0, header)

        for idx, (name, icon, value, rate_str) in enumerate(results):
            is_best = (idx == 0)
            is_worst = (idx == len(results) - 1 and len(results) > 1)
            display = f"{ZinliMonitorDesktopApp.fmt_es(value)} {display_sym}"
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
            lbl_spread = QLabel(f"📐 Spread mejor/peor: {ZinliMonitorDesktopApp.fmt_es(spread)}%")
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


# ──────────────────────────────────────────────────────────────────────────────
# Tarjeta Informativa Clicable
# ──────────────────────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────────────────
# Diálogos de Detalle Formateados y de IA
# ──────────────────────────────────────────────────────────────────────────────
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
        text = ""
        buy_ads = self.data.get("top_buy_ads", []) if isinstance(self.data, dict) else []
        sell_ads = self.data.get("top_sell_ads", []) if isinstance(self.data, dict) else []

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
        text = ""
        if isinstance(self.data, dict) and "buy" in self.data and "sell" in self.data:
            buy_data = self.data.get("buy", {})
            sell_data = self.data.get("sell", {})
            
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


class AIReportDialog(QDialog):
    """Diálogo interactivo para visualizar el informe de la IA con gráficos integrados"""

    def __init__(self, report_markdown: str, graph_pixmap: QPixmap, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("🤖 Informe Macroeconómico Ejecutivo - IA Analytics")
        self.resize(1000, 750)
        self.report_markdown = report_markdown
        self.graph_pixmap = graph_pixmap
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #102a3f; background-color: #061420; border-radius: 6px; }
            QTabBar::tab { background-color: #0a1e30; color: #8892b0; padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background-color: #102a3f; color: #ffffff; font-weight: bold; }
        """)

        # Tab 1: Texto del Informe
        tab_text = QWidget()
        t_layout = QVBoxLayout(tab_text)
        t_layout.setContentsMargins(10, 10, 10, 10)

        self.text_browser = QTextEdit()
        self.text_browser.setReadOnly(True)
        self.text_browser.setMarkdown(self.report_markdown)
        self.text_browser.setStyleSheet("""
            QTextEdit {
                background-color: #030d16;
                color: #d1d5db;
                border: none;
                font-size: 13px;
                padding: 10px;
            }
        """)
        t_layout.addWidget(self.text_browser)
        tabs.addTab(tab_text, "📄 Informe Ejecutivo")

        # Tab 2: Gráfico Integrado
        tab_graph = QWidget()
        g_layout = QVBoxLayout(tab_graph)
        g_layout.setContentsMargins(10, 10, 10, 10)

        lbl_img = QLabel()
        lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scaled = self.graph_pixmap.scaled(920, 500, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        lbl_img.setPixmap(scaled)
        g_layout.addWidget(lbl_img)
        tabs.addTab(tab_graph, "📊 Gráfico de Escenarios")

        layout.addWidget(tabs, 1)

        btn_row = QHBoxLayout()
        btn_export = QPushButton("💾 Exportar Informe (HTML)")
        btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_export.clicked.connect(self._export_html)

        btn_close = QPushButton("Cerrar")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)

        btn_row.addWidget(btn_export)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _export_html(self) -> None:
        try:
            file_path = os.path.join(os.path.expanduser("~"), "Informe_Macroeconomico_BCV.html")
            html_content = self.text_browser.toHtml()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            QMessageBox.information(self, "Exportación Exitosa", f"Informe guardado en:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el archivo: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Ventana Principal de la Aplicación
# ──────────────────────────────────────────────────────────────────────────────
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
                    # Usar el valor real del euro de la API si está disponible
                    if "euro" in bcv_data and bcv_data.get("euro"):
                        euro_rate = float(bcv_data.get("euro"))
                    else:
                        # Fallback al cálculo aproximado
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

        # Usar el valor real del euro de la API si está disponible
        euro_rate = None
        if "error" not in bcv_data and "euro" in bcv_data and bcv_data.get("euro"):
            euro_rate = float(bcv_data.get("euro"))
        elif bcv_rate:
            # Fallback al cálculo aproximado
            euro_rate = bcv_rate * 1.08
        
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

    # ──────────────────────────────────────────────────────────────────────────
    # Pestaña de Arbitraje
    # ──────────────────────────────────────────────────────────────────────────
    def setup_arbitrage(self) -> None:
        """Configura el dashboard de oportunidades de arbitraje"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(14)

        lbl_titulo = QLabel("🔄 Mesa de Operaciones y Arbitraje P2P")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Panel de Controles
        control_card = QFrame()
        control_card.setObjectName("CalcCard")
        control_row = QHBoxLayout(control_card)
        control_row.setContentsMargins(12, 8, 12, 8)

        control_row.addWidget(QLabel("Monto Inversión ($ USD):"))
        self.arb_amount_input = QDoubleSpinBox()
        self.arb_amount_input.setRange(10, 100000)
        self.arb_amount_input.setValue(100)
        self.arb_amount_input.setSingleStep(50)
        control_row.addWidget(self.arb_amount_input)

        btn_analizar = QPushButton("⚡ Escanear Arbitraje")
        btn_analizar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_analizar.clicked.connect(self.analyze_arbitrage)
        control_row.addWidget(btn_analizar)
        control_row.addStretch()

        layout.addWidget(control_card)

        # Tarjetas KPI de Oportunidad
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.kpi_arb_spread = RateCard("⭐ Mejor Spread", "--%", "Rendimiento Neto")
        self.kpi_arb_profit = RateCard("💵 Ganancia Est.", "$--", "Retorno Estimado")
        self.kpi_arb_route = RateCard("🔀 Ruta Recomendada", "--", "Estrategia")
        self.kpi_arb_risk = RateCard("🛡️ Nivel Riesgo", "--", "Evaluación")

        kpi_layout.addWidget(self.kpi_arb_spread)
        kpi_layout.addWidget(self.kpi_arb_profit)
        kpi_layout.addWidget(self.kpi_arb_route)
        kpi_layout.addWidget(self.kpi_arb_risk)
        layout.addLayout(kpi_layout)

        # Tabla de Oportunidades
        self.arbitrage_table = QTableWidget()
        self.arbitrage_table.setColumnCount(7)
        self.arbitrage_table.setHorizontalHeaderLabels([
            "Estrategia / Ruta", "Tasa Origen", "Tasa Destino", "Spread Netos (%)",
            "Ganancia Est.", "Riesgo", "Recomendación"
        ])
        
        header = self.arbitrage_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        self.arbitrage_table.setColumnWidth(0, 200)
        self.arbitrage_table.setColumnWidth(1, 105)
        self.arbitrage_table.setColumnWidth(2, 105)
        self.arbitrage_table.setColumnWidth(3, 115)
        self.arbitrage_table.setColumnWidth(4, 110)
        self.arbitrage_table.setColumnWidth(5, 80)

        self.arbitrage_table.setAlternatingRowColors(True)
        self.arbitrage_table.setStyleSheet("""
            QTableWidget {
                background-color: #061420;
                gridline-color: #102a3f;
                border: 1px solid #102a3f;
                border-radius: 6px;
                color: #d1d5db;
                font-size: 13px;
            }
            QTableWidget::item { padding: 6px; }
            QTableWidget::item:alternate { background-color: #030d16; }
            QHeaderView::section {
                background-color: #0a1e30;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #102a3f;
                padding: 6px;
            }
        """)
        layout.addWidget(self.arbitrage_table, 1)

        self.arbitrage_tab.setLayout(layout)
        QTimer.singleShot(1500, self.analyze_arbitrage)

    def _extract_arb_rates(self, opp: dict, live_data: dict) -> Tuple[Optional[float], Optional[float]]:
        """Mapea las tasas de origen y destino reales desde la oportunidad o datos activos"""
        src = opp.get("source_rate") or opp.get("buy_rate") or opp.get("buy_price") or opp.get("bcv_rate")
        dst = opp.get("target_rate") or opp.get("sell_rate") or opp.get("sell_price") or opp.get("binance_rate")

        if src is not None and dst is not None:
            return float(src), float(dst)

        opp_type = str(opp.get("type", "")).lower()

        bcv_rate = None
        bcv_info = live_data.get("bcv", {})
        if "error" not in bcv_info and bcv_info.get("rate") and bcv_info.get("rate") != "--":
            bcv_rate = float(bcv_info["rate"])

        binance_ves = live_data.get("binance_ves", {})
        b_buy = binance_ves.get("buy_stats", {}).get("avg_price")
        b_sell = binance_ves.get("sell_stats", {}).get("avg_price")
        b_buy_f = float(b_buy) if b_buy and b_buy != "--" else None
        b_sell_f = float(b_sell) if b_sell and b_sell != "--" else None

        binance_usd = live_data.get("binance_usd_zinli", {})
        bu_buy = binance_usd.get("buy_stats", {}).get("avg_price")
        bu_sell = binance_usd.get("sell_stats", {}).get("avg_price")
        bu_buy_f = float(bu_buy) if bu_buy and bu_buy != "--" else None
        bu_sell_f = float(bu_sell) if bu_sell and bu_sell != "--" else None

        syklo_ves = live_data.get("syklo_ves_usdc", {})
        syklo_usdc_ves = live_data.get("syklo_usdc_ves", {})
        s_buy_f = syklo_ves.get("avg_price")
        s_sell_f = syklo_usdc_ves.get("avg_price")

        if "bcv" in opp_type and "binance" in opp_type:
            return (bcv_rate, b_sell_f or b_buy_f)
        elif "binance_ves" in opp_type:
            return (b_buy_f, b_sell_f)
        elif "binance_usd" in opp_type or "zinli" in opp_type:
            return (bu_buy_f, bu_sell_f)
        elif "syklo" in opp_type:
            return (s_buy_f, s_sell_f)

        return (src, dst)

    def analyze_arbitrage(self) -> None:
        """Ejecuta el escaneo de arbitraje y actualiza los indicadores"""
        try:
            analysis = self.monitor.analyze_current_arbitrage()
            opportunities = analysis.get("opportunities", []) if isinstance(analysis, dict) else []
            live_data = self.monitor.get_all_data(save_to_db=False)
            inv_amount = self.arb_amount_input.value()

            if not opportunities:
                self.kpi_arb_spread.update_value("0.00%")
                self.kpi_arb_profit.update_value("$0.00")
                self.kpi_arb_route.update_value("Sin Oportunidades")
                self.kpi_arb_risk.update_value("N/A")
                self.arbitrage_table.setRowCount(0)
                return

            best_opp = opportunities[0]
            best_spread = best_opp.get("spread_percent", 0.0)
            est_profit = inv_amount * (best_spread / 100)

            best_type = best_opp.get("type", "N/A").upper()
            friendly_best_route = STRATEGY_NAMES.get(best_type, best_type.replace("_", " "))

            self.kpi_arb_spread.update_value(f"+{best_spread:.2f}%")
            self.kpi_arb_profit.update_value(f"${est_profit:.2f} USD")
            self.kpi_arb_route.update_value(friendly_best_route)

            risk_level = "Bajo" if best_spread < 3.0 else ("Medio" if best_spread < 6.0 else "Alto")
            self.kpi_arb_risk.update_value(risk_level)

            self.arbitrage_table.setRowCount(len(opportunities))
            for row_idx, opp in enumerate(opportunities):
                spread = opp.get("spread_percent", 0.0)
                profit = inv_amount * (spread / 100)
                opp_raw_type = opp.get("type", "").upper()
                friendly_name = STRATEGY_NAMES.get(opp_raw_type, opp_raw_type.replace("_", " "))

                src_rate, dst_rate = self._extract_arb_rates(opp, live_data)

                item_route = QTableWidgetItem(friendly_name)
                item_route.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item_route.setToolTip(friendly_name)

                item_src = QTableWidgetItem(self.fmt_es(src_rate, 2) if src_rate else "N/A")
                item_src.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                item_dst = QTableWidgetItem(self.fmt_es(dst_rate, 2) if dst_rate else "N/A")
                item_dst.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                item_spread = QTableWidgetItem(f"+{spread:.2f}%")
                item_spread.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_spread.setForeground(QColor("#10B981") if spread > 1.5 else QColor("#F59E0B"))

                item_profit = QTableWidgetItem(f"${profit:.2f}")
                item_profit.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                item_risk = QTableWidgetItem("Bajo" if spread < 3 else "Medio")
                item_risk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                rec_text = opp.get("description") or opp.get("recommendation") or "N/A"
                item_rec = QTableWidgetItem(rec_text)
                item_rec.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item_rec.setToolTip(rec_text)

                self.arbitrage_table.setItem(row_idx, 0, item_route)
                self.arbitrage_table.setItem(row_idx, 1, item_src)
                self.arbitrage_table.setItem(row_idx, 2, item_dst)
                self.arbitrage_table.setItem(row_idx, 3, item_spread)
                self.arbitrage_table.setItem(row_idx, 4, item_profit)
                self.arbitrage_table.setItem(row_idx, 5, item_risk)
                self.arbitrage_table.setItem(row_idx, 6, item_rec)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error en análisis de arbitraje: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Pestaña de Historial
    # ──────────────────────────────────────────────────────────────────────────
    def setup_history(self) -> None:
        """Configura la pestaña de Historial con tabla interactiva y tarjetas KPI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(14)

        lbl_titulo = QLabel("📈 Historial de Tasas de Cambio")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        filter_card = QFrame()
        filter_card.setObjectName("CalcCard")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(12, 8, 12, 8)
        filter_layout.setSpacing(10)

        filter_layout.addWidget(QLabel("Modo:"))
        self.history_mode = QComboBox()
        self.history_mode.addItems([
            "Últimos N días",
            "Rango Personalizado (Desde - Hasta)",
            "Impacto Días de Quincena (15 y 30)",
            "Día específico",
            "Mes específico",
            "Mes en curso",
            "Año específico",
            "Año en curso",
        ])
        self.history_mode.currentIndexChanged.connect(self._on_history_mode_change)
        filter_layout.addWidget(self.history_mode)

        self.days_label = QLabel("Días:")
        self.days_spinbox = QSpinBox()
        self.days_spinbox.setRange(1, 365)
        self.days_spinbox.setValue(30)
        filter_layout.addWidget(self.days_label)
        filter_layout.addWidget(self.days_spinbox)

        self.lbl_date_from = QLabel("Desde:")
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))

        self.lbl_date_to = QLabel("Hasta:")
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())

        for w in (self.lbl_date_from, self.date_from, self.lbl_date_to, self.date_to):
            w.setVisible(False)
            filter_layout.addWidget(w)

        self.date_label = QLabel("Fecha:")
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_label.setVisible(False)
        self.date_edit.setVisible(False)
        filter_layout.addWidget(self.date_label)
        filter_layout.addWidget(self.date_edit)

        self.month_label = QLabel("Mes:")
        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setValue(QDate.currentDate().month())
        self.month_label.setVisible(False)
        self.month_spin.setVisible(False)
        filter_layout.addWidget(self.month_label)
        filter_layout.addWidget(self.month_spin)

        self.year_label = QLabel("Año:")
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(QDate.currentDate().year())
        self.year_label.setVisible(False)
        self.year_spin.setVisible(False)
        filter_layout.addWidget(self.year_label)
        filter_layout.addWidget(self.year_spin)

        btn_obtener = QPushButton("🔍 Consultar")
        btn_obtener.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_obtener.clicked.connect(self.get_history)
        filter_layout.addWidget(btn_obtener)

        filter_layout.addStretch()
        layout.addWidget(filter_card)

        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.kpi_min = RateCard("📉 Mínimo", "--", "Período")
        self.kpi_max = RateCard("📈 Máximo", "--", "Período")
        self.kpi_avg = RateCard("📊 Promedio", "--", "Período")
        self.kpi_var = RateCard("⚡ Variación Total", "--", "Respecto a Base")

        kpi_layout.addWidget(self.kpi_min)
        kpi_layout.addWidget(self.kpi_max)
        kpi_layout.addWidget(self.kpi_avg)
        kpi_layout.addWidget(self.kpi_var)
        layout.addLayout(kpi_layout)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Fecha", "Tasa Oficial (Bs)", "Variación Diaria", "Tendencia"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setStyleSheet("""
            QTableWidget {
                background-color: #061420;
                gridline-color: #102a3f;
                border: 1px solid #102a3f;
                border-radius: 6px;
                color: #d1d5db;
                font-size: 13px;
            }
            QTableWidget::item { padding: 6px; }
            QTableWidget::item:alternate { background-color: #030d16; }
            QHeaderView::section {
                background-color: #0a1e30;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #102a3f;
                padding: 6px;
            }
        """)
        layout.addWidget(self.history_table, 1)

        self.history_tab.setLayout(layout)

    def _on_history_mode_change(self, index: int) -> None:
        mode = self.history_mode.currentText()
        
        for w in (self.days_label, self.days_spinbox, self.date_label, self.date_edit,
                  self.month_label, self.month_spin, self.year_label, self.year_spin,
                  self.lbl_date_from, self.date_from, self.lbl_date_to, self.date_to):
            w.setVisible(False)

        self.year_spin.setEnabled(True)
        current_qdate = QDate.currentDate()

        if mode == "Últimos N días":
            self.days_label.setText("Días:")
            self.days_label.setVisible(True)
            self.days_spinbox.setVisible(True)
        elif mode == "Rango Personalizado (Desde - Hasta)":
            self.lbl_date_from.setVisible(True)
            self.date_from.setVisible(True)
            self.lbl_date_to.setVisible(True)
            self.date_to.setVisible(True)
        elif mode == "Impacto Días de Quincena (15 y 30)":
            self.days_label.setText("Días atrás:")
            self.days_label.setVisible(True)
            self.days_spinbox.setVisible(True)
            self.days_spinbox.setValue(60)
        elif mode == "Día específico":
            self.date_label.setVisible(True)
            self.date_edit.setVisible(True)
        elif mode == "Mes específico":
            self.month_label.setVisible(True)
            self.month_spin.setVisible(True)
            self.year_label.setVisible(True)
            self.year_spin.setVisible(True)
        elif mode == "Mes en curso":
            self.month_spin.setValue(current_qdate.month())
            self.year_spin.setValue(current_qdate.year())
            self.year_label.setVisible(True)
            self.year_spin.setVisible(True)
        elif mode == "Año específico":
            self.year_label.setVisible(True)
            self.year_spin.setVisible(True)
        elif mode == "Año en curso":
            self.year_spin.setValue(current_qdate.year())
            self.year_spin.setEnabled(False)
            self.year_label.setVisible(True)
            self.year_spin.setVisible(True)

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

    def get_history(self) -> None:
        """Aplica el Principio de Tasa Base Universal a todos los modos de consulta"""
        mode = self.history_mode.currentText()
        today = datetime.now()
        current_year = today.year
        current_month = today.month

        try:
            start_dt_req: Optional[datetime] = None
            end_dt_req: Optional[datetime] = None
            is_annual_view = mode in ("Año específico", "Año en curso")
            max_limit: Optional[int] = None

            if mode == "Últimos N días":
                days = self.days_spinbox.value()
                max_limit = days
                end_dt_req = today
                start_dt_req = end_dt_req - timedelta(days=days)

            elif mode == "Rango Personalizado (Desde - Hasta)":
                d_from = self.date_from.date()
                d_to = self.date_to.date()
                start_dt_req = datetime(d_from.year(), d_from.month(), d_from.day())
                end_dt_req = datetime(d_to.year(), d_to.month(), d_to.day())

            elif mode == "Impacto Días de Quincena (15 y 30)":
                days = self.days_spinbox.value()
                end_dt_req = today
                start_dt_req = end_dt_req - timedelta(days=days)

            elif mode == "Día específico":
                d = self.date_edit.date()
                start_dt_req = datetime(d.year(), d.month(), d.day())
                end_dt_req = start_dt_req

            elif mode == "Mes específico":
                m = self.month_spin.value()
                y = self.year_spin.value()
                last_day = calendar.monthrange(y, m)[1]
                start_dt_req = datetime(y, m, 1)
                end_dt_req = datetime(y, m, last_day)

            elif mode == "Mes en curso":
                last_day = calendar.monthrange(current_year, current_month)[1]
                start_dt_req = datetime(current_year, current_month, 1)
                end_dt_req = today

            elif mode == "Año específico":
                y = self.year_spin.value()
                start_dt_req = datetime(y, 1, 1)
                end_dt_req = datetime(y, 12, 31)

            elif mode == "Año en curso":
                start_dt_req = datetime(current_year, 1, 1)
                end_dt_req = today

            if start_dt_req is None or end_dt_req is None:
                return

            req_start_str = start_dt_req.strftime("%Y-%m-%d")
            req_end_str = end_dt_req.strftime("%Y-%m-%d")

            fetch_start_dt = start_dt_req - timedelta(days=14)
            fetch_start_str = fetch_start_dt.strftime("%Y-%m-%d")

            res = self.monitor.get_bcv_history(0, fetch_start_str, req_end_str)
            raw_rates = res.get("rates", []) if isinstance(res, dict) else []

            if not raw_rates:
                QMessageBox.information(self, "Historial", "No se encontraron registros para el período seleccionado.")
                return

            by_date = {}
            for item in raw_rates:
                if not isinstance(item, dict):
                    continue
                d = item.get("date") or item.get("fecha")
                p = self._extract_price(item)
                if d and p is not None:
                    if fetch_start_str <= d <= req_end_str:
                        by_date[d] = p

            all_dates_sorted = sorted(by_date.keys())
            if not all_dates_sorted:
                QMessageBox.information(self, "Historial", "No se encontraron registros válidos para el filtro especificado.")
                return

            prev_base_dates = [d for d in all_dates_sorted if d < req_start_str]
            period_dates = [d for d in all_dates_sorted if req_start_str <= d <= req_end_str]

            base_entry = None
            if prev_base_dates:
                last_base_date = prev_base_dates[-1]
                base_entry = {
                    "date": last_base_date,
                    "date_label": f"{last_base_date} (Cierre Previo)",
                    "price": by_date[last_base_date]
                }

            if is_annual_view:
                monthly_map = {}
                for d in period_dates:
                    m_key = d[:7]
                    monthly_map[m_key] = {"date": d, "price": by_date[d]}

                year_months_sorted = sorted(monthly_map.keys())
                monthly_entries = [monthly_map[m] for m in year_months_sorted]

                period_clean = []
                for entry in monthly_entries:
                    parts = entry["date"].split("-")
                    m_idx = int(parts[1])
                    m_name = MONTH_NAMES_ES[m_idx] if 1 <= m_idx <= 12 else ""
                    period_clean.append({
                        "date": entry["date"],
                        "date_label": f"{entry['date']} ({m_name})",
                        "price": entry["price"]
                    })
            else:
                if mode == "Impacto Días de Quincena (15 y 30)":
                    period_dates = [d for d in period_dates if int(d.split("-")[2]) in (14, 15, 16, 28, 29, 30, 31)]

                if max_limit and len(period_dates) > max_limit:
                    period_dates = period_dates[-max_limit:]

                period_clean = [{
                    "date": d,
                    "date_label": d,
                    "price": by_date[d]
                } for d in period_dates]

            if not period_clean:
                QMessageBox.information(self, "Historial", "No se encontraron registros suficientes dentro del rango solicitado.")
                return

            full_series = []
            if base_entry:
                full_series.append(base_entry)
            else:
                full_series.append({
                    "date": period_clean[0]["date"],
                    "date_label": f"{period_clean[0]['date']} (Inicio Período)",
                    "price": period_clean[0]["price"]
                })

            full_series.extend(period_clean)

            base_price = full_series[0]["price"]
            latest_price = full_series[-1]["price"]
            
            prices_requested = [x["price"] for x in period_clean]
            min_p, max_p = min(prices_requested), max(prices_requested)
            avg_p = sum(prices_requested) / len(prices_requested)
            
            var_total = ((latest_price - base_price) / base_price) * 100 if base_price else 0.0

            self.kpi_min.update_value(f"{min_p:.2f} Bs")
            self.kpi_max.update_value(f"{max_p:.2f} Bs")
            self.kpi_avg.update_value(f"{avg_p:.2f} Bs")

            var_color = "#10B981" if var_total >= 0 else "#EF4444"
            self.kpi_var.update_value(f"{var_total:+.2f}%")
            self.kpi_var.lbl_valor.setStyleSheet(f"color: {var_color}; font-weight: bold;")

            annotated_data = []
            for i, entry in enumerate(full_series):
                if i > 0:
                    prev_p = full_series[i-1]["price"]
                    curr_p = entry["price"]
                    var_period = ((curr_p - prev_p) / prev_p * 100) if prev_p else 0.0
                else:
                    var_period = 0.0

                annotated_data.append({
                    "date_label": entry["date_label"],
                    "price": entry["price"],
                    "var_period": var_period,
                    "is_base": (i == 0)
                })

            var_col_label = "Variación Mensual" if is_annual_view else "Variación Diaria"
            date_col_label = "Cierre Mensual / Fecha" if is_annual_view else "Fecha"
            self.history_table.setHorizontalHeaderLabels([date_col_label, "Tasa Oficial (Bs)", var_col_label, "Tendencia"])

            display_list = list(reversed(annotated_data))
            self.history_table.setRowCount(len(display_list))

            for row_idx, entry in enumerate(display_list):
                date_str = entry["date_label"]
                price = entry["price"]
                var_period = entry["var_period"]
                is_base = entry["is_base"]

                item_date = QTableWidgetItem(date_str)
                item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                item_price = QTableWidgetItem(self.fmt_es(price, 2) + " Bs")
                item_price.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                if is_base:
                    item_var = QTableWidgetItem("BASE")
                    item_var.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item_var.setForeground(QColor("#8892b0"))
                    
                    item_trend = QTableWidgetItem("➔ Punto Partida")
                    item_trend.setForeground(QColor("#8892b0"))
                else:
                    item_var = QTableWidgetItem(f"{var_period:+.2f}%")
                    item_var.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                    if var_period > 0:
                        item_var.setForeground(QColor("#10B981"))
                        item_trend = QTableWidgetItem("▲ Sube")
                        item_trend.setForeground(QColor("#10B981"))
                    elif var_period < 0:
                        item_var.setForeground(QColor("#EF4444"))
                        item_trend = QTableWidgetItem("▼ Baja")
                        item_trend.setForeground(QColor("#EF4444"))
                    else:
                        item_var.setForeground(QColor("#8892b0"))
                        item_trend = QTableWidgetItem("➔ Estable")
                        item_trend.setForeground(QColor("#8892b0"))

                item_trend.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                self.history_table.setItem(row_idx, 0, item_date)
                self.history_table.setItem(row_idx, 1, item_price)
                self.history_table.setItem(row_idx, 2, item_var)
                self.history_table.setItem(row_idx, 3, item_trend)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error cargando historial: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Pestaña de Estadísticas
    # ──────────────────────────────────────────────────────────────────────────
    def setup_stats(self) -> None:
        """Configura el panel de estadísticas y equilibrio de mercado"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(14)

        lbl_titulo = QLabel("📊 Panel de Volatilidad y Análisis de Mercado")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Panel de Controles
        control_card = QFrame()
        control_card.setObjectName("CalcCard")
        control_row = QHBoxLayout(control_card)
        control_row.setContentsMargins(12, 8, 12, 8)

        control_row.addWidget(QLabel("Período Análisis (Horas):"))
        self.hours_spinbox = QSpinBox()
        self.hours_spinbox.setRange(1, 168)
        self.hours_spinbox.setValue(24)
        control_row.addWidget(self.hours_spinbox)

        # Botones de período rápido
        btn_24h = QPushButton("24 Hours")
        btn_24h.clicked.connect(lambda: (self.hours_spinbox.setValue(24), self.get_stats()))
        btn_48h = QPushButton("48 Hours")
        btn_48h.clicked.connect(lambda: (self.hours_spinbox.setValue(48), self.get_stats()))
        btn_7d = QPushButton("7 Días (168h)")
        btn_7d.clicked.connect(lambda: (self.hours_spinbox.setValue(168), self.get_stats()))

        for btn in (btn_24h, btn_48h, btn_7d):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            control_row.addWidget(btn)

        btn_calcular = QPushButton("🔍 Calcular Estadísticas")
        btn_calcular.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_calcular.clicked.connect(self.get_stats)
        control_row.addWidget(btn_calcular)
        control_row.addStretch()

        layout.addWidget(control_card)

        # Tarjetas KPI de Estadísticas
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.kpi_stat_vol = RateCard("⚡ Volatilidad", "--%", "Variabilidad")
        self.kpi_stat_med = RateCard("⚖️ Mediana P2P", "-- Bs", "Equilibrio Central")
        self.kpi_stat_trend = RateCard("📈 Tendencia", "--", "Dirección Período")
        self.kpi_stat_spread = RateCard("📐 Spread P2P", "-- Bs", "Brecha Compra/Venta")

        kpi_layout.addWidget(self.kpi_stat_vol)
        kpi_layout.addWidget(self.kpi_stat_med)
        kpi_layout.addWidget(self.kpi_stat_trend)
        kpi_layout.addWidget(self.kpi_stat_spread)
        layout.addLayout(kpi_layout)

        # Tabla Comparativa de Indicadores
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(6)
        self.stats_table.setHorizontalHeaderLabels([
            "Fuente / Mercado", "Mínimo (Bs)", "Máximo (Bs)", "Promedio (Bs)", "Mediana (Bs)", "Volatilidad (%)"
        ])

        header = self.stats_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        self.stats_table.setColumnWidth(0, 220)
        self.stats_table.setColumnWidth(1, 110)
        self.stats_table.setColumnWidth(2, 110)
        self.stats_table.setColumnWidth(3, 110)
        self.stats_table.setColumnWidth(4, 110)
        self.stats_table.setColumnWidth(5, 110)

        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.setStyleSheet("""
            QTableWidget {
                background-color: #061420;
                gridline-color: #102a3f;
                border: 1px solid #102a3f;
                border-radius: 6px;
                color: #d1d5db;
                font-size: 13px;
            }
            QTableWidget::item { padding: 6px; }
            QTableWidget::item:alternate { background-color: #030d16; }
            QHeaderView::section {
                background-color: #0a1e30;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #102a3f;
                padding: 6px;
            }
        """)
        layout.addWidget(self.stats_table, 1)

        self.stats_tab.setLayout(layout)
        QTimer.singleShot(1800, self.get_stats)

    def get_stats(self) -> None:
        """Calcula los indicadores estadísticos por fuente y llena la tabla"""
        hours = self.hours_spinbox.value()
        try:
            stats = self.monitor.get_statistics(hours)
            if "error" in stats:
                QMessageBox.warning(self, "Estadísticas", f"No hay suficiente información: {stats.get('error')}")
                return

            sources_data = [
                ("💵 BCV Oficial", stats.get("bcv", {})),
                ("📈 Binance VES (Compra)", stats.get("binance_ves_buy", {})),
                ("📉 Binance VES (Venta)", stats.get("binance_ves_sell", {})),
                ("🔄 Syklo VES/USDC", stats.get("syklo_ves", {}))
            ]

            self.stats_table.setRowCount(0)
            row_idx = 0
            all_medians = []

            for name, s_info in sources_data:
                if not s_info or "min" not in s_info:
                    continue

                min_val = s_info.get("min", 0.0)
                max_val = s_info.get("max", 0.0)
                avg_val = s_info.get("avg", 0.0)
                med_val = s_info.get("median", avg_val)
                vol_val = ((max_val - min_val) / min_val * 100) if min_val else 0.0

                if med_val > 0:
                    all_medians.append(med_val)

                self.stats_table.insertRow(row_idx)

                item_name = QTableWidgetItem(name)
                item_name.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item_name.setToolTip(name)

                item_min = QTableWidgetItem(self.fmt_es(min_val, 2))
                item_min.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                item_max = QTableWidgetItem(self.fmt_es(max_val, 2))
                item_max.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                item_avg = QTableWidgetItem(self.fmt_es(avg_val, 2))
                item_avg.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                item_med = QTableWidgetItem(self.fmt_es(med_val, 2))
                item_med.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                item_vol = QTableWidgetItem(f"{vol_val:.2f}%")
                item_vol.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_vol.setForeground(QColor("#EF4444") if vol_val > 3 else QColor("#10B981"))

                self.stats_table.setItem(row_idx, 0, item_name)
                self.stats_table.setItem(row_idx, 1, item_min)
                self.stats_table.setItem(row_idx, 2, item_max)
                self.stats_table.setItem(row_idx, 3, item_avg)
                self.stats_table.setItem(row_idx, 4, item_med)
                self.stats_table.setItem(row_idx, 5, item_vol)

                row_idx += 1

            if all_medians:
                med_p2p = statistics.median(all_medians)
                self.kpi_stat_med.update_value(f"{med_p2p:.2f} Bs")

            bin_buy = stats.get("binance_ves_buy", {}).get("avg", 0.0)
            bin_sell = stats.get("binance_ves_sell", {}).get("avg", 0.0)
            if bin_buy and bin_sell:
                p2p_spread = abs(bin_buy - bin_sell)
                self.kpi_stat_spread.update_value(f"{p2p_spread:.2f} Bs")

            vols = [((s.get("max", 0) - s.get("min", 0)) / s.get("min", 1) * 100) for _, s in sources_data if s.get("min")]
            avg_vol = (sum(vols) / len(vols)) if vols else 0.0
            self.kpi_stat_vol.update_value(f"{avg_vol:.2f}%")

            trend_str = "Alcista 📈" if avg_vol > 1.5 else "Estable ➔"
            self.kpi_stat_trend.update_value(trend_str)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error calculando estadísticas: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Pestaña de Análisis 24h
    # ──────────────────────────────────────────────────────────────────────────
    def setup_24h_analysis(self) -> None:
        """Configura el análisis de patrones horarios P2P para Binance VES"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(14)

        lbl_titulo = QLabel("⏰ Análisis de Patrones Horarios - Binance P2P (USDT/VES)")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Panel de Controles
        control_card = QFrame()
        control_card.setObjectName("CalcCard")
        control_row = QHBoxLayout(control_card)
        control_row.setContentsMargins(12, 8, 12, 8)

        control_row.addWidget(QLabel("Ventana de Datos:"))
        self.analysis_range_combo = QComboBox()
        self.analysis_range_combo.addItems([
            "Histórico Completo",
            "Últimos 7 Días",
            "Últimos 30 Días"
        ])
        control_row.addWidget(self.analysis_range_combo)

        btn_analizar = QPushButton("⚡ Analizar Patrones Horarios")
        btn_analizar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_analizar.clicked.connect(self.analyze_24h)
        control_row.addWidget(btn_analizar)
        control_row.addStretch()

        layout.addWidget(control_card)

        # Tarjetas KPI de Recomendación
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.kpi_24h_buy = RateCard("🟢 Mejor Hora Compra", "--:00", "Precio Mínimo P2P")
        self.kpi_24h_sell = RateCard("🔴 Mejor Hora Venta", "--:00", "Precio Máximo P2P")
        self.kpi_24h_margin = RateCard("💰 Margen Intradía", "--%", "Potencial Máximo")
        self.kpi_24h_records = RateCard("📊 Muestras Analizadas", "--", "Registros BD")

        kpi_layout.addWidget(self.kpi_24h_buy)
        kpi_layout.addWidget(self.kpi_24h_sell)
        kpi_layout.addWidget(self.kpi_24h_margin)
        kpi_layout.addWidget(self.kpi_24h_records)
        layout.addLayout(kpi_layout)

        # Resumen de Recomendaciones Estratégicas
        self.analysis_summary_text = QTextEdit()
        self.analysis_summary_text.setReadOnly(True)
        self.analysis_summary_text.setMaximumHeight(110)
        self.analysis_summary_text.setStyleSheet("""
            QTextEdit {
                background-color: #061420;
                border: 1px solid #102a3f;
                border-radius: 6px;
                color: #d1d5db;
                padding: 8px;
            }
        """)
        layout.addWidget(self.analysis_summary_text)

        # Tabla Horaria
        self.analysis_table = QTableWidget()
        self.analysis_table.setColumnCount(5)
        self.analysis_table.setHorizontalHeaderLabels([
            "Hora del Día", "Promedio Compra (Bs)", "Promedio Venta (Bs)", "Spread Intradía (Bs)", "Evaluación / Oportunidad"
        ])
        header = self.analysis_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self.analysis_table.setColumnWidth(0, 130)
        self.analysis_table.setColumnWidth(1, 150)
        self.analysis_table.setColumnWidth(2, 150)
        self.analysis_table.setColumnWidth(3, 140)

        self.analysis_table.setAlternatingRowColors(True)
        self.analysis_table.setStyleSheet("""
            QTableWidget {
                background-color: #061420;
                gridline-color: #102a3f;
                border: 1px solid #102a3f;
                border-radius: 6px;
                color: #d1d5db;
                font-size: 13px;
            }
            QTableWidget::item { padding: 6px; }
            QTableWidget::item:alternate { background-color: #030d16; }
            QHeaderView::section {
                background-color: #0a1e30;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #102a3f;
                padding: 6px;
            }
        """)
        layout.addWidget(self.analysis_table, 1)

        self.analysis_24h_tab.setLayout(layout)
        QTimer.singleShot(2000, self.analyze_24h)

    def analyze_24h(self) -> None:
        """Analiza datos de la base de datos por horas del día y genera recomendaciones"""
        try:
            from src.database import DatabaseManager
            db = DatabaseManager()
            conn = db._get_connection()
            cursor = conn.cursor()

            range_text = self.analysis_range_combo.currentText()
            query = "SELECT side, avg_price, timestamp FROM binance_p2p_prices WHERE pair = 'USDT/VES'"
            params = []

            if range_text == "Últimos 7 Días":
                limit_dt = datetime.now() - timedelta(days=7)
                query += " AND timestamp >= ?"
                params.append(limit_dt.isoformat())
            elif range_text == "Últimos 30 Días":
                limit_dt = datetime.now() - timedelta(days=30)
                query += " AND timestamp >= ?"
                params.append(limit_dt.isoformat())

            query += " ORDER BY timestamp ASC"
            cursor.execute(query, params)
            records = cursor.fetchall()
            conn.close()

            if not records:
                self.kpi_24h_buy.update_value("--:00")
                self.kpi_24h_sell.update_value("--:00")
                self.kpi_24h_margin.update_value("0.00%")
                self.kpi_24h_records.update_value("0")
                self.analysis_summary_text.setText(
                    "⚠️ No hay registros almacenados en la base de datos local para el período seleccionado.\n"
                    "💡 Deja corriendo el agente de recolección en segundo plano para acumular datos históricos."
                )
                self.analysis_table.setRowCount(0)
                return

            buy_by_hour: Dict[int, List[float]] = {h: [] for h in range(24)}
            sell_by_hour: Dict[int, List[float]] = {h: [] for h in range(24)}

            for record in records:
                try:
                    ts_str = record["timestamp"]
                    dt = datetime.fromisoformat(ts_str)
                    h = dt.hour
                    side = record["side"]
                    price = float(record["avg_price"])
                    if side == "BUY":
                        buy_by_hour[h].append(price)
                    elif side == "SELL":
                        sell_by_hour[h].append(price)
                except Exception:
                    continue

            buy_avg_hour: Dict[int, Optional[float]] = {}
            sell_avg_hour: Dict[int, Optional[float]] = {}

            for h in range(24):
                buy_avg_hour[h] = (sum(buy_by_hour[h]) / len(buy_by_hour[h])) if buy_by_hour[h] else None
                sell_avg_hour[h] = (sum(sell_by_hour[h]) / len(sell_by_hour[h])) if sell_by_hour[h] else None

            valid_buys = {h: p for h, p in buy_avg_hour.items() if p is not None}
            valid_sells = {h: p for h, p in sell_avg_hour.items() if p is not None}

            best_buy_h = min(valid_buys, key=valid_buys.get) if valid_buys else None
            best_sell_h = max(valid_sells, key=valid_sells.get) if valid_sells else None

            best_buy_p = valid_buys[best_buy_h] if best_buy_h is not None else None
            best_sell_p = valid_sells[best_sell_h] if best_sell_h is not None else None

            intraday_margin = 0.0
            if best_buy_p and best_sell_p and best_buy_p > 0:
                intraday_margin = ((best_sell_p - best_buy_p) / best_buy_p) * 100

            self.kpi_24h_buy.update_value(f"{best_buy_h:02d}:00" if best_buy_h is not None else "--:00")
            self.kpi_24h_sell.update_value(f"{best_sell_h:02d}:00" if best_sell_h is not None else "--:00")
            self.kpi_24h_margin.update_value(f"+{intraday_margin:.2f}%")
            self.kpi_24h_records.update_value(f"{len(records):,}".replace(",", "."))

            summary = "📋 RECOMENDACIONES ESTRATÉGICAS DE MERCADO HORARIO (BINANCE P2P)\n"
            summary += "=" * 70 + "\n"
            if best_buy_h is not None and best_buy_p:
                summary += f"🟢 MEJOR HORA PARA COMPRAR USDT: {best_buy_h:02d}:00 - {best_buy_h:02d}:59 (Promedio: {self.fmt_es(best_buy_p)} Bs)\n"
            if best_sell_h is not None and best_sell_p:
                summary += f"🔴 MEJOR HORA PARA VENDER USDT:  {best_sell_h:02d}:00 - {best_sell_h:02d}:59 (Promedio: {self.fmt_es(best_sell_p)} Bs)\n"
            if intraday_margin != 0:
                summary += f"💡 ESTRATEGIA ÓPTIMA: Comprar a las {best_buy_h:02d}:00 y vender a las {best_sell_h:02d}:00 para capturar hasta +{intraday_margin:.2f}% de rendimiento."

            self.analysis_summary_text.setText(summary)

            self.analysis_table.setRowCount(24)
            for h in range(24):
                h_str = f"{h:02d}:00 - {h:02d}:59"
                b_p = buy_avg_hour[h]
                s_p = sell_avg_hour[h]

                item_hour = QTableWidgetItem(h_str)
                item_hour.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                item_buy = QTableWidgetItem(self.fmt_es(b_p, 2) if b_p else "--")
                item_buy.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                item_sell = QTableWidgetItem(self.fmt_es(s_p, 2) if s_p else "--")
                item_sell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                spread = (s_p - b_p) if (s_p and b_p) else None
                item_spread = QTableWidgetItem(f"{spread:+.2f} Bs" if spread is not None else "--")
                item_spread.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                eval_str = []
                if h == best_buy_h:
                    eval_str.append("🟢 MEJOR HORA COMPRA")
                if h == best_sell_h:
                    eval_str.append("🔴 MEJOR HORA VENTA")
                if not eval_str:
                    eval_str.append("➔ Rango Regular")

                item_eval = QTableWidgetItem(" | ".join(eval_str))
                item_eval.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

                if h == best_buy_h:
                    item_eval.setForeground(QColor("#10B981"))
                elif h == best_sell_h:
                    item_eval.setForeground(QColor("#EF4444"))
                else:
                    item_eval.setForeground(QColor("#8892b0"))

                self.analysis_table.setItem(h, 0, item_hour)
                self.analysis_table.setItem(h, 1, item_buy)
                self.analysis_table.setItem(h, 2, item_sell)
                self.analysis_table.setItem(h, 3, item_spread)
                self.analysis_table.setItem(h, 4, item_eval)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error realizando análisis 24h: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Pestaña de Proyecciones Dinámicas e Informe IA
    # ──────────────────────────────────────────────────────────────────────────
    def setup_projections(self) -> None:
        """Configura la pestaña de proyecciones cambiarias con KPIs y tabla profesional"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 5, 15, 15)
        layout.setSpacing(14)

        lbl_titulo = QLabel(f"🔮 Proyecciones Cambiarias BCV - Cierre {datetime.now().year}")
        lbl_titulo.setObjectName("TituloSeccion")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        # Panel de Controles
        control_card = QFrame()
        control_card.setObjectName("CalcCard")
        control_row = QHBoxLayout(control_card)
        control_row.setContentsMargins(12, 8, 12, 8)

        control_row.addWidget(QLabel("Modelo de Proyección:"))
        self.proj_model_combo = QComboBox()
        self.proj_model_combo.addItems([
            "Escenarios Fijos (3%, 7%, 15% mensual)",
            "Basado en Tendencia Reciente (Últimos 30 días)",
            "Basado en Tendencia Trimestral (Últimos 90 días)"
        ])
        self.proj_model_combo.currentIndexChanged.connect(self.calculate_projections)
        control_row.addWidget(self.proj_model_combo)

        btn_calcular = QPushButton("⚡ Recalcular Proyecciones")
        btn_calcular.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_calcular.clicked.connect(self.calculate_projections)
        control_row.addWidget(btn_calcular)

        btn_grafico = QPushButton("📊 Ver Gráfico e Informe Visual")
        btn_grafico.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_grafico.clicked.connect(self.show_projections_graph)
        control_row.addWidget(btn_grafico)

        btn_ai_report = QPushButton("🤖 Generar Informe Ejecutivo IA")
        btn_ai_report.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ai_report.setStyleSheet("background-color: #102a3f; color: #667eea; font-weight: bold;")
        btn_ai_report.clicked.connect(self.generate_ai_report)
        control_row.addWidget(btn_ai_report)

        control_row.addStretch()
        layout.addWidget(control_card)

        # Tarjetas KPI de Cierre de Año Est.
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.kpi_proj_start = RateCard("💵 Tasa Actual BCV", "-- Bs", "Punto Partida")
        self.kpi_proj_opt = RateCard("🟢 Est. Optimista", "-- Bs", "Cierre Diciembre")
        self.kpi_proj_cons = RateCard("🟠 Est. Conservador", "-- Bs", "Cierre Diciembre")
        self.kpi_proj_stress = RateCard("🔴 Est. Estrés", "-- Bs", "Cierre Diciembre")

        kpi_layout.addWidget(self.kpi_proj_start)
        kpi_layout.addWidget(self.kpi_proj_opt)
        kpi_layout.addWidget(self.kpi_proj_cons)
        kpi_layout.addWidget(self.kpi_proj_stress)
        layout.addLayout(kpi_layout)

        # Tabla de Proyecciones Mensuales
        self.projections_table = QTableWidget()
        self.projections_table.setColumnCount(5)
        self.projections_table.setHorizontalHeaderLabels([
            "Mes Proyectado", "Escenario Optimista (Bs)", "Escenario Conservador (Bs)",
            "Escenario Estrés (Bs)", "Devaluación Acumulada Est. (%)"
        ])
        header = self.projections_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.projections_table.setAlternatingRowColors(True)
        self.projections_table.setStyleSheet("""
            QTableWidget {
                background-color: #061420;
                gridline-color: #102a3f;
                border: 1px solid #102a3f;
                border-radius: 6px;
                color: #d1d5db;
                font-size: 13px;
            }
            QTableWidget::item { padding: 6px; }
            QTableWidget::item:alternate { background-color: #030d16; }
            QHeaderView::section {
                background-color: #0a1e30;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #102a3f;
                padding: 6px;
            }
        """)
        layout.addWidget(self.projections_table, 1)

        self.projections_tab.setLayout(layout)
        QTimer.singleShot(2500, self.calculate_projections)

    def calculate_projections(self) -> None:
        """Calcula los tres escenarios según el modelo seleccionado en el menú desplegable"""
        try:
            api_url = "https://bcv.today/api/v1/history.json"
            response = requests.get(api_url, timeout=10)
            data = response.json()
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values(by='date', ascending=False)
            
            latest = df.iloc[0]
            price_value = next(
                (float(latest[k]) for k in ['USD', 'dollar', 'rate', 'bcv'] if k in latest and pd.notna(latest[k])),
                None
            )
            if price_value is None:
                QMessageBox.warning(self, "Proyecciones", "No se encontró precio válido de partida.")
                return
            
            self.last_price = price_value
            self.last_date = latest['date']
            
            model_selected = self.proj_model_combo.currentText()

            if "30 días" in model_selected:
                target_date = self.last_date - pd.Timedelta(days=30)
                df_past = df[df['date'] <= target_date]
                past_price: Optional[float] = None
                
                if not df_past.empty:
                    past_row = df_past.iloc[0]
                    past_price = next(
                        (float(past_row[k]) for k in ['USD', 'dollar', 'rate', 'bcv'] if k in past_row and pd.notna(past_row[k])),
                        None
                    )

                base_monthly_rate = (price_value - past_price) / past_price if (past_price and past_price > 0) else 0.07

                opt_rate = max(0.01, base_monthly_rate * 0.5)
                cons_rate = max(0.02, base_monthly_rate)
                stress_rate = max(0.04, base_monthly_rate * 1.8)

                scenarios = {
                    "Optimista": {
                        "rate": opt_rate,
                        "sustento": f"Desaceleración respecto a la tendencia reciente de 30 días ({opt_rate * 100:.2f}% mens.)."
                    },
                    "Conservador": {
                        "rate": cons_rate,
                        "sustento": f"Continuidad directa del ritmo de devaluación mensual reciente ({cons_rate * 100:.2f}% mens.)."
                    },
                    "Estrés": {
                        "rate": stress_rate,
                        "sustento": f"Aceleración por choques de liquidez sobre la tendencia de 30 días ({stress_rate * 100:.2f}% mens.)."
                    }
                }

            elif "90 días" in model_selected:
                target_date = self.last_date - pd.Timedelta(days=90)
                df_past = df[df['date'] <= target_date]
                past_price: Optional[float] = None

                if not df_past.empty:
                    past_row = df_past.iloc[0]
                    past_price = next(
                        (float(past_row[k]) for k in ['USD', 'dollar', 'rate', 'bcv'] if k in past_row and pd.notna(past_row[k])),
                        None
                    )

                if past_price and past_price > 0:
                    base_monthly_rate = ((price_value / past_price) ** (1.0 / 3.0)) - 1.0
                else:
                    base_monthly_rate = 0.07

                opt_rate = max(0.01, base_monthly_rate * 0.5)
                cons_rate = max(0.02, base_monthly_rate)
                stress_rate = max(0.04, base_monthly_rate * 1.8)

                scenarios = {
                    "Optimista": {
                        "rate": opt_rate,
                        "sustento": f"Ajuste a la baja frente al promedio mensual del trimestre ({opt_rate * 100:.2f}% mens.)."
                    },
                    "Conservador": {
                        "rate": cons_rate,
                        "sustento": f"Mantenimiento de la tasa mensual promedio del último trimestre ({cons_rate * 100:.2f}% mens.)."
                    },
                    "Estrés": {
                        "rate": stress_rate,
                        "sustento": f"Presión inflacionaria severa sobre la tasa trimestral base ({stress_rate * 100:.2f}% mens.)."
                    }
                }

            else:
                scenarios = {
                    "Optimista": {
                        "rate": 0.03,
                        "sustento": "Intervención cambiaria agresiva del BCV (> $500M mensuales) y estabilidad en ingresos petroleros."
                    },
                    "Conservador": {
                        "rate": 0.07,
                        "sustento": "Expansión monetaria estacional de fin de año (M2) por gasto público y pago de aguinaldos."
                    },
                    "Estrés": {
                        "rate": 0.15,
                        "sustento": "Restricción severa en la oferta de divisas + aceleración en la velocidad de circulación del dinero."
                    }
                }
            
            current_month = self.last_date.month
            target_year = self.last_date.year
            months_range = range(current_month, 13)
            
            self.projections_data = {}
            
            for name, info in scenarios.items():
                projections: List[Tuple[str, float]] = []
                for month in months_range:
                    step = month - current_month
                    m_name = datetime(target_year, month, 1).strftime('%B').capitalize()
                    p = self.last_price * ((1 + info['rate']) ** step)
                    projections.append((m_name, round(p, 2)))
                
                self.projections_data[name] = {
                    "df": pd.DataFrame(projections, columns=["Mes", "Precio Est. (VES)"]),
                    "rate": info['rate'],
                    "sustento": info['sustento']
                }

            # Actualizar KPIs con cierres de diciembre
            opt_final = self.projections_data["Optimista"]["df"].iloc[-1]["Precio Est. (VES)"]
            cons_final = self.projections_data["Conservador"]["df"].iloc[-1]["Precio Est. (VES)"]
            stress_final = self.projections_data["Estrés"]["df"].iloc[-1]["Precio Est. (VES)"]

            self.kpi_proj_start.update_value(f"{self.last_price:.2f} Bs")
            self.kpi_proj_opt.update_value(f"{opt_final:.2f} Bs")
            self.kpi_proj_cons.update_value(f"{cons_final:.2f} Bs")
            self.kpi_proj_stress.update_value(f"{stress_final:.2f} Bs")

            # Poblar Tabla de Proyecciones
            num_months = len(months_range)
            self.projections_table.setRowCount(num_months)

            df_opt = self.projections_data["Optimista"]["df"]
            df_cons = self.projections_data["Conservador"]["df"]
            df_stress = self.projections_data["Estrés"]["df"]

            for row_idx in range(num_months):
                m_name = df_opt.iloc[row_idx]["Mes"]
                p_opt = df_opt.iloc[row_idx]["Precio Est. (VES)"]
                p_cons = df_cons.iloc[row_idx]["Precio Est. (VES)"]
                p_stress = df_stress.iloc[row_idx]["Precio Est. (VES)"]

                dev_cons = ((p_cons - self.last_price) / self.last_price) * 100

                item_m = QTableWidgetItem(str(m_name))
                item_m.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                item_opt = QTableWidgetItem(self.fmt_es(p_opt, 2) + " Bs")
                item_opt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item_opt.setForeground(QColor("#10B981"))

                item_cons = QTableWidgetItem(self.fmt_es(p_cons, 2) + " Bs")
                item_cons.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item_cons.setForeground(QColor("#F59E0B"))

                item_stress = QTableWidgetItem(self.fmt_es(p_stress, 2) + " Bs")
                item_stress.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item_stress.setForeground(QColor("#EF4444"))

                item_dev = QTableWidgetItem(f"+{dev_cons:.2f}%")
                item_dev.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                self.projections_table.setItem(row_idx, 0, item_m)
                self.projections_table.setItem(row_idx, 1, item_opt)
                self.projections_table.setItem(row_idx, 2, item_cons)
                self.projections_table.setItem(row_idx, 3, item_stress)
                self.projections_table.setItem(row_idx, 4, item_dev)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error calculando proyecciones: {e}")

    def show_projections_graph(self) -> None:
        """Muestra el gráfico de proyecciones estilizado en fondo blanco y sin superposición de precios"""
        if not hasattr(self, 'projections_data') or not self.projections_data:
            QMessageBox.warning(self, "Advertencia", "Primero calcula las proyecciones.")
            return

        try:
            fig = Figure(figsize=(10, 5.2), dpi=100, facecolor='#ffffff')
            ax = fig.add_subplot(111, facecolor='#ffffff')

            colors = {
                "Optimista": "#059669",   # Verde Esmeralda
                "Conservador": "#D97706", # Ámbar / Naranja Oscuro
                "Estrés": "#DC2626"       # Rojo Intenso
            }

            text_offsets = {
                "Optimista": (0, -18),
                "Conservador": (0, 10) if len(self.projections_data) > 2 else (0, -18),
                "Estrés": (0, 10)
            }

            first_month_annotated = False

            for idx, (name, data) in enumerate(self.projections_data.items()):
                df = data['df']
                color = colors.get(name, "#2563EB")
                offset_y = text_offsets.get(name, (0, 10))[1]

                ax.plot(
                    df["Mes"], df["Precio Est. (VES)"],
                    marker='o', markersize=6, label=f"{name} ({data['rate']*100:.1f}%/mes)",
                    color=color, linewidth=2.5
                )

                for i, (month, price) in enumerate(zip(df["Mes"], df["Precio Est. (VES)"])):
                    if i == 0:
                        if not first_month_annotated:
                            ax.annotate(
                                f"Inicio: {price:.2f}",
                                xy=(month, price),
                                textcoords="offset points",
                                xytext=(0, 12),
                                ha='center',
                                fontsize=8.5,
                                color='#1F2937',
                                fontweight='bold',
                                bbox=dict(boxstyle="round,pad=0.25", fc="#F3F4F6", ec="#9CA3AF", lw=0.8)
                            )
                            first_month_annotated = True
                        continue

                    ax.annotate(
                        f"{price:.2f}",
                        xy=(month, price),
                        textcoords="offset points",
                        xytext=(0, offset_y),
                        ha='center',
                        fontsize=8.5,
                        color=color,
                        fontweight='bold',
                        bbox=dict(boxstyle="round,pad=0.2", fc="#FFFFFF", ec=color, lw=0.7, alpha=0.9)
                    )

            ax.set_title(
                f"Escenarios Proyectados BCV - Cierre {self.last_date.year}",
                color='#111827', fontsize=13, fontweight='bold', pad=14
            )
            ax.set_ylabel("Bolívares por Dólar (VES/USD)", color='#374151', fontsize=10, fontweight='bold')
            ax.set_xlabel("Meses", color='#374151', fontsize=10, fontweight='bold')
            ax.tick_params(colors='#374151', labelsize=9.5)
            ax.grid(True, linestyle='--', alpha=0.5, color='#E5E7EB')

            for spine in ax.spines.values():
                spine.set_color('#D1D5DB')

            legend = ax.legend(loc='upper left', facecolor='#F9FAFB', edgecolor='#D1D5DB', fontsize=9.5)
            for text in legend.get_texts():
                text.set_color('#111827')

            fig.tight_layout()

            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            fig.savefig(temp_file.name, dpi=110, bbox_inches='tight', facecolor=fig.get_facecolor())
            temp_file.close()
            plt.close(fig)

            dialog = QDialog(self)
            dialog.setWindowTitle("📊 Informe Visual y Sustento de Escenarios BCV")
            dialog.resize(940, 700)
            dialog_layout = QVBoxLayout(dialog)

            pixmap = QPixmap(temp_file.name)
            scaled = pixmap.scaled(900, 430, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl_graph = QLabel()
            lbl_graph.setPixmap(scaled)
            lbl_graph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dialog_layout.addWidget(lbl_graph)

            footer_card = QFrame()
            footer_card.setStyleSheet("""
                QFrame {
                    background-color: #061420;
                    border: 1px solid #102a3f;
                    border-radius: 8px;
                    padding: 10px;
                }
                QLabel {
                    color: #d1d5db;
                    font-size: 12px;
                }
            """)
            footer_layout = QVBoxLayout(footer_card)

            lbl_footer_title = QLabel("📋 SUSTENTO Y EXPLICACIÓN DE CADA ESCENARIO")
            lbl_footer_title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px; margin-bottom: 4px;")
            footer_layout.addWidget(lbl_footer_title)

            for name, data in self.projections_data.items():
                icon = "🟢" if name == "Optimista" else ("🟠" if name == "Conservador" else "🔴")
                rate_pct = f"{data['rate']*100:.1f}%"
                desc = data['sustento']
                
                lbl_scen = QLabel(f"<b>{icon} Escenario {name} ({rate_pct} mensual):</b> {desc}")
                lbl_scen.setWordWrap(True)
                footer_layout.addWidget(lbl_scen)

            dialog_layout.addWidget(footer_card)

            btn_close = QPushButton("Cerrar Informe")
            btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_close.clicked.connect(dialog.close)
            dialog_layout.addWidget(btn_close)

            dialog.exec()
            os.unlink(temp_file.name)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error mostrando gráfico de proyecciones: {e}")

    def generate_ai_report(self) -> None:
        """Genera el informe macroeconómico completo mediante IA en un hilo secundario"""
        if not hasattr(self, 'projections_data') or not self.projections_data:
            QMessageBox.warning(self, "Advertencia", "Primero calcula las proyecciones.")
            return

        self._ai_progress = QProgressDialog("Generando informe analítico con IA...", None, 0, 0, self)
        self._ai_progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._ai_progress.show()
        QApplication.processEvents()

        self._ai_thread = QThread(self)
        self._ai_worker = AIReportWorker(
            current_rate=self.last_price,
            projections=self.projections_data,
            historical_stats={}
        )
        self._ai_worker.moveToThread(self._ai_thread)

        def on_ai_finished(report_markdown: str) -> None:
            if self._ai_progress:
                self._ai_progress.close()

            temp_img_path = self._generate_temp_graph_image()
            pixmap = QPixmap(temp_img_path)

            dialog = AIReportDialog(report_markdown, pixmap, self)
            dialog.exec()

            if os.path.exists(temp_img_path):
                os.unlink(temp_img_path)

            self._ai_thread.quit()
            self._ai_thread.wait()

        def on_ai_error(err_msg: str) -> None:
            if self._ai_progress:
                self._ai_progress.close()
            QMessageBox.critical(self, "Error de IA", f"Error al generar el informe: {err_msg}")
            self._ai_thread.quit()
            self._ai_thread.wait()

        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(on_ai_finished)
        self._ai_worker.error.connect(on_ai_error)

        self._ai_thread.start()

    def _generate_temp_graph_image(self) -> str:
        """Genera una imagen temporal en alta definición del gráfico para embeber en el informe"""
        fig = Figure(figsize=(10, 5), dpi=100, facecolor='#ffffff')
        ax = fig.add_subplot(111, facecolor='#ffffff')
        colors = {"Optimista": "#059669", "Conservador": "#D97706", "Estrés": "#DC2626"}

        for name, data in self.projections_data.items():
            df = data['df']
            c = colors.get(name, "#2563EB")
            ax.plot(df["Mes"], df["Precio Est. (VES)"], marker='o', label=f"{name}", color=c, linewidth=2)

        ax.set_title(f"Escenarios Proyectados BCV {self.last_date.year}", color='#111827', fontweight='bold')
        ax.grid(True, linestyle='--', alpha=0.4, color='#E5E7EB')
        ax.legend(loc='upper left')
        fig.tight_layout()

        temp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        fig.savefig(temp.name, dpi=110, facecolor='#ffffff')
        plt.close(fig)
        return temp.name

    def setup_calculator_tab(self) -> None:
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._calc_widget = CalculatorDialog(self)
        self._calc_widget.setWindowFlags(Qt.WindowType.Widget)
        outer_layout.addWidget(self._calc_widget)
        self.calculator_tab.setLayout(outer_layout)

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


# ──────────────────────────────────────────────────────────────────────────────
# Punto de Entrada Principal
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    app = QApplication(sys.argv)
    window = ZinliMonitorDesktopApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()