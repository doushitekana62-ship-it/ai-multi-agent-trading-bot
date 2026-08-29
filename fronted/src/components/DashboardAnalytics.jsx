import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Chip, Divider, FormControl, Grid, InputLabel, MenuItem, Select, Stack, Typography } from '@mui/material';
import { Radar, Doughnut } from 'react-chartjs-2';
import { Chart as ChartJS, ArcElement, RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend } from 'chart.js';
import axios from 'axios';

ChartJS.register(ArcElement, RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

const idr = (value) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value) || 0);
const pct = (value) => `${(Number(value) || 0).toFixed(1)}%`;
const safeArray = (value) => Array.isArray(value) ? value.filter(Boolean) : [];
const VOLUME_COLORS = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2', '#db2777', '#65a30d', '#ea580c', '#475569'];

function ConflictAnalyzer({ decision }) {
  const analysis = decision?.analysis || decision?.hold_analysis || {};
  const votes = decision?.votes || analysis.votes || {};
  const scores = decision?.market_scores || analysis.market_scores || {};
  const holdAgents = safeArray(analysis.hold_agents || decision?.hold_agents);
  const opposingAgents = safeArray(analysis.opposing_agents || decision?.opposing_agents);
  const entries = Object.entries(votes);
  const directional = entries.filter(([, v]) => ['BUY', 'SELL', 'STRONG_BUY', 'STRONG_SELL'].includes(String(v).toUpperCase()));
  const blockers = holdAgents.length ? holdAgents : entries.filter(([, v]) => String(v).toUpperCase() === 'HOLD').map(([name]) => name);
  const action = String(decision?.action || decision?.final_action || 'HOLD').toUpperCase();
  const conflict = (directional.length > 0 && blockers.length > 0) || opposingAgents.length > 0;
  const dominant = blockers.length ? blockers[0] : opposingAgents[0] || 'None';
  return <Card variant="outlined" sx={{ height: '100%' }}><CardContent><Stack direction="row" justifyContent="space-between" alignItems="center"><Box><Typography variant="h6">Conflict Analyzer</Typography><Typography variant="caption" color="text.secondary">Why agents agree, HOLD, or oppose the candidate.</Typography></Box><Chip size="small" label={conflict ? 'CONFLICT' : 'ALIGNED'} color={conflict ? 'warning' : 'success'} /></Stack><Stack spacing={1.2} sx={{ mt: 2 }}><Stack direction="row" justifyContent="space-between"><Typography variant="body2">Final action</Typography><Chip size="small" label={action} color={action === 'BUY' ? 'success' : action === 'SELL' ? 'error' : 'default'} /></Stack><Stack direction="row" justifyContent="space-between"><Typography variant="body2">Directional agents</Typography><Typography fontWeight={700}>{directional.length}</Typography></Stack><Stack direction="row" justifyContent="space-between"><Typography variant="body2">HOLD blockers</Typography><Typography fontWeight={700}>{blockers.length}</Typography></Stack><Stack direction="row" justifyContent="space-between"><Typography variant="body2">Opposing agents</Typography><Typography fontWeight={700}>{opposingAgents.length}</Typography></Stack><Divider /><Typography variant="caption" color="text.secondary">Dominant blocker</Typography><Typography variant="body2" fontWeight={700}>{dominant}</Typography><Typography variant="caption" color="text.secondary">Score map: technical {Number(scores.technical || 0).toFixed(2)} · decision {Number(scores.decision || 0).toFixed(2)} · forecast {Number(scores.forecast || 0).toFixed(2)} · sentiment {Number(scores.sentiment || 0).toFixed(2)}</Typography></Stack></CardContent></Card>;
}

function ScalpingRadar({ insights }) {
  const ranked = safeArray(insights).slice(0, 12);
  const labels = ranked.length ? ranked.map((item) => item.pair) : ['No scanner data'];
  const dataValues = ranked.length ? ranked.map((item) => { const range = Number(item.range_position); const volume = Number(item.volume_idr); const volumeBoost = volume > 0 ? Math.min(25, Math.log10(volume) * 2) : 0; const rangeScore = Number.isFinite(range) ? 100 - Math.abs(50 - range) : 50; return Math.max(0, Math.min(100, rangeScore * 0.75 + volumeBoost)); }) : [0];
  const data = { labels, datasets: [{ label: 'Scalping opportunity score', data: dataValues, fill: true, borderWidth: 2, pointRadius: 3 }] };
  const options = { responsive: true, maintainAspectRatio: false, scales: { r: { min: 0, max: 100, ticks: { stepSize: 25 } } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (context) => `${context.label}: ${Number(context.raw || 0).toFixed(1)} / 100` } } } };
  return <Card variant="outlined" sx={{ height: '100%' }}><CardContent><Typography variant="h6">INDODAX Scalping Radar</Typography><Typography variant="caption" color="text.secondary">Read-only ranking from public IDR market data. Higher score means better market context, not an order signal.</Typography><Box sx={{ height: 300, mt: 1 }}>{ranked.length ? <Radar data={data} options={options} /> : <Box sx={{ height: '100%', display: 'grid', placeItems: 'center', color: 'text.secondary' }}>Scanner data unavailable.</Box>}</Box></CardContent></Card>;
}

