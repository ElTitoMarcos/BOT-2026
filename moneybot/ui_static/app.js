const tabButtons = document.querySelectorAll(".tab-button");
const panels = document.querySelectorAll(".panel");

const statusContainer = document.getElementById("status-data");
const statusSummary = document.getElementById("status-summary");
const healthContainer = document.getElementById("health-data");
const metricsContainer = document.getElementById("metrics-data");
const tradesContainer = document.getElementById("trades-data");
const logsContainer = document.getElementById("logs-data");
const statusError = document.getElementById("status-error");
const metricsError = document.getElementById("metrics-error");
const tradesError = document.getElementById("trades-error");
const logsError = document.getElementById("logs-error");
const dataError = document.getElementById("data-error");
const statusUpdated = document.getElementById("status-updated");
const healthUpdated = document.getElementById("health-updated");
const metricsUpdated = document.getElementById("metrics-updated");
const tradesUpdated = document.getElementById("trades-updated");
const logsUpdated = document.getElementById("logs-updated");
const envValue = document.getElementById("env-value");
const statusBadge = document.getElementById("status-badge");
const logsClearButton = document.getElementById("logs-clear-btn");

const startButton = document.getElementById("start-btn");
const stopButton = document.getElementById("stop-btn");
const modeSelect = document.getElementById("mode-select");
const toast = document.getElementById("toast");
const dataSymbolSelect = document.getElementById("data-symbol-select");
const dataRefreshButton = document.getElementById("data-refresh-btn");
const dataDatesTable = document.getElementById("data-dates-table");
const dataUpdated = document.getElementById("data-updated");
const dataStorageBar = document.getElementById("data-storage-bar");
const dataStorageText = document.getElementById("data-storage-text");
const dataStorageUpdated = document.getElementById("data-storage-updated");
const recordSymbolsSelect = document.getElementById("record-symbols");
const recordStartButton = document.getElementById("record-start-btn");
const recordStopButton = document.getElementById("record-stop-btn");
const recordError = document.getElementById("record-error");

let toastTimer;
let currentStatus = null;

tabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    tabButtons.forEach((btn) => btn.classList.remove("active"));
    panels.forEach((panel) => panel.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(button.dataset.tab).classList.add("active");
  });
});

const showToast = (message, isError = false) => {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove("show");
  }, 3000);
};

const formatValue = (value) => {
  if (value === null || value === undefined) return "N/A";
  if (typeof value === "number") return value.toFixed(4);
  if (typeof value === "boolean") return value ? "Sí" : "No";
  return String(value);
};

const formatDuration = (seconds) => {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "N/A";
  }
  const totalSeconds = Math.max(0, Math.floor(Number(seconds)));
  const minutes = Math.floor(totalSeconds / 60);
  const remaining = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
};

const formatLastUpdate = (status) => {
  const iso = status?.last_update_iso;
  const age = status?.last_update_age_s;
  if (!iso) {
    return "Última actualización: N/A";
  }
  const timeLabel = new Date(iso).toLocaleTimeString();
  const ageLabel =
    age === null || age === undefined ? "N/A" : `${Math.max(0, Math.round(age))}s`;
  return `Última actualización: ${timeLabel} (hace ${ageLabel})`;
};

const formatEventRates = (rates) => {
  const aggTrade = rates?.aggTrade ?? 0;
  const depth = rates?.depth ?? 0;
  const bookTicker = rates?.bookTicker ?? 0;
  return `Eventos/s: aggTrade=${aggTrade.toFixed(2)}, depth=${depth.toFixed(
    2,
  )}, bookTicker=${bookTicker.toFixed(2)}`;
};

const renderStatusSummary = (status) => {
  if (!statusSummary) return;
  const lines = [
    formatLastUpdate(status),
    `Uptime: ${formatDuration(status?.uptime_s)}`,
    formatEventRates(status?.event_rate_per_s || {}),
    `Edad último evento WS: ${
      status?.last_ws_event_age_ms === null || status?.last_ws_event_age_ms === undefined
        ? "N/A"
        : `${Math.max(0, Math.round(status.last_ws_event_age_ms))} ms`
    }`,
  ];
  statusSummary.innerHTML = lines.map((line) => `<div>${line}</div>`).join("");
};

