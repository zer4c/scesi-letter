import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ApiError, redeemInvitation } from '../../core/api.js';
import { BrandPanel } from '../../shared/components/BrandPanel.jsx';

function invitationError(error) {
  if (!(error instanceof ApiError)) return 'No se pudo conectar. Comprueba tu conexión e inténtalo de nuevo.';
  if (error.status === 404 || error.status === 409 || error.status === 422) {
    return 'Esta invitación no es válida, ya fue utilizada o venció. Solicita una nueva invitación al administrador.';
  }
  if (error.status >= 500) return 'El servicio no está disponible en este momento. Inténtalo más tarde.';
  return 'No se pudo crear la cuenta. Revisa los datos de la invitación.';
}

export default function InvitationPage() {
  const { token: routeToken } = useParams();
  const [searchParams] = useState(() => new URLSearchParams(window.location.search));
  const token = routeToken || searchParams.get('token') || '';
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');

    if (!token) {
      setError('Falta el código de invitación. Abre el enlace completo que recibiste.');
      return;
    }
    if (!displayName.trim()) {
      setError('Ingresa tu nombre completo.');
      return;
    }
    if (password !== confirmation) {
      setError('Las contraseñas no coinciden.');
      return;
    }
    if (password.length < 12) {
      setError('La contraseña debe tener al menos 12 caracteres.');
      return;
    }

    setSubmitting(true);
    try {
      await redeemInvitation(token, displayName.trim(), password);
      navigate('/login?invited=1', { replace: true });
    } catch (requestError) {
      setError(invitationError(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="access-layout">
      <BrandPanel />
      <section className="access-panel" aria-labelledby="invite-title">
        <div className="access-panel__inner">
          <h1 id="invite-title">Crear cuenta</h1>
          <p className="access-panel__intro">Completa tus datos para activar tu acceso a SCESI Letter.</p>
          {!token && <p className="notice notice--error" role="alert">Abre el enlace completo de invitación que recibiste.</p>}
          {error && <p className="notice notice--error" role="alert">{error}</p>}
          <form aria-busy={submitting} className="auth-form" onSubmit={handleSubmit}>
            <label className="field" htmlFor="invite-name">
              <span>Nombre completo</span>
              <input
                autoComplete="name"
                id="invite-name"
                maxLength={120}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                value={displayName}
              />
            </label>
            <label className="field" htmlFor="invite-password">
              <span>Contraseña</span>
              <input
                autoComplete="new-password"
                aria-describedby="invite-password-hint"
                id="invite-password"
                maxLength={1024}
                minLength={12}
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
              <span className="field__hint" id="invite-password-hint">Usa al menos 12 caracteres.</span>
            </label>
            <label className="field" htmlFor="invite-confirmation">
              <span>Repite la contraseña</span>
              <input
                autoComplete="new-password"
                id="invite-confirmation"
                onChange={(event) => setConfirmation(event.target.value)}
                required
                type="password"
                value={confirmation}
              />
            </label>
            <button className="button-primary" disabled={submitting || !token} type="submit">
              {submitting ? 'Creando cuenta…' : 'Crear cuenta'}
            </button>
          </form>
          <p className="access-panel__help">La invitación solo se puede utilizar una vez.</p>
          <Link className="text-link" to="/login">Volver a iniciar sesión</Link>
        </div>
      </section>
    </main>
  );
}
