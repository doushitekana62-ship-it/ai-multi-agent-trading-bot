import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Alert, Box, Button, Card, CardContent, Chip, Divider, FormControl, Grid, InputLabel, MenuItem, Select, Slider, Stack, Switch, TextField, Typography } from '@mui/material';

const PRESETS = {
  CONSERVATIVE: { stop_loss_mode: 'ATR', stop_atr_multiplier: 2.0, take_profit_mode: 'RISK_REWARD', risk_reward_ratio: 2.0, trailing_enabled: true, trailing_mode: 'ATR', trailing_atr_multiplier: 1.5, break_even_enabled: true, break_even_trigger_r: 1.0 },
  BALANCED: { stop_loss_mode: 'ATR', stop_atr_multiplier: 1.5, take_profit_mode: 'RISK_REWARD', risk_reward_ratio: 2.0, trailing_enabled: true, trailing_mode: 'ATR', trailing_atr_multiplier: 1.25, break_even_enabled: true, break_even_trigger_r: 1.0 },
  AGGRESSIVE: { stop_loss_mode: 'FIXED_PERCENT', stop_loss_pct: 0.6, take_profit_mode: 'FIXED_PERCENT', take_profit_pct: 1.2, trailing_enabled: true, trailing_mode: 'PERCENT', trailing_pct: 0.5, break_even_enabled: true, break_even_trigger_r: 0.8 },
};

const idrPct = (v) => `${Number(v || 0).toFixed(2)}%`;