const renderKeyValue = (target, data) => {
  target.innerHTML = "";
  Object.entries(data).forEach(([key, value]) => {
    const row = document.createElement("div");
    row.className = "kv";
    row.innerHTML = `<span>${key}</span><strong>${formatValue(value)}</strong>`;
    target.appendChild(row);
  });
};

const renderMetrics = (data) => {
  metricsContainer.innerHTML = "";
  const entries = Object.entries(data);
  if (!entries.length) {
    metricsContainer.innerHTML = '<p class="muted">Sin métricas aún.</p>';
    return;
  }
  entries.forEach(([key, value]) => {
    const item = document.createElement("div");
    item.className = "metric";
    item.innerHTML = `<span>${key}</span><strong>${formatValue(value)}</strong>`;
    metricsContainer.appendChild(item);
  });
};

const renderTradesTable = (target, trades) => {
  target.innerHTML = "";
  if (!trades.length) {
    target.innerHTML = '<p class="muted">Sin trades registrados.</p>';
    return;
  }
  const columns = Object.keys(trades[0]);
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>${columns
    .map((col) => `<th>${col}</th>`)
    .join("")}</tr>`;
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  trades.forEach((trade) => {
    const row = document.createElement("tr");
    row.innerHTML = columns
      .map((col) => `<td>${formatValue(trade[col])}</td>`)
      .join("");
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  target.appendChild(table);
};

const renderDataTable = (target, rows, emptyMessage) => {
  target.innerHTML = "";
  if (!rows.length) {
    target.innerHTML = `<p class="muted">${emptyMessage}</p>`;
    return;
  }
  const columns = Object.keys(rows[0]);
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>${columns
    .map((col) => `<th>${col}</th>`)
    .join("")}</tr>`;
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  rows.forEach((rowData) => {
    const row = document.createElement("tr");
    row.innerHTML = columns
      .map((col) => `<td>${formatValue(rowData[col])}</td>`)
      .join("");
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  target.appendChild(table);
};

const renderTrades = (trades) => {
  renderTradesTable(tradesContainer, trades);
};

const renderDataDates = (dates, symbol) => {
  dataDatesTable.innerHTML = "";
  if (!dates.length) {
    dataDatesTable.innerHTML = '<p class="muted">No hay fechas disponibles.</p>';
    return;
  }
  const table = document.createElement("table");
  table.innerHTML = `
    <thead>
      <tr>
        <th>Fecha</th>
        <th>Acciones</th>
      </tr>
    </thead>
  `;
  const tbody = document.createElement("tbody");
  dates.forEach((day) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${day}</td>
      <td class="data-actions">
        <button class="btn secondary" data-action="download" data-date="${day}">Descargar</button>
        <button class="btn warn" data-action="delete" data-date="${day}">Borrar</button>
      </td>
    `;
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  dataDatesTable.appendChild(table);
  dataDatesTable.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      const date = button.dataset.date;
      if (action === "download") {
        window.location.href = `/data/download?symbol=${encodeURIComponent(
          symbol,
        )}&start=${date}&end=${date}`;
        return;
      }
      if (!confirm(`¿Borrar datos de ${symbol} para ${date}?`)) {
        return;
      }
      try {
        await fetchJson(
          `/data/day?symbol=${encodeURIComponent(symbol)}&date=${encodeURIComponent(date)}`,
          { method: "DELETE" },
        );
        showToast(`Datos de ${symbol} ${date} borrados`);
        refreshDataDates();
        refreshStorage();
      } catch (error) {
        showToast(error.message, true);
      }
    });
  });
};

const fetchJson = async (url, options = {}) => {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Error ${response.status} en ${url}`);
  }
  return response.json();
};

const getLogCleanToken = () => {
  let token = sessionStorage.getItem("logCleanToken");
  if (!token) {
    token = window.prompt("Ingresa el token para limpiar logs:");
    if (token) {
      sessionStorage.setItem("logCleanToken", token);
    }
  }
  return token;
};

const refreshStatus = async () => {
  statusError.textContent = "";
  try {
    const data = await fetchJson("/status");
    currentStatus = data;
    renderStatusSummary(data);
    const statusExtras = { ...data };
    [
      "last_update_iso",
      "last_update_age_s",
      "uptime_s",
      "event_rate_per_s",
      "last_ws_event_age_ms",
    ].forEach((key) => {
      delete statusExtras[key];
    });
    renderKeyValue(statusContainer, statusExtras);
    if (data?.mode) {
      modeSelect.value = data.mode;
    }
    const healthSnapshot = buildHealthSnapshot(data);
    renderKeyValue(healthContainer, healthSnapshot);
    updateStatusBadge(data);
    statusUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
    healthUpdated.textContent = statusUpdated.textContent;
  } catch (error) {
    statusError.textContent = error.message;
  }
};

const refreshMetrics = async () => {
  metricsError.textContent = "";
  try {
    const data = await fetchJson("/metrics");
    renderMetrics(data);
    metricsUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    metricsError.textContent = error.message;
  }
};

const refreshTrades = async () => {
  tradesError.textContent = "";
  try {
    const data = await fetchJson("/trades?limit=20");
    renderTrades(data.trades || []);
    tradesUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    tradesError.textContent = error.message;
  }
};

const refreshLogs = async () => {
  logsError.textContent = "";
  try {
    const data = await fetchJson("/logs/tail?limit=200");
    if (!data.available) {
      logsContainer.textContent = "Logs aún no disponibles.";
    } else {
      logsContainer.textContent = (data.lines || []).join("\n");
    }
    logsUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    logsError.textContent = error.message;
  }
};

const buildHealthSnapshot = (status) => {
  const health = status?.live_feed_health || status?.live_feed || status?.health || {};
  return {
    "Mensajes/s":
      health.messages_per_sec ??
      health.msgs_per_sec ??
      health.messages_per_second ??
      "N/A",
    Reconexiones: health.reconnects ?? health.reconnections ?? "N/A",
    "Rate-limit": health.rate_limit ?? health.rate_limited ?? "N/A",
    Cola: health.queue_depth ?? health.queue ?? "N/A",
  };
};

const updateStatusBadge = (status) => {
  if (!statusBadge) return;
  const running = Boolean(status?.is_running);
  const mode = status?.mode || "N/A";
  statusBadge.textContent = `${running ? "RUNNING" : "STOPPED"} · ${mode}`;
  statusBadge.classList.toggle("running", running);
  statusBadge.classList.toggle("stopped", !running);
};

const refreshStorage = async () => {
  try {
    const data = await fetchJson("/data/storage");
    const maxBytes = data.max_gb * 1024 * 1024 * 1024;
    const ratio = maxBytes > 0 ? Math.min(data.size_bytes / maxBytes, 1) : 0;
    dataStorageBar.style.width = `${(ratio * 100).toFixed(1)}%`;
    dataStorageText.textContent = `${(data.size_bytes / (1024 * 1024)).toFixed(
      2,
    )} MB usados de ${data.max_gb} GB`;
    dataStorageUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    dataStorageText.textContent = "No disponible";
  }
};

const refreshSymbols = async () => {
  try {
    const data = await fetchJson("/data/symbols");
    const symbols = data.symbols || [];
    dataSymbolSelect.innerHTML = "";
    recordSymbolsSelect.innerHTML = "";
    if (!symbols.length) {
      dataSymbolSelect.innerHTML = '<option value="">Sin símbolos</option>';
    } else {
      symbols.forEach((symbol) => {
        const option = document.createElement("option");
        option.value = symbol;
        option.textContent = symbol;
        dataSymbolSelect.appendChild(option);
        const recordOption = option.cloneNode(true);
        recordSymbolsSelect.appendChild(recordOption);
      });
    }
  } catch (error) {
    dataError.textContent = error.message;
  }
};

const refreshDataDates = async () => {
  dataError.textContent = "";
  const symbol = dataSymbolSelect.value;
  if (!symbol) {
    dataDatesTable.innerHTML = '<p class="muted">Selecciona un símbolo.</p>';
    return;
  }
  try {
    const data = await fetchJson(
      `/data/available-dates?symbol=${encodeURIComponent(symbol)}`,
    );
    renderDataDates(data.dates || [], symbol);
    dataUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    dataError.textContent = error.message;
  }
};

const refreshEnv = async () => {
  try {
    const data = await fetchJson("/config/status");
    envValue.textContent = data.env || "N/A";
  } catch (error) {
    envValue.textContent = "N/A";
  }
};

const refreshAll = () => {
  refreshStatus();
  refreshMetrics();
  refreshTrades();
  refreshLogs();
  refreshStorage();
};

const runControlAction = async (url, payload, successMessage) => {
  try {
    await fetchJson(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: payload ? JSON.stringify(payload) : undefined,
    });
    await Promise.all([refreshStatus(), refreshMetrics()]);
    showToast(successMessage || "Acción completada");
  } catch (error) {
    showToast(error.message, true);
  }
};

