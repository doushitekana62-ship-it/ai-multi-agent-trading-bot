import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Grid, Paper, Typography, Button, Card, CardContent, LinearProgress, Chip, IconButton, AppBar, Toolbar, Menu, MenuItem, Divider, ToggleButton, ToggleButtonGroup, Alert, Select, FormControl, InputLabel, TextField, Stack } from '@mui/material';
import { AccountCircle, Logout, Refresh, ShowChart, LockOutlined, TrendingUp, TrendingDown } from '@mui/icons-material';
import { useAuth } from '../context/AuthContext';
import DashboardTools from '../components/DashboardTools';
import axios from 'axios';
import toast from 'react-hot-toast';

const formatIDR = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);
const formatMarketPrice = (value, quote = 'IDR') => { const n = Number(value) || 0; return quote === 'IDR' ? formatIDR(n) : `${n.toLocaleString('en-US', { maximumFractionDigits: 8 })} ${quote}`; };
const PAIR_OPTIONS = [['btc_idr', 'BTC/IDR'], ['eth_idr', 'ETH/IDR'], ['usdt_idr', 'USDT/IDR'], ['xrp_idr', 'XRP/IDR'], ['doge_idr', 'DOGE/IDR'], ['sol_idr', 'SOL/IDR']];
const DEFAULT_TARGETS = { daily: 0, weekly: 0, monthly: 0 };

