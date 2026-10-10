import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { ApiError, getSession, logIn, logOut } from '../../core/api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading');
  const [user, setUser] = useState(null);
  const [csrfToken, setCsrfToken] = useState('');
  const [sessionIssue, setSessionIssue] = useState(false);

  const restore = useCallback(async () => {
    setStatus('loading');
    try {
      const session = await getSession();
      setUser(session.user);
      setCsrfToken(session.csrf_token);
      setSessionIssue(false);
      setStatus('ready');
      return true;
    } catch (error) {
      setUser(null);
      setCsrfToken('');
      setSessionIssue(!(error instanceof ApiError) || error.status !== 401);
      setStatus('ready');
      return false;
    }
  }, []);

  useEffect(() => {
    restore();
  }, [restore]);

  const signIn = useCallback(async (email, password) => {
    const session = await logIn(email, password);
    setUser(session.user);
    setCsrfToken(session.csrf_token);
    setSessionIssue(false);
    setStatus('ready');
    return session.user;
  }, []);

  const signOut = useCallback(async () => {
    if (csrfToken) await logOut(csrfToken);
    setUser(null);
    setCsrfToken('');
    setSessionIssue(false);
    setStatus('ready');
  }, [csrfToken]);

  const expireSession = useCallback(() => {
    setUser(null);
    setCsrfToken('');
    setStatus('ready');
  }, []);

  const value = useMemo(() => ({
    status,
    user,
    csrfToken,
    sessionIssue,
    signIn,
    signOut,
    restore,
    expireSession,
  }), [status, user, csrfToken, sessionIssue, signIn, signOut, restore, expireSession]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
