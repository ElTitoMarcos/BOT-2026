const tabButtons = document.querySelectorAll(".tab-button");
const panels = document.querySelectorAll(".panel");

const statusContainer = document.getElementById("status-data");
const metricsContainer = document.getElementById("metrics-data");
const tradesContainer = document.getElementById("trades-data");
const logsContainer = document.getElementById("logs-data");
const statusError = document.getElementById("status-error");
const metricsError = document.getElementById("metrics-error");
const tradesError = document.getElementById("trades-error");
const logsError = document.getElementById("logs-error");
const backtestError = document.getElementById("backtest-error");
const statusUpdated = document.getElementById("status-updated");
const metricsUpdated = document.getElementById("metrics-updated");
const tradesUpdated = document.getElementById("trades-updated");
const logsUpdated = document.getElementById("logs-updated");
const backtestUpdated = document.getElementById("backtest-updated");
const envValue = document.getElementById("env-value");

const startButton = document.getElementById("start-btn");
const stopButton = document.getElementById("stop-btn");
const modeSelect = document.getElementById("mode-select");
const toast = document.getElementById("toast");
const backtestRunButton = document.getElementById("backtest-run-btn");
const backtestDownloadButton = document.getElementById("backtest-download-btn");
const backtestSymbols = document.getElementById("backtest-symbols");
const backtestInterval = document.getElementById("backtest-interval");
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
    renderKeyValue(statusContainer, data);
    if (data?.mode) {
      modeSelect.value = data.mode;
    }
    statusUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
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
    const data = await fetchJson("/trades?limit=50");
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
  const symbols = backtestSymbols.value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  const payload = {
    symbols,
    interval: backtestInterval.value || "1h",
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