function VolumeShare({ insights }) {
  const rows = safeArray(insights).filter((item) => Number(item.volume_idr) > 0).slice(0, 10);
  const total = rows.reduce((sum, item) => sum + Number(item.volume_idr || 0), 0);
  const data = { labels: rows.length ? rows.map((item) => item.pair) : ['No data'], datasets: [{ data: rows.length ? rows.map((item) => Number(item.volume_idr || 0)) : [1], backgroundColor: rows.length ? rows.map((_, index) => VOLUME_COLORS[index % VOLUME_COLORS.length]) : ['#94a3b8'], borderColor: '#ffffff', borderWidth: 2, hoverOffset: 8 }] };
  const options = { responsive: true, maintainAspectRatio: false, cutout: '58%', interaction: { intersect: false }, plugins: { legend: { position: 'right', labels: { usePointStyle: true, padding: 12 } }, tooltip: { enabled: true, callbacks: { title: (items) => items[0]?.label || '', label: (context) => { const value = Number(context.raw || 0); return `${idr(value)} · ${total ? pct(value / total * 100) : '0.0%'}`; }, afterLabel: () => 'Volume share of displayed scanner markets' } } } };
  return <Card variant="outlined" sx={{ height: '100%' }}><CardContent><Stack direction="row" justifyContent="space-between" alignItems="center"><Box><Typography variant="h6">Volume Share</Typography><Typography variant="caption" color="text.secondary">Hover a slice for pair, IDR volume, and percentage.</Typography></Box>{rows.length > 0 && <Chip size="small" label={`${rows.length} markets`} />}</Stack><Box sx={{ height: 300, mt: 1 }}>{rows.length ? <Doughnut data={data} options={options} /> : <Box sx={{ height: '100%', display: 'grid', placeItems: 'center', color: 'text.secondary' }}>No volume data.</Box>}</Box></CardContent></Card>;
}

function ScannerList({ insights, selectedPair, onPairChange }) {
  const [filter, setFilter] = useState('ALL');
  const filtered = useMemo(() => safeArray(insights).filter((item) => filter === 'HIGH' ? item.signal === 'NEAR 24H HIGH' : filter === 'LOW' ? item.signal === 'NEAR 24H LOW' : filter === 'MID' ? item.signal === 'MID 24H RANGE' : true), [insights, filter]);
  const supported = safeArray(insights).filter((item) => item?.scalping_supported !== false);
  return <Card variant="outlined"><CardContent><Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1} alignItems={{ xs: 'stretch', md: 'center' }}><Box><Typography variant="h6">Market Scanner</Typography><Typography variant="caption" color="text.secondary">Showing {filtered.length} available markets; no five-row hard cap.</Typography></Box><Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}><FormControl size="small" sx={{ minWidth: 150 }}><InputLabel>Scanner filter</InputLabel><Select value={filter} label="Scanner filter" onChange={(e) => setFilter(e.target.value)}><MenuItem value="ALL">All markets</MenuItem><MenuItem value="HIGH">Near 24H High</MenuItem><MenuItem value="LOW">Near 24H Low</MenuItem><MenuItem value="MID">Mid 24H Range</MenuItem></Select></FormControl><FormControl size="small" sx={{ minWidth: 170 }}><InputLabel>Scalping coin</InputLabel><Select value={selectedPair} label="Scalping coin" onChange={(e) => onPairChange(e.target.value)}>{supported.map((item) => <MenuItem key={item.pair} value={String(item.pair).toLowerCase().replace('/', '_')}>{item.pair}</MenuItem>)}</Select></FormControl></Stack></Stack><Box sx={{ maxHeight: 430, overflowY: 'auto', mt: 2, pr: .5 }}><Grid container spacing={1}>{filtered.map((item) => <Grid item xs={12} sm={6} md={4} key={item.pair}><Card variant="outlined" sx={{ height: '100%' }}><CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}><Stack direction="row" justifyContent="space-between" alignItems="center"><Box><Typography variant="body2" fontWeight={700}>{item.pair}</Typography><Typography variant="caption" color="text.secondary">{idr(item.last)} · Vol {idr(item.volume_idr)}</Typography></Box><Chip size="small" label={item.signal} color={item.signal === 'NEAR 24H HIGH' ? 'success' : item.signal === 'NEAR 24H LOW' ? 'error' : 'default'} /></Stack></CardContent></Card></Grid>)}</Grid>{!filtered.length && <Typography sx={{ py: 3 }} color="text.secondary">No markets match this filter.</Typography>}</Box></CardContent></Card>;
}

