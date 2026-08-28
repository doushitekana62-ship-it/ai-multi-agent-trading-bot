import React from 'react';
import ReactDOM from 'react-dom/client';
import axios from 'axios';
import App from './App';

// Keep dashboard control requests bounded so a slow diagnostic request cannot
// leave the Paper START/STOP control locked indefinitely.
axios.defaults.timeout = 10000;

const getPaperToken = () => localStorage.getItem('token') || '';

// Defensive control path for the existing visible START/STOP button.
// The dashboard layout and React component remain unchanged.
document.addEventListener('click', async (event) => {
  const button = event.target?.closest?.('button');
  if (!button || button.disabled) return;

  const label = (button.textContent || '').trim();
  const isStart = label.includes('START PAPER BOT');
  const isStop = label.includes('STOP PAPER BOT');
  if (!isStart && !isStop) return;

  event.preventDefault();
  event.stopPropagation();
  if (button.dataset.paperControlBusy === '1') return;
  button.dataset.paperControlBusy = '1';
  button.disabled = true;

  try {
    const endpoint = isStart ? '/api/dashboard/paper/start' : '/api/dashboard/paper/stop';
    const pair = localStorage.getItem('paperTradingPair') || 'btc_idr';
    const url = isStart ? `${endpoint}?pair=${encodeURIComponent(pair)}` : endpoint;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getPaperToken()}`,
        Accept: 'application/json',
      },
      cache: 'no-store',
    });

    if (!response.ok) {
      let detail = 'Paper trading control failed';
      try {
        const body = await response.json();
        detail = body.detail || body.error || detail;
      } catch (_) {
        // Keep the generic message when the Worker did not return JSON.
      }
      throw new Error(detail);
    }

    // Reflect the authoritative Durable Object state immediately.
    window.location.reload();
  } catch (error) {
    console.error('Paper control fallback error:', error);
    button.dataset.paperControlBusy = '0';
    button.disabled = false;
    window.alert(error.message || 'Paper trading control failed');
  }
}, true);

// Browser-side fallback only. It NEVER enables the bot. It can submit a paper
// cycle only when the persistent Worker state is already enabled=true.
// Cloudflare Cron remains the primary server-side scheduler.
const runPaperWatchdog = async () => {
  const token = getPaperToken();
  if (!token) return;

  try {
    const statusResponse = await fetch('/api/dashboard/status?watchdog=1', {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!statusResponse.ok) return;

    const state = await statusResponse.json();
    if (!state.enabled || state.cycle_running) return;

    const lastCycle = state.last_cycle_at ? Date.parse(state.last_cycle_at) : 0;
    const staleMs = Date.now() - lastCycle;
    if (lastCycle && staleMs < 75000) return;

    await fetch('/api/dashboard/paper/cycle', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      cache: 'no-store',
    });
  } catch (error) {
    console.debug('Paper watchdog skipped:', error);
  }
};

window.setInterval(runPaperWatchdog, 20000);

const root = ReactDOM.createRoot(
  document.getElementById('root')
);

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
