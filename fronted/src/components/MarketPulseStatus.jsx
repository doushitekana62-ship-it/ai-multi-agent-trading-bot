import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Box, Chip, Paper, Stack, Typography } from '@mui/material';
import { TrendingDown, TrendingUp, Remove } from '@mui/icons-material';

const POLL_MS = 5000;
const WINDOW_MS = 30 * 60 * 1000;
const FLAT_THRESHOLD_PCT = 0.05;
const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);

export default function MarketPulseStatus() {
  const [market, setMarket] = useState(null);
  const samplesRef = useRef([]);
  const [samples, setSamples] = useState([]);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    const load = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      try {
        const response = await axios.get('/api/market/overview', { params: { pair: localStorage.getItem('paperTradingPair') || 'btc_idr', _ts: Date.now() }, headers: { 'Cache-Control': 'no-cache' }, timeout: 8000 });
        if (cancelled) return;
        const data = response.data || {};
        setMarket(data);
        const now = Date.now();
        const price = Number(data.last || 0);
        if (price > 0) {
          const next = [...samplesRef.current, { at: now, price }].filter((item) => now - item.at <= WINDOW_MS).slice(-400);
          samplesRef.current = next;
          setSamples(next);
        }
      } catch {
        // Market Pulse remains readable from the existing dashboard data.
      } finally {
        inFlight = false;
      }
    };
    load();
    const timer = window.setInterval(load, POLL_MS);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const move = useMemo(() => {
    if (samples.length < 2 || samples[0].price <= 0) return null;
    return ((samples[samples.length - 1].price - samples[0].price) / samples[0].price) * 100;
  }, [samples]);

  const status = move == null ? 'UNAVAILABLE' : Math.abs(move) < FLAT_THRESHOLD_PCT ? 'FLAT' : move > 0 ? 'UP' : 'DOWN';
  const color = status === 'UP' ? 'success.main' : status === 'DOWN' ? 'error.main' : 'text.secondary';
  const Icon = status === 'UP' ? TrendingUp : status === 'DOWN' ? TrendingDown : Remove;

  return (
    <Paper sx={{ position: 'fixed', top: 78, right: 18, zIndex: 1380, px: 1.5, py: 1, minWidth: { xs: 230, sm: 300 }, maxWidth: 'calc(100vw - 36px)', backdropFilter: 'blur(10px)' }}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Icon sx={{ color }} fontSize="small" />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>MARKET PULSE · 30 MIN</Typography>
          <Typography variant="body2" fontWeight={700}>{move == null ? 'Menunggu cukup data' : `${move >= 0 ? '+' : ''}${move.toFixed(2)}%`}</Typography>
        </Box>
        <Chip size="small" label={status} sx={{ color, fontWeight: 700 }} />
      </Stack>
      <Stack direction="row" spacing={1.5} sx={{ mt: .7 }}>
        <Typography variant="caption" color="text.secondary">24H High {idr(market?.high)}</Typography>
        <Typography variant="caption" color="text.secondary">24H Low {idr(market?.low)}</Typography>
        <Typography variant="caption" color="text.secondary">Vol {idr(market?.volume)}</Typography>
      </Stack>
    </Paper>
  );
}
