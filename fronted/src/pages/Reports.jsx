import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppBar, Box, Button, ButtonGroup, Card, CardContent, Chip, Grid, IconButton, LinearProgress, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Toolbar, Typography } from '@mui/material';
import { AccountCircle, ArrowBack, Assessment, Logout } from '@mui/icons-material';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAuth } from '../context/AuthContext';

const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);
const PERIODS = ['daily', 'weekly', 'monthly', 'all-time'];

export default function Reports() {
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const [period, setPeriod] = useState('daily');
  const [report, setReport] = useState(null);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [performanceResponse, tradesResponse] = await Promise.all([
        axios.get('/api/dashboard/performance', { params: { _ts: Date.now() } }),
        axios.get('/api/dashboard/trades', { params: { limit: 500, _ts: Date.now() } }),
      ]);
      setReport(performanceResponse.data?.performance || null);
      setTrades(tradesResponse.data?.trades || []);
    } catch (error) {
      console.error('Reports load failed:', error);
      toast.error(error.response?.data?.detail || 'Reports unavailable');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [period]);
  const completed = useMemo(() => trades.filter((x) => String(x.action || x.side).toUpperCase() === 'SELL'), [trades]);
  const shownTrades = useMemo(() => {
    if (period === 'all-time') return completed;
    const days = period === 'daily' ? 1 : period === 'weekly' ? 7 : 30;
    const cutoff = Date.now() - days * 86400000;
    return completed.filter((x) => {
      const stamp = Date.parse(x.created_at || x.exit_time || '');
      return Number.isFinite(stamp) && stamp >= cutoff;
    });
  }, [completed, period]);

  const derived = useMemo(() => {
    const pnls = shownTrades.map((x) => Number(x.pnl) || 0);
    const wins = pnls.filter((x) => x > 0);
    const losses = pnls.filter((x) => x < 0);
    const grossProfit = wins.reduce((a, b) => a + b, 0);
    const grossLoss = Math.abs(losses.reduce((a, b) => a + b, 0));
    const total = pnls.reduce((a, b) => a + b, 0);
    return { total_trades: pnls.length, winning_trades: wins.length, losing_trades: losses.length, win_rate: pnls.length ? wins.length / pnls.length : 0, total_pnl: total, profit_factor: grossLoss ? grossProfit / grossLoss : null, max_profit: pnls.length ? Math.max(...pnls) : 0, max_loss: pnls.length ? Math.min(...pnls) : 0 };
  }, [shownTrades]);
  const metrics = shownTrades.length ? derived : (report || derived);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="static"><Toolbar><IconButton color="inherit" onClick={() => navigate('/')}><ArrowBack /></IconButton><Assessment sx={{ mx: 1.5 }} /><Typography variant="h6" sx={{ flexGrow: 1 }}>Performance Reports</Typography><AccountCircle sx={{ mr: 1 }} /><Typography variant="body2" sx={{ mr: 2 }}>{user?.username || 'Admin'}</Typography><IconButton color="inherit" onClick={async () => { await logout(); navigate('/login'); }}><Logout /></IconButton></Toolbar></AppBar>
      <Box sx={{ p: { xs: 1.5, md: 3 } }}>
        {loading && <LinearProgress sx={{ mb: 2 }} />}
        <Paper sx={{ p: 2, mb: 3 }}><Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}><Typography variant="h6">Paper Trading Audit</Typography><ButtonGroup size="small">{PERIODS.map((p) => <Button key={p} variant={period === p ? 'contained' : 'outlined'} onClick={() => setPeriod(p)}>{p === 'all-time' ? 'All Time' : p[0].toUpperCase() + p.slice(1)}</Button>)}</ButtonGroup></Stack></Paper>
        <Grid container spacing={3} sx={{ mb: 3 }}>
          {[['Completed Trades', metrics.total_trades || 0], ['Win Rate', `${((Number(metrics.win_rate) || 0) * 100).toFixed(1)}%`], ['Total PnL', idr(metrics.total_pnl)], ['Profit Factor', metrics.profit_factor == null ? '—' : Number(metrics.profit_factor).toFixed(2)]].map(([label, value]) => <Grid item xs={12} sm={6} md={3} key={label}><Card><CardContent><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h5" sx={{ mt: .5 }}>{value}</Typography></CardContent></Card></Grid>)}
        </Grid>
        <Paper sx={{ p: 2.5, mb: 3 }}><Typography variant="h6">Metrics</Typography><Grid container spacing={2} sx={{ mt: .5 }}><Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">Wins</Typography><Typography>{metrics.winning_trades || 0}</Typography></Grid><Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">Losses</Typography><Typography>{metrics.losing_trades || 0}</Typography></Grid><Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">Best</Typography><Typography color="success.main">{idr(metrics.max_profit)}</Typography></Grid><Grid item xs={6} md={3}><Typography variant="caption" color="text.secondary">Worst</Typography><Typography color="error.main">{idr(metrics.max_loss)}</Typography></Grid></Grid></Paper>
        <Paper sx={{ p: 2.5 }}><Typography variant="h6" gutterBottom>Trade History</Typography>{shownTrades.length === 0 ? <Typography color="text.secondary">No completed paper trades in this period.</Typography> : <TableContainer><Table size="small"><TableHead><TableRow><TableCell>Symbol</TableCell><TableCell>Side</TableCell><TableCell>Price</TableCell><TableCell>Quantity</TableCell><TableCell>PnL</TableCell><TableCell>Status</TableCell><TableCell>Time</TableCell></TableRow></TableHead><TableBody>{shownTrades.slice(-50).reverse().map((trade, i) => <TableRow key={`${trade.created_at || ''}-${i}`}><TableCell>{trade.symbol}</TableCell><TableCell><Chip size="small" label={trade.side || trade.action} color="error" /></TableCell><TableCell>{idr(trade.price || trade.exit_price)}</TableCell><TableCell>{Number(trade.quantity || 0).toFixed(8)}</TableCell><TableCell sx={{ color: Number(trade.pnl) >= 0 ? 'success.main' : 'error.main', fontWeight: 700 }}>{idr(trade.pnl)}</TableCell><TableCell>{trade.status || 'CLOSED'}</TableCell><TableCell>{trade.created_at ? new Date(trade.created_at).toLocaleString('id-ID') : '—'}</TableCell></TableRow>)}</TableBody></Table></TableContainer>}</Paper>
      </Box>
    </Box>
  );
}