export default function PaperRiskControls() {
  const [settings, setSettings] = useState(null);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const response = await axios.get('/api/dashboard/paper/risk', { params: { _ts: Date.now() }, headers: { 'Cache-Control': 'no-cache' } });
      const value = response.data?.risk_settings || {};
      setSettings(value);
      setDraft(value);
    } catch (err) {
      setError(err.response?.data?.detail || 'Risk settings unavailable.');
    }
  };

  useEffect(() => { load(); }, []);

  const update = (key, value) => setDraft((current) => ({ ...current, [key]: value }));
  const applyPreset = (name) => setDraft((current) => ({ ...current, ...PRESETS[name] }));

  const save = async () => {
    if (!draft) return;
    setSaving(true); setError(''); setMessage('');
    try {
      const response = await axios.post('/api/dashboard/paper/settings', { risk_settings: draft });
      const value = response.data?.risk_settings || draft;
      setSettings(value); setDraft(value); setMessage('Risk profile saved. It applies to new and open paper positions.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not save risk settings.');
    } finally { setSaving(false); }
  };

  if (!draft) return null;

  return <Card sx={{ mb: 3 }}>
    <CardContent>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }} spacing={1}>
        <Box><Typography variant="h6">AI Risk & Exit Profile</Typography><Typography variant="body2" color="text.secondary">The AI still decides direction. This layer controls how an open paper position is protected and closed.</Typography></Box>
        <Chip size="small" label={draft.enabled ? 'RISK ENGINE ON' : 'RISK ENGINE OFF'} color={draft.enabled ? 'success' : 'default'} />
      </Stack>
      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 2 }}>
        {Object.keys(PRESETS).map((name) => <Button key={name} size="small" variant="outlined" onClick={() => applyPreset(name)}>{name}</Button>)}
      </Stack>
      <Grid container spacing={2} sx={{ mt: 0.5 }}>
        <Grid item xs={12} md={3}><FormControl fullWidth size="small"><InputLabel>Stop Loss</InputLabel><Select value={draft.stop_loss_mode} label="Stop Loss" onChange={(e) => update('stop_loss_mode', e.target.value)}><MenuItem value="ATR">ATR adaptive</MenuItem><MenuItem value="FIXED_PERCENT">Fixed %</MenuItem></Select></FormControl></Grid>
        <Grid item xs={12} md={3}>{draft.stop_loss_mode === 'ATR' ? <Box sx={{ px: 1 }}><Typography variant="caption">Stop distance: {Number(draft.stop_atr_multiplier).toFixed(2)} × ATR</Typography><Slider value={Number(draft.stop_atr_multiplier)} min={0.5} max={4} step={0.1} valueLabelDisplay="auto" onChange={(_, v) => update('stop_atr_multiplier', v)} /></Box> : <TextField fullWidth size="small" label="Stop %" type="number" value={draft.stop_loss_pct} onChange={(e) => update('stop_loss_pct', Number(e.target.value))} />}</Grid>
        <Grid item xs={12} md={3}><FormControl fullWidth size="small"><InputLabel>Take Profit</InputLabel><Select value={draft.take_profit_mode} label="Take Profit" onChange={(e) => update('take_profit_mode', e.target.value)}><MenuItem value="RISK_REWARD">Risk / Reward</MenuItem><MenuItem value="ATR">ATR adaptive</MenuItem><MenuItem value="FIXED_PERCENT">Fixed %</MenuItem></Select></FormControl></Grid>
        <Grid item xs={12} md={3}>{draft.take_profit_mode === 'RISK_REWARD' ? <Box sx={{ px: 1 }}><Typography variant="caption">Reward: {Number(draft.risk_reward_ratio).toFixed(2)}R</Typography><Slider value={Number(draft.risk_reward_ratio)} min={1} max={5} step={0.25} valueLabelDisplay="auto" onChange={(_, v) => update('risk_reward_ratio', v)} /></Box> : draft.take_profit_mode === 'ATR' ? <Box sx={{ px: 1 }}><Typography variant="caption">TP distance: {Number(draft.take_profit_atr_multiplier).toFixed(2)} × ATR</Typography><Slider value={Number(draft.take_profit_atr_multiplier)} min={0.5} max={8} step={0.25} valueLabelDisplay="auto" onChange={(_, v) => update('take_profit_atr_multiplier', v)} /></Box> : <TextField fullWidth size="small" label="Take Profit %" type="number" value={draft.take_profit_pct} onChange={(e) => update('take_profit_pct', Number(e.target.value))} />}</Grid>
        <Grid item xs={12} md={4}><Stack direction="row" alignItems="center" justifyContent="space-between"><Box><Typography variant="body2" fontWeight={700}>Trailing stop</Typography><Typography variant="caption" color="text.secondary">Locks gains as price rises.</Typography></Box><Switch checked={Boolean(draft.trailing_enabled)} onChange={(e) => update('trailing_enabled', e.target.checked)} /></Stack></Grid>
        <Grid item xs={12} md={4}><Stack direction="row" alignItems="center" justifyContent="space-between"><Box><Typography variant="body2" fontWeight={700}>Break-even protection</Typography><Typography variant="caption" color="text.secondary">Moves protection above entry after profit.</Typography></Box><Switch checked={Boolean(draft.break_even_enabled)} onChange={(e) => update('break_even_enabled', e.target.checked)} /></Stack></Grid>
        <Grid item xs={12} md={4}><Stack direction="row" alignItems="center" justifyContent="space-between"><Box><Typography variant="body2" fontWeight={700}>Realistic execution friction</Typography><Typography variant="caption" color="text.secondary">Fee {idrPct(Number(draft.fee_rate) * 100)} · Slippage {Number(draft.slippage_bps).toFixed(1)} bps</Typography></Box><Switch checked disabled /></Stack></Grid>
      </Grid>
      <Divider sx={{ my: 2 }} />
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={2} alignItems={{ xs: 'stretch', sm: 'center' }}>
        <Typography variant="caption" color="text.secondary">Recommended starting point: BALANCED. ATR adapts protection to volatility instead of using one fixed distance.</Typography>
        <Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save risk profile'}</Button>
      </Stack>
      {message && <Alert severity="success" sx={{ mt: 2 }}>{message}</Alert>}
      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
    </CardContent>
  </Card>;
}
