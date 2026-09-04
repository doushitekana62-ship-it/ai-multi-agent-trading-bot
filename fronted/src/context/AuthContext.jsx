import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';

const AuthContext = createContext();
const DEFAULT_API_URL = 'https://ai-multi-agent-trading-bot-7ba9bcfc.fastapicloud.dev';
const API_URL = String(import.meta.env.VITE_API_URL || DEFAULT_API_URL).trim().replace(/\/$/, '');
axios.defaults.baseURL = API_URL;
axios.defaults.headers.common.Accept = 'application/json';

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [refreshToken, setRefreshToken] = useState(localStorage.getItem('refresh_token'));
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const applyAccessToken = (accessToken) => {
    setToken(accessToken);
    localStorage.setItem('token', accessToken);
    axios.defaults.headers.common.Authorization = `Bearer ${accessToken}`;
  };

  const clearSession = () => {
    setToken(null); setRefreshToken(null); setUser(null); setIsAuthenticated(false);
    localStorage.removeItem('token'); localStorage.removeItem('refresh_token');
    delete axios.defaults.headers.common.Authorization;
  };

  useEffect(() => {
    if (token) axios.defaults.headers.common.Authorization = `Bearer ${token}`;
    else delete axios.defaults.headers.common.Authorization;
  }, [token]);

  const refreshAccessToken = async () => {
    const stored = refreshToken || localStorage.getItem('refresh_token');
    if (!stored) return false;
    try {
      const response = await axios.post('/api/auth/refresh', { refresh_token: stored });
      if (!response.data?.access_token) return null;
      applyAccessToken(response.data.access_token);
      return true;
    } catch (error) {
      if (error.response?.status === 401) { clearSession(); return false; }
      return null;
    }
  };

  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      (response) => response,
      async (error) => {
        const original = error.config;
        const stored = localStorage.getItem('refresh_token');
        if (error.response?.status !== 401 || !original || original._retry || original.url?.includes('/api/auth/login') || original.url?.includes('/api/auth/refresh') || !stored) return Promise.reject(error);
        original._retry = true;
        try {
          const response = await axios.post('/api/auth/refresh', { refresh_token: stored });
          if (!response.data?.access_token) return Promise.reject(error);
          applyAccessToken(response.data.access_token);
          original.headers = original.headers || {};
          original.headers.Authorization = `Bearer ${response.data.access_token}`;
          return axios(original);
        } catch (refreshError) {
          if (refreshError.response?.status === 401) clearSession();
          return Promise.reject(refreshError);
        }
      }
    );
    return () => axios.interceptors.response.eject(interceptor);
  }, []);

  const login = async (username, password) => {
    try {
      const response = await axios.post('/api/auth/login', {
        username: String(username || '').trim(),
        password: String(password || ''),
      });
      applyAccessToken(response.data.access_token);
      setRefreshToken(response.data.refresh_token);
      localStorage.setItem('refresh_token', response.data.refresh_token);
      setUser({ username: response.data.username });
      setIsAuthenticated(true);
      toast.success('Login successful!');
      return response.data;
    } catch (error) {
      const statusCode = error.response?.status;
      const detail = error.response?.data?.detail;
      if (!error.response) toast.error('API tidak dapat dihubungi. Periksa koneksi atau deployment FastAPI.');
      else if (statusCode === 401) toast.error('Username atau password salah.');
      else if (statusCode === 503) toast.error(detail || 'Authentication API belum dikonfigurasi.');
      else toast.error(detail || `Login gagal (HTTP ${statusCode}).`);
      throw error;
    }
  };

  const logout = async () => {
    try { if (token) await axios.post('/api/auth/logout'); }
    catch { /* local logout still succeeds */ }
    finally { clearSession(); toast.success('Logged out'); }
  };

  const verifyToken = async () => {
    const current = token || localStorage.getItem('token');
    if (!current) { setLoading(false); return false; }
    try {
      axios.defaults.headers.common.Authorization = `Bearer ${current}`;
      const response = await axios.get('/api/auth/verify');
      if (response.data.is_authenticated) {
        setUser({ username: response.data.username }); setIsAuthenticated(true); setLoading(false); return true;
      }
    } catch {
      const refreshed = await refreshAccessToken();
      if (refreshed === true) {
        try {
          const response = await axios.get('/api/auth/verify');
          if (response.data.is_authenticated) { setUser({ username: response.data.username }); setIsAuthenticated(true); setLoading(false); return true; }
        } catch { /* fall through to clear */ }
      }
    }
    clearSession(); setLoading(false); return false;
  };

  useEffect(() => { verifyToken(); }, []);

  return <AuthContext.Provider value={{ user, token, refreshToken, loading, isAuthenticated, login, logout, verifyToken, refreshAccessToken }}>{children}</AuthContext.Provider>;
};
