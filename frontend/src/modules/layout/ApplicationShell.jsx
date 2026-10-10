import { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { BrandWordmark } from '../../shared/components/BrandPanel.jsx';
import { useAuth } from '../auth/AuthProvider.jsx';

export default function ApplicationShell() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [logoutError, setLogoutError] = useState(false);

  const handleSignOut = async () => {
    setLogoutError(false);
    try {
      await signOut();
      navigate('/login', { replace: true });
    } catch {
      setLogoutError(true);
    }
  };

  return (
    <div className="app-frame">
      <header className="app-header">
        <NavLink aria-label="SCESI Letter, ir a cartas" className="app-header__brand" to="/documents">
          <BrandWordmark />
        </NavLink>
        <nav aria-label="Navegación principal" className="primary-navigation">
          <NavLink className={({ isActive }) => `primary-navigation__link${isActive ? ' is-active' : ''}`} to="/documents">
            Cartas
          </NavLink>
        </nav>
        <div className="account-controls">
          <div className="account-controls__identity">
            <span className="account-controls__name">{user?.display_name}</span>
            <span className="account-controls__email">{user?.email}</span>
          </div>
          <button className="button-quiet" onClick={handleSignOut} type="button">Cerrar sesión</button>
        </div>
      </header>
      <main className="app-content" id="main-content">
        {logoutError && <p className="notice notice--error" role="alert">No se pudo confirmar el cierre de sesión. Comprueba tu conexión e inténtalo de nuevo.</p>}
        {location.state?.denied && <p className="notice notice--error" role="status">Esta sección está disponible únicamente para administradores.</p>}
        <Outlet />
      </main>
      <footer className="app-footer">
        <span>SCESI Letter</span>
        <span>Correspondencia académica</span>
      </footer>
    </div>
  );
}
