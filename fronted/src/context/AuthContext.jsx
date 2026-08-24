import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';

const AuthContext = createContext();

// In production the dashboard uses the same-origin /api path and
// Cloudflare Worker proxies it to the configured FastAPI backend.
// REACT_APP_API_URL can still be set for local development or a
// separately hosted API.
const configuredApiUrl = process.env.REACT_APP_API_URL?.trim() || '';
const API_URL = configuredApiUrl.replace(/\/$/, '');

export const useAuth = () => {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }

  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete axios.defaults.headers.common['Authorization'];
    }
  }, [token]);

  const login = async (username, password) => {
    try {
      const response = await axios.post(
        `${API_URL}/api/auth/login`,
        {
          username,
          password,
        }
      );

      const {
        access_token,
        username: userUsername,
      } = response.data;

      setToken(access_token);
      setUser({
        username: userUsername,
      });
      setIsAuthenticated(true);

      localStorage.setItem('token', access_token);

      axios.defaults.headers.common['Authorization'] =
        `Bearer ${access_token}`;

      toast.success('Login successful!');

      return response.data;
    } catch (error) {
      console.error('Login error:', error);

      toast.error(
        error.response?.data?.detail || 'Login failed'
      );

      throw error;
    }
  };

  const logout = async () => {
    try {
      await axios.post(`${API_URL}/api/auth/logout`);
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setToken(null);
      setUser(null);
      setIsAuthenticated(false);

      localStorage.removeItem('token');

      delete axios.defaults.headers.common['Authorization'];

      toast.success('Logged out');
    }
  };

  const verifyToken = async () => {
    if (!token) {
      setLoading(false);
      return false;
    }

    try {
      const response = await axios.get(
        `${API_URL}/api/auth/verify`
      );

      if (response.data.is_authenticated) {
        setUser({
          username: response.data.username,
        });

        setIsAuthenticated(true);

        return true;
      }

      return false;
    } catch (error) {
      console.error('Token verification failed:', error);

      setToken(null);
      setUser(null);
      setIsAuthenticated(false);

      localStorage.removeItem('token');

      delete axios.defaults.headers.common['Authorization'];

      return false;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    verifyToken();
  }, []);

  const value = {
    user,
    token,
    loading,
    isAuthenticated,
    login,
    logout,
    verifyToken,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
