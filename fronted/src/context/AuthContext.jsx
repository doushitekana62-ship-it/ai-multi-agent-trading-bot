import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';

const AuthContext = createContext();
const API_URL = String(import.meta.env.VITE_API_URL || '').trim().replace(/\/$/, '');
if (API_URL) axios.defaults.baseURL = API_URL;

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
      console.warn('Refresh token temporarily unavailable:', error.message);
      return null;
    }
  };

  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      (response) => response,
      async (error) => {
        const original = error.config;
        const stored = localStorage.getItem('refresh_token');
        if (error.response?.status !== 401 || !original || original._retry || original.url?.includes('/api/auth/login') || original.url?.includes('/api/auth/refresh') || original.url?.includes('/api/auth/logout') || !stored) return Promise.reject(error);
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
      const response = await axios.post('/api/auth/login', { username, password });
      applyAccessToken(response.data.access_token);
      setRefreshToken(response.data.refresh_token);
      localStorage.setItem('refresh_token', response.data.refresh_token);
      setUser({ username: response.data.username });
      setIsAuthenticated(true);
      toast.success('Login successful!');
      return response.data;
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Login failed');
      throw error;
    }
  };

  const logout = async () => {
    try { if (token) await axios.post('/api/auth/logout'); }
    catch (error) { console.warn('Logout request failed:', error.message); }
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
    } catch (error) {
      const refreshed = await refreshAccessToken();
      if (refreshed === true) {
        try {
          const response = await axios.get('/api/auth/verify');
          if (response.data.is_authenticated) { setUser({ username: response.data.username }); setIsAuthenticated(true); setLoading(false); return true; }
        } catch (verifyError) {
          if (verifyError.response?.status === 401) { clearSession(); setLoading(false); return false; }
        }
      }
      if (refreshed === null) { setIsAuthenticated(true); setLoading(false); return true; }
    }
    clearSession(); setLoading(false); return false;
  };

  useEffect(() => { verifyToken(); }, []);

  return <AuthContext.Provider value={{ user, token, refreshToken, loading, isAuthenticated, login, logout, verifyToken, refreshAccessToken }}>{children}</AuthContext.Provider>;
};
