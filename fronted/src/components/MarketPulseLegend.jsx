import React from 'react';
import { Box, Chip, Stack, Typography } from '@mui/material';

const items = [
  { color: 'success.main', label: 'GREEN / UP', meaning: 'Harga naik pada window 30 menit' },
  { color: 'error.main', label: 'RED / DOWN', meaning: 'Harga turun pada window 30 menit' },
  { color: 'text.secondary', label: 'GRAY / FLAT', meaning: 'Perubahan belum signifikan atau data belum cukup' },
];

export default function MarketPulseLegend() {
  return (
    <Box component="aside" aria-label="Market Pulse legend" sx={{ mt: 1.5, p: 1.25, borderRadius: 2, bgcolor: 'action.hover' }}>
      <Typography variant="caption" fontWeight={700} sx={{ display: 'block', mb: .8 }}>MARKET PULSE · ARTI SIMBOL</Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.2} flexWrap="wrap">
        {items.map((item) => <Stack key={item.label} direction="row" spacing={.6} alignItems="center"><Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: item.color }} /><Chip size="small" label={item.label} sx={{ height: 22 }} /><Typography variant="caption" color="text.secondary">{item.meaning}</Typography></Stack>)}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: .7 }}>24H High, 24H Low, dan 24H Volume tetap menjadi konteks pasar dan tidak di-reset oleh window 30 menit.</Typography>
    </Box>
  );
}
