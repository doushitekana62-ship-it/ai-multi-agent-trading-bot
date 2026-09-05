let sb;
const apiBaseUrl = (window.APP_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");

async function boot() {
  const config = window.APP_CONFIG || {};
  if (!config.supabaseUrl || !config.supabaseAnonKey || !apiBaseUrl) {
    throw Error("public/config.js is not configured");
  }
  sb = window.supabase.createClient(config.supabaseUrl, config.supabaseAnonKey, {
    auth: { autoRefreshToken: true, persistSession: true, detectSessionInUrl: true },
  });
  const { data } = await sb.auth.getSession();
  if (data.session) show();
}

async function signIn() {
  const email = emailEl.value.trim();
  const password = passwordEl.value;
  const { data, error } = await sb.auth.signInWithPassword({ email, password });
  if (error) {
    loginMsg.textContent = error.message;
    return;
  }
  if (data.session) show();
}

async function api(path, options = {}) {
  const { data } = await sb.auth.getSession();
  if (!data.session) throw Error("Session expired");
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${data.session.access_token}`);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers });
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

async function startEngine() {
  try {
    await api("/engine/start", { method: "POST" });
    await load();
  } catch (e) {
    data.textContent = e.message;
  }
}

async function stopEngine() {
  try {
    await api("/engine/stop", { method: "POST" });
    await load();
  } catch (e) {
    data.textContent = e.message;
  }
}

function show() {
  login.hidden = true;
  dashboard.hidden = false;
  load();
}

const emailEl = document.querySelector("#email");
const passwordEl = document.querySelector("#password");
const login = document.querySelector("#login");
const dashboard = document.querySelector("#dashboard");
const loginMsg = document.querySelector("#loginMsg");
const state = document.querySelector("#state");
const apiEl = document.querySelector("#api");
const engine = document.querySelector("#engine");
const positions = document.querySelector("#positions");
const data = document.querySelector("#data");

document.querySelector("#loginBtn").onclick = signIn;
document.querySelector("#refresh").onclick = load;
document.querySelector("#startEngine").onclick = startEngine;
document.querySelector("#stopEngine").onclick = stopEngine;
document.querySelector("#logout").onclick = async () => {
  await sb.auth.signOut();
  location.reload();
};

boot().catch((e) => {
  state.textContent = "ERROR";
  loginMsg.textContent = e.message;
});
