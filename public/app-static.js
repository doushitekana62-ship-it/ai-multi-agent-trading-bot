const apiBaseUrl = (window.APP_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");
const TOKEN_KEY = "compound_scalping_dashboard_token";

async function api(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) throw Error("Dashboard token is not set");
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers });
  if (response.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    throw Error("Dashboard token is invalid or expired");
  }
  if (!response.ok) throw Error(await response.text());
  return response.json();
}

async function load() {
  try {
    const d = await api("/dashboard");
    state.textContent = d.engine?.runtime?.running ? "RUNNING" : "READY";
    apiEl.textContent = "OK";
    engine.textContent = d.engine?.name || "Unavailable";
    positions.textContent = Array.isArray(d.positions) ? d.positions.length : "—";
    data.textContent = JSON.stringify(d, null, 2);
  } catch (e) {
    state.textContent = "ERROR";
    apiEl.textContent = "ERROR";
    data.textContent = e.message;
  }
}

async function connect() {
  const token = tokenEl.value.trim();
  if (!token) {
    loginMsg.textContent = "Enter the dashboard token.";
    return;
  }
  localStorage.setItem(TOKEN_KEY, token);
  try {
    await api("/me");
    show();
  } catch (e) {
    localStorage.removeItem(TOKEN_KEY);
    loginMsg.textContent = e.message;
  }
}

async function startEngine() {
  try {
    await api("/engine/start", { method: "POST" });
    await load();
  } catch (e) { data.textContent = e.message; }
}

async function stopEngine() {
  try {
    await api("/engine/stop", { method: "POST" });
    await load();
  } catch (e) { data.textContent = e.message; }
}

function show() {
  login.hidden = true;
  dashboard.hidden = false;
  load();
}

const tokenEl = document.querySelector("#token");
const login = document.querySelector("#login");
const dashboard = document.querySelector("#dashboard");
const loginMsg = document.querySelector("#loginMsg");
const state = document.querySelector("#state");
const apiEl = document.querySelector("#api");
const engine = document.querySelector("#engine");
const positions = document.querySelector("#positions");
const data = document.querySelector("#data");

document.querySelector("#loginBtn").onclick = connect;
document.querySelector("#refresh").onclick = load;
document.querySelector("#startEngine").onclick = startEngine;
document.querySelector("#stopEngine").onclick = stopEngine;
document.querySelector("#logout").onclick = () => {
  localStorage.removeItem(TOKEN_KEY);
  location.reload();
};

if (!apiBaseUrl) {
  state.textContent = "ERROR";
  loginMsg.textContent = "FastAPI URL is not configured.";
} else if (localStorage.getItem(TOKEN_KEY)) {
  api("/me").then(show).catch(() => localStorage.removeItem(TOKEN_KEY));
}
