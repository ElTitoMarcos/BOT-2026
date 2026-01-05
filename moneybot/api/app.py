from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from moneybot.config import VALID_ENVIRONMENTS, get_config, load_env, save_config
from moneybot.observability import ObservabilityStore
from moneybot.runtime import BotRuntime

app = FastAPI(title="MoneyBot")
runtime = BotRuntime()
observability = ObservabilityStore()

load_env()


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


@app.get("/metrics")
def metrics_status() -> dict:
    return observability.get_metrics()


@app.get("/trades")
def trades_status(limit: int = Query(50, ge=1, le=200)) -> dict:
    return {"trades": observability.get_trades(limit)}


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
    env_value = config.get("ENV", "LIVE")
    return f"""
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8" />
        <title>MoneyBot UI</title>
        <style>
          body {{
            font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
            margin: 0;
            background: #0b1120;
            color: #e2e8f0;
          }}
          header {{
            padding: 24px 32px;
            background: #111827;
            border-bottom: 1px solid #1f2937;
          }}
          header h1 {{
            margin: 0;
            font-size: 1.4rem;
          }}
          header p {{
            margin: 6px 0 0;
            color: #94a3b8;
            font-size: 0.9rem;
          }}
          main {{
            padding: 24px 32px 40px;
          }}
          .tabs {{
            display: flex;
            gap: 12px;
            border-bottom: 1px solid #1f2937;
            margin-bottom: 20px;
          }}
          .tab-button {{
            padding: 10px 16px;
            border: none;
            background: transparent;
            color: #94a3b8;
            font-weight: 600;
            cursor: pointer;
            border-bottom: 2px solid transparent;
          }}
          .tab-button.active {{
            color: #38bdf8;
            border-bottom-color: #38bdf8;
          }}
          .panel {{
            display: none;
          }}
          .panel.active {{
            display: block;
          }}
          .card {{
            background: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 16px;
          }}
          .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
          }}
          .kv {{
            display: flex;
            justify-content: space-between;
            font-size: 0.95rem;
            border-bottom: 1px solid #1e293b;
            padding: 6px 0;
          }}
          .kv:last-child {{
            border-bottom: none;
          }}
          .metric {{
            background: #111827;
            border-radius: 10px;
            padding: 12px;
          }}
          .metric span {{
            display: block;
            color: #94a3b8;
            font-size: 0.85rem;
          }}
          .metric strong {{
            font-size: 1.2rem;
          }}
          table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
          }}
          th, td {{
            text-align: left;
            padding: 8px 6px;
            border-bottom: 1px solid #1e293b;
          }}
          th {{
            color: #94a3b8;
            font-weight: 600;
          }}
          .muted {{
            color: #94a3b8;
          }}
          .error {{
            color: #f87171;
            font-size: 0.9rem;
          }}
          .timestamp {{
            font-size: 0.8rem;
            color: #64748b;
          }}
        </style>
      </head>
      <body>
        <header>
          <h1>MoneyBot UI</h1>
          <p>Entorno actual: <strong>{env_value}</strong> · Auto refresh cada 5s</p>
        </header>
        <main>
          <div class="tabs">
            <button class="tab-button active" data-tab="status">Status</button>
            <button class="tab-button" data-tab="metrics">Metrics</button>
            <button class="tab-button" data-tab="trades">Trades</button>
          </div>

          <section id="status" class="panel active">
            <div class="card">
              <h2>Status</h2>
              <div id="status-data"></div>
              <div class="timestamp" id="status-updated"></div>
              <div class="error" id="status-error"></div>
            </div>
          </section>

          <section id="metrics" class="panel">
            <div class="card">
              <h2>Metrics</h2>
              <div class="grid" id="metrics-data"></div>
              <div class="timestamp" id="metrics-updated"></div>
              <div class="error" id="metrics-error"></div>
            </div>
          </section>

          <section id="trades" class="panel">
            <div class="card">
              <h2>Trades</h2>
              <div id="trades-data"></div>
              <div class="timestamp" id="trades-updated"></div>
              <div class="error" id="trades-error"></div>
            </div>
          </section>
        </main>
        <script>
          const tabButtons = document.querySelectorAll(".tab-button");
          const panels = document.querySelectorAll(".panel");

          tabButtons.forEach((button) => {{
            button.addEventListener("click", () => {{
              tabButtons.forEach((btn) => btn.classList.remove("active"));
              panels.forEach((panel) => panel.classList.remove("active"));
              button.classList.add("active");
              document.getElementById(button.dataset.tab).classList.add("active");
            }});
          }});

          const statusContainer = document.getElementById("status-data");
          const metricsContainer = document.getElementById("metrics-data");
          const tradesContainer = document.getElementById("trades-data");
          const statusError = document.getElementById("status-error");
          const metricsError = document.getElementById("metrics-error");
          const tradesError = document.getElementById("trades-error");
          const statusUpdated = document.getElementById("status-updated");
          const metricsUpdated = document.getElementById("metrics-updated");
          const tradesUpdated = document.getElementById("trades-updated");

          const formatValue = (value) => {{
            if (value === null || value === undefined) return "N/A";
            if (typeof value === "number") return value.toFixed(4);
            if (typeof value === "boolean") return value ? "Sí" : "No";
            return String(value);
          }};

          const renderKeyValue = (target, data) => {{
            target.innerHTML = "";
            Object.entries(data).forEach(([key, value]) => {{
              const row = document.createElement("div");
              row.className = "kv";
              row.innerHTML = `<span>${{key}}</span><strong>${{formatValue(value)}}</strong>`;
              target.appendChild(row);
            }});
          }};

          const renderMetrics = (data) => {{
            metricsContainer.innerHTML = "";
            const entries = Object.entries(data);
            if (!entries.length) {{
              metricsContainer.innerHTML = '<p class="muted">Sin métricas aún.</p>';
              return;
            }}
            entries.forEach(([key, value]) => {{
              const item = document.createElement("div");
              item.className = "metric";
              item.innerHTML = `<span>${{key}}</span><strong>${{formatValue(value)}}</strong>`;
              metricsContainer.appendChild(item);
            }});
          }};

          const renderTrades = (trades) => {{
            tradesContainer.innerHTML = "";
            if (!trades.length) {{
              tradesContainer.innerHTML = '<p class="muted">Sin trades registrados.</p>';
              return;
            }}
            const columns = Object.keys(trades[0]);
            const table = document.createElement("table");
            const thead = document.createElement("thead");
            thead.innerHTML = `<tr>${{columns.map((col) => `<th>${{col}}</th>`).join("")}}</tr>`;
            table.appendChild(thead);
            const tbody = document.createElement("tbody");
            trades.forEach((trade) => {{
              const row = document.createElement("tr");
              row.innerHTML = columns
                .map((col) => `<td>${{formatValue(trade[col])}}</td>`)
                .join("");
              tbody.appendChild(row);
            }});
            table.appendChild(tbody);
            tradesContainer.appendChild(table);
          }};

          const fetchJson = async (url) => {{
            const response = await fetch(url);
            if (!response.ok) {{
              throw new Error(`Error ${{response.status}} en ${{url}}`);
            }}
            return response.json();
          }};

          const refreshStatus = async () => {{
            statusError.textContent = "";
            try {{
              const data = await fetchJson("/status");
              renderKeyValue(statusContainer, data);
              statusUpdated.textContent = `Actualizado: ${{new Date().toLocaleTimeString()}}`;
            }} catch (error) {{
              statusError.textContent = error.message;
            }}
          }};

          const refreshMetrics = async () => {{
            metricsError.textContent = "";
            try {{
              const data = await fetchJson("/metrics");
              renderMetrics(data);
              metricsUpdated.textContent = `Actualizado: ${{new Date().toLocaleTimeString()}}`;
            }} catch (error) {{
              metricsError.textContent = error.message;
            }}
          }};

          const refreshTrades = async () => {{
            tradesError.textContent = "";
            try {{
              const data = await fetchJson("/trades?limit=50");
              renderTrades(data.trades || []);
              tradesUpdated.textContent = `Actualizado: ${{new Date().toLocaleTimeString()}}`;
            }} catch (error) {{
              tradesError.textContent = error.message;
            }}
          }};

          const refreshAll = () => {{
            refreshStatus();
            refreshMetrics();
            refreshTrades();
          }};

          refreshAll();
          setInterval(refreshAll, 5000);
        </script>
      </body>
    </html>
    """
