import React, { useEffect, useMemo, useState } from 'react';
import { Box, Card, CardContent, Chip, Grid, LinearProgress, Paper, Stack, Typography } from '@mui/material';
import { TrendingDown, TrendingUp, Remove } from '@mui/icons-material';
import axios from 'axios';
import { Radar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);
const LIVE_POLL_MS = 5000;
const MAX_OPEN_POSITIONS = 3;
const ALLOCATION_PER_TRADE = 10;
const EXECUTION_THRESHOLD = 75;

const Indicator = ({ label, ok, value }) => (
  <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
    <Stack direction="row" alignItems="center" spacing={1}>
      <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: ok ? 'success.main' : 'error.main', flexShrink: 0 }} />
      <Typography variant="body2">{label}</Typography>
    </Stack>
    <Typography variant="caption" color={ok ? 'success.main' : 'error.main'} sx={{ fontWeight: 700 }}>
      {value}
    </Typography>
  </Stack>
);

export default function DashboardTools({ market, decision, counts, runtimeHours = 0, cycles = 0, targets, dailyActual = 0, decisionHistory = [], positions = [] }) {
  const [health, setHealth] = useState(null);

  const loadHealth = async () => {
    try {
      const response = await axios.get('/api/dashboard/status', {
        params: { _ts: Date.now() },
        headers: { 'Cache-Control': 'no-cache' },
      });
      setHealth(response.data?.system_health || null);
    } catch (error) {
      console.error('Unable to fetch system health:', error);
      setHealth({
        database: { connected: false },
        market_data: { fresh: false, stale: true, age_seconds: null },
        mode: 'unknown',
        engine: { running: false },
      });
    }
  };

  useEffect(() => {
    loadHealth();
    const interval = setInterval(loadHealth, LIVE_POLL_MS);
    return () => clearInterval(interval);
  }, []);

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

  const radarValues = useMemo(() => {
    const scores = decision?.market_scores || {};
    return [
      Number(scores.sentiment || 0),
      Number(scores.technical || 0),
      Number(scores.decision || 0),
      Number(scores.forecast || 0),
      Number(scores.mimic_trader || 0),
      Number(scores.consensus || 0),
    ].map((v) => Math.max(-1, Math.min(1, Number.isFinite(v) ? v : 0)));
  }, [decision]);

  const radarRows = useMemo(() => [
    ['Sentiment', radarValues[0]],
    ['Technical', radarValues[1]],
    ['Decision', radarValues[2]],
    ['Forecast', radarValues[3]],
    ['Mimic Trader', radarValues[4]],
    ['Consensus', radarValues[5]],
  ], [radarValues]);

  const radarData = useMemo(() => ({
    labels: ['Sentiment', 'Technical', 'Decision', 'Forecast', 'Mimic Trader', 'Consensus'],
    datasets: [{ label: 'Agent score', data: radarValues, fill: true, borderWidth: 1.5, pointRadius: 3 }],
  }), [radarValues]);

  const radarOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    scales: { r: { min: -1, max: 1, ticks: { stepSize: 0.5 } } },
    plugins: { legend: { display: false } },
  }), []);

  const marketFresh = health?.market_data?.fresh === true && health?.market_data?.stale !== true;
  const databaseOk = health?.database?.connected === true;
  const engineRunning = health?.engine?.running === true;
  const mode = String(health?.mode || 'paper').toUpperCase();
  const marketAge = health?.market_data?.age_seconds;

  return (
    <Grid container spacing={3} sx={{ mb: 3 }}>
      <Grid item xs={12} md={4}>
        <Paper sx={{ p: 2.5, height: '100%' }}>
          <Typography variant="h6">System Health</Typography>
          <Typography variant="caption" color="text.secondary">Read-only diagnostics. This panel never starts an AI cycle.</Typography>
          <Stack spacing={1.3} sx={{ mt: 2 }}>
            <Indicator label="Database" ok={databaseOk} value={databaseOk ? 'CONNECTED' : 'DISCONNECTED'} />
            <Indicator label="Market data" ok={marketFresh} value={marketFresh ? `FRESH${marketAge != null ? ` · ${Number(marketAge).toFixed(1)}s` : ''}` : 'STALE'} />
            <Indicator label="Mode" ok={mode === 'PAPER'} value={mode} />
            <Indicator label="Engine" ok={engineRunning} value={engineRunning ? 'ACTIVE' : 'OFF'} />
          </Stack>
        </Paper>
      </Grid>
      <Grid item xs={12} md={8}>
        <Paper sx={{ p: 2.5, height: '100%' }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Box>
              <Typography variant="h6">Agent Score Radar</Typography>
              <Typography variant="caption" color="text.secondary">Latest OrchestratorResult.market_scores. Live view; never triggers analysis.</Typography>
            </Box>
            {decision?.confidence != null && <Chip label={`Confidence ${confidence.toFixed(1)}%`} size="small" color={confidence >= EXECUTION_THRESHOLD ? 'success' : 'default'} />}
          </Stack>
          <Grid container spacing={2} alignItems="center" sx={{ mt: 0.5 }}>
            <Grid item xs={12} md={7}>
              <Box sx={{ height: 250 }}>
                {decision?.market_scores ? <Radar data={radarData} options={radarOptions} /> : <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.secondary' }}>Waiting for an AI analysis result...</Box>}
              </Box>
            </Grid>
            <Grid item xs={12} md={5}>
              <Stack spacing={0.7}>
                {radarRows.map(([label, value]) => (
                  <Stack key={label} direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="caption" color="text.secondary">{label}</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>{Number(value).toFixed(2)}</Typography>
                  </Stack>
                ))}
              </Stack>
            </Grid>
          </Grid>
        </Paper>
      </Grid>
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
          <Typography variant="caption" color="text.secondary">Live counters from the persistent paper state.</Typography>
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
          <Typography variant="caption" color="text.secondary">Latest dashboard observations, stored locally.</Typography>
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
          <Typography variant="caption" color="text.secondary">Paper execution policy.</Typography>
          <Stack spacing={1.2} sx={{ mt: 2 }}>
            <Stack direction="row" justifyContent="space-between"><Typography>Open positions</Typography><Typography>{positions.length}</Typography></Stack>
            <Stack direction="row" justifyContent="space-between"><Typography>Max positions</Typography><Typography>{MAX_OPEN_POSITIONS}</Typography></Stack>
            <Stack direction="row" justifyContent="space-between"><Typography>Allocation / trade</Typography><Typography>{ALLOCATION_PER_TRADE}%</Typography></Stack>
            <Stack direction="row" justifyContent="space-between"><Typography>Execution threshold</Typography><Typography>{EXECUTION_THRESHOLD}%</Typography></Stack>
            <Chip label={positions.length <= MAX_OPEN_POSITIONS ? 'WITHIN PAPER LIMIT' : 'REVIEW REQUIRED'} color={positions.length <= MAX_OPEN_POSITIONS ? 'success' : 'warning'} size="small" />
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
