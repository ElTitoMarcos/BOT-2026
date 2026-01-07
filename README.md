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

## Modos de ejecución

MoneyBot soporta los siguientes modos configurables con `BOT_MODE`:

- `SIM`: simulación local con replay.
- `LIVE`: streaming en tiempo real sobre Binance mainnet.
- `TESTNET`: streaming en tiempo real sobre Binance testnet.
- `HIST`: replay histórico usando eventos grabados en `./data`.

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
