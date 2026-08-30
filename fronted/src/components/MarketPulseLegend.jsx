import React, { useEffect, useMemo, useState } from 'react';
import { Box, Chip, Paper, Stack, Tooltip, Typography } from '@mui/material';
import axios from 'axios';

const POLL_MS = 5000;
const MINUTE_MS = 60 * 1000;
const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);
const statusColor = (status) => status === 'GREEN' ? 'success.main' : status === 'RED' ? 'error.main' : 'grey.500';
const statusLabel = (status) => status === 'GREEN' ? 'UP' : status === 'RED' ? 'DOWN' : 'FLAT';

const normalizeTimestamp = (point) => {
  const raw = Number(point?.timestamp ?? point?.date ?? point?.trade_time ?? 0);
  if (!Number.isFinite(raw) || raw <= 0) return null;
  return raw > 1e12 ? raw : raw * 1000;
};

export default function MarketPulseLegend() {
  const [market, setMarket] = useState(null);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    const load = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      try {
        const pair = localStorage.getItem('paperTradingPair') || 'btc_idr';
        const response = await axios.get('/api/market/overview', {
          params: { pair, _ts: Date.now() },
          headers: { 'Cache-Control': 'no-cache' },
          timeout: 8000,
        });
        if (!cancelled) setMarket(response.data || {});
      } catch {
        // Keep the last server snapshot. Never synthesize market state in the UI.
      } finally {
        inFlight = false;
      }
    };
    load();
    const timer = window.setInterval(load, POLL_MS);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const pulse = useMemo(() => {
    const points = Array.isArray(market?.points) ? market.points : [];
    const normalized = points.map((point) => ({
      at: normalizeTimestamp(point),
      price: Number(point?.price || 0),
    })).filter((point) => Number.isFinite(point.at) && point.at > 0 && Number.isFinite(point.price) && point.price > 0)
      .sort((a, b) => a.at - b.at);

    if (!normalized.length) return { segments: [], move30: null, current: null };

    const anchor = normalized[normalized.length - 1].at;
    const currentMinute = Math.floor(anchor / MINUTE_MS) * MINUTE_MS;
    const buckets = new Map();
    for (const sample of normalized) {
      const minute = Math.floor(sample.at / MINUTE_MS) * MINUTE_MS;
      if (minute < currentMinute - 29 * MINUTE_MS || minute > currentMinute) continue;
      const bucket = buckets.get(minute) || { open: sample.price, close: sample.price, samples: 0 };
      bucket.close = sample.price;
      bucket.samples += 1;
      buckets.set(minute, bucket);
    }

    const segments = [];
    for (let i = 29; i >= 0; i -= 1) {
      const minute = currentMinute - i * MINUTE_MS;
      const bucket = buckets.get(minute);
      if (!bucket) {
        segments.push({ minute, status: 'GRAY', move: null, samples: 0 });
        continue;
      }
      const move = bucket.open > 0 ? ((bucket.close - bucket.open) / bucket.open) * 100 : 0;
      segments.push({ minute, status: move > 0 ? 'GREEN' : move < 0 ? 'RED' : 'GRAY', move, samples: bucket.samples, open: bucket.open, close: bucket.close });
    }

    const populated = segments.filter((item) => Number.isFinite(item.move));
    const first = populated[0]?.open;
    const last = populated[populated.length - 1]?.close || Number(market?.last || 0);
    const move30 = first > 0 && last > 0 ? ((last - first) / first) * 100 : null;
    const current = segments[segments.length - 1] || null;
    return { segments, move30, current };
  }, [market]);

  const status = pulse.current?.status || 'GRAY';
  const move30 = pulse.move30;
  const currentMove = Number.isFinite(pulse.current?.move) ? pulse.current.move : null;

  return (
    <Paper sx={{ mt: 1.5, p: 2, borderRadius: 2.5 }} aria-label="Market Pulse 30 minute timeline">
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }} spacing={1}>
        <Box>
          <Typography variant="caption" fontWeight={700} sx={{ display: 'block' }}>MARKET PULSE · ROLLING 30 MINUTES</Typography>
          <Typography variant="caption" color="text.secondary">Satu blok = satu menit. Sumber segment adalah trade publik INDODAX; tanpa trade pada menit tersebut = FLAT.</Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" label={statusLabel(status)} sx={{ bgcolor: statusColor(status), color: 'common.white', fontWeight: 700 }} />
          <Typography variant="body2" fontWeight={700}>{move30 == null ? '—' : `${move30 >= 0 ? '+' : ''}${move30.toFixed(3)}% / 30m`}</Typography>
        </Stack>
      </Stack>

      <Stack direction="row" spacing={0.35} sx={{ mt: 1.5, alignItems: 'stretch' }}>
        {pulse.segments.map((segment) => (
          <Tooltip key={segment.minute} title={`${new Date(segment.minute).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })} · ${statusLabel(segment.status)}${Number.isFinite(segment.move) ? ` ${segment.move >= 0 ? '+' : ''}${segment.move.toFixed(4)}%` : ' · no trade data'}`}>
            <Box sx={{ flex: 1, minWidth: 4, height: 30, borderRadius: .7, bgcolor: statusColor(segment.status), opacity: segment.samples ? 1 : .28, border: segment.minute === pulse.current?.minute ? '2px solid' : 'none', borderColor: 'primary.main', cursor: 'help' }} />
          </Tooltip>
        ))}
      </Stack>

      <Stack direction="row" justifyContent="space-between" sx={{ mt: .7 }}>
        <Typography variant="caption" color="text.secondary">30 menit lalu</Typography>
        <Typography variant="caption" color={currentMove == null ? 'text.secondary' : currentMove > 0 ? 'success.main' : currentMove < 0 ? 'error.main' : 'text.secondary'} fontWeight={700}>{currentMove == null ? 'Menunggu trade menit berjalan' : `${currentMove >= 0 ? '+' : ''}${currentMove.toFixed(4)}% menit berjalan`}</Typography>
        <Typography variant="caption" color="text.secondary">sekarang</Typography>
      </Stack>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 1 }}>
        <Typography variant="caption" color="text.secondary">Price {idr(market?.last)}</Typography>
        <Typography variant="caption" color="text.secondary">24H High {idr(market?.high)}</Typography>
        <Typography variant="caption" color="text.secondary">24H Low {idr(market?.low)}</Typography>
        <Typography variant="caption" color="text.secondary">24H Volume {idr(market?.volume)}</Typography>
      </Stack>
    </Paper>
  );
}
