import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container, Box, Typography, TextField, Button, Paper, Alert, Stack, Avatar,
} from '@mui/material';
import {
  ShowChart, Psychology, QueryStats, Gavel, AutoAwesome, TrendingUp,
} from '@mui/icons-material';
import { useAuth } from '../context/AuthContext';

const agents = [
  { name: 'Sentiment', icon: Psychology },
  { name: 'Technical', icon: ShowChart },
  { name: 'Decision', icon: Gavel },
  { name: 'Forecast', icon: QueryStats },
  { name: 'Reflector', icon: AutoAwesome },
];

const Login = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        px: 2,
        py: 5,
        position: 'relative',
        overflow: 'hidden',
        background: (theme) => theme.palette.mode === 'dark'
          ? 'radial-gradient(circle at 15% 20%, rgba(0,212,167,.13), transparent 32%), radial-gradient(circle at 85% 80%, rgba(77,171,247,.10), transparent 30%), #080b0d'
          : 'radial-gradient(circle at 15% 20%, rgba(0,121,107,.10), transparent 32%), radial-gradient(circle at 85% 80%, rgba(21,101,192,.08), transparent 30%), #f3f6f8',
      }}
    >
      <Container component="main" maxWidth="sm">
        <Paper
          elevation={0}
          sx={{
            p: { xs: 3, sm: 5 },
            borderRadius: 4,
            position: 'relative',
            overflow: 'hidden',
            '&:before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: 3,
              background: 'linear-gradient(90deg, #00d4a7, #4dabf7, #00d4a7)',
            },
          }}
        >
          <Stack spacing={2.5} alignItems="center">
            <Avatar
              sx={{
                width: 68,
                height: 68,
                bgcolor: 'primary.main',
                color: '#06110f',
                boxShadow: '0 0 32px rgba(0,212,167,.28)',
              }}
            >
              <ShowChart sx={{ fontSize: 38 }} />
            </Avatar>

            <Box sx={{ textAlign: 'center' }}>
              <Typography component="h1" variant="h4" sx={{ fontWeight: 800 }}>
                AI Trading Bot
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                Multi-agent market analysis dashboard
              </Typography>
            </Box>

            <Box sx={{ width: '100%' }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                AI CORE
              </Typography>
              <Stack direction="row" spacing={1} sx={{ overflowX: 'auto', pb: 0.5 }}>
                {agents.map(({ name, icon: Icon }) => (
                  <Box
                    key={name}
                    sx={{
                      minWidth: 88,
                      flex: 1,
                      px: 1,
                      py: 1.2,
                      textAlign: 'center',
                      borderRadius: 2,
                      bgcolor: 'action.hover',
                      border: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Icon sx={{ color: 'primary.main', fontSize: 21, mb: 0.4 }} />
                    <Typography variant="caption" sx={{ display: 'block', fontWeight: 700 }}>
                      {name}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </Box>

            {error && <Alert severity="error" sx={{ width: '100%' }}>{error}</Alert>}

            <form onSubmit={handleSubmit} style={{ width: '100%' }}>
              <Stack spacing={1.5}>
                <TextField
                  required fullWidth id="username" label="Username" name="username"
                  autoComplete="username" autoFocus value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
                <TextField
                  required fullWidth name="password" label="Password" type="password"
                  id="password" autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <Button
                  type="submit" fullWidth variant="contained" size="large"
                  startIcon={<TrendingUp />} disabled={loading}
                  sx={{ mt: 1, py: 1.35 }}
                >
                  {loading ? 'Logging in...' : 'Enter Dashboard'}
                </Button>
              </Stack>
            </form>

            <Typography variant="caption" color="text.secondary" sx={{ textAlign: 'center' }}>
              Secure access · Trading remains OFF until explicitly enabled
            </Typography>
          </Stack>
        </Paper>
      </Container>
    </Box>
  );
};

export default Login;
