# MoneyBot

## Requisitos

- Python 3.10+
- Dependencias instaladas con `pip install -r requirements.txt`

## Arranque

```bash
python BOT.py
```

Al iniciar, el servicio queda disponible en `http://127.0.0.1:8000` y la UI en:

- `http://127.0.0.1:8000/ui`

## Entorno sin interfaz gráfica

MoneyBot expone una UI web vía FastAPI, por lo que no requiere entorno gráfico
en la máquina donde corre. Puedes abrir `/ui` desde cualquier navegador en otra
máquina si la red lo permite.

## Logs y limpieza

Los logs se guardan en `logs/moneybot.log` con rotación automática. Puedes ajustar
la retención con:

- `LOG_MAX_BYTES`: tamaño máximo del archivo antes de rotar (por defecto 5 MB).
- `LOG_BACKUP_COUNT`: cantidad de backups a conservar (por defecto 5).

Para limpiar logs de forma manual o programada, hay dos endpoints protegidos por
`LOG_CLEAN_TOKEN` enviado en el header `X-API-Token`:

- `POST /logs/clear`: vacía el log principal y borra backups rotados.
- `POST /logs/delete`: elimina el directorio de logs y recrea un log vacío.

## Modos de ejecución

MoneyBot soporta los siguientes modos configurables con `BOT_MODE`:

- `SIM`: simulación local con replay.
- `LIVE`: streaming en tiempo real sobre Binance mainnet.
- `TESTNET`: streaming en tiempo real sobre Binance testnet.
- `HIST`: replay histórico usando eventos grabados en `./data`.

## Streams de mercado y estrategia de acumulación

La estrategia de acumulación consume tres tipos de streams de mercado:

- `aggTrade`: trades agregados que alimentan el cálculo de volumen comprador/vendedor.
- `depth`: actualizaciones del order book que ayudan a detectar resistencia o presión en niveles cercanos.
- `bookTicker`: mejor bid/ask para actualizar el precio actual y validar objetivos.

En conjunto, el motor usa `aggTrade` para medir el ratio de compras sobre ventas,
`depth`/`bookTicker` para contextualizar la liquidez disponible y definir entradas o
cancelaciones, y el mejor bid/ask para calcular los precios de salida.

Variables de entorno útiles:

- `LIVE_WS_URL`: URL de WebSocket para mainnet (por defecto `wss://stream.binance.com:9443/ws`).
- `TESTNET_WS_URL`: URL de WebSocket para testnet (por defecto `wss://testnet.binance.vision/ws`).
- `HIST_SYMBOLS`: símbolos para el modo histórico (por defecto `BTCUSDT`).
- `USE_ACCUMULATION_STRATEGY`: fuerza la estrategia de acumulación en `SIM`/`HIST` (en `LIVE`/`TESTNET` se usa siempre).
- `ACCUMULATION_TICK_SIZE`: tamaño del tick usado para calcular objetivos y cancelaciones.
- `ACCUMULATION_MIN_VOLUME_BTC`: volumen mínimo en el último minuto para permitir entradas (por defecto `5`).
- `ACCUMULATION_BUY_THRESHOLD`: umbral de acumulación en el lado comprador (por defecto `0.60`).
- `ACCUMULATION_FEE_RATE`: comisión estimada para el cálculo de P&L cuando no se reporta en los fills.
- `ACCUMULATION_PROFIT_TICK`: incremento de precio para la orden de salida (por defecto igual a `ACCUMULATION_TICK_SIZE`).
- `ACCUMULATION_TRADE_NOTIONAL`: notional fijo por operación; si no se define se usa el 10% del capital por símbolo.
