import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Grid, Paper, Typography, Button, Card, CardContent,
  LinearProgress, Chip, IconButton, AppBar, Toolbar, Menu,
  MenuItem, Divider, ToggleButton, ToggleButtonGroup, Alert,
  Select, FormControl, InputLabel, TextField, Stack,
} from '@mui/material';
import { AccountCircle, Logout, Refresh, ShowChart, LockOutlined, TrendingUp, TrendingDown } from '@mui/icons-material';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import toast from 'react-hot-toast';

const formatIDR = (value) => new Intl.NumberFormat('id-ID', {
  style: 'currency', currency: 'IDR', maximumFractionDigits: 0,
}).format(Number(value) || 0);

const formatMarketPrice = (value, quote = 'IDR') => {
  const n = Number(value) || 0;
  if (quote === 'IDR') return formatIDR(n);
  return `${n.toLocaleString('en-US', { maximumFractionDigits: 8 })} ${quote}`;
};

const PAIR_OPTIONS = [
  ['btc_idr', 'BTC/IDR'], ['eth_idr', 'ETH/IDR'], ['usdt_idr', 'USDT/IDR'],
  ['xrp_idr', 'XRP/IDR'], ['doge_idr', 'DOGE/IDR'], ['sol_idr', 'SOL/IDR'],
];

const DEFAULT_TARGETS = { daily: 0, weekly: 0, monthly: 0 };

const SimplePriceChart = ({ points }) => {
  const values = (points || []).map((p) => Number(p.price)).filter((v) => Number.isFinite(v) && v > 0);
  if (values.length < 2) return <Box sx={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.secondary' }}>Waiting for recent public trades...</Box>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const coords = values.map((value, index) => {
    const x = (index / (values.length - 1)) * 100;
    const y = 95 - ((value - min) / range) * 85;
    return `${x},${y}`;
  }).join(' ');
  return (
    <Box sx={{ height: 220, px: 1 }}>
      <svg viewBox="0 0 100 100" width="100%" height="100%" preserveAspectRatio="none" aria-label="recent market price chart">
        <polyline points={coords} fill="none" stroke="currentColor" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
      </svg>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', color: 'text.secondary', fontSize: 12 }}>
        <span>{formatMarketPrice(min)}</span><span>{formatMarketPrice(max)}</span>
      </Box>
    </Box>
  );
};

