import React, { useEffect, useMemo, useState } from 'react';
import { Box, Card, CardContent, Chip, Grid, LinearProgress, Paper, Select, MenuItem, FormControl, InputLabel, Stack, TextField, Typography } from '@mui/material';
import { TrendingDown, TrendingUp, Remove } from '@mui/icons-material';
import axios from 'axios';
import { Chart as ChartJS, RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend, CategoryScale, LinearScale, LineController } from 'chart.js';
import { Radar, Line } from 'react-chartjs-2';

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend, CategoryScale, LinearScale, LineController);

const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);
const localDate = () => { const d = new Date(); const off = d.getTimezoneOffset(); return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10); };

const Indicator = ({ label, ok, value }) => (
  <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
    <Stack direction="row" alignItems="center" spacing={1}><Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: ok ? 'success.main' : 'error.main' }} /><Typography variant="body2">{label}</Typography></Stack>
    <Typography variant="caption" color={ok ? 'success.main' : 'error.main'} sx={{ fontWeight: 700 }}>{value}</Typography>
  </Stack>
);

export default function DashboardTools({ market, decision, counts, runtimeHours = 0, cycles = 0, targets, dailyActual = 0, decisionHistory = [], positions = [] }) {
  const [health, setHealth] = useState(null);
  const [maxPositions, setMaxPositions] = useState(3);
  const [historyDate, setHistoryDate] = useState(localDate());
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');

  const loadHealth = async () => {
    try { const response = await axios.get('/api/dashboard/status', { params: { _ts: Date.now() }, headers: { 'Cache-Control': 'no-cache' } }); setHealth(response.data?.system_health || null); setMaxPositions(Number(response.data?.max_open_positions || 3)); }
    catch (error) { console.error('Unable to fetch system health:', error); }
  };
  const loadHistory = async (date = historyDate) => {
    setHistoryLoading(true); setHistoryError('');
    try { const response = await axios.get('/api/dashboard/history', { params: { date, _ts: Date.now() }, headers: { 'Cache-Control': 'no-cache' } }); setHistory(response.data?.history || []); }
    catch (error) { console.error('Unable to fetch paper history:', error); setHistory([]); setHistoryError(error.response?.data?.detail || 'History unavailable'); }
    finally { setHistoryLoading(false); }
  };
  useEffect(() => { loadHealth(); const interval = setInterval(loadHealth, 5000); return () => clearInterval(interval); }, []);
  useEffect(() => { loadHistory(historyDate); }, [historyDate]);

  const saveMaxPositions = async (event) => {
    const value = Math.max(1, Math.min(3, Number(event.target.value) || 3));
    setMaxPositions(value);
    try { await axios.post('/api/dashboard/paper/settings', { max_open_positions: value }); }
    catch (error) { console.error('Unable to save position limit:', error); }
  };

  const move = Number(market?.recent_move); const action = String(decision?.action || '—').toUpperCase(); const confidence = Number(decision?.confidence || 0) * 100; const rangePosition = Number(market?.range_position);
  const condition = Number.isFinite(rangePosition) ? rangePosition >= 75 ? 'NEAR 24H HIGH' : rangePosition <= 25 ? 'NEAR 24H LOW' : 'MID 24H RANGE' : 'UNAVAILABLE';
  const marketBias = Number.isFinite(move) ? (move > 0.5 ? 'RISING' : move < -0.5 ? 'FALLING' : 'FLAT') : condition;
  const observation = marketBias === 'RISING' && action === 'HOLD' ? 'Market rising while AI is HOLD.' : marketBias === 'FALLING' && action === 'HOLD' ? 'Market falling while AI is HOLD.' : 'No notable market/AI divergence.';

  const consensus = useMemo(() => {
    const values = Object.values(decision?.votes || {}).map((v) => String(v).toUpperCase()); const buy = values.filter((v) => v === 'BUY').length; const sell = values.filter((v) => v === 'SELL').length; const hold = values.filter((v) => v === 'HOLD').length; const total = values.length;
    if (!total) return { label: 'NO DATA', percent: 0, buy, sell, hold }; const max = Math.max(buy, sell, hold); const label = max === buy ? 'BUY' : max === sell ? 'SELL' : 'HOLD'; return { label, percent: max / total * 100, buy, sell, hold };
  }, [decision]);

  const radarValues = useMemo(() => {
    const s = decision?.market_scores || {}; return [Number(s.sentiment || 0), Number(s.technical || 0), Number(s.decision || 0), Number(s.forecast || 0), Number(s.mimic_trader || 0), Number(s.consensus || 0)].map((v) => Math.max(-1, Math.min(1, Number.isFinite(v) ? v : 0)));
  }, [decision]);
  const radarData = useMemo(() => ({ labels: ['Sentiment', 'Technical', 'Decision', 'Forecast', 'Trader', 'Consensus'], datasets: [{ label: 'Score', data: radarValues, fill: true, borderWidth: 2, pointRadius: 3 }] }), [radarValues]);
  const radarOptions = useMemo(() => ({ responsive: true, maintainAspectRatio: false, scales: { r: { min: -1, max: 1, ticks: { stepSize: 0.5 }, pointLabels: { font: { size: 11 } } } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${Number(ctx.raw).toFixed(2)}` } } } }), []);

  const chart = useMemo(() => {
    const points = Array.isArray(market?.points) ? market.points.filter((p) => Number(p.price) > 0).slice(-40) : [];
    const labels = points.map((p, i) => p.timestamp ? new Date(Number(p.timestamp) * 1000).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : `${i + 1}`);
    const prices = points.map((p) => Number(p.price));
    const entry = positions.length ? Number(positions[0].entry_price || 0) : 0;
    const profit = points.map((p) => entry > 0 ? Math.max(0, (Number(p.price) - entry) * Number(positions[0].quantity || 0)) : 0);
    const loss = points.map((p) => entry > 0 ? Math.min(0, (Number(p.price) - entry) * Number(positions[0].quantity || 0)) : 0);
    const forecastScore = Number(decision?.market_scores?.forecast || 0);
    const forecast = prices.map((p, i) => p * (1 + forecastScore * 0.004 * (i + 1)));
    return { labels, datasets: [
      { label: 'Market Price', data: prices, borderColor: '#666', backgroundColor: 'transparent', yAxisID: 'price', tension: 0.25, pointRadius: 0 },
      { label: 'Profit', data: profit, borderColor: '#16a34a', backgroundColor: 'transparent', yAxisID: 'pnl', tension: 0.2, pointRadius: 0 },
      { label: 'Loss', data: loss, borderColor: '#dc2626', backgroundColor: 'transparent', yAxisID: 'pnl', tension: 0.2, pointRadius: 0 },
      { label: 'Forecast', data: forecast, borderColor: '#2563eb', backgroundColor: 'transparent', yAxisID: 'price', borderDash: [6, 4], tension: 0.25, pointRadius: 0 },
    ] };
  }, [market, decision, positions]);
  const chartOptions = useMemo(() => ({ responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, scales: { price: { type: 'linear', position: 'left', title: { display: true, text: 'Price (IDR)' } }, pnl: { type: 'linear', position: 'right', title: { display: true, text: 'PnL (IDR)' }, grid: { drawOnChartArea: false } } }, plugins: { legend: { display: true, position: 'bottom' } } }), []);

  return (
    <Grid container spacing={3} sx={{ mb: 3 }}>
      <Grid item xs={12} md={4}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">System Health</Typography><Typography variant="caption" color="text.secondary">Read-only diagnostics.</Typography><Stack spacing={1.3} sx={{ mt: 2 }}><Indicator label="Database" ok={health?.database?.connected === true} value={health?.database?.connected ? 'CONNECTED' : 'DISCONNECTED'} /><Indicator label="Market data" ok={health?.market_data?.fresh === true} value={health?.market_data?.fresh ? 'FRESH' : 'STALE'} /><Indicator label="Mode" ok={String(health?.mode || 'paper').toUpperCase() === 'PAPER'} value={String(health?.mode || 'paper').toUpperCase()} /><Indicator label="Engine" ok={health?.engine?.enabled === true} value={health?.engine?.enabled ? 'ARMED' : 'OFF'} /></Stack></Paper></Grid>

      <Grid item xs={12} md={8}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">Agent Score Radar — How to Read</Typography><Typography variant="caption" color="text.secondary">Each spoke is one signal. Positive values lean BUY, negative values lean SELL, and values near 0 mean neutral. The outer edge is stronger evidence; this chart does not execute trades.</Typography><Box sx={{ height: 270, mt: 1 }}>{decision?.market_scores ? <Radar data={radarData} options={radarOptions} /> : <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.secondary' }}>Waiting for an AI result...</Box>}</Box><Stack direction="row" spacing={1} flexWrap="wrap"><Chip size="small" label="+1 strong BUY bias" /><Chip size="small" label="0 neutral" /><Chip size="small" label="−1 strong SELL bias" /></Stack></Paper></Grid>

      <Grid item xs={12}><Paper sx={{ p: 2.5 }}><Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }} spacing={1}><Box><Typography variant="h6">Trading Flow Chart</Typography><Typography variant="caption" color="text.secondary">Gray = market price · green = profit PnL · red = loss PnL · blue dashed = AI forecast projection.</Typography></Box><Chip label={action} color={action === 'BUY' ? 'success' : action === 'SELL' ? 'error' : 'default'} /></Stack><Box sx={{ height: 360, mt: 2 }}>{chart.labels.length > 1 ? <Line data={chart} options={chartOptions} /> : <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.secondary' }}>Waiting for recent market points...</Box>}</Box></Paper></Grid>

      <Grid item xs={12} md={4}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">Position Control</Typography><Typography variant="caption" color="text.secondary">Choose the maximum number of simultaneous paper positions. Hard limit: 3.</Typography><FormControl fullWidth size="small" sx={{ mt: 2 }}><InputLabel>Maximum positions</InputLabel><Select value={maxPositions} label="Maximum positions" onChange={saveMaxPositions}><MenuItem value={1}>1 position</MenuItem><MenuItem value={2}>2 positions</MenuItem><MenuItem value={3}>3 positions</MenuItem></Select></FormControl><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>Current: {positions.length} / {maxPositions} open. Each new BUY uses up to 10% of current equity.</Typography></Paper></Grid>

      <Grid item xs={12} md={4}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">Market vs AI</Typography><Typography variant="caption" color="text.secondary">Observation only.</Typography><Stack direction="row" spacing={1} sx={{ mt: 2, mb: 1 }} alignItems="center">{Number.isFinite(move) && move !== 0 ? (move > 0 ? <TrendingUp color="success" /> : <TrendingDown color="error" />) : <Remove color="disabled" />}<Typography variant="h5" color={move > 0 ? 'success.main' : move < 0 ? 'error.main' : 'text.primary'}>{Number.isFinite(move) ? `${move > 0 ? '+' : ''}${move.toFixed(2)}%` : '—'}</Typography><Typography color="text.secondary">market</Typography></Stack><Typography variant="body2">{observation}</Typography><Typography variant="caption" color="text.secondary">AI confidence: {confidence ? `${confidence.toFixed(1)}%` : '—'}</Typography></Paper></Grid>

      <Grid item xs={12} md={4}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">AI Consensus</Typography><Typography variant="caption" color="text.secondary">Current agent agreement.</Typography><Stack direction="row" spacing={1} sx={{ mt: 2, mb: 1 }}><Chip label={`${consensus.label} ${consensus.percent ? `${consensus.percent.toFixed(0)}%` : ''}`} color={consensus.label === 'BUY' ? 'success' : consensus.label === 'SELL' ? 'error' : 'default'} /></Stack><Typography variant="body2">BUY {consensus.buy} · HOLD {consensus.hold} · SELL {consensus.sell}</Typography><Typography variant="caption" color="text.secondary">Market condition: {marketBias} · {condition}</Typography></Paper></Grid>

      <Grid item xs={12} md={4}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">Paper Session</Typography><Typography variant="caption" color="text.secondary">Cash changes when a paper BUY/SELL is filled.</Typography><Grid container spacing={1.5} sx={{ mt: 1 }}><Grid item xs={6}><Typography variant="caption" color="text.secondary">Runtime</Typography><Typography>{Number(runtimeHours).toFixed(1)} h</Typography></Grid><Grid item xs={6}><Typography variant="caption" color="text.secondary">Cycles</Typography><Typography>{cycles || 0}</Typography></Grid><Grid item xs={4}><Typography variant="caption" color="text.secondary">BUY</Typography><Typography color="success.main">{counts?.BUY || 0}</Typography></Grid><Grid item xs={4}><Typography variant="caption" color="text.secondary">SELL</Typography><Typography color="error.main">{counts?.SELL || 0}</Typography></Grid><Grid item xs={4}><Typography variant="caption" color="text.secondary">HOLD</Typography><Typography>{counts?.HOLD || 0}</Typography></Grid></Grid></Paper></Grid>

      <Grid item xs={12} md={5}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">Decision History</Typography><Typography variant="caption" color="text.secondary">Recent dashboard observations plus persistent daily library below.</Typography><Stack spacing={0.8} sx={{ mt: 1.5 }}>{decisionHistory.length === 0 && <Typography color="text.secondary">No observations yet.</Typography>}{decisionHistory.slice(0,6).map((item,index)=><Card key={`${item.timestamp}-${index}`} variant="outlined"><CardContent sx={{ py:0.8, '&:last-child':{pb:0.8} }}><Stack direction="row" justifyContent="space-between"><Typography variant="caption">{new Date(item.timestamp).toLocaleTimeString('id-ID',{hour:'2-digit',minute:'2-digit'})}</Typography><Chip size="small" label={item.action} color={item.action==='BUY'?'success':item.action==='SELL'?'error':'default'} /></Stack><Typography variant="caption" color="text.secondary">{item.pair} · market {item.move == null ? '—' : `${item.move > 0 ? '+' : ''}${Number(item.move).toFixed(2)}%`} · confidence {item.confidence == null ? '—' : `${Number(item.confidence).toFixed(0)}%`}</Typography></CardContent></Card>)}</Stack></Paper></Grid>

      <Grid item xs={12} md={3}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">Risk Snapshot</Typography><Typography variant="caption" color="text.secondary">Paper account guardrails.</Typography><Stack spacing={1.2} sx={{ mt: 2 }}><Stack direction="row" justifyContent="space-between"><Typography>Open positions</Typography><Typography>{positions.length}</Typography></Stack><Stack direction="row" justifyContent="space-between"><Typography>Max positions</Typography><Typography>{maxPositions}</Typography></Stack><Stack direction="row" justifyContent="space-between"><Typography>Allocation / trade</Typography><Typography>10%</Typography></Stack><Chip label={positions.length <= maxPositions ? 'WITHIN LIMIT' : 'REVIEW'} color={positions.length <= maxPositions ? 'success' : 'warning'} size="small" /></Stack></Paper></Grid>

      <Grid item xs={12} md={4}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">Target Review</Typography><Typography variant="caption" color="text.secondary">Benchmark only.</Typography>{['daily','weekly','monthly'].map((period)=><Box key={period} sx={{ mt:1.3 }}><Stack direction="row" justifyContent="space-between"><Typography variant="caption">{period.toUpperCase()}</Typography><Typography variant="caption">{Number(targets?.[period])>0?idr(targets[period]):'not set'}</Typography></Stack><LinearProgress variant="determinate" value={Number(targets?.[period])>0?Math.min(100,Math.max(0,(dailyActual/Number(targets[period]))*100)):0}/></Box>)}</Paper></Grid>

      <Grid item xs={12}><Paper sx={{ p: 2.5 }}><Stack direction={{ xs:'column', md:'row' }} justifyContent="space-between" alignItems={{ xs:'flex-start', md:'center' }} spacing={1}><Box><Typography variant="h6">Paper History Library</Typography><Typography variant="caption" color="text.secondary">Persistent Supabase snapshots. Select a date to reconstruct the paper session and audit each cycle.</Typography></Box><Stack direction="row" spacing={1} alignItems="center"><TextField size="small" type="date" label="Trading date" value={historyDate} onChange={(e)=>setHistoryDate(e.target.value)} InputLabelProps={{ shrink:true }} /><Chip label={`${history.length} cycles`} /></Stack></Stack>{historyError && <Typography color="error" sx={{ mt:2 }}>{historyError}</Typography>}{historyLoading ? <LinearProgress sx={{ mt:2 }} /> : history.length === 0 ? <Typography color="text.secondary" sx={{ mt:2 }}>No persistent cycles for {historyDate}.</Typography> : <Stack spacing={1} sx={{ mt:2 }}>{history.map((row)=><Card key={row.id} variant="outlined"><CardContent sx={{ py:1.2 }}><Grid container spacing={1} alignItems="center"><Grid item xs={12} md={2}><Typography variant="subtitle2">{new Date(row.cycle_at).toLocaleTimeString('id-ID',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</Typography><Typography variant="caption" color="text.secondary">{row.pair}</Typography></Grid><Grid item xs={6} md={1}><Chip size="small" label={row.action} color={row.action==='BUY'?'success':row.action==='SELL'?'error':'default'} /></Grid><Grid item xs={6} md={2}><Typography variant="caption" color="text.secondary">Price</Typography><Typography>{idr(row.price)}</Typography></Grid><Grid item xs={6} md={2}><Typography variant="caption" color="text.secondary">Balance</Typography><Typography>{idr(row.balance)}</Typography></Grid><Grid item xs={6} md={2}><Typography variant="caption" color="text.secondary">Equity</Typography><Typography>{idr(row.portfolio_value)}</Typography></Grid><Grid item xs={6} md={1}><Typography variant="caption" color="text.secondary">Confidence</Typography><Typography>{Number(row.confidence||0).toFixed(0)}%</Typography></Grid><Grid item xs={6} md={2}><Typography variant="caption" color="text.secondary">PnL</Typography><Typography color={Number(row.daily_pnl||0)>=0?'success.main':'error.main'}>{idr(row.daily_pnl)}</Typography></Grid></Grid><Typography variant="caption" color="text.secondary">Positions {row.active_positions} · Consensus {row.consensus_action || '—'} · Source {row.engine_source || '—'}</Typography></CardContent></Card>)}</Stack>}</Paper></Grid>
    </Grid>
  );
}
