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
import PaperHistoryLibrary from './components/PaperHistoryLibrary';
import PaperRiskControls from './components/PaperRiskControls';
import PaperPerformanceSnapshot from './components/PaperPerformanceSnapshot';
import { AuthProvider, useAuth } from './context/AuthContext';

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <div>Loading...</div>;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
};

function DashboardLanding() {
  return <><Dashboard /><Box sx={{ px: { xs: 1.5, md: 3 }, pb: 4, maxWidth: 1800, mx: 'auto' }}><PaperPerformanceSnapshot /><PaperRiskControls /><PaperHistoryLibrary /></Box></>;
}

function App() {
  const [mode, setMode] = useState(() => localStorage.getItem('dashboardTheme') || 'dark');
  const toggleMode = () => { const next = mode === 'dark' ? 'light' : 'dark'; setMode(next); localStorage.setItem('dashboardTheme', next); };
  const theme = createTheme({
    palette: { mode, primary: { main: mode === 'dark' ? '#22d3a7' : '#087f6a' }, secondary: { main: mode === 'dark' ? '#7c9cff' : '#536dfe' }, success: { main: mode === 'dark' ? '#3ddc97' : '#16a36a' }, error: { main: mode === 'dark' ? '#ff6b7a' : '#d6455d' }, warning: { main: mode === 'dark' ? '#f4b860' : '#b66b00' }, background: mode === 'dark' ? { default: '#0b1117', paper: '#121c24' } : { default: '#eef3f6', paper: '#f9fbfc' }, text: mode === 'dark' ? { primary: '#e8f0f3', secondary: '#91a5ae' } : { primary: '#17242b', secondary: '#60737c' }, divider: mode === 'dark' ? 'rgba(159, 189, 201, .12)' : 'rgba(38, 64, 74, .12)' },
    typography: { fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif', h5: { fontWeight: 700, letterSpacing: '-0.02em' }, h6: { fontWeight: 700 } },
    shape: { borderRadius: 12 },
  });
  return <ThemeProvider theme={theme}><CssBaseline /><AuthProvider><Router basename={import.meta.env.BASE_URL}><Routes><Route path="/login" element={<Login />} /><Route path="/" element={<ProtectedRoute><DashboardLanding /></ProtectedRoute>} /><Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} /><Route path="*" element={<Navigate to="/" replace />} /></Routes><CycleUpdateToast /><TradingLibraryAlertToast /><Box sx={{ position: 'fixed', right: 18, bottom: 18, zIndex: 1400 }}><Tooltip title={mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}><IconButton onClick={toggleMode} aria-label="toggle dashboard theme" sx={{ width: 46, height: 46, color: 'primary.main', bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', boxShadow: 4, '&:hover': { bgcolor: 'action.hover' } }}>{mode === 'dark' ? <LightMode /> : <DarkMode />}</IconButton></Tooltip></Box></Router><Toaster position="top-right" /></AuthProvider></ThemeProvider>;
}

export default App;
