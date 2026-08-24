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
  Avatar,
  Divider,
} from '@mui/material';
import {
  AccountCircle,
  Logout,
  Refresh,
  TrendingUp,
  TrendingDown,
  ShowChart,
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
    } catch (error) {
      console.error('Error fetching data:', error);
      toast.error('Failed to fetch dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = async () => {
    handleMenuClose();
    await logout();
    navigate('/login');
  };

  const handleAnalyze = async () => {
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

  return (
    <Box sx={{ flexGrow: 1 }}>
      {/* App Bar */}
      <AppBar position="static">
        <Toolbar>
          <ShowChart sx={{ mr: 2 }} />
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            AI Trading Dashboard
          </Typography>
          <Button color="inherit" onClick={handleAnalyze} startIcon={<Refresh />}>
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
            anchorOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
            keepMounted
            transformOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
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
        {/* Loading */}
        {loading && <LinearProgress sx={{ mb: 2 }} />}

        {/* Status Cards */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Portfolio Value
                </Typography>
                <Typography variant="h5">
                  ${status?.portfolio_value?.toFixed(2) || '0.00'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Balance: ${status?.balance?.toFixed(2) || '0.00'}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Daily PnL
                </Typography>
                <Typography variant="h5" color={status?.daily_pnl >= 0 ? 'success.main' : 'error.main'}>
                  {(status?.daily_pnl * 100)?.toFixed(2) || '0.00'}%
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {status?.daily_trades || 0} trades today
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Active Positions
                </Typography>
                <Typography variant="h5">
                  {status?.active_positions || 0}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Max: {status?.max_open_positions || 5}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Total Trades
                </Typography>
                <Typography variant="h5">
                  {status?.total_trades || 0}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Win Rate: {performance?.win_rate ? (performance.win_rate * 100).toFixed(1) : '0'}%
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Latest Decision */}
        {decision && (
          <Paper sx={{ p: 3, mb: 3, bgcolor: 'primary.dark' }}>
            <Grid container alignItems="center" spacing={2}>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" color="text.secondary">
                  Latest Decision
                </Typography>
                <Typography variant="h4">
                  {decision.action || 'HOLD'}
                </Typography>
                <Typography variant="body2">
                  Confidence: {(decision.confidence * 100)?.toFixed(1) || '0'}%
                </Typography>
                <Typography variant="body2">
                  Position: {(decision.position_size * 100)?.toFixed(1) || '0'}%
                </Typography>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" color="text.secondary">
                  Agent Votes
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  {decision.votes && Object.entries(decision.votes).map(([agent, vote]) => (
                    <Chip
                      key={agent}
                      label={`${agent}: ${vote}`}
                      size="small"
                      color={
                        vote === 'BUY' || vote === 'STRONG_BUY' ? 'success' :
                        vote === 'SELL' || vote === 'STRONG_SELL' ? 'error' :
                        'default'
                      }
                    />
                  ))}
                </Box>
              </Grid>
            </Grid>
          </Paper>
        )}

        {/* Positions */}
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Positions
          </Typography>
          {positions.length === 0 ? (
            <Typography color="text.secondary">No active positions</Typography>
          ) : (
            <Grid container spacing={2}>
              {positions.map((pos, index) => (
                <Grid item xs={12} sm={6} md={4} key={index}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="h6">{pos.symbol}</Typography>
                      <Typography variant="body2">
                        {pos.side} - {pos.quantity.toFixed(4)}
                      </Typography>
                      <Typography variant="body2">
                        Entry: ${pos.entry_price.toFixed(2)}
                      </Typography>
                      <Typography variant="body2" color={pos.unrealized_pnl >= 0 ? 'success.main' : 'error.main'}>
                        PnL: ${pos.unrealized_pnl.toFixed(2)}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}
        </Paper>

        {/* Agents Status */}
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>
            AI Agents Status
          </Typography>
          <Grid container spacing={2}>
            {agents.map((agent, index) => (
              <Grid item xs={12} sm={6} md={4} key={index}>
                <Card variant="outlined">
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box
                        sx={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          bgcolor: agent.status === 'active' ? 'success.main' : 'error.main',
                        }}
                      />
                      <Typography variant="subtitle1">{agent.name}</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      {agent.description}
                    </Typography>
                    <Chip
                      label={agent.status}
                      size="small"
                      color={agent.status === 'active' ? 'success' : 'default'}
                      sx={{ mt: 1 }}
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Paper>
      </Box>
    </Box>
  );
};

export default Dashboard;