startButton.addEventListener("click", () => {
  runControlAction("/control/start", null, "Bot iniciado");
});

stopButton.addEventListener("click", () => {
  runControlAction("/control/stop", null, "Bot detenido");
});

modeSelect.addEventListener("change", (event) => {
  const mode = event.target.value;
  runControlAction("/control/set-mode", { mode }, `Modo actualizado a ${mode}`);
});
dataSymbolSelect.addEventListener("change", () => {
  refreshDataDates();
});

dataRefreshButton.addEventListener("click", () => {
  refreshDataDates();
  refreshStorage();
});

recordStartButton.addEventListener("click", async () => {
  recordError.textContent = "";
  const selectedSymbols = Array.from(recordSymbolsSelect.selectedOptions).map(
    (option) => option.value,
  );
  const selectedStreams = Array.from(
    document.querySelectorAll('.checkbox-group input[type="checkbox"]:checked'),
  ).map((checkbox) => checkbox.value);
  try {
    await fetchJson("/data/record/start", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ symbols: selectedSymbols, streams: selectedStreams }),
    });
    showToast("Grabación iniciada");
  } catch (error) {
    recordError.textContent = error.message;
  }
});

recordStopButton.addEventListener("click", async () => {
  recordError.textContent = "";
  try {
    await fetchJson("/data/record/stop", { method: "POST" });
    showToast("Grabación detenida");
  } catch (error) {
    recordError.textContent = error.message;
  }
});

if (logsClearButton) {
  logsClearButton.addEventListener("click", async () => {
    const token = getLogCleanToken();
    if (!token) {
      showToast("Token requerido para limpiar logs.", true);
      return;
    }
    try {
      await fetchJson("/logs/clear", {
        method: "POST",
        headers: {
          "X-API-Token": token,
        },
      });
      showToast("Logs limpiados");
      refreshLogs();
    } catch (error) {
      showToast(error.message, true);
    }
  });
}

refreshEnv();
refreshSymbols().then(refreshDataDates);
refreshAll();
setInterval(refreshAll, 5000);

const sendHeartbeat = () => {
  fetch("/ui/heartbeat", { method: "POST", keepalive: true }).catch(() => {});
};

const sendFinalHeartbeat = () => {
  if (navigator.sendBeacon) {
    navigator.sendBeacon("/ui/heartbeat");
    return;
  }
  sendHeartbeat();
};

sendHeartbeat();
setInterval(sendHeartbeat, 3000);
window.addEventListener("beforeunload", sendFinalHeartbeat);
window.addEventListener("pagehide", sendFinalHeartbeat);
