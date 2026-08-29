import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Toaster } from 'react-hot-toast';
import { Box, IconButton, Tooltip } from '@mui/material';
import { DarkMode, LightMode } from '@mui/icons-material';

import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Reports from './pages/Reports';
import CycleUpdateToast from './components/CycleUpdateToast';
import TradingLibraryAlertToast from './components/TradingLibraryAlertToast';
import { AuthProvider, useAuth } from './context/AuthContext';

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <div>Loading...</div>;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
};

function App() {
  const [mode, setMode] = useState(() => localStorage.getItem('dashboardTheme') || 'dark');

  const toggleMode = () => {
    const next = mode === 'dark' ? 'light' : 'dark';
    setMode(next);
    localStorage.setItem('dashboardTheme', next);
  };

  const theme = createTheme({
    palette: {
      mode,
      primary: { main: mode === 'dark' ? '#00d4a7' : '#00796b' },
      secondary: { main: mode === 'dark' ? '#4dabf7' : '#1565c0' },
      success: { main: '#35c759' },
      error: { main: '#ff5c5c' },
      background: mode === 'dark'
        ? { default: '#080b0d', paper: '#151a1d' }
        : { default: '#f3f6f8', paper: '#ffffff' },
    },
    typography: {
      fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
      h5: { fontWeight: 700, letterSpacing: '-0.02em' },
      h6: { fontWeight: 700 },
    },
    shape: { borderRadius: 12 },
    components: {
      MuiAppBar: {
        styleOverrides: {
          root: {
            background: mode === 'dark'
              ? 'linear-gradient(90deg, #10171a 0%, #14211f 55%, #10171a 100%)'
              : 'linear-gradient(90deg, #ffffff 0%, #edf7f5 55%, #ffffff 100%)',
            color: mode === 'dark' ? '#f5f7f8' : '#172024',
            borderBottom: '1px solid',
            borderColor: mode === 'dark' ? 'rgba(0,212,167,.18)' : 'rgba(0,121,107,.15)',
            boxShadow: mode === 'dark' ? '0 8px 30px rgba(0,0,0,.28)' : '0 6px 22px rgba(35,60,70,.08)',
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            border: '1px solid',
            borderColor: mode === 'dark' ? 'rgba(255,255,255,.07)' : 'rgba(20,50,60,.10)',
            backgroundImage: 'none',
            boxShadow: mode === 'dark' ? '0 10px 30px rgba(0,0,0,.18)' : '0 8px 28px rgba(20,50,60,.07)',
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            border: '1px solid',
            borderColor: mode === 'dark' ? 'rgba(255,255,255,.07)' : 'rgba(20,50,60,.10)',
            backgroundImage: 'none',
            transition: 'transform .18s ease, box-shadow .18s ease, border-color .18s ease',
            '&:hover': {
              transform: 'translateY(-2px)',
              boxShadow: mode === 'dark' ? '0 12px 28px rgba(0,0,0,.25)' : '0 12px 28px rgba(20,50,60,.10)',
              borderColor: mode === 'dark' ? 'rgba(0,212,167,.30)' : 'rgba(0,121,107,.25)',
            },
          },
        },
      },
      MuiButton: { styleOverrides: { root: { borderRadius: 9, textTransform: 'none', fontWeight: 700 } } },
      MuiToggleButton: { styleOverrides: { root: { borderRadius: 8, textTransform: 'none', fontWeight: 700 } } },
    },
  });

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <Router>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
          </Routes>
          <CycleUpdateToast />
          <TradingLibraryAlertToast />
          <Box sx={{ position: 'fixed', right: 18, bottom: 18, zIndex: 1400 }}>
            <Tooltip title={mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
              <IconButton
                onClick={toggleMode}
                aria-label="toggle dashboard theme"
                sx={{
                  width: 46,
                  height: 46,
                  color: 'primary.main',
                  bgcolor: 'background.paper',
                  border: '1px solid',
                  borderColor: 'divider',
                  boxShadow: 4,
                  '&:hover': { bgcolor: 'action.hover' },
                }}
              >
                {mode === 'dark' ? <LightMode /> : <DarkMode />}
              </IconButton>
            </Tooltip>
          </Box>
        </Router>
        <Toaster
          position="top-right"
          toastOptions={{ style: { background: mode === 'dark' ? '#151a1d' : '#ffffff', color: mode === 'dark' ? '#ffffff' : '#172024' } }}
        />
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
