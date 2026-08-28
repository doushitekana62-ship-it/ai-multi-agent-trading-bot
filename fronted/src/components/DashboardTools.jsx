import React, { useEffect, useState } from 'react';
import { Box, Chip, Grid, Paper, Stack, Typography } from '@mui/material';
import axios from 'axios';

function Indicator({ label, ok, value }) {
  return <Stack direction="row" justifyContent="space-between" alignItems="center"><Stack direction="row" spacing={1} alignItems="center"><Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: ok ? 'success.main' : 'error.main' }} /><Typography variant="body2">{label}</Typography></Stack><Typography variant="caption" fontWeight={700} color={ok ? 'success.main' : 'error.main'}>{value}</Typography></Stack>;
}

export default function DashboardTools() {
  const [health, setHealth] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = async () => { try { const response = await axios.get('/api/dashboard/status'); if (alive) setHealth(response.data?.system_health || null); } catch { if (alive) setHealth(null); } };
    load(); const timer = setInterval(load, 60000); return () => { alive = false; clearInterval(timer); };
  }, []);
  return <Grid container spacing={3}><Grid item xs={12}><Paper sx={{ p: 2.5 }}><Typography variant="h6">Runtime Diagnostics</Typography><Typography variant="caption" color="text.secondary">Read-only. This component never starts or intercepts trading actions.</Typography><Stack spacing={1.2} sx={{ mt: 2 }}><Indicator label="Database" ok={health?.database?.connected === true} value={health?.database?.connected ? 'CONNECTED' : 'UNKNOWN'} /><Indicator label="Market data" ok={health?.market_data?.fresh === true} value={health?.market_data?.fresh ? 'FRESH' : 'UNKNOWN'} /><Indicator label="Engine" ok={health?.engine?.running === true} value={health?.engine?.running ? 'RUNNING' : 'OFF'} /></Stack><Chip sx={{ mt: 2 }} size="small" label="No browser scheduler" /></Paper></Grid></Grid>;
}
