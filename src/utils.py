#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Utility Functions
Funciones comunes utilizadas por diferentes módulos del sistema
"""

from typing import List, Dict, Any, Optional
from datetime import datetime


def calculate_price_stats(prices: List[float]) -> Dict[str, Any]:
    """
    Calcula estadísticas de precios de forma genérica
    
    Args:
        prices: Lista de precios
        
    Returns:
        Diccionario con estadísticas
    """
    if not prices:
        return {"error": "No prices available"}
    
    prices_sorted = sorted(prices)
    return {
        "count": len(prices),
        "min_price": min(prices),
        "max_price": max(prices),
        "avg_price": sum(prices) / len(prices),
        "median_price": prices_sorted[len(prices_sorted) // 2],
        "top_5_prices": sorted(prices)[:5],
    }


def calculate_spread(buy_price: float, sell_price: float) -> Dict[str, float]:
    """
    Calcula el spread entre precios de compra y venta
    
    Args:
        buy_price: Precio de compra
        sell_price: Precio de venta
        
    Returns:
        Diccionario con spread y porcentaje
    """
    if not buy_price or not sell_price:
        return {"spread": 0, "spread_percent": 0}
    
    spread = buy_price - sell_price
    spread_percent = (spread / sell_price) * 100 if sell_price != 0 else 0
    
    return {
        "spread": spread,
        "spread_percent": spread_percent,
    }


def format_table(
    data: List[Dict[str, Any]],
    columns: List[str],
    headers: List[str],
    column_widths: Optional[List[int]] = None
) -> str:
    """
    Formatea datos en formato de tabla
    
    Args:
        data: Lista de diccionarios con datos
        columns: Lista de claves a mostrar
        headers: Lista de encabezados
        column_widths: Lista de anchos de columna (opcional)
        
    Returns:
        String con la tabla formateada
    """
    if not data:
        return "No data available"
    
    # Calcular anchos si no se proporcionan
    if column_widths is None:
        column_widths = []
        for i, col in enumerate(columns):
            max_len = len(headers[i])
            for row in data:
                value = str(row.get(col, ""))
                max_len = max(max_len, len(value))
            column_widths.append(max_len + 2)  # +2 para padding
    
    # Crear línea separadora
    separator = "+" + "+".join(["-" * w for w in column_widths]) + "+"
    
    # Crear header
    header_line = "|"
    for i, header in enumerate(headers):
        header_line += f" {header:<{column_widths[i]-2}} |"
    
    # Crear filas de datos
    rows = []
    for row_data in data:
        row_line = "|"
        for i, col in enumerate(columns):
            value = str(row_data.get(col, ""))
            row_line += f" {value:<{column_widths[i]-2}} |"
        rows.append(row_line)
    
    # Combinar todo
    table = separator + "\n"
    table += header_line + "\n"
    table += separator + "\n"
    table += "\n".join(rows) + "\n"
    table += separator
    
    return table


def format_framed_output(data: Dict[str, Any], field_order: List[str], labels: Dict[str, str]) -> str:
    """
    Formatea datos en un marco elegante
    
    Args:
        data: Diccionario con datos
        field_order: Orden de campos a mostrar
        labels: Diccionario de etiquetas para cada campo
        
    Returns:
        String con el output formateado
    """
    max_key_len = max(len(labels[k]) for k in field_order)
    max_val_len = max(len(str(data.get(k, ""))) for k in field_order)
    
    border = "+" + "-" * (max_key_len + 2) + "+" + "-" * (max_val_len + 2) + "+"
    border_green = "\033[32m" + border + "\033[0m"
    
    framed_output = border_green + "\n"
    for i, k in enumerate(field_order):
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
        if i < len(field_order) - 1:
            framed_output += border_green + "\n"
    framed_output += border_green
    return framed_output


def format_timestamp(timestamp: Optional[str], format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Formatea un timestamp ISO a un formato legible
    
    Args:
        timestamp: Timestamp en formato ISO
        format_str: Formato de salida
        
    Returns:
        String con el timestamp formateado
    """
    if not timestamp:
        return "N/A"
    
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.strftime(format_str)
    except (ValueError, AttributeError):
        return timestamp


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Convierte un valor a float de forma segura
    
    Args:
        value: Valor a convertir
        default: Valor por defecto si falla la conversión
        
    Returns:
        Float o valor por defecto
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Convierte un valor a int de forma segura
    
    Args:
        value: Valor a convertir
        default: Valor por defecto si falla la conversión
        
    Returns:
        Int o valor por defecto
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def format_currency(value: float, currency: str = "USD", decimal_places: int = 2) -> str:
    """
    Formatea un valor como moneda
    
    Args:
        value: Valor numérico
        currency: Código de moneda
        decimal_places: Número de decimales
        
    Returns:
        String con el valor formateado
    """
    return f"{value:,.{decimal_places}f} {currency}"


def format_percentage(value: float, decimal_places: int = 2) -> str:
    """
    Formatea un valor como porcentaje
    
    Args:
        value: Valor numérico
        decimal_places: Número de decimales
        
    Returns:
        String con el porcentaje formateado
    """
    return f"{value:+.{decimal_places}f}%"


def detect_arbitrage_opportunity(
    spread_percent: float,
    threshold: float = 2.0,
    opportunity_type: str = "general"
) -> Dict[str, Any]:
    """
    Detecta si hay una oportunidad de arbitraje basada en el spread
    
    Args:
        spread_percent: Porcentaje de spread
        threshold: Umbral para considerar oportunidad
        opportunity_type: Tipo de oportunidad
        
    Returns:
        Diccionario con información de la oportunidad
    """
    is_opportunity = abs(spread_percent) >= threshold
    
    if is_opportunity:
        return {
            "is_opportunity": True,
            "type": opportunity_type,
            "spread_percent": spread_percent,
            "threshold": threshold,
            "recommendation": "buy" if spread_percent > 0 else "sell",
            "significance": "high" if abs(spread_percent) > threshold * 2 else "moderate",
        }
    else:
        return {
            "is_opportunity": False,
            "type": opportunity_type,
            "spread_percent": spread_percent,
            "threshold": threshold,
            "recommendation": "wait",
            "significance": "low",
        }
