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
