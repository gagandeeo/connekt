import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { login as apiLogin, register as apiRegister, getMe, setTokenGetter } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [authToken, setAuthToken] = useState(null);
  const [loading, setLoading] = useState(true);

  const isAdmin = currentUser?.role === 'ADMIN';

  const setAuth = useCallback((user, token) => {
    setCurrentUser(user);
    setAuthToken(token);
    localStorage.setItem('connekt_user', JSON.stringify(user));
    localStorage.setItem('connekt_token', token);
  }, []);

  const logout = useCallback(() => {
    setCurrentUser(null);
    setAuthToken(null);
    localStorage.removeItem('connekt_user');
    localStorage.removeItem('connekt_token');
  }, []);

  const login = useCallback(async (username, password) => {
    const data = await apiLogin(username, password);
    if (data.user && data.token) {
      setAuth(data.user, data.token);
      return { ok: true };
    }
    return { ok: false, error: data.error || 'Authentication failed.' };
  }, [setAuth]);

  const register = useCallback(async (username, password) => {
    const data = await apiRegister(username, password);
    if (data.user) {
      // Auto-login after register
      const loginData = await apiLogin(username, password);
      if (loginData.token) {
        setAuth(loginData.user, loginData.token);
        return { ok: true };
      }
      return { ok: false, error: 'Registered! Please log in.' };
    }
    return { ok: false, error: data.error || 'Registration failed.' };
  }, [setAuth]);

  // Wire up the token getter for api.js
  useEffect(() => {
    setTokenGetter(() => authToken);
  }, [authToken]);

  // Validate saved session on mount
  useEffect(() => {
    (async () => {
      const savedToken = localStorage.getItem('connekt_token');
      const savedUser = localStorage.getItem('connekt_user');
      if (savedToken && savedUser) {
        try {
          const data = await getMe(savedToken);
          if (data?.user) {
            setCurrentUser(data.user);
            setAuthToken(savedToken);
            setLoading(false);
            return;
          }
        } catch (e) {
          // token invalid
        }
      }
      setLoading(false);
    })();
  }, []);

  return (
    <AuthContext.Provider value={{ currentUser, authToken, isAdmin, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
