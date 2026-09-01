import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Box, Card, CardContent, Grid, Stack, Typography } from '@mui/material';

const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);

function Metric({ label, value, tone }) { return <Box><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h6" color={tone || 'text.primary'}>{value}</Typography></Box>; }

export default function PaperPerformanceSnapshot() {
  const [data, setData] = useState(null);
  const load = async () => { try { const response = await axios.get('/api/dashboard/performance', { params: { _ts: Date.now() }, headers: { 'Cache-Control': 'no-cache' } }); setData(response.data?.performance || null); } catch { setData(null); } };
  useEffect(() => { load(); const timer = setInterval(load, 15000); return () => clearInterval(timer); }, []);
  if (!data) return null;
  const pnl = Number(data.total_pnl || 0); const winRate = Number(data.win_rate || 0) * 100; const factor = data.profit_factor == null ? '—' : Number(data.profit_factor).toFixed(2);
  return <Card sx={{ mb: 3 }}><CardContent><Typography variant="h6">Performance Snapshot</Typography><Typography variant="caption" color="text.secondary">Realized results after simulated fees and slippage.</Typography><Grid container spacing={3} sx={{ mt: 0.5 }}><Grid item xs={6} sm={3} md={2}><Metric label="Closed trades" value={data.closed_trades ?? 0} /></Grid><Grid item xs={6} sm={3} md={2}><Metric label="Win rate" value={`${winRate.toFixed(1)}%`} /></Grid><Grid item xs={6} sm={3} md={2}><Metric label="Net PnL" value={idr(pnl)} tone={pnl > 0 ? 'success.main' : pnl < 0 ? 'error.main' : undefined} /></Grid><Grid item xs={6} sm={3} md={2}><Metric label="Profit factor" value={factor} /></Grid><Grid item xs={6} sm={3} md={2}><Metric label="Average win" value={idr(data.average_win)} tone="success.main" /></Grid><Grid item xs={6} sm={3} md={2}><Metric label="Average loss" value={idr(data.average_loss)} tone="error.main" /></Grid><Grid item xs={6} sm={3} md={2}><Metric label="Fees" value={idr(data.fees)} /></Grid><Grid item xs={6} sm={3} md={2}><Metric label="Open positions" value={data.open_positions ?? 0} /></Grid></Grid><Stack direction="row" spacing={2} sx={{ mt: 2 }}><Typography variant="caption" color="text.secondary">Gross profit {idr(data.gross_profit)}</Typography><Typography variant="caption" color="text.secondary">Gross loss {idr(data.gross_loss)}</Typography><Typography variant="caption" color="text.secondary">Wins {data.wins ?? 0} · Losses {data.losses ?? 0}</Typography></Stack></CardContent></Card>;
}
