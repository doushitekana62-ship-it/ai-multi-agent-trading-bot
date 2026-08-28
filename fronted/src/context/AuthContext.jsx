import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';

const AuthContext = createContext();
const API_URL = '';

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
    setToken(null);
    setRefreshToken(null);
    setUser(null);
    setIsAuthenticated(false);
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    delete axios.defaults.headers.common.Authorization;
  };

  useEffect(() => {
    if (token) axios.defaults.headers.common.Authorization = `Bearer ${token}`;
    else delete axios.defaults.headers.common.Authorization;
  }, [token]);

  const refreshAccessToken = async () => {
    const storedRefreshToken = refreshToken || localStorage.getItem('refresh_token');
    if (!storedRefreshToken) return false;
    try {
      const response = await axios.post(`${API_URL}/api/auth/refresh`, { refresh_token: storedRefreshToken });
      applyAccessToken(response.data.access_token);
      return true;
    } catch (error) {
      clearSession();
      return false;
    }
  };

  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      (response) => response,
      async (error) => {
        const original = error.config;
        const storedRefreshToken = localStorage.getItem('refresh_token');
        if (error.response?.status !== 401 || !original || original._retry || original.url?.includes('/api/auth/login') || original.url?.includes('/api/auth/refresh') || original.url?.includes('/api/auth/logout') || !storedRefreshToken) return Promise.reject(error);
        original._retry = true;
        try {
          const response = await axios.post(`${API_URL}/api/auth/refresh`, { refresh_token: storedRefreshToken });
          applyAccessToken(response.data.access_token);
          original.headers = original.headers || {};
          original.headers.Authorization = `Bearer ${response.data.access_token}`;
          return axios(original);
        } catch (refreshError) {
          clearSession();
          return Promise.reject(refreshError);
        }
      }
    );
    return () => axios.interceptors.response.eject(interceptor);
  }, []);

  useEffect(() => {
    const keepPaperButtonEnabled = () => {
      const button = Array.from(document.querySelectorAll('button')).find((node) => node.textContent?.trim().includes('START PAPER BOT'));
      if (!button) return;
      button.disabled = false;
      button.removeAttribute('disabled');
      button.removeAttribute('aria-disabled');
      button.classList.remove('Mui-disabled');
    };
    keepPaperButtonEnabled();
    const interval = window.setInterval(keepPaperButtonEnabled, 500);
    return () => window.clearInterval(interval);
  }, []);

  const login = async (username, password) => {
    try {
      const response = await axios.post(`${API_URL}/api/auth/login`, { username, password });
      applyAccessToken(response.data.access_token);
      setRefreshToken(response.data.refresh_token);
      localStorage.setItem('refresh_token', response.data.refresh_token);
      setUser({ username: response.data.username });
      setIsAuthenticated(true);
      toast.success('Login successful!');
      return response.data;
    } catch (error) {
      console.error('Login error:', error);
      toast.error(error.response?.data?.detail || 'Login failed');
      throw error;
    }
  };

  const logout = async () => {
    try {
      if (token) await axios.post(`${API_URL}/api/auth/logout`);
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      clearSession();
      toast.success('Logged out');
    }
  };

  const verifyToken = async () => {
    const currentToken = token || localStorage.getItem('token');
    if (!currentToken) {
      setLoading(false);
      return false;
    }
    try {
      axios.defaults.headers.common.Authorization = `Bearer ${currentToken}`;
      const response = await axios.get(`${API_URL}/api/auth/verify`);
      if (response.data.is_authenticated) {
        setUser({ username: response.data.username });
        setIsAuthenticated(true);
        setLoading(false);
        return true;
      }
    } catch (error) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        try {
          const response = await axios.get(`${API_URL}/api/auth/verify`);
          if (response.data.is_authenticated) {
            setUser({ username: response.data.username });
            setIsAuthenticated(true);
            setLoading(false);
            return true;
          }
        } catch (verifyError) {
          console.error('Token verification after refresh failed:', verifyError);
        }
      }
    }
    clearSession();
    setLoading(false);
    return false;
  };

  useEffect(() => {
    verifyToken();
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, refreshToken, loading, isAuthenticated, login, logout, verifyToken, refreshAccessToken }}>
      {children}
    </AuthContext.Provider>
  );
};