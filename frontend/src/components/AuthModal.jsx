import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';

export default function AuthModal() {
  const { currentUser, login, register } = useAuth();
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (currentUser) return null;

  const handleSubmit = async () => {
    if (!username.trim() || !password) {
      setError('Username and password are required.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const result = mode === 'login'
        ? await login(username.trim(), password)
        : await register(username.trim(), password);
      if (!result.ok) {
        setError(result.error);
        if (result.error === 'Registered! Please log in.') {
          setMode('login');
        }
      }
    } catch (err) {
      setError('Network error: ' + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSubmit();
  };

  return (
    <div className="auth-overlay">
      <div className="auth-modal">
        <h2>Connekt</h2>
        <div className="auth-tabs">
          <button
            className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => { setMode('login'); setError(''); }}
          >
            Login
          </button>
          <button
            className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
            onClick={() => { setMode('register'); setError(''); }}
          >
            Register
          </button>
        </div>
        <div className="auth-error">{error}</div>
        <input
          type="text"
          placeholder="Username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          type="password"
          placeholder="Password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button className="auth-btn" onClick={handleSubmit} disabled={submitting}>
          {mode === 'login' ? 'Login' : 'Register'}
        </button>
      </div>
    </div>
  );
}
