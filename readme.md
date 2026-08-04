# Dólar Monitor - Monitor de tasas y análisis horario

![Python](https://img.shields.io/badge/python-3.x-blue.svg) ![Status](https://img.shields.io/badge/status-active-green.svg) ![License](https://img.shields.io/badge/license-GPLv3-blue.svg) ![Security](https://img.shields.io/badge/security-audit-red.svg) ![Database](https://img.shields.io/badge/database-SQLite-lightgrey.svg)

Aplicación de escritorio y agente de bandeja para recopilar y analizar tasas (BCV, Binance P2P, Syklo). Registra datos periódicos en una base SQLite y muestra estadísticas y análisis por hora (p. ej. mejores horas para comprar/vender).

## 📋 Descripción

Dólar Monitor recopila automáticamente tasas del BCV y precios de Binance P2P (USDT/VES, USDT/USD) junto con datos de Syklo. Los datos se guardan en una base SQLite (zinli_monitor.db) y la app de escritorio muestra:

- Dashboard con tarjetas resumen (BCV, Binance, Syklo)
- Pestaña "Análisis 24h": agrupa datos históricos por hora del día para identificar las mejores horas para comprar o vender
- Estadísticas y análisis de oportunidades de arbitraje

El agente de bandeja (dolar_monitor_agent.py) permite recolectar datos cada 10 minutos sin abrir la interfaz principal.

## 📁 Estructura del proyecto

```
/home/lhedwin/Programacion/Git/Zinli/
├── desktop_app.py                 # Aplicación principal (GUI)
├── dolar_monitor_agent.py         # Agente de bandeja (tray) que recolecta datos periódicamente
├── readme.md                      # Este archivo
├── config.yaml                    # Configuración (opcional)
├── zinli_monitor.db               # Base de datos SQLite (datos históricos)
└── src/
    ├── database.py                # Gestor de la base de datos
    ├── config_manager.py          # Cargador de configuración
    ├── providers/                 # Proveedores: BCV, Binance P2P, Syklo
    └── utils.py                   # Utilidades varias
```

## 🔧 Requisitos

- Sistema operativo: Linux (probado en CachyOS/Arch Linux)
- Python 3.x
- Dependencias Python: requests, PyQt6 (si usas la GUI)

Instalación rápida (ejemplo Debian/Ubuntu):

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 -m pip install -r requirements.txt  # si existe
# o instalar dependencias necesarias manualmente
python3 -m pip install requests PyQt6
```

## 🚀 Uso

1. Ejecutar la app de escritorio:

```bash
python3 desktop_app.py
```

2. Ejecutar el agente de bandeja (opcional, para recopilación continua):

```bash
python3 dolar_monitor_agent.py &
```

Nota: el agente guarda datos en `zinli_monitor.db` y actualiza el menú de la bandeja cada ciclo.

## 🗄️ Base de datos

- Archivo: `zinli_monitor.db` en la raíz del proyecto
- Tablas principales: `bcv_rates`, `binance_p2p_prices`, `consolidated_data`, `syklo_orderbook`

Nota: el archivo de base de datos no se versiona en el repositorio (está en `.gitignore`). Para facilitar que otros usuarios arranquen la app sin un `.db` real, se incluye un script de inicialización.

Crear la base de datos y agregar datos de ejemplo:

```bash
# Crea ./zinli_monitor.db con 8 filas de ejemplo por tabla (por defecto)
python3 init_db.py --path ./zinli_monitor.db

# Especificar distinto tamaño de semilla
python3 init_db.py --path ./zinli_monitor.db --sample-size 16

# Forzar sobrescritura (se crea respaldo .bak)
python3 init_db.py --path ./zinli_monitor.db --force

# Crear solo esquema sin datos de ejemplo
python3 init_db.py --no-sample
```

Consultas útiles:

```bash
# Ver tablas
sqlite3 zinli_monitor.db ".tables"
# Contar filas en binance_p2p_prices
sqlite3 zinli_monitor.db "SELECT COUNT(*) FROM binance_p2p_prices;"
```

## 🔁 Autostart (opcional)

En Linux se puede habilitar autostart creando un archivo `.desktop` en `~/.config/autostart/` con Exec apuntando a `python3 /ruta/al/proyecto/dolar_monitor_agent.py`.

## 🧰 Mantenimiento y limpieza

- Los artefactos `__pycache__` y `*.pyc` pueden eliminarse de forma segura.
- La base de datos antigua en `src/providers/` (si existe) puede archivarse o eliminarse si ya fue migrada.
- El agente ya no escribe logs rotativos por defecto (el archivo de log fue removido por limpieza). Si deseas logging, reactivar la configuración en `dolar_monitor_agent.py`.

## 🐞 Solución de problemas

- Si la app no muestra datos: verificar que `zinli_monitor.db` existe y contiene registros.
- Si el agente no guarda datos: comprobar que el agente está corriendo (`pgrep -f dolar_monitor_agent.py`) y que `dolar_monitor_agent.py` está ejecutándose desde el directorio del proyecto (usa `os.chdir(BASE_DIR)` internamente).
- Reiniciar agente (ejemplo):

```bash
# localizar PID y matar proceso
pgrep -f dolar_monitor_agent.py
kill <PID>
# reiniciar
python3 dolar_monitor_agent.py &
```

## 🧩 Desarrollo

- Código fuente en `src/` (providers, database, utils)
- Buen punto de partida: `src/database.py` y `src/providers/*` para entender cómo se guardan y normalizan las tasas

## 👨‍💻 Contribuciones

Para contribuir: abrir issues o pull requests con cambios pequeños y pruebas. Antes de modificar la ruta de la BD o la lógica de persistencia, confirmar migraciones si existen múltiples archivos DB.

## ⚖️ Licencia

Licencia: GNU GPL v3 (ver archivo LICENSE en el repositorio).

---

**Proyecto**: Dólar Monitor  
**Autor**: Edwin López  
**Última actualización**: 2026-08-04