import React, { useMemo } from 'react';
import { Box, Chip, Stack, Typography } from '@mui/material';

const idr = (value) => new Intl.NumberFormat('id-ID', {
  style: 'currency', currency: 'IDR', maximumFractionDigits: 0,
}).format(Number(value) || 0);

const num = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

export default function TradingFlowChart({ points = [], positions = [], decision = null }) {
  const rows = useMemo(() => (Array.isArray(points) ? points : [])
    .map((point) => ({
      price: num(point?.price),
      timestamp: point?.timestamp ?? point?.observed_at ?? point?.date ?? null,
    }))
    .filter((point) => point.price !== null && point.price > 0)
    .slice(-180), [points]);

  const values = rows.map((row) => row.price);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const range = max - min || Math.max(min * 0.0001, 1);
  const path = values.length >= 2
    ? values.map((value, index) => `${(index / (values.length - 1)) * 100},${94 - ((value - min) / range) * 82}`).join(' ')
    : '';

  const latest = values.at(-1);
  const previous = values.at(-2);
  const move = latest && previous ? ((latest - previous) / previous) * 100 : null;
  const positionPnl = (Array.isArray(positions) ? positions : []).reduce(
    (sum, position) => sum + (num(position?.unrealized_pnl ?? position?.pnl) || 0), 0,
  );

  const forecastPath = useMemo(() => {
    const candidate = decision?.most_likely_path || decision?.forecast_path || decision?.forecast?.most_likely_path;
    if (!Array.isArray(candidate) || candidate.length < 2) return '';
    const forecast = candidate.map(num).filter((value) => value !== null && value > 0);
    if (forecast.length < 2) return '';
    const combinedMin = Math.min(min || forecast[0], ...forecast);
    const combinedMax = Math.max(max || forecast[0], ...forecast);
    const combinedRange = combinedMax - combinedMin || Math.max(combinedMin * 0.0001, 1);
    return forecast.map((value, index) => {
      const x = 78 + (index / Math.max(forecast.length - 1, 1)) * 22;
      const y = 94 - ((value - combinedMin) / combinedRange) * 82;
      return `${x},${y}`;
    }).join(' ');
  }, [decision, min, max]);

  return (
    <Box aria-label="Trading Flow Chart">
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} spacing={1}>
        <Box>
          <Typography variant="h6">Trading Flow Chart</Typography>
          <Typography variant="caption" color="text.secondary">
            Live INDODAX market path, current paper PnL, and falsifiable forecast when the Forecast Agent provides one.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Chip size="small" label={decision?.action || 'HOLD'} />
          <Chip size="small" label={forecastPath ? 'FORECAST READY' : 'FORECAST WAITING'} />
        </Stack>
      </Stack>

      {values.length >= 2 ? (
        <Box sx={{ mt: 1.5 }}>
          <svg viewBox="0 0 100 100" width="100%" height="230" preserveAspectRatio="none" role="img" aria-label="Live market price flow">
            <polyline points={path} fill="none" stroke="currentColor" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
            {forecastPath && <polyline points={forecastPath} fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" opacity="0.55" />}
          </svg>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="caption" color="text.secondary">Low {idr(min)}</Typography>
            <Typography variant="caption" color="text.secondary">{move == null ? '—' : `${move >= 0 ? '+' : ''}${move.toFixed(4)}% latest observed move`}</Typography>
            <Typography variant="caption" color="text.secondary">High {idr(max)}</Typography>
          </Stack>
        </Box>
      ) : (
        <Box sx={{ height: 230, display: 'grid', placeItems: 'center', color: 'text.secondary' }}>
          <Typography variant="body2">Collecting persisted live market points...</Typography>
        </Box>
      )}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mt: 1 }}>
        <Typography variant="caption" color="text.secondary">Current price: {latest ? idr(latest) : '—'}</Typography>
        <Typography variant="caption" color="text.secondary">Open-position PnL: {idr(positionPnl)}</Typography>
        <Typography variant="caption" color="text.secondary">Source: INDODAX public market data</Typography>
      </Stack>
    </Box>
  );
}
