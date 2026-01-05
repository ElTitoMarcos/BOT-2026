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
const backtestError = document.getElementById("backtest-error");
const statusUpdated = document.getElementById("status-updated");
const healthUpdated = document.getElementById("health-updated");
const metricsUpdated = document.getElementById("metrics-updated");
const tradesUpdated = document.getElementById("trades-updated");
const logsUpdated = document.getElementById("logs-updated");
const backtestUpdated = document.getElementById("backtest-updated");
const envValue = document.getElementById("env-value");
const statusBadge = document.getElementById("status-badge");

const startButton = document.getElementById("start-btn");
const stopButton = document.getElementById("stop-btn");
const modeSelect = document.getElementById("mode-select");
const toast = document.getElementById("toast");
const backtestRunButton = document.getElementById("backtest-run-btn");
const backtestDownloadButton = document.getElementById("backtest-download-btn");
const backtestStartDate = document.getElementById("backtest-start-date");
const backtestEndDate = document.getElementById("backtest-end-date");
const backtestFeeRate = document.getElementById("backtest-fee-rate");
const backtestSlippageBps = document.getElementById("backtest-slippage-bps");
const backtestStatus = document.getElementById("backtest-status");
const backtestSummary = document.getElementById("backtest-summary");
const backtestDiagnostics = document.getElementById("backtest-diagnostics");
const backtestTrades = document.getElementById("backtest-trades");
const backtestEquity = document.getElementById("backtest-equity");
const backtestEquityEmpty = document.getElementById("backtest-equity-empty");
const backtestProgress = document.getElementById("backtest-progress");

let toastTimer;
let currentStatus = null;
let backtestPoller = null;
let activeBacktestJobId = null;

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

