import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Accordion, AccordionDetails, AccordionSummary, Box, Chip, CircularProgress, Divider, Grid, IconButton, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip, Typography } from '@mui/material';
import { ExpandMore, Refresh } from '@mui/icons-material';

const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);
const pct = (value, digits = 2) => Number.isFinite(Number(value)) ? `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(digits)}%` : '—';
const actionColor = (action) => action === 'BUY' ? 'success' : action === 'SELL' ? 'error' : 'default';
const exitLabel = (row) => row.risk_exit_reason || row.trade?.exit_reason || row.execution_result?.trade?.exit_reason || (row.action === 'SELL' ? 'AI EXIT' : '—');
const statusLabel = (row) => {
  const actual = String(row.execution_status || '').toUpperCase();
  if (actual === 'FILLED' || actual === 'APPROVED') return { text: 'EXECUTED', color: 'success' };
  if (actual.includes('ERROR')) return { text: 'ERROR', color: 'error' };
  if (row.action === 'HOLD') return { text: 'NO TRADE', color: 'default' };
  return { text: 'NOT EXECUTED', color: 'warning' };
};
const readableReason = (row) => {
  const exit = exitLabel(row);
  if (exit === 'TAKE_PROFIT') return 'Take profit reached';
  if (exit === 'STOP_LOSS') return 'Stop loss reached';
  if (exit === 'TRAILING_STOP') return 'Trailing stop protected profit';
  if (exit === 'BREAK_EVEN') return 'Break-even protection';
  if (exit === 'TIME_EXIT') return 'Maximum holding time reached';
  if (exit !== '—') return exit.replaceAll('_', ' ');
  const reason = row.risk_rejection_reason || row.execution_gate?.reason || row.hold_analysis?.reason;
  return String(reason || row.reasoning || 'No trade').replaceAll('_', ' ');
};

