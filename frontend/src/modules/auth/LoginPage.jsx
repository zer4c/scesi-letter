import { useState } from 'react';
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import { ApiError } from '../../core/api.js';
import { BrandPanel } from '../../shared/components/BrandPanel.jsx';
import { useAuth } from './AuthProvider.jsx';

function loginError(error) {
  if (!(error instanceof ApiError)) return 'No se pudo conectar. Comprueba tu conexión e inténtalo de nuevo.';
  if (error.status === 401) return 'El correo o la contraseña no coinciden. Revisa los datos e inténtalo de nuevo.';
  if (error.status === 429) return 'Se alcanzó el límite temporal de intentos. Espera un momento antes de volver a intentarlo.';
  if (error.status >= 500) return 'El servicio no está disponible en este momento. Inténtalo más tarde.';
  return 'No se pudo iniciar sesión. Revisa los datos e inténtalo de nuevo.';
}

export default function LoginPage() {
  const { status, user, sessionIssue, signIn } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(() => (
    location.state?.expired || searchParams.get('expired') === '1'
      ? 'Tu sesión terminó. Inicia sesión para continuar.'
      : searchParams.get('invited') === '1'
        ? 'Tu cuenta está lista. Inicia sesión para continuar.'
        : ''
  ));

  if (status === 'loading') {
    return <p className="screen-status" role="status">Comprobando tu sesión…</p>;
  }

  if (user) return <Navigate to="/documents" replace />;

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      const destination = location.state?.from?.pathname;
      navigate(destination?.startsWith('/') ? destination : '/documents', { replace: true });
    } catch (requestError) {
      setError(loginError(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="access-layout">
      <BrandPanel />
      <section className="access-panel" aria-labelledby="login-title">
        <div className="access-panel__inner">
          <h1 id="login-title">Iniciar sesión</h1>
          <p className="access-panel__intro">Ingresa con la cuenta que recibiste por invitación.</p>
          {sessionIssue && <p className="notice notice--error" role="status">No se pudo comprobar la sesión anterior. Puedes intentar ingresar de nuevo.</p>}
          {message && <p className="notice notice--info" role="status">{message}</p>}
          {error && <p className="notice notice--error" role="alert">{error}</p>}
          <form aria-busy={submitting} className="auth-form" onSubmit={handleSubmit}>
            <label className="field" htmlFor="login-email">
              <span>Correo electrónico</span>
              <input
                autoComplete="username"
                id="login-email"
                name="email"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </label>
            <label className="field" htmlFor="login-password">
              <span>Contraseña</span>
              <input
                autoComplete="current-password"
                id="login-password"
                maxLength={1024}
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            <button className="button-primary" disabled={submitting} type="submit">
              {submitting ? 'Ingresando…' : 'Ingresar'}
            </button>
          </form>
          <p className="access-panel__help">
            ¿Aún no tienes una cuenta? Pide una invitación a la persona administradora.
          </p>
          <p className="access-panel__help">
            La recuperación de acceso aún no está habilitada. Si pierdes la contraseña, la firma no podrá recuperarse.
          </p>
        </div>
      </section>
    </main>
  );
}