const Dashboard = () => {
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const [anchorEl, setAnchorEl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null);
  const [positions, setPositions] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [decision, setDecision] = useState(null);
  const [agents, setAgents] = useState([]);
  const [tradingMode, setTradingMode] = useState('paper');
  const [selectedPair, setSelectedPair] = useState(localStorage.getItem('paperTradingPair') || 'btc_idr');
  const [market, setMarket] = useState(null);
  const [insights, setInsights] = useState([]);
  const [targets, setTargets] = useState(() => {
    try { return { ...DEFAULT_TARGETS, ...JSON.parse(localStorage.getItem('paperTradingTargets') || '{}') }; }
    catch { return DEFAULT_TARGETS; }
  });
  const [targetDraft, setTargetDraft] = useState(targets);
  const [botEnabled] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statusRes, positionsRes, performanceRes, decisionRes, agentsRes, marketRes, insightRes] = await Promise.all([
        axios.get('/api/dashboard/status'),
        axios.get('/api/dashboard/positions'),
        axios.get('/api/dashboard/performance'),
        axios.get('/api/dashboard/recent-decision'),
        axios.get('/api/dashboard/agents'),
        axios.get('/api/market/overview', { params: { pair: selectedPair } }),
        axios.get('/api/market/insights'),
      ]);
      setStatus(statusRes.data);
      setPositions(positionsRes.data.positions || []);
      setPerformance(performanceRes.data.performance || null);
      setDecision(decisionRes.data.decision || null);
      setAgents(agentsRes.data.agents || []);
      setMarket(marketRes.data);
      setInsights(insightRes.data.items || []);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      toast.error('Failed to fetch dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [selectedPair]);

  const handleLogout = async () => {
    setAnchorEl(null);
    await logout();
    navigate('/login');
  };

  const handleAnalyze = async () => {
    if (!botEnabled || tradingMode !== 'paper') {
      toast('Paper trading is OFF. No AI cycle was started.');
      return;
    }
    try {
      toast.loading('Analyzing...');
      const response = await axios.post('/api/dashboard/analyze', null, { params: { symbol: selectedPair.toUpperCase() } });
      toast.dismiss();
      toast.success('Analysis complete!');
      setDecision(response.data);
      fetchData();
    } catch (error) {
      toast.dismiss();
      toast.error(error.response?.data?.detail || 'Analysis failed');
    }
  };

  const handleModeChange = (_event, newMode) => {
    if (newMode === 'real') {
      toast('Real Trading is visible for future use but remains locked.');
      return;
    }
    if (newMode) setTradingMode(newMode);
  };

  const handlePairChange = (event) => {
    const value = event.target.value;
    setSelectedPair(value);
    localStorage.setItem('paperTradingPair', value);
  };

  const saveTargets = () => {
    const normalized = {
      daily: Math.max(0, Number(targetDraft.daily) || 0),
      weekly: Math.max(0, Number(targetDraft.weekly) || 0),
      monthly: Math.max(0, Number(targetDraft.monthly) || 0),
    };
    setTargets(normalized);
    setTargetDraft(normalized);
    localStorage.setItem('paperTradingTargets', JSON.stringify(normalized));
    toast.success('Evaluation targets saved');
  };

  const counts = status?.decision_counts || { BUY: 0, SELL: 0, HOLD: 0 };
  const currentPairLabel = PAIR_OPTIONS.find(([value]) => value === selectedPair)?.[1] || selectedPair.toUpperCase();
  const dailyActual = Number(status?.daily_pnl || 0) * Number(status?.balance || 0);
  const targetProgress = (target) => target > 0 ? Math.min(100, Math.max(0, (dailyActual / target) * 100)) : 0;
  const insightRows = useMemo(() => insights.slice(0, 5), [insights]);

  return (
    <Box sx={{ flexGrow: 1, minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="static">
        <Toolbar>
          <ShowChart sx={{ mr: 2 }} />
          <Typography variant="h6" sx={{ flexGrow: 1 }}>AI Trading Dashboard</Typography>
          <Chip label={botEnabled ? 'BOT ON' : 'BOT OFF'} color={botEnabled ? 'success' : 'default'} size="small" sx={{ mr: 2, fontWeight: 700 }} />
          <Button color="inherit" onClick={handleAnalyze} startIcon={<Refresh />} disabled={!botEnabled || tradingMode !== 'paper'}>Analyze</Button>
          <IconButton size="large" edge="end" color="inherit" onClick={(e) => setAnchorEl(e.currentTarget)}><AccountCircle /></IconButton>
          <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            <MenuItem disabled><Typography variant="body2">{user?.username || 'Admin'}</Typography></MenuItem>
            <Divider />
            <MenuItem onClick={() => { setAnchorEl(null); navigate('/reports'); }}>Reports</MenuItem>
            <MenuItem onClick={handleLogout}><Logout sx={{ mr: 1 }} fontSize="small" />Logout</MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>

      <Box sx={{ p: 3 }}>
        {loading && <LinearProgress sx={{ mb: 2 }} />}

        <Paper sx={{ p: 2.5, mb: 3, border: '1px solid', borderColor: 'divider' }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={5}>
              <Typography variant="overline" color="text.secondary">Trading Environment</Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, mb: 0.5 }}>{tradingMode === 'paper' ? 'Paper Trading' : 'Real Trading'}</Typography>
              <Typography variant="body2" color="text.secondary">Paper is the active validation environment. Real Trading is visible for future use only and is not connected to any exchange.</Typography>
            </Grid>
            <Grid item xs={12} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Trading Pair</InputLabel>
                <Select value={selectedPair} label="Trading Pair" onChange={handlePairChange}>
                  {PAIR_OPTIONS.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={4} sx={{ display: 'flex', justifyContent: { xs: 'flex-start', md: 'flex-end' } }}>
              <ToggleButtonGroup value={tradingMode} exclusive onChange={handleModeChange}>
                <ToggleButton value="paper">PAPER</ToggleButton>
                <ToggleButton value="real" disabled><LockOutlined sx={{ mr: 0.75, fontSize: 18 }} />REAL</ToggleButton>
              </ToggleButtonGroup>
            </Grid>
          </Grid>
          <Alert severity="info" sx={{ mt: 2 }}>Safety mode: BOT OFF by default. Selecting, refreshing, or viewing this dashboard never starts an AI trading cycle.</Alert>
        </Paper>

        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 2.5, height: '100%' }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Box>
                  <Typography variant="h6">Market Pulse</Typography>
                  <Typography variant="body2" color="text.secondary">{currentPairLabel} · INDODAX public data · recent trades only</Typography>
                </Box>
                <Typography variant="h6">{formatMarketPrice(market?.last, market?.quote_currency)}</Typography>
              </Stack>
              <SimplePriceChart points={market?.points} />
              <Grid container spacing={1} sx={{ mt: 1 }}>
                <Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">24h High</Typography><Typography>{formatMarketPrice(market?.high, market?.quote_currency)}</Typography></Grid>
                <Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">24h Low</Typography><Typography>{formatMarketPrice(market?.low, market?.quote_currency)}</Typography></Grid>
                <Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">Recent Move</Typography><Typography color={Number(market?.recent_move || 0) >= 0 ? 'success.main' : 'error.main'}>{market?.recent_move == null ? '—' : `${Number(market.recent_move).toFixed(2)}%`}</Typography></Grid>
                <Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">24h Volume</Typography><Typography>{formatIDR(market?.volume)}</Typography></Grid>
              </Grid>
              <Typography variant="caption" color="text.secondary">Recent Move = movement across the latest public trades returned by INDODAX, not a claimed 24h percentage change.</Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 2.5, height: '100%' }}>
              <Typography variant="h6" gutterBottom>Market Scanner</Typography>
              <Typography variant="caption" color="text.secondary">Lightweight watchlist ranked by IDR volume. It does not place trades.</Typography>
              <Stack spacing={1} sx={{ mt: 2 }}>
                {insightRows.map((item) => (
                  <Card key={item.pair} variant="outlined"><CardContent sx={{ py: 1.2, '&:last-child': { pb: 1.2 } }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                      <Box><Typography variant="subtitle2">{item.pair}</Typography><Typography variant="caption" color="text.secondary">{formatIDR(item.last)} · Vol {formatIDR(item.volume_idr)}</Typography></Box>
                      <Chip icon={item.range_position >= 50 ? <TrendingUp /> : <TrendingDown />} label={item.signal} size="small" color={item.range_position >= 80 ? 'success' : item.range_position <= 20 ? 'error' : 'default'} />
                    </Stack>
                  </CardContent></Card>
                ))}
                {insightRows.length === 0 && <Typography color="text.secondary">Market scanner unavailable.</Typography>}
              </Stack>
            </Paper>
          </Grid>
        </Grid>

        <Paper sx={{ p: 2.5, mb: 3 }}>
          <Grid container alignItems="center" spacing={2}>
            <Grid item xs={12} md={8}><Typography variant="h6">Paper Trading Control</Typography><Typography variant="body2" color="text.secondary">Current state: <strong>OFF</strong>. The trading engine remains disconnected until the persistent safety gate is implemented.</Typography></Grid>
            <Grid item xs={12} md={4} sx={{ display: 'flex', justifyContent: { xs: 'flex-start', md: 'flex-end' } }}><Button variant="contained" disabled>START PAPER BOT</Button></Grid>
          </Grid>
        </Paper>

        <Grid container spacing={3} sx={{ mb: 3 }}>
          {[
            ['Portfolio Value', formatIDR(status?.portfolio_value), `Balance: ${formatIDR(status?.balance)}`],
            ['Daily PnL', formatIDR(dailyActual), `${status?.daily_trades || 0} trades today`],
            ['Active Positions', status?.active_positions || 0, `Max: ${status?.max_open_positions || 5}`],
            ['Total Trades', status?.total_trades || 0, `Win Rate: ${((performance?.win_rate || 0) * 100).toFixed(1)}%`],
          ].map(([title, value, sub]) => <Grid item xs={12} sm={6} md={3} key={title}><Card><CardContent><Typography color="text.secondary" gutterBottom>{title}</Typography><Typography variant="h5">{value}</Typography><Typography variant="body2" color="text.secondary">{sub}</Typography></CardContent></Card></Grid>)}
        </Grid>

        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} md={7}>
            <Paper sx={{ p: 2.5, height: '100%' }}>
              <Typography variant="h6" gutterBottom>AI Runtime & Decisions</Typography>
              <Grid container spacing={2}>
                <Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">AI Runtime</Typography><Typography variant="h6">{Number(status?.runtime_hours || 0).toFixed(1)} h</Typography></Grid>
                <Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">Cycles</Typography><Typography variant="h6">{status?.cycles_today || 0}</Typography></Grid>
                <Grid item xs={4} md={2}><Typography variant="caption" color="text.secondary">BUY</Typography><Typography color="success.main" variant="h6">{counts.BUY || 0}</Typography></Grid>
                <Grid item xs={4} md={2}><Typography variant="caption" color="text.secondary">SELL</Typography><Typography color="error.main" variant="h6">{counts.SELL || 0}</Typography></Grid>
                <Grid item xs={4} md={2}><Typography variant="caption" color="text.secondary">HOLD</Typography><Typography variant="h6">{counts.HOLD || 0}</Typography></Grid>
              </Grid>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>Runtime and cycle counters remain zero until the explicit paper-bot start gate is enabled.</Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={5}>
            <Paper sx={{ p: 2.5, height: '100%' }}>
              <Typography variant="h6" gutterBottom>Evaluation Targets</Typography>
              <Typography variant="caption" color="text.secondary">Targets measure bot quality only. They never force BUY/SELL decisions.</Typography>
              <Stack spacing={1.2} sx={{ mt: 2 }}>
                {['daily', 'weekly', 'monthly'].map((period) => <TextField key={period} size="small" label={`${period[0].toUpperCase()}${period.slice(1)} target`} type="number" value={targetDraft[period]} onChange={(e) => setTargetDraft({ ...targetDraft, [period]: e.target.value })} InputProps={{ startAdornment: <Typography sx={{ mr: 1, color: 'text.secondary' }}>Rp</Typography> }} />)}
                <Button variant="outlined" onClick={saveTargets}>Save Targets</Button>
              </Stack>
              <Stack spacing={0.8} sx={{ mt: 2 }}>
                <Typography variant="caption">Daily progress: {targets.daily > 0 ? `${targetProgress(targets.daily).toFixed(0)}%` : 'not set'}</Typography>
                <LinearProgress variant="determinate" value={targetProgress(targets.daily)} />
              </Stack>
            </Paper>
          </Grid>
        </Grid>

        <Paper sx={{ p: 2.5, mb: 3 }}>
          <Typography variant="h6" gutterBottom>Paper Account</Typography>
          <Typography variant="body2" color="text.secondary">Currency: IDR · Initial validation balance: {formatIDR(10000000)} · Selected market: {currentPairLabel}</Typography>
          {decision && <Box sx={{ mt: 2 }}><Typography variant="subtitle2" color="text.secondary">Latest Decision</Typography><Typography variant="h4">{decision.action || 'HOLD'}</Typography><Typography variant="body2">Confidence: {((decision.confidence || 0) * 100).toFixed(1)}%</Typography><Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1 }}>{decision.votes && Object.entries(decision.votes).map(([agent, vote]) => <Chip key={agent} label={`${agent}: ${vote}`} size="small" />)}</Box></Box>}
        </Paper>

        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>Positions</Typography>
          {positions.length === 0 ? <Typography color="text.secondary">No active positions</Typography> : <Grid container spacing={2}>{positions.map((pos, index) => <Grid item xs={12} sm={6} md={4} key={index}><Card variant="outlined"><CardContent><Typography variant="h6">{pos.symbol}</Typography><Typography variant="body2">{pos.side} · {Number(pos.quantity || 0).toFixed(8)}</Typography><Typography variant="body2">Entry: {formatMarketPrice(pos.entry_price, 'IDR')}</Typography><Typography variant="body2" color={Number(pos.unrealized_pnl) >= 0 ? 'success.main' : 'error.main'}>PnL: {formatIDR(pos.unrealized_pnl)}</Typography></CardContent></Card></Grid>)}</Grid>}
        </Paper>

        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>AI Agents Status</Typography>
          <Grid container spacing={2}>{agents.map((agent, index) => <Grid item xs={12} sm={6} md={4} key={index}><Card variant="outlined"><CardContent><Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: agent.status === 'active' ? 'success.main' : 'text.disabled' }} /><Typography variant="subtitle1">{agent.name}</Typography></Box><Typography variant="body2" color="text.secondary">{agent.description}</Typography><Chip label={agent.status.toUpperCase()} size="small" sx={{ mt: 1 }} /></CardContent></Card></Grid>)}</Grid>
        </Paper>
      </Box>
    </Box>
  );
};

export default Dashboard;
