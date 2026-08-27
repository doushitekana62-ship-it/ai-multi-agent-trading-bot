import React, { useMemo } from 'react';
import { Box, Card, CardContent, Chip, Grid, LinearProgress, Paper, Stack, Typography } from '@mui/material';
import { TrendingDown, TrendingUp, Remove } from '@mui/icons-material';

const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);

export default function DashboardTools({ market, decision, counts, runtimeHours = 0, cycles = 0, targets, dailyActual = 0, decisionHistory = [], positions = [] }) {
  const move = Number(market?.recent_move);
  const action = String(decision?.action || '—').toUpperCase();
  const confidence = Number(decision?.confidence || 0) * 100;
  const rangePosition = Number(market?.range_position);
  const condition = Number.isFinite(rangePosition)
    ? rangePosition >= 75 ? 'NEAR 24H HIGH' : rangePosition <= 25 ? 'NEAR 24H LOW' : 'MID 24H RANGE'
    : 'UNAVAILABLE';
  const marketBias = Number.isFinite(move) ? (move > 0.5 ? 'RISING' : move < -0.5 ? 'FALLING' : 'FLAT') : condition;
  const observation = marketBias === 'RISING' && action === 'HOLD'
    ? 'Observation: market is rising while AI is HOLD.'
    : marketBias === 'FALLING' && action === 'HOLD'
      ? 'Observation: market is falling while AI is HOLD.'
      : 'No notable market/AI divergence detected.';
  const consensus = useMemo(() => {
    const votes = decision?.votes || {};
    const values = Object.values(votes).map((v) => String(v).toUpperCase());
    const buy = values.filter((v) => v === 'BUY').length;
    const sell = values.filter((v) => v === 'SELL').length;
    const hold = values.filter((v) => v === 'HOLD').length;
    const total = values.length;
    if (!total) return { label: 'NO DATA', percent: 0, buy, sell, hold };
    const max = Math.max(buy, sell, hold);
    const label = max === buy ? 'BUY' : max === sell ? 'SELL' : 'HOLD';
    return { label, percent: (max / total) * 100, buy, sell, hold };
  }, [decision]);
  const progress = (target) => Number(target) > 0 ? Math.min(100, Math.max(0, (dailyActual / Number(target)) * 100)) : 0;

  return (
    <Grid container spacing={3} sx={{ mb: 3 }}>
      <Grid item xs={12} md={4}>
        <Paper sx={{ p: 2.5, height: '100%' }}>
          <Typography variant="h6">Market vs AI</Typography>
          <Typography variant="caption" color="text.secondary">Observation only. This does not alter AI decisions.</Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 2, mb: 1 }} alignItems="center">
            {Number.isFinite(move) && move !== 0 ? (move > 0 ? <TrendingUp color="success" /> : <TrendingDown color="error" />) : <Remove color="disabled" />}
            <Typography variant="h5" color={move > 0 ? 'success.main' : move < 0 ? 'error.main' : 'text.primary'}>{Number.isFinite(move) ? `${move > 0 ? '+' : ''}${move.toFixed(2)}%` : '—'}</Typography>
            <Typography color="text.secondary">market</Typography>
            <Chip label={action} size="small" />
          </Stack>
          <Typography variant="body2">{observation}</Typography>
          <Typography variant="caption" color="text.secondary">AI confidence: {confidence ? `${confidence.toFixed(1)}%` : '—'}</Typography>
        </Paper>
      </Grid>

      <Grid item xs={12} md={4}>
        <Paper sx={{ p: 2.5, height: '100%' }}>
          <Typography variant="h6">AI Consensus</Typography>
          <Typography variant="caption" color="text.secondary">Current agent agreement. Informational only.</Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 2, mb: 1 }}>
            <Chip label={`${consensus.label} ${consensus.percent ? `${consensus.percent.toFixed(0)}%` : ''}`} color={consensus.label === 'BUY' ? 'success' : consensus.label === 'SELL' ? 'error' : 'default'} />
          </Stack>
          <Typography variant="body2">BUY {consensus.buy} · HOLD {consensus.hold} · SELL {consensus.sell}</Typography>
          <Typography variant="caption" color="text.secondary">Market condition: {marketBias} · {condition}</Typography>
        </Paper>
      </Grid>

      <Grid item xs={12} md={4}>
        <Paper sx={{ p: 2.5, height: '100%' }}>
          <Typography variant="h6">Paper Session</Typography>
          <Typography variant="caption" color="text.secondary">Counters remain zero while BOT is OFF.</Typography>
          <Grid container spacing={1.5} sx={{ mt: 1 }}>
            <Grid item xs={6}><Typography variant="caption" color="text.secondary">Runtime</Typography><Typography>{Number(runtimeHours).toFixed(1)} h</Typography></Grid>
            <Grid item xs={6}><Typography variant="caption" color="text.secondary">Cycles</Typography><Typography>{cycles || 0}</Typography></Grid>
            <Grid item xs={4}><Typography variant="caption" color="text.secondary">BUY</Typography><Typography color="success.main">{counts?.BUY || 0}</Typography></Grid>
            <Grid item xs={4}><Typography variant="caption" color="text.secondary">SELL</Typography><Typography color="error.main">{counts?.SELL || 0}</Typography></Grid>
            <Grid item xs={4}><Typography variant="caption" color="text.secondary">HOLD</Typography><Typography>{counts?.HOLD || 0}</Typography></Grid>
          </Grid>
        </Paper>
      </Grid>

      <Grid item xs={12} md={5}>
        <Paper sx={{ p: 2.5, height: '100%' }}>
          <Typography variant="h6">Decision History</Typography>
          <Typography variant="caption" color="text.secondary">Last dashboard observations, stored locally.</Typography>
          <Stack spacing={0.8} sx={{ mt: 1.5 }}>
            {decisionHistory.length === 0 && <Typography color="text.secondary">No observations yet.</Typography>}
            {decisionHistory.slice(0, 6).map((item, index) => (
              <Card key={`${item.timestamp}-${index}`} variant="outlined"><CardContent sx={{ py: 0.8, '&:last-child': { pb: 0.8 } }}>
                <Stack direction="row" justifyContent="space-between"><Typography variant="caption">{new Date(item.timestamp).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })}</Typography><Chip size="small" label={item.action} color={item.action === 'BUY' ? 'success' : item.action === 'SELL' ? 'error' : 'default'} /></Stack>
                <Typography variant="caption" color="text.secondary">{item.pair} · market {item.move == null ? '—' : `${item.move > 0 ? '+' : ''}${Number(item.move).toFixed(2)}%`} · confidence {item.confidence == null ? '—' : `${Number(item.confidence).toFixed(0)}%`}</Typography>
              </CardContent></Card>
            ))}
          </Stack>
        </Paper>
      </Grid>

      <Grid item xs={12} md={4}>
        <Paper sx={{ p: 2.5, height: '100%' }}>
          <Typography variant="h6">Risk Snapshot</Typography>
          <Typography variant="caption" color="text.secondary">Read-only paper account view.</Typography>
          <Stack spacing={1.2} sx={{ mt: 2 }}>
            <Stack direction="row" justifyContent="space-between"><Typography>Open positions</Typography><Typography>{positions.length}</Typography></Stack>
            <Stack direction="row" justifyContent="space-between"><Typography>Max positions</Typography><Typography>5</Typography></Stack>
            <Stack direction="row" justifyContent="space-between"><Typography>Exposure</Typography><Typography>{positions.length ? 'ACTIVE' : '0%'}</Typography></Stack>
            <Chip label={positions.length <= 5 ? 'WITHIN PAPER LIMIT' : 'REVIEW REQUIRED'} color={positions.length <= 5 ? 'success' : 'warning'} size="small" />
          </Stack>
        </Paper>
      </Grid>

      <Grid item xs={12} md={3}>
        <Paper sx={{ p: 2.5, height: '100%' }}>
          <Typography variant="h6">Target Review</Typography>
          <Typography variant="caption" color="text.secondary">Benchmark only, never an AI instruction.</Typography>
          {['daily', 'weekly', 'monthly'].map((period) => <Box key={period} sx={{ mt: 1.3 }}><Stack direction="row" justifyContent="space-between"><Typography variant="caption">{period.toUpperCase()}</Typography><Typography variant="caption">{Number(targets?.[period]) > 0 ? idr(targets[period]) : 'not set'}</Typography></Stack><LinearProgress variant="determinate" value={progress(targets?.[period])} /></Box>)}
        </Paper>
      </Grid>
    </Grid>
  );
}
