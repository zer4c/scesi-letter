import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from './AuthProvider.jsx';

export function ProtectedRoute() {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return <p className="screen-status" role="status">Comprobando tu sesión…</p>;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location, expired: true }} />;
  }

  return <Outlet />;
}

export function AdminRoute() {
  const { user } = useAuth();
  const location = useLocation();

  if (!user || user.role !== 'admin') {
    return <Navigate to="/documents" replace state={{ denied: true, from: location.pathname }} />;
  }

  return <Outlet />;
}