function PaperHistoryLibrary() {
  const [page, setPage] = useState(0);
  const [date, setDate] = useState('');
  const [rows, setRows] = useState([]);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = async (nextPage = page) => { setLoading(true); setError(''); try { const params = { page: nextPage + 1, page_size: 10, _ts: Date.now() }; if (date) params.date = date; const response = await axios.get('/api/dashboard/history', { params, headers: { 'Cache-Control': 'no-cache' }, timeout: 8000 }); const payload = response.data || {}; setRows(safeArray(payload.history)); setHasNext(payload.has_next === true); setPage(nextPage); } catch (err) { setRows([]); setHasNext(false); setError(err.response?.data?.detail || 'Paper history library unavailable.'); } finally { setLoading(false); } };
  useEffect(() => { setPage(0); load(0); }, [date]);
  const next = () => { if (hasNext && !loading) load(page + 1); };
  const previous = () => { if (page > 0 && !loading) load(page - 1); };
  return <Card variant="outlined"><CardContent><Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'stretch', md: 'center' }} spacing={1}><Box><Typography variant="h6">Paper History Library</Typography><Typography variant="caption" color="text.secondary">10 history cycles per page. Previous/Next browses the Supabase-backed history without changing paper-trading state.</Typography></Box><Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap"><input aria-label="history date" type="date" value={date} onChange={(e) => setDate(e.target.value)} style={{ padding: 8, borderRadius: 8, border: '1px solid #bbb' }} /><Button size="small" variant="outlined" onClick={previous} disabled={loading || page === 0}>Previous</Button><Chip size="small" label={`Page ${page + 1}`} /><Button size="small" variant="outlined" onClick={next} disabled={loading || !hasNext}>Next</Button></Stack></Stack>{error && <Alert severity="warning" sx={{ mt: 2 }}>{error}</Alert>}<Box sx={{ overflowX: 'auto', mt: 2 }}><table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}><thead><tr>{['Time','Pair','Action','Confidence','Price','Daily PnL','Positions','Engine'].map((h) => <th key={h} style={{ textAlign: 'left', padding: 9, borderBottom: '1px solid rgba(127,127,127,.25)' }}>{h}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.id || `${row.cycle_at}-${row.pair}`}><td style={{ padding: 9 }}>{row.cycle_at ? new Date(row.cycle_at).toLocaleString('id-ID') : '—'}</td><td style={{ padding: 9 }}>{row.pair || '—'}</td><td style={{ padding: 9 }}><Chip size="small" label={row.action || 'HOLD'} color={row.action === 'BUY' ? 'success' : row.action === 'SELL' ? 'error' : 'default'} /></td><td style={{ padding: 9 }}>{pct(row.confidence)}</td><td style={{ padding: 9 }}>{idr(row.price)}</td><td style={{ padding: 9 }}>{idr(row.daily_pnl)}</td><td style={{ padding: 9 }}>{row.active_positions ?? 0}</td><td style={{ padding: 9 }}>{row.engine_source || '—'}</td></tr>)}</tbody></table>{!loading && !rows.length && <Typography sx={{ py: 3 }} color="text.secondary">No paper history found for this page/filter.</Typography>}</Box>{loading && <Typography variant="caption" color="text.secondary">Loading paper history…</Typography>}</CardContent></Card>;
}

export default function DashboardAnalytics({ decision, insights, selectedPair, onPairChange }) {
  return <Stack spacing={3} sx={{ mb: 3 }}><Grid container spacing={3}><Grid item xs={12} md={5}><ConflictAnalyzer decision={decision} /></Grid><Grid item xs={12} md={7}><ScalpingRadar insights={insights} /></Grid></Grid><Grid container spacing={3}><Grid item xs={12} md={5}><VolumeShare insights={insights} /></Grid><Grid item xs={12} md={7}><ScannerList insights={insights} selectedPair={selectedPair} onPairChange={onPairChange} /></Grid></Grid><PaperHistoryLibrary /></Stack>;
}
