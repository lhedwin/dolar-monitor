#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Configuration Manager
Gestiona la carga y validación de la configuración desde archivos YAML
"""

import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigManager:
    """Gestor de configuración centralizado"""
    
    # Configuración por defecto
    DEFAULT_CONFIG = {
        "general": {
            "debug": False,
            "log_level": "INFO",
            "timeout": 30,
            "max_retries": 3,
        },
        "bcv": {
            "api_url": "https://bcv-api.rafnixg.dev/rates/",
            "web_url": "https://bcv.org.ve",
            "timezone": "America/Caracas",
            "fallback_enabled": True,
            "timeout": 10,
        },
        "binance_p2p": {
            "base_url": "https://p2p.binance.com",
            "endpoint": "/bapi/c2c/v2/friendly/c2c/adv/search",
            "default_limit": 20,
            "timeout": 20,
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "ves": {
                "fiat": "VES",
                "filter_merchant": True,
                "limit": 20,
            },
            "usd_zinli": {
                "fiat": "USD",
                "payment_method": "zinli",
                "filter_merchant": True,
                "limit": 20,
            },
        },
        "syklo": {
            "base_url": "https://syklo-orderbook.ddns.net",
            "timeout": 100,
            "retries": 3,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "ves_usdc": {
                "send_pms": "VES:VE:VEBN1,VES:VE:VEBN2,VES:VE:VEBN29",
                "receive_pms": "USDC:ALL:SYKLO",
                "method_aliases": {
                    "VEBN1": "Banco de Venezuela",
                    "VEBN2": "Banesco",
                    "VEBN29": "BNC",
                },
                "send_methods": ["VEBN1", "VEBN2", "VEBN29"],
            },
            "usdc_usd": {
                "send_pms": "USDC:ALL:SYKLO",
                "receive_pms": "USD:ALL:ZI",
                "send_methods": ["USD", "ZI"],
            },
        },
        "output": {
            "format": "table",
            "colors": True,
            "decimal_places": 2,
            "show_timestamp": True,
        },
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Inicializa el gestor de configuración
        
        Args:
            config_path: Ruta al archivo de configuración. Si es None, busca config.yaml
        """
        self.config_path = config_path or self._find_config_file()
        self.config = self._load_config()
    
    def _find_config_file(self) -> str:
        """Busca el archivo de configuración en ubicaciones estándar"""
        # Directorio actual
        current_dir = Path.cwd()
        config_file = current_dir / "config.yaml"
        if config_file.exists():
            return str(config_file)
        
        # Directorio del script
        script_dir = Path(__file__).parent.parent
        config_file = script_dir / "config.yaml"
        if config_file.exists():
            return str(config_file)
        
        # Directorio home
        home_dir = Path.home()
        config_file = home_dir / ".zinli_monitor" / "config.yaml"
        if config_file.exists():
            return str(config_file)
        
        # Retornar ruta por defecto si no existe
        return str(current_dir / "config.yaml")
    
    def _load_config(self) -> Dict[str, Any]:
        """Carga la configuración desde archivo o usa defaults"""
        if not self.config_path or not os.path.exists(self.config_path):
            print(f"Config file not found: {self.config_path}, using defaults")
            return self.DEFAULT_CONFIG.copy()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)
            
            if not user_config:
                print(f"Empty config file: {self.config_path}, using defaults")
                return self.DEFAULT_CONFIG.copy()
            
            # Merge con defaults (user config sobrescribe defaults)
            merged_config = self._deep_merge(self.DEFAULT_CONFIG.copy(), user_config)
            return merged_config
            
        except yaml.YAMLError as e:
            print(f"Error parsing YAML config: {e}, using defaults")
            return self.DEFAULT_CONFIG.copy()
        except Exception as e:
            print(f"Error loading config: {e}, using defaults")
            return self.DEFAULT_CONFIG.copy()
    
    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """Merge profundo de diccionarios"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Obtiene un valor de configuración usando notación de puntos
        
        Args:
            key: Clave en formato "seccion.subseccion.valor"
            default: Valor por defecto si no se encuentra
            
        Returns:
            El valor de configuración o el default
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Obtiene una sección completa de configuración
        
        Args:
            section: Nombre de la sección
            
        Returns:
            Diccionario con la sección o dict vacío si no existe
        """
        return self.config.get(section, {})
    
    def set(self, key: str, value: Any) -> None:
        """
        Establece un valor de configuración (solo en memoria)
        
        Args:
            key: Clave en formato "seccion.subseccion.valor"
            value: Valor a establecer
        """
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def save(self, path: Optional[str] = None) -> bool:
        """
        Guarda la configuración actual a un archivo YAML
        
        Args:
            path: Ruta donde guardar. Si es None, usa self.config_path
            
        Returns:
            True si se guardó correctamente, False en caso contrario
        """
        save_path = path or self.config_path
        
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def reload(self) -> None:
        """Recarga la configuración desde el archivo"""
        self.config = self._load_config()
    
    def validate(self) -> bool:
        """
        Valida que la configuración sea correcta
        
        Returns:
            True si la configuración es válida, False en caso contrario
        """
        required_sections = ["general", "bcv", "binance_p2p", "syklo", "output"]
        
        for section in required_sections:
            if section not in self.config:
                print(f"Missing required section: {section}")
                return False
        
        # Validar campos críticos
        if not self.get("bcv.api_url"):
            print("Missing bcv.api_url")
            return False
        
        if not self.get("binance_p2p.base_url"):
            print("Missing binance_p2p.base_url")
            return False
        
        if not self.get("syklo.base_url"):
            print("Missing syklo.base_url")
            return False
        
        return True
    
    def __repr__(self) -> str:
        return f"ConfigManager(path={self.config_path})"


# Instancia global por defecto
_default_config = None


def get_config(config_path: Optional[str] = None) -> ConfigManager:
    """
    Obtiene la instancia del gestor de configuración (singleton)
    
    Args:
        config_path: Ruta al archivo de configuración (solo primera vez)
        
    Returns:
        Instancia de ConfigManager
    """
    global _default_config
    if _default_config is None:
        _default_config = ConfigManager(config_path)
    return _default_config


def reset_config() -> None:
    """Resetea la instancia global de configuración"""
    global _default_config
    _default_config = None
