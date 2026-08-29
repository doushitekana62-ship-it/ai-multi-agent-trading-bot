import React from 'react';
import { Box, Chip, GlobalStyles, Stack, Typography } from '@mui/material';

const items = [
  { bg: 'success.main', label: 'GREEN / UP', meaning: 'Harga naik pada window 30 menit' },
  { bg: 'error.main', label: 'RED / DOWN', meaning: 'Harga turun pada window 30 menit' },
  { bg: 'text.secondary', label: 'GRAY / FLAT', meaning: 'Perubahan belum signifikan atau data belum cukup' },
];

export default function MarketPulseLegend() {
  return (
    <>
      <GlobalStyles styles={{
        '[aria-label="recent market price chart"]': { display: 'none !important' },
        '.MuiBox-root:has(> [aria-label="recent market price chart"])': { display: 'none !important' },
      }} />
      <Box component="aside" aria-label="Market Pulse status legend" sx={{ mt: 1.5, p: 1.5, borderRadius: 2.5, bgcolor: 'action.hover' }}>
        <Typography variant="caption" fontWeight={700} sx={{ display: 'block', mb: 1 }}>MARKET PULSE · STATUS 30 MENIT</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          {items.map((item) => (
            <Box key={item.label} sx={{ flex: 1, minWidth: 0, p: 1.1, borderRadius: 2, bgcolor: item.bg, color: item.label === 'GRAY / FLAT' ? 'text.primary' : 'common.white' }}>
              <Stack direction="row" spacing={.7} alignItems="center">
                <Chip size="small" label={item.label} sx={{ height: 22, bgcolor: 'rgba(255,255,255,.2)', color: 'inherit', fontWeight: 700 }} />
              </Stack>
              <Typography variant="caption" sx={{ display: 'block', mt: .6, color: 'inherit', opacity: .95 }}>{item.meaning}</Typography>
            </Box>
          ))}
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>24H High, 24H Low, dan 24H Volume tetap menjadi konteks pasar dan tidak di-reset oleh window 30 menit.</Typography>
      </Box>
    </>
  );
}
