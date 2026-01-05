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
const statusUpdated = document.getElementById("status-updated");
const metricsUpdated = document.getElementById("metrics-updated");
const tradesUpdated = document.getElementById("trades-updated");
const logsUpdated = document.getElementById("logs-updated");
const envValue = document.getElementById("env-value");

const startButton = document.getElementById("start-btn");
const stopButton = document.getElementById("stop-btn");
const pauseResumeButton = document.getElementById("pause-resume-btn");
const modeSelect = document.getElementById("mode-select");
const toast = document.getElementById("toast");

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

const renderTrades = (trades) => {
  tradesContainer.innerHTML = "";
  if (!trades.length) {
    tradesContainer.innerHTML = '<p class="muted">Sin trades registrados.</p>';
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
  tradesContainer.appendChild(table);
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
    if (typeof data?.is_paused === "boolean") {
      pauseResumeButton.textContent = data.is_paused ? "Resume" : "Pause";
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

pauseResumeButton.addEventListener("click", () => {
  const shouldResume = currentStatus?.is_paused;
  if (shouldResume) {
    runControlAction("/control/resume", null, "Bot reanudado");
  } else {
    runControlAction("/control/pause", null, "Bot pausado");
  }
});

modeSelect.addEventListener("change", (event) => {
  const mode = event.target.value;
  runControlAction("/control/set-mode", { mode }, `Modo actualizado a ${mode}`);
});

refreshEnv();
refreshAll();
setInterval(refreshAll, 5000);