const fetchJson = async (url, options = {}) => {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Error ${response.status} en ${url}`);
  }
  return response.json();
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


const renderBacktestSummary = (summary) => {
  if (!summary || Object.keys(summary).length === 0) {
    backtestSummary.innerHTML = '<p class="muted">Sin resumen disponible.</p>';
    return;
  }
  const { diagnostics, ...summaryFields } = summary;
  renderKeyValue(backtestSummary, summaryFields);
};

const renderBacktestDiagnostics = (diagnostics) => {
  if (!backtestDiagnostics) return;
  backtestDiagnostics.innerHTML = "";
  if (!diagnostics || Object.keys(diagnostics).length === 0) {
    backtestDiagnostics.innerHTML = '<p class="muted">Sin diagnostics disponibles.</p>';
    return;
  }
  const { per_symbol: perSymbol = [], ...summaryFields } = diagnostics;
  const summaryGrid = document.createElement("div");
  summaryGrid.className = "grid";
  renderKeyValue(summaryGrid, summaryFields);
  backtestDiagnostics.appendChild(summaryGrid);
  const perSymbolTitle = document.createElement("div");
  perSymbolTitle.className = "section-title";
  perSymbolTitle.textContent = "Per symbol";
  backtestDiagnostics.appendChild(perSymbolTitle);
  const perSymbolContainer = document.createElement("div");
  renderDataTable(perSymbolContainer, perSymbol, "Sin diagnostics por símbolo.");
  backtestDiagnostics.appendChild(perSymbolContainer);
};

const drawEquityCurve = (series) => {
  if (!backtestEquity) return;
  const ctx = backtestEquity.getContext("2d");
  const width = backtestEquity.clientWidth || backtestEquity.width;
  const height = backtestEquity.clientHeight || backtestEquity.height;
  backtestEquity.width = width;
  backtestEquity.height = height;
  ctx.clearRect(0, 0, width, height);
  if (!series || series.length === 0) {
    backtestEquityEmpty.textContent = "Sin datos de equity.";
    return;
  }
  backtestEquityEmpty.textContent = "";
  const values = series.map((point) => Number(point.equity || 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padding = 24;
  ctx.strokeStyle = "#1e293b";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding, padding);
  ctx.lineTo(padding, height - padding);
  ctx.lineTo(width - padding, height - padding);
  ctx.stroke();
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 2;
  ctx.beginPath();
  series.forEach((point, index) => {
    const x =
      padding +
      (index / Math.max(series.length - 1, 1)) * (width - padding * 2);
    const y =
      height - padding - ((Number(point.equity || 0) - min) / range) * (height - padding * 2);
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();
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

const updateBacktestProgress = (status) => {
  if (!backtestProgress) return;
  const steps = backtestProgress.querySelectorAll(".progress-step");
  steps.forEach((step) => {
    step.classList.remove("active", "done", "failed");
  });
  if (!status) return;
  if (status.state === "failed") {
    steps.forEach((step) => step.classList.add("failed"));
    return;
  }
  const progress = Number(status.progress ?? 0);
  let activeStep = "download";
  if (progress >= 55) {
    activeStep = "replay";
  } else if (progress >= 35) {
    activeStep = "record";
  }
  steps.forEach((step) => {
    const name = step.dataset.step;
    if (status.state === "completed" || name === activeStep) {
      step.classList.add(status.state === "completed" ? "done" : "active");
    }
    if (
      (activeStep === "record" && name === "download") ||
      (activeStep === "replay" && (name === "download" || name === "record"))
    ) {
      step.classList.add("done");
    }
  });
};

const updateBacktestStatus = (status) => {
  if (!status) {
    backtestStatus.textContent = "";
    return;
  }
  const state = status.state || "unknown";
  const normalizedState =
    state === "completed" ? "FINISHED" : state === "failed" ? "FAILED" : state.toUpperCase();
  backtestStatus.textContent = `${normalizedState} · ${status.progress ?? 0}% · ${
    status.message || ""
  }`;
  updateBacktestProgress(status);
  backtestUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
};

const stopBacktestPolling = () => {
  if (backtestPoller) {
    clearInterval(backtestPoller);
    backtestPoller = null;
  }
};

const fetchBacktestResult = async (jobId) => {
  const result = await fetchJson(`/backtest/result/${jobId}`);
  renderBacktestSummary(result.summary || {});
  renderBacktestDiagnostics(result.summary?.diagnostics || {});
  renderTradesTable(backtestTrades, result.trades || []);
  drawEquityCurve(result.equity_series || []);
};

const pollBacktestStatus = async (jobId) => {
  backtestError.textContent = "";
  try {
    const status = await fetchJson(`/backtest/status/${jobId}`);
    updateBacktestStatus(status);
    if (status.state === "completed") {
      stopBacktestPolling();
      await fetchBacktestResult(jobId);
      backtestDownloadButton.disabled = false;
      showToast("Backtest finalizado");
    } else if (status.state === "failed") {
      stopBacktestPolling();
      backtestError.textContent = status.message || "Backtest fallido.";
      backtestDownloadButton.disabled = true;
    }
  } catch (error) {
    backtestError.textContent = error.message;
    stopBacktestPolling();
  }
};

const startBacktestPolling = (jobId) => {
  stopBacktestPolling();
  backtestPoller = setInterval(() => {
    pollBacktestStatus(jobId);
  }, 1000);
  pollBacktestStatus(jobId);
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


backtestRunButton.addEventListener("click", async () => {
  backtestError.textContent = "";
  const payload = {
    start_date: backtestStartDate.value || null,
    end_date: backtestEndDate.value || null,
    fee_rate: backtestFeeRate.value ? Number(backtestFeeRate.value) : 0.001,
    slippage_bps: backtestSlippageBps.value ? Number(backtestSlippageBps.value) : 0,
  };
  try {
    backtestRunButton.disabled = true;
    backtestDownloadButton.disabled = true;
    backtestSummary.innerHTML = "";
    backtestDiagnostics.innerHTML = "";
    backtestTrades.innerHTML = "";
    backtestEquityEmpty.textContent = "Ejecutando backtest...";
    const response = await fetchJson("/backtest/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    activeBacktestJobId = response.job_id;
    showToast("Backtest en ejecución");
    startBacktestPolling(activeBacktestJobId);
  } catch (error) {
    backtestError.textContent = error.message;
  } finally {
    backtestRunButton.disabled = false;
  }
});

backtestDownloadButton.addEventListener("click", () => {
  if (!activeBacktestJobId) {
    showToast("No hay job de backtest disponible", true);
    return;
  }
  window.location.href = `/backtest/download/${activeBacktestJobId}`;
});

refreshEnv();
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
