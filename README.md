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
