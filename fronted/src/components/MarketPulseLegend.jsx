import React, { useEffect, useMemo, useState } from 'react';
import { Box, Chip, Paper, Stack, Tooltip, Typography } from '@mui/material';
import axios from 'axios';

const POLL_MS = 5000;
const MINUTE_MS = 60 * 1000;
const WINDOW_MINUTES = 30;
const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);
const color = (status) => status === 'GREEN' ? 'success.main' : status === 'RED' ? 'error.main' : 'grey.500';
const label = (status) => status === 'GREEN' ? 'UP' : status === 'RED' ? 'DOWN' : 'FLAT';
const tsMs = (item) => { const n = Number(item?.timestamp ?? item?.date ?? item?.trade_time ?? 0); if (!Number.isFinite(n) || n <= 0) return null; return n > 1e12 ? n : n * 1000; };

function localFallback(points) {
  const rows = (points || []).map((p) => ({ at: tsMs(p), price: Number(p?.price) })).filter((p) => p.at && p.price > 0).sort((a, b) => a.at - b.at);
  const anchor = rows.at(-1)?.at || Date.now();
  const current = Math.floor(anchor / MINUTE_MS) * MINUTE_MS;
  const buckets = new Map();
  rows.forEach((p) => {
    const minute = Math.floor(p.at / MINUTE_MS) * MINUTE_MS;
    if (minute < current - 29 * MINUTE_MS || minute > current) return;
    const b = buckets.get(minute) || { minute, open: p.price, close: p.price, samples: 0, changed: false, lastDirection: 'GRAY' };
    if (p.price !== b.close) { b.changed = true; b.lastDirection = p.price > b.close ? 'GREEN' : 'RED'; }
    b.close = p.price; b.samples += 1; buckets.set(minute, b);
  });
  const segments = Array.from({ length: WINDOW_MINUTES }, (_, i) => {
    const minute = current - (WINDOW_MINUTES - 1 - i) * MINUTE_MS;
    const b = buckets.get(minute);
    if (!b) return { minute, status: 'GRAY', move: null, samples: 0, changed: false };
    const move = b.open > 0 ? ((b.close - b.open) / b.open) * 100 : 0;
    const status = move > 0 ? 'GREEN' : move < 0 ? 'RED' : b.changed ? b.lastDirection : 'GRAY';
    return { ...b, move, status };
  });
  const populated = segments.filter((s) => Number.isFinite(s.move) && s.open > 0);
  const first = populated[0]?.open; const last = populated.at(-1)?.close;
  return { segments, move30: first > 0 && last > 0 ? ((last - first) / first) * 100 : null };
}

function normalizeServerPulse(raw) {
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const segments = raw.slice(-WINDOW_MINUTES).map((item) => {
    const minute = tsMs(item) || Date.now();
    const move = Number(item?.move_pct);
    const status = ['GREEN', 'RED', 'GRAY'].includes(String(item?.status).toUpperCase()) ? String(item.status).toUpperCase() : 'GRAY';
    return { ...item, minute, move: Number.isFinite(move) ? move : null, samples: Number(item?.observations || 0), status };
  });
  while (segments.length < WINDOW_MINUTES) {
    const first = segments[0]?.minute || Date.now();
    segments.unshift({ minute: first - MINUTE_MS, status: 'GRAY', move: null, samples: 0, changed: false });
  }
  const populated = segments.filter((s) => Number.isFinite(s.move) && Number(s.open) > 0);
  const first = populated[0]?.open; const last = populated.at(-1)?.close;
  return { segments: segments.slice(-WINDOW_MINUTES), move30: first > 0 && last > 0 ? ((last - first) / first) * 100 : null };
}

