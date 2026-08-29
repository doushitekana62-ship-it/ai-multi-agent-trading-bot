import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Accordion, AccordionDetails, AccordionSummary, Box, Chip, CircularProgress, Divider, Grid, IconButton, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip, Typography } from '@mui/material';
import { ExpandMore, Refresh } from '@mui/icons-material';

const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);
const pct = (value, digits = 3) => Number.isFinite(Number(value)) ? `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(digits)}%` : '—';
const pretty = (value) => JSON.stringify(value ?? {}, null, 2);

const actionColor = (action) => action === 'BUY' ? 'success' : action === 'SELL' ? 'error' : 'default';

function JsonBlock({ value }) {
  return <Box component="pre" sx={{ m: 0, p: 1.5, borderRadius: 1.5, bgcolor: 'action.hover', overflow: 'auto', maxHeight: 320, fontSize: 11, lineHeight: 1.45 }}>{pretty(value)}</Box>;
}

export default function PaperHistoryLibrary() {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState([]);
  const [hasNext, setHasNext] = useState(false);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await axios.get('/api/dashboard/history', { params: { date, page, page_size: 10, _ts: Date.now() }, headers: { 'Cache-Control': 'no-cache' } });
      const data = response.data || {};
      setRows(Array.isArray(data.history) ? data.history : []);
      setHasNext(Boolean(data.has_next));
      setConnected(data.connected === true);
    } catch (err) {
      setRows([]);
      setHasNext(false);
      setConnected(false);
      setError(err.response?.data?.detail || 'Supabase paper history unavailable.');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [date, page]);

  return (
    <Paper sx={{ p: 2.5, mt: 3 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }} spacing={1}>
        <Box>
          <Typography variant="h6">Paper History Library</Typography>
          <Typography variant="caption" color="text.secondary">Supabase is the only source. Runtime/local observations are never substituted into this library.</Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" label={connected ? 'SUPABASE CONNECTED' : 'SUPABASE UNAVAILABLE'} color={connected ? 'success' : 'error'} />
          <Tooltip title="Refresh history"><IconButton onClick={load} disabled={loading}><Refresh /></IconButton></Tooltip>
          <input aria-label="History date" type="date" value={date} onChange={(e) => { setPage(1); setDate(e.target.value); }} />
        </Stack>
      </Stack>

      {error && <Typography color="error.main" sx={{ mt: 2 }}>{error}</Typography>}
      {loading && <Stack alignItems="center" sx={{ py: 4 }}><CircularProgress size={28} /></Stack>}
      {!loading && !error && rows.length === 0 && <Typography color="text.secondary" sx={{ py: 4 }}>No persisted cycles for this date.</Typography>}

      {!loading && rows.length > 0 && <Stack spacing={1} sx={{ mt: 2 }}>
        {rows.map((row) => {
          const action = String(row.action || 'HOLD').toUpperCase();
          const scores = row.market_scores || {};
          const votes = row.agent_votes || {};
          return (
            <Accordion key={row.id} disableGutters>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Grid container spacing={1} alignItems="center">
                  <Grid item xs={12} md={2}><Typography variant="caption">Cycle #{row.cycle_number ?? '—'}</Typography><Typography variant="body2" fontWeight={700}>{row.cycle_at ? new Date(row.cycle_at).toLocaleTimeString('id-ID') : '—'}</Typography></Grid>
                  <Grid item xs={6} md={1.2}><Chip size="small" label={action} color={actionColor(action)} /></Grid>
                  <Grid item xs={6} md={1.8}><Typography variant="caption" color="text.secondary">Price</Typography><Typography variant="body2">{idr(row.price)}</Typography></Grid>
                  <Grid item xs={6} md={1.4}><Typography variant="caption" color="text.secondary">30m</Typography><Typography variant="body2">{pct(row.move_30m_pct)}</Typography></Grid>
                  <Grid item xs={6} md={1.4}><Typography variant="caption" color="text.secondary">1m</Typography><Typography variant="body2">{pct(row.move_1m_pct)}</Typography></Grid>
                  <Grid item xs={6} md={1.4}><Typography variant="caption" color="text.secondary">Consensus</Typography><Typography variant="body2">{Number(row.consensus_score || 0).toFixed(3)}</Typography></Grid>
                  <Grid item xs={6} md={1.5}><Typography variant="caption" color="text.secondary">Votes</Typography><Typography variant="body2">{Object.keys(votes).length} agents</Typography></Grid>
                  <Grid item xs={12} md={1.7}><Chip size="small" label={row.pulse_status || 'GRAY'} /></Grid>
                </Grid>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" gutterBottom>Agent Votes</Typography>
                    <TableContainer><Table size="small"><TableHead><TableRow><TableCell>Agent</TableCell><TableCell>Vote</TableCell><TableCell>Score</TableCell></TableRow></TableHead><TableBody>{Object.entries(votes).map(([agent, vote]) => <TableRow key={agent}><TableCell>{agent}</TableCell><TableCell><Chip size="small" label={String(vote)} color={actionColor(String(vote).toUpperCase())} /></TableCell><TableCell>{Number(scores[agent] ?? scores[String(agent).toLowerCase().replace(/ agent$/i, '')] ?? 0).toFixed(3)}</TableCell></TableRow>)}</TableBody></Table></TableContainer>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" gutterBottom>Market Movement</Typography>
                    <Stack direction="row" spacing={2} flexWrap="wrap"><Typography variant="caption">1m {pct(row.move_1m_pct)}</Typography><Typography variant="caption">5m {pct(row.move_5m_pct)}</Typography><Typography variant="caption">15m {pct(row.move_15m_pct)}</Typography><Typography variant="caption">30m {pct(row.move_30m_pct)}</Typography></Stack>
                    <Divider sx={{ my: 1.5 }} />
                    <Typography variant="subtitle2" gutterBottom>Account Snapshot</Typography>
                    <Stack direction="row" spacing={2} flexWrap="wrap"><Typography variant="caption">Balance {idr(row.balance)}</Typography><Typography variant="caption">Equity {idr(row.portfolio_value)}</Typography><Typography variant="caption">Daily PnL {idr(row.daily_pnl)}</Typography><Typography variant="caption">Total PnL {idr(row.total_pnl)}</Typography></Stack>
                  </Grid>
                  <Grid item xs={12} md={4}><Typography variant="subtitle2" gutterBottom>Hold / Conflict Analysis</Typography><JsonBlock value={row.hold_analysis} /></Grid>
                  <Grid item xs={12} md={4}><Typography variant="subtitle2" gutterBottom>Execution Gate</Typography><JsonBlock value={row.execution_gate} /></Grid>
                  <Grid item xs={12} md={4}><Typography variant="subtitle2" gutterBottom>Confidence Components</Typography><JsonBlock value={row.confidence_components} /></Grid>
                  <Grid item xs={12} md={6}><Typography variant="subtitle2" gutterBottom>Agent Detail</Typography><JsonBlock value={row.agent_details} /></Grid>
                  <Grid item xs={12} md={6}><Typography variant="subtitle2" gutterBottom>30-Minute Pulse Segments</Typography><JsonBlock value={row.pulse_segments} /></Grid>
                  <Grid item xs={12}><Typography variant="subtitle2" gutterBottom>Market Snapshot</Typography><JsonBlock value={row.market_snapshot} /></Grid>
                  <Grid item xs={12}><Typography variant="subtitle2" gutterBottom>Reasoning</Typography><Typography variant="body2">{row.reasoning || '—'}</Typography></Grid>
                  <Grid item xs={12}><Typography variant="caption" color="text.secondary">cycle_id: {row.cycle_id || '—'} · decision_id: {row.decision_id || '—'} · trade_id: {row.trade_id || '—'} · persistence: {row.persistence_status || 'saved'} · source: {row.market_source || '—'}</Typography></Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>
          );
        })}
      </Stack>}

      <Stack direction="row" justifyContent="space-between" sx={{ mt: 2 }}>
        <Typography variant="caption" color="text.secondary">Page {page}</Typography>
        <Stack direction="row" spacing={1}><button type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button><button type="button" disabled={!hasNext || loading} onClick={() => setPage((value) => value + 1)}>Next</button></Stack>
      </Stack>
    </Paper>
  );
}