function Money({ label, value, color }) {
  return <Box><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={700} color={color}>{idr(value)}</Typography></Box>;
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
    setLoading(true); setError('');
    try {
      const response = await axios.get('/api/dashboard/history', { params: { date, page, page_size: 10, _ts: Date.now() }, headers: { 'Cache-Control': 'no-cache' } });
      const data = response.data || {};
      setRows(Array.isArray(data.history) ? data.history : []);
      setHasNext(Boolean(data.has_next));
      setConnected(data.connected === true);
    } catch (err) {
      setRows([]); setHasNext(false); setConnected(false); setError(err.response?.data?.detail || 'Supabase paper history unavailable.');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [date, page]);

  return <Paper sx={{ p: 2.5, mt: 3 }}>
    <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }} spacing={1}>
      <Box><Typography variant="h6">Paper History — Human View</Typography><Typography variant="caption" color="text.secondary">One row per AI cycle. Supabase remains the only persisted source.</Typography></Box>
      <Stack direction="row" spacing={1} alignItems="center"><Chip size="small" label={connected ? 'SUPABASE CONNECTED' : 'SUPABASE UNAVAILABLE'} color={connected ? 'success' : 'error'} /><Tooltip title="Refresh history"><IconButton onClick={load} disabled={loading}><Refresh /></IconButton></Tooltip><input aria-label="History date" type="date" value={date} onChange={(e) => { setPage(1); setDate(e.target.value); }} /></Stack>
    </Stack>

    {error && <Typography color="error.main" sx={{ mt: 2 }}>{error}</Typography>}
    {loading && <Stack alignItems="center" sx={{ py: 4 }}><CircularProgress size={28} /></Stack>}
    {!loading && !error && rows.length === 0 && <Typography color="text.secondary" sx={{ py: 4 }}>No persisted cycles for this date.</Typography>}

    {!loading && rows.length > 0 && <TableContainer sx={{ mt: 2 }}>
      <Table size="small" aria-label="human readable paper trading history">
        <TableHead><TableRow><TableCell>Time</TableCell><TableCell>AI</TableCell><TableCell>Execution</TableCell><TableCell>Price</TableCell><TableCell>30m</TableCell><TableCell>1m</TableCell><TableCell>PnL</TableCell><TableCell>Why</TableCell><TableCell /></TableRow></TableHead>
        <TableBody>{rows.map((row) => {
          const ai = String(row.candidate_action || row.raw_action || row.action || 'HOLD').toUpperCase();
          const actual = String(row.action || 'HOLD').toUpperCase();
          const status = statusLabel(row);
          const pnl = Number(row.realized_pnl ?? row.pnl ?? row.execution_result?.trade?.pnl ?? 0);
          return <React.Fragment key={row.id || row.cycle_id}>
            <TableRow hover>
              <TableCell><Typography variant="body2" fontWeight={700}>{row.cycle_at ? new Date(row.cycle_at).toLocaleTimeString('id-ID') : '—'}</Typography><Typography variant="caption" color="text.secondary">Cycle #{row.cycle_number ?? '—'}</Typography></TableCell>
              <TableCell><Stack direction="row" spacing={0.5}><Chip size="small" label={ai} color={actionColor(ai)} /><Typography variant="caption" sx={{ alignSelf: 'center' }}>{Number(row.confidence || 0).toFixed(0)}%</Typography></Stack></TableCell>
              <TableCell><Stack direction="row" spacing={0.5} alignItems="center"><Chip size="small" label={actual} color={actionColor(actual)} /><Chip size="small" label={status.text} color={status.color} variant="outlined" /></Stack></TableCell>
              <TableCell>{idr(row.price)}</TableCell>
              <TableCell>{pct(row.move_30m_pct)}</TableCell>
              <TableCell>{pct(row.move_1m_pct)}</TableCell>
              <TableCell><Typography color={pnl > 0 ? 'success.main' : pnl < 0 ? 'error.main' : 'text.secondary'} fontWeight={700}>{pnl === 0 ? '—' : idr(pnl)}</Typography></TableCell>
              <TableCell><Typography variant="body2">{readableReason(row)}</Typography></TableCell>
              <TableCell><AccordionSummary expandIcon={<ExpandMore />} sx={{ minHeight: 0, '& .MuiAccordionSummary-content': { m: 0 } }} /></TableCell>
            </TableRow>
            <TableRow><TableCell colSpan={9} sx={{ p: 0, border: 0 }}><Accordion disableGutters elevation={0} sx={{ bgcolor: 'transparent' }}><AccordionSummary sx={{ display: 'none' }} /><AccordionDetails sx={{ pt: 0, pb: 2, px: 2 }}>
              <Grid container spacing={2}>
                <Grid item xs={12} md={4}><Typography variant="subtitle2">Trade result</Typography><Stack direction="row" spacing={3} sx={{ mt: 1 }}><Money label="Realized PnL" value={row.realized_pnl ?? pnl} color={pnl > 0 ? 'success.main' : pnl < 0 ? 'error.main' : undefined} /><Money label="Fees" value={row.fees ?? row.execution_result?.trade?.fee} /></Stack></Grid>
                <Grid item xs={12} md={4}><Typography variant="subtitle2">Protection</Typography><Stack spacing={0.5} sx={{ mt: 1 }}><Typography variant="body2">Stop loss: {idr(row.stop_loss || row.execution_result?.trade?.stop_loss)}</Typography><Typography variant="body2">Take profit: {idr(row.take_profit || row.execution_result?.trade?.take_profit)}</Typography><Typography variant="body2">Exit reason: <b>{exitLabel(row).replaceAll('_', ' ')}</b></Typography></Stack></Grid>
                <Grid item xs={12} md={4}><Typography variant="subtitle2">Market context</Typography><Stack spacing={0.5} sx={{ mt: 1 }}><Typography variant="body2">Pulse: {row.pulse_status || 'GRAY'} · current {row.current_pulse_status || 'GRAY'}</Typography><Typography variant="body2">Consensus: {Number(row.consensus_score || 0).toFixed(3)} · source: {row.market_source || 'INDODAX public market data'}</Typography></Stack></Grid>
                <Grid item xs={12}><Divider sx={{ my: 1 }} /><Typography variant="subtitle2">AI explanation</Typography><Typography variant="body2" sx={{ mt: 0.5, lineHeight: 1.6 }}>{row.reasoning || '—'}</Typography></Grid>
                <Grid item xs={12} md={6}><Typography variant="subtitle2">Agent votes</Typography><Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1 }}>{Object.entries(row.agent_votes || {}).map(([agent, vote]) => <Chip key={agent} size="small" label={`${agent}: ${vote}`} />)}</Stack></Grid>
                <Grid item xs={12} md={6}><Typography variant="subtitle2">Forensic IDs</Typography><Typography variant="caption" color="text.secondary">cycle {row.cycle_id || '—'} · decision {row.decision_id || '—'} · trade {row.trade_id || '—'} · persistence {row.persistence_status || 'saved'}</Typography></Grid>
              </Grid>
            </AccordionDetails></Accordion></TableCell></TableRow>
          </React.Fragment>;
        })}</TableBody>
      </Table>
    </TableContainer>}

    <Stack direction="row" justifyContent="space-between" sx={{ mt: 2 }}><Typography variant="caption" color="text.secondary">Page {page}</Typography><Stack direction="row" spacing={1}><button type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button><button type="button" disabled={!hasNext || loading} onClick={() => setPage((value) => value + 1)}>Next</button></Stack></Stack>
  </Paper>;
}
