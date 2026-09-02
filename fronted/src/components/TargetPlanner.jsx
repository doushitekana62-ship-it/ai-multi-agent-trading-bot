import React, { useMemo, useState } from 'react';
import { Box, Button, Divider, Grid, Paper, Stack, TextField, Typography } from '@mui/material';

const KEY = 'paperTargetPlanner:v1';
const num = (v, fallback = 0) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};
const idr = (v) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(num(v));

const defaults = {
  daily: '',
  weekly: '',
  monthly: '',
  entry: '',
  capital: '',
  tpPct: '1.00',
  slPct: '0.50',
  feePct: '0.0111',
  quantity: '',
};

function loadSaved() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
    return { ...defaults, ...(saved && typeof saved === 'object' ? saved : {}) };
  } catch {
    return defaults;
  }
}

export default function TargetPlanner({ dailyActual = 0 }) {
  const [values, setValues] = useState(loadSaved);
  const set = (key) => (event) => setValues((current) => ({ ...current, [key]: event.target.value }));

  const save = () => {
    try { localStorage.setItem(KEY, JSON.stringify(values)); } catch { /* browser storage unavailable */ }
  };
  const reset = () => {
    setValues(defaults);
    try { localStorage.removeItem(KEY); } catch { /* ignore */ }
  };

  const calc = useMemo(() => {
    const entry = num(values.entry);
    const capital = num(values.capital);
    const tpPct = num(values.tpPct);
    const slPct = num(values.slPct);
    const feePct = Math.max(0, num(values.feePct));
    const explicitQty = num(values.quantity);
    const qty = explicitQty > 0 ? explicitQty : (entry > 0 && capital > 0 ? capital / entry : 0);
    const tpPrice = entry > 0 ? entry * (1 + tpPct / 100) : 0;
    const slPrice = entry > 0 ? entry * (1 - slPct / 100) : 0;
    const grossTp = entry > 0 && qty > 0 ? (tpPrice - entry) * qty : 0;
    const grossSl = entry > 0 && qty > 0 ? (entry - slPrice) * qty : 0;
    const roundTripFee = entry > 0 && qty > 0 ? entry * qty * (feePct / 100) * 2 : 0;
    const netTp = grossTp - roundTripFee;
    const netSl = grossSl + roundTripFee;
    const rr = slPct > 0 ? tpPct / slPct : 0;
    return { entry, qty, tpPrice, slPrice, grossTp, grossSl, roundTripFee, netTp, netSl, rr };
  }, [values]);

  const daily = num(values.daily);
  const dailyProgress = daily > 0 ? Math.min(100, Math.max(0, num(dailyActual) / daily * 100)) : 0;

  return <Paper sx={{ p: 2.5, height: '100%' }}>
    <Typography variant="h6">Target & TP / SL Planner</Typography>
    <Typography variant="caption" color="text.secondary">Simulasi pribadi di browser. Tidak dikirim ke server dan tidak memengaruhi risk engine, sizing, scheduler, atau execution.</Typography>

    <Typography variant="subtitle2" sx={{ mt: 2 }}>Target pribadi</Typography>
    <Grid container spacing={1.2} sx={{ mt: .1 }}>
      {['daily', 'weekly', 'monthly'].map((period) => <Grid item xs={12} sm={4} key={period}>
        <TextField fullWidth size="small" label={`${period.toUpperCase()} target`} value={values[period]} onChange={set(period)} type="number" inputProps={{ min: 0, step: 1000 }} InputProps={{ startAdornment: <Typography variant="caption" sx={{ mr: .5 }}>Rp</Typography> }} />
      </Grid>)}
    </Grid>
    <Box sx={{ mt: 1.2 }}>
      <Stack direction="row" justifyContent="space-between"><Typography variant="caption">Daily progress</Typography><Typography variant="caption">{daily > 0 ? `${dailyProgress.toFixed(1)}% · ${idr(dailyActual)} / ${idr(daily)}` : 'not set'}</Typography></Stack>
    </Box>

    <Divider sx={{ my: 2 }} />
    <Typography variant="subtitle2">TP / SL calculator</Typography>
    <Grid container spacing={1.2} sx={{ mt: .1 }}>
      <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Entry price" value={values.entry} onChange={set('entry')} type="number" inputProps={{ min: 0, step: 1 }} /></Grid>
      <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Capital / position" value={values.capital} onChange={set('capital')} type="number" inputProps={{ min: 0, step: 1000 }} /></Grid>
      <Grid item xs={4}><TextField fullWidth size="small" label="TP %" value={values.tpPct} onChange={set('tpPct')} type="number" inputProps={{ step: .05, min: 0 }} /></Grid>
      <Grid item xs={4}><TextField fullWidth size="small" label="SL %" value={values.slPct} onChange={set('slPct')} type="number" inputProps={{ step: .05, min: 0 }} /></Grid>
      <Grid item xs={4}><TextField fullWidth size="small" label="Fee % / side" value={values.feePct} onChange={set('feePct')} type="number" inputProps={{ step: .001, min: 0 }} /></Grid>
      <Grid item xs={12}><TextField fullWidth size="small" label="Quantity (optional; blank = capital / entry)" value={values.quantity} onChange={set('quantity')} type="number" inputProps={{ min: 0, step: .00000001 }} /></Grid>
    </Grid>

    <Grid container spacing={1.2} sx={{ mt: 1 }}>
      <Grid item xs={6}><Box sx={{ p: 1.2, border: 1, borderColor: 'success.main', borderRadius: 1 }}><Typography variant="caption" color="text.secondary">TP price</Typography><Typography fontWeight={700}>{calc.tpPrice > 0 ? idr(calc.tpPrice) : '—'}</Typography><Typography variant="caption" color="success.main">Gross +{idr(calc.grossTp)} · Net +{idr(calc.netTp)}</Typography></Box></Grid>
      <Grid item xs={6}><Box sx={{ p: 1.2, border: 1, borderColor: 'error.main', borderRadius: 1 }}><Typography variant="caption" color="text.secondary">SL price</Typography><Typography fontWeight={700}>{calc.slPrice > 0 ? idr(calc.slPrice) : '—'}</Typography><Typography variant="caption" color="error.main">Gross -{idr(calc.grossSl)} · Net -{idr(calc.netSl)}</Typography></Box></Grid>
    </Grid>
    <Stack direction="row" justifyContent="space-between" sx={{ mt: 1 }}>
      <Typography variant="caption" color="text.secondary">Quantity: {calc.qty > 0 ? calc.qty.toFixed(8) : '—'}</Typography>
      <Typography variant="caption" color="text.secondary">TP/SL ratio: {calc.rr > 0 ? `${calc.rr.toFixed(2)}R` : '—'} · Round-trip fee: {idr(calc.roundTripFee)}</Typography>
    </Stack>
    <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
      <Button size="small" variant="contained" onClick={save}>Save in browser</Button>
      <Button size="small" variant="outlined" onClick={reset}>Clear</Button>
    </Stack>
  </Paper>;
}
