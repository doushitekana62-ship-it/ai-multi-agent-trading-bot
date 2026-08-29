import React from 'react';
import { Box, Chip, Paper, Stack, Typography } from '@mui/material';

const items = [
  { color: 'success.main', label: 'GREEN', meaning: 'Harga naik pada window 30 menit' },
  { color: 'error.main', label: 'RED', meaning: 'Harga turun pada window 30 menit' },
  { color: 'text.secondary', label: 'GRAY', meaning: 'Harga flat / perubahan belum signifikan' },
];

export default function MarketPulseLegend() {
  return (
    <Paper
      component="aside"
      aria-label="Market Pulse legend"
      sx={{
        position: 'fixed',
        left: 18,
        bottom: 18,
        zIndex: 1390,
        p: 1.5,
        width: { xs: 'calc(100vw - 36px)', sm: 360 },
        maxWidth: 'calc(100vw - 36px)',
        backdropFilter: 'blur(10px)',
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, fontWeight: 700 }}>
        MARKET PULSE · ARTI TANDA
      </Typography>
      <Stack spacing={0.7}>
        {items.map((item) => (
          <Stack key={item.label} direction="row" spacing={1} alignItems="center">
            <Box sx={{ width: 9, height: 9, borderRadius: '50%', bgcolor: item.color, flex: '0 0 auto' }} />
            <Chip size="small" label={item.label} sx={{ minWidth: 58, height: 22 }} />
            <Typography variant="caption" color="text.secondary">{item.meaning}</Typography>
          </Stack>
        ))}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
        24H High, 24H Low, dan 24H Volume tetap menjadi konteks pasar dan tidak di-reset oleh window 30 menit.
      </Typography>
    </Paper>
  );
}
