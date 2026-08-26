import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Grid, Paper, Typography, Button, Card, CardContent,
  LinearProgress, Chip, IconButton, AppBar, Toolbar, Menu,
  MenuItem, Divider, ToggleButton, ToggleButtonGroup, Alert,
} from '@mui/material';
import { AccountCircle, Logout, Refresh, ShowChart, LockOutlined } from '@mui/icons-material';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import toast from 'react-hot-toast';

const formatIDR = (value) => new Intl.NumberFormat('id-ID', {
  style: 'currency', currency: 'IDR', maximumFractionDigits: 0,
}).format(Number(value) || 0);

const formatPrice = (value) => formatIDR(value);

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
  const [botEnabled] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statusRes, positionsRes, performanceRes, decisionRes, agentsRes] = await Promise.all([
        axios.get('/api/dashboard/status'),
        axios.get('/api/dashboard/positions'),
        axios.get('/api/dashboard/performance'),
        axios.get('/api/dashboard/recent-decision'),
        axios.get('/api/dashboard/agents'),
      ]);
      setStatus(statusRes.data);
      setPositions(positionsRes.data.positions || []);
      setPerformance(performanceRes.data.performance || null);
      setDecision(decisionRes.data.decision || null);
      setAgents(agentsRes.data.agents || []);
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
  }, []);

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
      const response = await axios.post('/api/dashboard/analyze', null, { params: { symbol: 'BTC-IDR' } });
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
      toast('Real Trading is not connected and remains locked.');
      return;
    }
    if (newMode) setTradingMode(newMode);
  };

  return (
    <Box sx={{ flexGrow: 1, minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="static">
        <Toolbar>
          <ShowChart sx={{ mr: 2 }} />
          <Typography variant="h6" sx={{ flexGrow: 1 }}>AI Trading Dashboard</Typography>
          <Chip label={botEnabled ? 'BOT ON' : 'BOT OFF'} color={botEnabled ? 'success' : 'default'} size="small" sx={{ mr: 2, fontWeight: 700 }} />
          <Button color="inherit" onClick={handleAnalyze} startIcon={<Refresh />} disabled={!botEnabled || tradingMode !== 'paper'}>Analyze</Button>
          <IconButton size="large" edge="end" color="inherit" onClick={(e) => setAnchorEl(e.currentTarget)}>
            <AccountCircle />
          </IconButton>
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
            <Grid item xs={12} md={7}>
              <Typography variant="overline" color="text.secondary">Trading Environment</Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, mb: 0.5 }}>
                {tradingMode === 'paper' ? 'Paper Trading' : 'Real Trading'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Paper Trading is the active validation environment. Real Trading is visible for future use only and is not connected to any exchange.
              </Typography>
            </Grid>
            <Grid item xs={12} md={5} sx={{ display: 'flex', justifyContent: { xs: 'flex-start', md: 'flex-end' } }}>
              <ToggleButtonGroup value={tradingMode} exclusive onChange={handleModeChange}>
                <ToggleButton value="paper">PAPER</ToggleButton>
                <ToggleButton value="real" disabled><LockOutlined sx={{ mr: 0.75, fontSize: 18 }} />REAL</ToggleButton>
              </ToggleButtonGroup>
            </Grid>
          </Grid>
          <Alert severity="info" sx={{ mt: 2 }}>
            Safety mode: BOT OFF by default. Selecting, refreshing, or viewing this dashboard never starts an AI trading cycle.
          </Alert>
        </Paper>

        <Paper sx={{ p: 2.5, mb: 3 }}>
          <Grid container alignItems="center" spacing={2}>
            <Grid item xs={12} md={8}>
              <Typography variant="h6">Paper Trading Control</Typography>
              <Typography variant="body2" color="text.secondary">
                Current state: <strong>OFF</strong>. The trading engine remains disconnected from dashboard requests until the persistent safety gate is implemented.
              </Typography>
            </Grid>
            <Grid item xs={12} md={4} sx={{ display: 'flex', justifyContent: { xs: 'flex-start', md: 'flex-end' } }}>
              <Button variant="contained" disabled>START PAPER BOT</Button>
            </Grid>
          </Grid>
        </Paper>

        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card><CardContent>
              <Typography color="text.secondary" gutterBottom>Portfolio Value</Typography>
              <Typography variant="h5">{formatIDR(status?.portfolio_value)}</Typography>
              <Typography variant="body2" color="text.secondary">Balance: {formatIDR(status?.balance)}</Typography>
            </CardContent></Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card><CardContent>
              <Typography color="text.secondary" gutterBottom>Daily PnL</Typography>
              <Typography variant="h5" color={Number(status?.daily_pnl) >= 0 ? 'success.main' : 'error.main'}>
                {formatIDR((status?.daily_pnl || 0) * (status?.balance || 0))}
              </Typography>
              <Typography variant="body2" color="text.secondary">{status?.daily_trades || 0} trades today</Typography>
            </CardContent></Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card><CardContent>
              <Typography color="text.secondary" gutterBottom>Active Positions</Typography>
              <Typography variant="h5">{status?.active_positions || 0}</Typography>
              <Typography variant="body2" color="text.secondary">Max: {status?.max_open_positions || 5}</Typography>
            </CardContent></Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card><CardContent>
              <Typography color="text.secondary" gutterBottom>Total Trades</Typography>
              <Typography variant="h5">{status?.total_trades || 0}</Typography>
              <Typography variant="body2" color="text.secondary">Win Rate: {((performance?.win_rate || 0) * 100).toFixed(1)}%</Typography>
            </CardContent></Card>
          </Grid>
        </Grid>

        <Paper sx={{ p: 2.5, mb: 3 }}>
          <Typography variant="h6" gutterBottom>Paper Account</Typography>
          <Typography variant="body2" color="text.secondary">
            Currency: IDR · Initial validation balance: {formatIDR(10000000)} · Market convention: BTC-IDR
          </Typography>
          {decision && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle2" color="text.secondary">Latest Decision</Typography>
              <Typography variant="h4">{decision.action || 'HOLD'}</Typography>
              <Typography variant="body2">Confidence: {((decision.confidence || 0) * 100).toFixed(1)}%</Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1 }}>
                {decision.votes && Object.entries(decision.votes).map(([agent, vote]) => (
                  <Chip key={agent} label={`${agent}: ${vote}`} size="small" />
                ))}
              </Box>
            </Box>
          )}
        </Paper>

        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>Positions</Typography>
          {positions.length === 0 ? <Typography color="text.secondary">No active positions</Typography> : (
            <Grid container spacing={2}>{positions.map((pos, index) => (
              <Grid item xs={12} sm={6} md={4} key={index}>
                <Card variant="outlined"><CardContent>
                  <Typography variant="h6">{pos.symbol}</Typography>
                  <Typography variant="body2">{pos.side} · {Number(pos.quantity || 0).toFixed(8)}</Typography>
                  <Typography variant="body2">Entry: {formatPrice(pos.entry_price)}</Typography>
                  <Typography variant="body2" color={Number(pos.unrealized_pnl) >= 0 ? 'success.main' : 'error.main'}>PnL: {formatIDR(pos.unrealized_pnl)}</Typography>
                </CardContent></Card>
              </Grid>
            ))}</Grid>
          )}
        </Paper>

        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>AI Agents Status</Typography>
          <Grid container spacing={2}>
            {agents.map((agent, index) => (
              <Grid item xs={12} sm={6} md={4} key={index}>
                <Card variant="outlined"><CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: agent.status === 'active' ? 'success.main' : 'text.disabled' }} />
                    <Typography variant="subtitle1">{agent.name}</Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary">{agent.description}</Typography>
                  <Chip label={agent.status.toUpperCase()} size="small" sx={{ mt: 1 }} />
                </CardContent></Card>
              </Grid>
            ))}
          </Grid>
        </Paper>
      </Box>
    </Box>
  );
};

export default Dashboard;