export default function MarketPulseLegend() {
  const [market, setMarket] = useState(null);
  const [points, setPoints] = useState([]);

  useEffect(() => {
    let stopped = false;
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const pair = localStorage.getItem('paperTradingPair') || 'btc_idr';
        const response = await axios.get('/api/market/overview', { params: { pair, _ts: Date.now() }, headers: { 'Cache-Control': 'no-cache' }, timeout: 8000 });
        if (stopped) return;
        const data = response.data || {};
        setMarket(data);
        setPoints((current) => [...current, ...(Array.isArray(data.points) ? data.points : [])].slice(-360));
      } catch {
        // Preserve the last valid pulse on transient API failures.
      } finally {
        inFlight = false;
      }
    };
    load();
    const timer = window.setInterval(load, POLL_MS);
    return () => { stopped = true; window.clearInterval(timer); };
  }, []);

  const fallback = useMemo(() => localFallback(points), [points]);
  const pulse = useMemo(() => fallback, [fallback]);
  const current = pulse.segments.at(-1);
  const currentMove = Number.isFinite(Number(current?.move)) ? Number(current.move) : null;

  return <Paper sx={{ mt: 1.5, p: 2, borderRadius: 2.5 }} aria-label="Market Pulse 30 minute timeline">
    <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }} spacing={1}>
      <Box>
        <Typography variant="caption" fontWeight={700} sx={{ display: 'block' }}>MARKET PULSE · ROLLING 30 MINUTES</Typography>
        <Typography variant="caption" color="text.secondary">Satu blok = satu menit. Sumber utama mengikuti observasi market live. Setiap perubahan harga yang terobservasi dalam menit tersebut harus menghasilkan GREEN/RED; hanya menit tanpa data yang GRAY.</Typography>
      </Box>
      <Stack direction="row" spacing={1} alignItems="center">
        <Chip size="small" label={label(current?.status || 'GRAY')} sx={{ bgcolor: color(current?.status || 'GRAY'), color: 'common.white', fontWeight: 700 }} />
        <Typography variant="body2" fontWeight={700}>{pulse.move30 == null ? '—' : `${pulse.move30 >= 0 ? '+' : ''}${pulse.move30.toFixed(3)}% / 30m`}</Typography>
      </Stack>
    </Stack>
    <Stack direction="row" spacing={0.35} sx={{ mt: 1.5, minHeight: 34 }}>
      {pulse.segments.map((segment, index) => <Tooltip key={`${segment.minute}-${index}`} title={`${new Date(segment.minute).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })} · ${label(segment.status)}${Number.isFinite(Number(segment.move)) ? ` ${Number(segment.move) >= 0 ? '+' : ''}${Number(segment.move).toFixed(4)}%` : ' · no observed data'}${segment.changed ? ' · price changed' : ''}`}><Box sx={{ flex: 1, minWidth: 4, height: 30, borderRadius: .7, bgcolor: color(segment.status), opacity: Number(segment.samples ?? segment.observations ?? 0) > 0 ? 1 : .28, border: index === pulse.segments.length - 1 ? '2px solid' : 'none', borderColor: 'primary.main' }} /></Tooltip>)}
    </Stack>
    <Stack direction="row" justifyContent="space-between" sx={{ mt: .7 }}>
      <Typography variant="caption" color="text.secondary">30 menit lalu</Typography>
      <Typography variant="caption" color={currentMove == null ? 'text.secondary' : currentMove > 0 ? 'success.main' : currentMove < 0 ? 'error.main' : 'text.secondary'} fontWeight={700}>{currentMove == null ? 'Menunggu data menit berjalan' : `${currentMove >= 0 ? '+' : ''}${currentMove.toFixed(4)}% menit berjalan`}</Typography>
      <Typography variant="caption" color="text.secondary">sekarang</Typography>
    </Stack>
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 1 }}>
      <Typography variant="caption" color="text.secondary">Price {idr(market?.last)}</Typography>
      <Typography variant="caption" color="text.secondary">24H High {idr(market?.high)}</Typography>
      <Typography variant="caption" color="text.secondary">24H Low {idr(market?.low)}</Typography>
      <Typography variant="caption" color="text.secondary">24H Volume {idr(market?.volume)}</Typography>
    </Stack>
  </Paper>;
}
