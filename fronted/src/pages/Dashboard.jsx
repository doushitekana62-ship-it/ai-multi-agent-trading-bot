import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Grid,
  Paper,
  Typography,
  Button,
  Card,
  CardContent,
  LinearProgress,
  Chip,
  IconButton,
  AppBar,
  Toolbar,
  Menu,
  MenuItem,
  Divider,
  ToggleButton,
  ToggleButtonGroup,
  Alert,
} from '@mui/material';
import {
  AccountCircle,
  Logout,
  Refresh,
  ShowChart,
  LockOutlined,
} from '@mui/icons-material';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import toast from 'react-hot-toast';

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

  // Paper trading is the only selectable mode during the validation phase.
  // Real trading is intentionally visible but locked and has no API connection.
  const [tradingMode, setTradingMode] = useState('paper');
  const [botEnabled, setBotEnabled] = useState(false);

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
      setPerformance(performanceRes.data.performance);
      setDecision(decisionRes.data.decision);
      setAgents(agentsRes.data.agents || []);

      // Never infer that the bot is running from dashboard data.
      // Until the explicit start/stop API is implemented, the UI remains OFF.
      setBotEnabled(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      toast.error('Failed to fetch dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleMenuOpen = (event) => setAnchorEl(event.currentTarget);
  const handleMenuClose = () => setAnchorEl(null);

  const handleLogout = async () => {
    handleMenuClose();
    await logout();
    navigate('/login');
  };

  const handleAnalyze = async () => {
    // Safety gate: manual analysis is disabled until an explicit bot-start
    // control is implemented. Opening the dashboard must never start work.
    if (!botEnabled || tradingMode !== 'paper') {
      toast('Paper trading is OFF. No AI cycle was started.');
      return;
    }

    try {
      toast.loading('Analyzing...');
      const response = await axios.post('/api/dashboard/analyze', null, {
        params: { symbol: 'BTC-USD' },
      });
      toast.dismiss();
      toast.success('Analysis complete!');
      setDecision(response.data);
      fetchData();
    } catch (error) {
      toast.dismiss();
      toast.error('Analysis failed');
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
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            AI Trading Dashboard
          </Typography>

          <Chip
            label={botEnabled ? 'BOT ON' : 'BOT OFF'}
            color={botEnabled ? 'success' : 'default'}
            size="small"
            sx={{ mr: 2, fontWeight: 700 }}
          />

          <Button
            color="inherit"
            onClick={handleAnalyze}
            startIcon={<Refresh />}
            disabled={!botEnabled || tradingMode !== 'paper'}
          >
            Analyze
          </Button>

          <IconButton
            size="large"
            edge="end"
            aria-label="account"
            aria-controls="menu-appbar"
            aria-haspopup="true"
            onClick={handleMenuOpen}
            color="inherit"
          >
            <AccountCircle />
          </IconButton>
          <Menu
            id="menu-appbar"
            anchorEl={anchorEl}
            anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
            keepMounted
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            open={Boolean(anchorEl)}
            onClose={handleMenuClose}
          >
            <MenuItem disabled>
              <Typography variant="body2">{user?.username || 'Admin'}</Typography>
            </MenuItem>
            <Divider />
            <MenuItem onClick={() => { handleMenuClose(); navigate('/reports'); }}>
              Reports
            </MenuItem>
            <MenuItem onClick={handleLogout}>
              <Logout sx={{ mr: 1 }} fontSize="small" />
              Logout
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>

      <Box sx={{ p: 3 }}>
        {loading && <LinearProgress sx={{ mb: 2 }} />}

        {/* Explicit environment separation. Real mode is visual-only for now. */}
        <Paper sx={{ p: 2.5, mb: 3, border: '1px solid', borderColor: 'divider' }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={7}>
              <Typography variant="overline" color="text.secondary">
                Trading Environment
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, mb: 0.5 }}>
                {tradingMode === 'paper' ? 'Paper Trading' : 'Real Trading'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Paper Trading is the active validation environment. Real Trading is visible for future use only and is not connected to any exchange.
              </Typography>
            </Grid>
            <Grid item xs={12} md={5} sx={{ display: 'flex', justifyContent: { xs: 'flex-start', md: 'flex-end' } }}>
              <ToggleButtonGroup
                value={tradingMode}
                exclusive
                onChange={handleModeChange}
                aria-label="trading environment"
              >
                <ToggleButton value="paper" aria-label="paper trading">
                  Paper
                </ToggleButton>
                <ToggleButton value="real" aria-label="real trading" disabled>
                  <LockOutlined sx={{ mr: 0.75, fontSize: 18 }} />
                  Real
                </ToggleButton>
              </ToggleButtonGroup>
            </Grid>
          </Grid>
          <Alert severity="info" sx={{ mt: 2 }}>
            Safety mode: BOT OFF by default. Selecting or viewing this dashboard never starts an AI trading cycle.
          </Alert>
        </Paper>

        {/* Explicit bot control placeholder. Start/Stop API is intentionally not connected yet. */}
        <Paper sx={{ p: 2.5, mb: 3 }}>
          <Grid container alignItems="center" spacing={2}>
            <Grid item xs={12} md={8}>
              <Typography variant="h6">Paper Trading Control</Typography>
              <Typography variant="body2" color="text.secondary">
                Current state: <strong>OFF</strong>. The START trigger will be connected only after the dashboard API safety gate is verified.
              </Typography>
            </Grid>
            <Grid item xs={12} md={4} sx={{ display: 'flex', justifyContent: { xs: 'flex-start', md: 'flex-end' } }}>
              <Button variant="contained" disabled>
                START PAPER BOT
              </Button>
            </Grid>
          </Grid>
        </Paper>

        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card><CardContent>
              <Typography color="text.secondary" gutterBottom>Portfolio Value</Typography>
              <Typography variant="h5">${status?.portfolio_value?.toFixed(2) || '0.00'}</Typography>
              <Typography variant="body2" color="text.secondary">Balance: ${status?.balance?.toFixed(2) || '0.00'}</Typography>
            </CardContent></Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card><CardContent>
              <Typography color="text.secondary" gutterBottom>Daily PnL</Typography>
              <Typography variant="h5" color={status?.daily_pnl >= 0 ? 'success.main' : 'error.main'}>
                {Number.isFinite(status?.daily_pnl) ? `${(status.daily_pnl * 100).toFixed(2)}%` : '—'}
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
              <Typography variant="body2" color="text.secondary">Win Rate: {performance?.win_rate ? (performance.win_rate * 100).toFixed(1) : '0'}%</Typography>
            </CardContent></Card>
          </Grid>
        </Grid>

        {decision && (
          <Paper sx={{ p: 3, mb: 3, bgcolor: 'primary.dark' }}>
            <Grid container alignItems="center" spacing={2}>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" color="text.secondary">Latest Decision</Typography>
                <Typography variant="h4">{decision.action || 'HOLD'}</Typography>
                <Typography variant="body2">Confidence: {(decision.confidence * 100)?.toFixed(1) || '0'}%</Typography>
                <Typography variant="body2">Position: {(decision.position_size * 100)?.toFixed(1) || '0'}%</Typography>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" color="text.secondary">Agent Votes</Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  {decision.votes && Object.entries(decision.votes).map(([agent, vote]) => (
                    <Chip key={agent} label={`${agent}: ${vote}`} size="small" color={vote === 'BUY' || vote === 'STRONG_BUY' ? 'success' : vote === 'SELL' || vote === 'STRONG_SELL' ? 'error' : 'default'} />
                  ))}
                </Box>
              </Grid>
            </Grid>
          </Paper>
        )}

        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>Positions</Typography>
          {positions.length === 0 ? <Typography color="text.secondary">No active positions</Typography> : (
            <Grid container spacing={2}>
              {positions.map((pos, index) => (
                <Grid item xs={12} sm={6} md={4} key={index}>
                  <Card variant="outlined"><CardContent>
                    <Typography variant="h6">{pos.symbol}</Typography>
                    <Typography variant="body2">{pos.side} - {pos.quantity.toFixed(4)}</Typography>
                    <Typography variant="body2">Entry: ${pos.entry_price.toFixed(2)}</Typography>
                    <Typography variant="body2" color={pos.unrealized_pnl >= 0 ? 'success.main' : 'error.main'}>PnL: ${pos.unrealized_pnl.toFixed(2)}</Typography>
                  </CardContent></Card>
                </Grid>
              ))}
            </Grid>
          )}
        </Paper>

        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>AI Agents Status</Typography>
          <Grid container spacing={2}>
            {agents.map((agent, index) => (
              <Grid item xs={12} sm={6} md={4} key={index}>
                <Card variant="outlined"><CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: agent.status === 'active' ? 'success.main' : 'error.main' }} />
                    <Typography variant="subtitle1">{agent.name}</Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary">{agent.description}</Typography>
                  <Chip label={agent.status} size="small" color={agent.status === 'active' ? 'success' : 'default'} sx={{ mt: 1 }} />
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