const SimplePriceChart = ({ points }) => {
  const values = (points || []).map((p) => Number(p.price)).filter((v) => Number.isFinite(v) && v > 0);
  if (values.length < 2) return <Box sx={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.secondary' }}>Waiting for recent public trades...</Box>;
  const min = Math.min(...values), max = Math.max(...values), range = max - min || 1;
  const coords = values.map((value, index) => `${(index / (values.length - 1)) * 100},${95 - ((value - min) / range) * 85}`).join(' ');
  return <Box sx={{ height: 220, px: 1 }}><svg viewBox="0 0 100 100" width="100%" height="100%" preserveAspectRatio="none"><polyline points={coords} fill="none" stroke="currentColor" strokeWidth="1.2" vectorEffect="non-scaling-stroke" /></svg><Box sx={{ display: 'flex', justifyContent: 'space-between', color: 'text.secondary', fontSize: 12 }}><span>{formatMarketPrice(min)}</span><span>{formatMarketPrice(max)}</span></Box></Box>;
};

const Dashboard = () => {
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const [anchorEl, setAnchorEl] = useState(null), [loading, setLoading] = useState(false), [status, setStatus] = useState(null), [positions, setPositions] = useState([]), [performance, setPerformance] = useState(null), [decision, setDecision] = useState(null), [agents, setAgents] = useState([]), [tradingMode, setTradingMode] = useState('paper');
  const [selectedPair, setSelectedPair] = useState(localStorage.getItem('paperTradingPair') || 'btc_idr'), [market, setMarket] = useState(null), [insights, setInsights] = useState([]), [decisionHistory, setDecisionHistory] = useState(() => { try { return JSON.parse(localStorage.getItem('aiDecisionObservations') || '[]'); } catch { return []; } });
  const [targets, setTargets] = useState(() => { try { return { ...DEFAULT_TARGETS, ...JSON.parse(localStorage.getItem('paperTradingTargets') || '{}') }; } catch { return DEFAULT_TARGETS; } }), [targetDraft, setTargetDraft] = useState(targets), [botLoading, setBotLoading] = useState(false);
  const botEnabled = Boolean(status?.bot_enabled ?? status?.enabled);

  const recordDecisionObservation = (nextDecision, nextMarket) => {
    if (!nextDecision) return;
    const timestamp = nextDecision.timestamp || new Date().toISOString();
    const item = { timestamp, action: String(nextDecision.action || 'HOLD').toUpperCase(), confidence: Number(nextDecision.confidence || 0) * 100, move: nextMarket?.recent_move == null ? null : Number(nextMarket.recent_move), pair: PAIR_OPTIONS.find(([value]) => value === selectedPair)?.[1] || selectedPair.toUpperCase() };
    setDecisionHistory((current) => { if (current[0]?.timestamp === timestamp) return current; const next = [item, ...current].slice(0, 20); localStorage.setItem('aiDecisionObservations', JSON.stringify(next)); return next; });
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const results = await Promise.all([
        axios.get('/api/dashboard/status'), axios.get('/api/dashboard/positions'), axios.get('/api/dashboard/performance'), axios.get('/api/dashboard/recent-decision'), axios.get('/api/dashboard/agents'), axios.get('/api/market/overview', { params: { pair: selectedPair } }), axios.get('/api/market/insights'),
      ]);
      const [statusRes, positionsRes, performanceRes, decisionRes, agentsRes, marketRes, insightRes] = results;
      setStatus(statusRes.data); setPositions(positionsRes.data.positions || []); setPerformance(performanceRes.data.performance || null); setDecision(decisionRes.data.decision || null); setAgents(agentsRes.data.agents || []); setMarket(marketRes.data); setInsights(insightRes.data.items || []); recordDecisionObservation(decisionRes.data.decision, marketRes.data);
    } catch (error) { console.error(error); toast.error(error.response?.data?.detail || 'Failed to fetch dashboard data'); } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); const interval = setInterval(fetchData, 60000); return () => clearInterval(interval); }, [selectedPair]);

  const handleStartBot = async () => {
    if (tradingMode !== 'paper') return toast.error('Only Paper Trading can be started.');
    if (botLoading || botEnabled) return;
    setBotLoading(true);
    try {
      const response = await axios.post('/api/bot/start', null, { params: { pair: selectedPair } });
      setStatus((current) => ({ ...(current || {}), ...response.data, bot_enabled: true, enabled: true }));
      toast.success('Paper Trading started');
      await fetchData();
    } catch (error) { toast.error(error.response?.data?.detail || error.response?.data?.reason || 'Unable to start Paper Trading'); await fetchData(); } finally { setBotLoading(false); }
  };

  const handleStopBot = async () => {
    if (botLoading || !botEnabled) return;
    setBotLoading(true);
    try { await axios.post('/api/bot/stop'); toast.success('Paper Trading stopped'); await fetchData(); }
    catch (error) { toast.error(error.response?.data?.detail || 'Unable to stop Paper Trading'); }
    finally { setBotLoading(false); }
  };

  const handleAnalyze = async () => {
    if (!botEnabled || tradingMode !== 'paper') return toast('Paper trading is OFF. Start the bot first.');
    try { toast.loading('Running paper cycle...'); const response = await axios.post('/api/dashboard/analyze', null, { params: { pair: selectedPair } }); toast.dismiss(); toast.success(`Cycle complete: ${String(response.data.action || 'HOLD').toUpperCase()}`); await fetchData(); }
    catch (error) { toast.dismiss(); toast.error(error.response?.data?.detail || error.response?.data?.reason || 'Paper cycle failed'); await fetchData(); }
  };

  const handleModeChange = (_event, newMode) => { if (newMode === 'real') return toast('Real Trading remains locked.'); if (newMode) setTradingMode(newMode); };
  const handlePairChange = (event) => { const value = event.target.value; setSelectedPair(value); localStorage.setItem('paperTradingPair', value); };
  const saveTargets = () => { const normalized = { daily: Math.max(0, Number(targetDraft.daily) || 0), weekly: Math.max(0, Number(targetDraft.weekly) || 0), monthly: Math.max(0, Number(targetDraft.monthly) || 0) }; setTargets(normalized); setTargetDraft(normalized); localStorage.setItem('paperTradingTargets', JSON.stringify(normalized)); toast.success('Evaluation targets saved'); };
  const counts = status?.decision_counts || { BUY: 0, SELL: 0, HOLD: 0 }, currentPairLabel = PAIR_OPTIONS.find(([value]) => value === selectedPair)?.[1] || selectedPair.toUpperCase();
  const dailyActual = Number(status?.daily_pnl || 0), insightRows = useMemo(() => insights.slice(0, 5), [insights]);

  return <Box sx={{ flexGrow: 1, minHeight: '100vh', bgcolor: 'background.default' }}>
    <AppBar position="static"><Toolbar><ShowChart sx={{ mr: 2 }} /><Typography variant="h6" sx={{ flexGrow: 1 }}>AI Trading Dashboard</Typography><Chip label={botEnabled ? 'BOT ON' : 'BOT OFF'} color={botEnabled ? 'success' : 'default'} size="small" sx={{ mr: 2 }} /><Button color="inherit" onClick={handleAnalyze} startIcon={<Refresh />} disabled={!botEnabled || tradingMode !== 'paper' || botLoading}>Analyze</Button><IconButton size="large" edge="end" color="inherit" onClick={(e) => setAnchorEl(e.currentTarget)}><AccountCircle /></IconButton><Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}><MenuItem disabled><Typography variant="body2">{user?.username || 'Admin'}</Typography></MenuItem><Divider /><MenuItem onClick={() => { setAnchorEl(null); navigate('/reports'); }}>Reports</MenuItem><MenuItem onClick={async () => { setAnchorEl(null); await logout(); navigate('/login'); }}><Logout sx={{ mr: 1 }} fontSize="small" />Logout</MenuItem></Menu></Toolbar></AppBar>
    <Box sx={{ p: 3 }}>{loading && <LinearProgress sx={{ mb: 2 }} />}
      <Paper sx={{ p: 2.5, mb: 3 }}><Grid container spacing={2} alignItems="center"><Grid item xs={12} md={5}><Typography variant="overline" color="text.secondary">Trading Environment</Typography><Typography variant="h5">Paper Trading</Typography><Typography variant="body2" color="text.secondary">Paper mode only. Real Trading remains locked.</Typography></Grid><Grid item xs={12} md={3}><FormControl fullWidth size="small"><InputLabel>Trading Pair</InputLabel><Select value={selectedPair} label="Trading Pair" onChange={handlePairChange}>{PAIR_OPTIONS.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}</Select></FormControl></Grid><Grid item xs={12} md={4}><ToggleButtonGroup value={tradingMode} exclusive onChange={handleModeChange}><ToggleButton value="paper">PAPER</ToggleButton><ToggleButton value="real" disabled><LockOutlined sx={{ mr: .75, fontSize: 18 }} />REAL</ToggleButton></ToggleButtonGroup></Grid></Grid><Alert severity={botEnabled ? 'success' : 'info'} sx={{ mt: 2 }}>{botEnabled ? 'Paper Trading is ON. No real exchange orders are permitted.' : 'Paper Trading is OFF. Starting it will only use the paper engine.'}</Alert></Paper>

      <Grid container spacing={3} sx={{ mb: 3 }}><Grid item xs={12} md={8}><Paper sx={{ p: 2.5, height: '100%' }}><Stack direction="row" justifyContent="space-between" alignItems="center"><Box><Typography variant="h6">Market Pulse</Typography><Typography variant="body2" color="text.secondary">{currentPairLabel} · INDODAX public data</Typography></Box><Typography variant="h6">{formatMarketPrice(market?.last, market?.quote_currency)}</Typography></Stack><SimplePriceChart points={market?.points} /><Grid container spacing={1}><Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">24h High</Typography><Typography>{formatMarketPrice(market?.high, market?.quote_currency)}</Typography></Grid><Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">24h Low</Typography><Typography>{formatMarketPrice(market?.low, market?.quote_currency)}</Typography></Grid><Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">Recent Move</Typography><Typography color={Number(market?.recent_move || 0) >= 0 ? 'success.main' : 'error.main'}>{market?.recent_move == null ? '—' : `${Number(market.recent_move).toFixed(2)}%`}</Typography></Grid><Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">Volume</Typography><Typography>{formatIDR(market?.volume)}</Typography></Grid></Grid></Paper></Grid><Grid item xs={12} md={4}><Paper sx={{ p: 2.5, height: '100%' }}><Typography variant="h6">Market Scanner</Typography><Stack spacing={1} sx={{ mt: 2 }}>{insightRows.map((item) => <Card key={item.pair} variant="outlined"><CardContent sx={{ py: 1.2 }}><Stack direction="row" justifyContent="space-between"><Box><Typography variant="subtitle2">{item.pair}</Typography><Typography variant="caption" color="text.secondary">{formatIDR(item.last)}</Typography></Box><Chip icon={item.range_position >= 50 ? <TrendingUp /> : <TrendingDown />} label={item.signal} size="small" /></Stack></CardContent></Card>)}</Stack></Paper></Grid></Grid>

      <Paper sx={{ p: 2.5, mb: 3 }}><Grid container alignItems="center" spacing={2}><Grid item xs={12} md={8}><Typography variant="h6">Paper Trading Control</Typography><Typography variant="body2" color="text.secondary">State: <strong>{botEnabled ? 'ON' : 'OFF'}</strong> · {botEnabled ? 'Paper engine is armed.' : 'No paper cycle will run until started.'}</Typography></Grid><Grid item xs={12} md={4} sx={{ display: 'flex', justifyContent: { xs: 'flex-start', md: 'flex-end' }, gap: 1 }}><Button variant="contained" color="success" onClick={handleStartBot} disabled={botEnabled || botLoading || tradingMode !== 'paper'}>{botLoading ? 'STARTING...' : 'START PAPER BOT'}</Button><Button variant="outlined" color="error" onClick={handleStopBot} disabled={!botEnabled || botLoading}>STOP</Button></Grid></Grid></Paper>

      <Grid container spacing={3} sx={{ mb: 3 }}>{[['Portfolio Value', formatIDR(status?.portfolio_value), `Balance: ${formatIDR(status?.balance)}`], ['Daily PnL', formatIDR(dailyActual), `${status?.daily_trades || 0} trades today`], ['Active Positions', status?.active_positions || 0, `Max: ${status?.max_open_positions || 5}`], ['Total Trades', status?.total_trades || 0, `Win Rate: ${((performance?.win_rate || 0) * 100).toFixed(1)}%`]].map(([title, value, sub]) => <Grid item xs={12} sm={6} md={3} key={title}><Card><CardContent><Typography color="text.secondary" gutterBottom>{title}</Typography><Typography variant="h5">{value}</Typography><Typography variant="body2" color="text.secondary">{sub}</Typography></CardContent></Card></Grid>)}</Grid>

      <Grid container spacing={3}><Grid item xs={12} md={6}><Paper sx={{ p: 2.5 }}><Typography variant="h6">Decision Monitor</Typography><Stack direction="row" spacing={1} sx={{ mt: 2 }}><Chip label={`BUY ${counts.BUY || 0}`} color="success" /><Chip label={`SELL ${counts.SELL || 0}`} color="error" /><Chip label={`HOLD ${counts.HOLD || 0}`} /></Stack><Typography sx={{ mt: 2 }} color="text.secondary">Last decision: {decision?.action || '—'}</Typography></Paper></Grid><Grid item xs={12} md={6}><Paper sx={{ p: 2.5 }}><Typography variant="h6">System Safety</Typography><Typography variant="body2" sx={{ mt: 1 }}>Mode: {status?.mode || 'paper'}</Typography><Typography variant="body2">Real trading locked: {status?.safety?.real_trading_locked !== false ? 'YES' : 'NO'}</Typography><Typography variant="body2">Cycle running: {status?.cycle_running ? 'YES' : 'NO'}</Typography></Paper></Grid></Grid>
    </Box>
  </Box>;
};

export default Dashboard;
