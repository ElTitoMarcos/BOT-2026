from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from moneybot.config import VALID_ENVIRONMENTS, get_config, load_env, save_config
from moneybot.runtime import BotRuntime

app = FastAPI(title="MoneyBot")
runtime = BotRuntime()

load_env()


def _mask_api_key(api_key: Optional[str]) -> str:
    if not api_key:
        return ""
    tail = api_key[-4:]
    return f"****{tail}"


class ConfigPayload(BaseModel):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    env: Optional[str] = None
    persist: bool = True


@app.get("/", include_in_schema=False)
def redirect_to_ui() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@app.get("/config/status")
def config_status() -> dict:
    config = get_config()
    return {
        "has_api_key": bool(config.get("BINANCE_API_KEY")),
        "env": config.get("ENV", "LIVE"),
    }


@app.post("/control/start")
def control_start() -> dict:
    runtime.start()
    return runtime.status()


@app.post("/control/stop")
def control_stop() -> dict:
    runtime.stop()
    return runtime.status()


@app.post("/control/pause")
def control_pause() -> dict:
    runtime.pause()
    return runtime.status()


@app.post("/control/resume")
def control_resume() -> dict:
    runtime.resume()
    return runtime.status()


@app.get("/status")
def runtime_status() -> dict:
    return runtime.status()


@app.post("/config/save")
def config_save(payload: ConfigPayload) -> dict:
    current = get_config()
    api_key = payload.api_key.strip() if payload.api_key else None
    api_secret = payload.api_secret.strip() if payload.api_secret else None
    env = payload.env.strip().upper() if payload.env else current.get("ENV", "LIVE")

    if api_key and api_key.startswith("****"):
        api_key = None

    if env not in VALID_ENVIRONMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"ENV inválido: {env}. Usa LIVE o TESTNET.",
        )

    if api_key is None:
        api_key = current.get("BINANCE_API_KEY")
    if api_secret is None:
        api_secret = current.get("BINANCE_API_SECRET")

    save_config(api_key, api_secret, env, persist=payload.persist)

    return {
        "has_api_key": bool(api_key),
        "env": env,
    }


@app.get("/ui", response_class=HTMLResponse)
def ui_placeholder() -> str:
    config = get_config()
    masked_key = _mask_api_key(config.get("BINANCE_API_KEY"))
    env_value = config.get("ENV", "LIVE")
    return f"""
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8" />
        <title>MoneyBot UI</title>
        <style>
          body {{
            font-family: Arial, sans-serif;
            margin: 2rem;
            background: #0f172a;
            color: #f8fafc;
          }}
          .card {{
            max-width: 520px;
            background: #1e293b;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.35);
          }}
          label {{
            display: block;
            margin-top: 16px;
            margin-bottom: 6px;
            font-weight: 600;
          }}
          input, select {{
            width: 100%;
            padding: 10px 12px;
            border-radius: 8px;
            border: 1px solid #334155;
            background: #0f172a;
            color: #f8fafc;
          }}
          button {{
            margin-top: 20px;
            width: 100%;
            padding: 12px 16px;
            border-radius: 8px;
            border: none;
            background: #38bdf8;
            color: #0f172a;
            font-weight: 700;
            cursor: pointer;
          }}
          .status {{
            margin-top: 12px;
            font-size: 0.9rem;
            color: #94a3b8;
          }}
        </style>
      </head>
      <body>
        <h1>MoneyBot UI</h1>
        <div class="card">
          <h2>Config</h2>
          <label for="api-key">API Key</label>
          <input id="api-key" type="text" placeholder="API Key" value="{masked_key}" />

          <label for="api-secret">API Secret</label>
          <input id="api-secret" type="password" placeholder="API Secret" />

          <label for="env">Entorno</label>
          <select id="env">
            <option value="LIVE">LIVE</option>
            <option value="TESTNET">TESTNET</option>
          </select>

          <button id="save-config" type="button">Guardar configuración</button>
          <div class="status" id="status"></div>
        </div>
        <script>
          const envSelect = document.getElementById("env");
          envSelect.value = "{env_value}";

          const apiKeyInput = document.getElementById("api-key");
          const apiSecretInput = document.getElementById("api-secret");
          const statusEl = document.getElementById("status");

          const maskKey = (key) => {
            if (!key) return "";
            const tail = key.slice(-4);
            return `****${{tail}}`;
          };

          document.getElementById("save-config").addEventListener("click", async () => {
            const payload = {{ env: envSelect.value }};
            if (apiKeyInput.value && !apiKeyInput.value.startsWith("****")) {{
              payload.api_key = apiKeyInput.value;
            }}
            if (apiSecretInput.value) {{
              payload.api_secret = apiSecretInput.value;
            }}

            statusEl.textContent = "Guardando...";
            try {{
              const response = await fetch("/config/save", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify(payload),
              }});
              if (!response.ok) {{
                throw new Error("No se pudo guardar la configuración");
              }}
              const data = await response.json();
              if (payload.api_key) {{
                apiKeyInput.value = maskKey(payload.api_key);
              }}
              apiSecretInput.value = "";
              statusEl.textContent = data.has_api_key
                ? `Configuración guardada (${data.env}).`
                : "Configuración guardada, sin API key.";
            }} catch (error) {{
              statusEl.textContent = error.message;
            }}
          }});
        </script>
      </body>
    </html>
    """
