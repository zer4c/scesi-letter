import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { ApiError, listDocuments } from '../../core/api.js';
import { useAuth } from '../auth/AuthProvider.jsx';

const documentTypeNames = {
  INV: 'Invitación',
  SOL: 'Solicitud',
  MEM: 'Memorándum',
  ACT: 'Acta',
  PRES: 'Presentación',
  CIRC: 'Circular',
  NOT: 'Notificación',
  GEN: 'Carta',
};

function formatDate(value) {
  return new Intl.DateTimeFormat('es-BO', { dateStyle: 'medium' }).format(new Date(value));
}

export default function DocumentListPage() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retryKey, setRetryKey] = useState(0);
  const { expireSession } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    listDocuments()
      .then((page) => {
        if (active) setDocuments(page.items);
      })
      .catch((requestError) => {
        if (!active) return;
        if (requestError instanceof ApiError && requestError.status === 401) {
          expireSession();
          navigate('/login', { replace: true, state: { expired: true, from: location } });
          return;
        }
        setError('No se pudieron cargar las cartas. Comprueba la conexión e inténtalo de nuevo.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [expireSession, location, navigate, retryKey]);

  return (
    <section className="document-page" aria-labelledby="documents-title">
      <div className="page-heading">
        <div>
          <h1 id="documents-title">Cartas</h1>
          <p className="page-heading__intro">Correspondencia académica de tu comunidad.</p>
        </div>
      </div>

      {loading && <p className="inline-status" role="status">Cargando cartas…</p>}
      {error && (
        <div className="error-state">
          <p className="notice notice--error" role="alert">{error}</p>
          <button className="button-quiet" onClick={() => setRetryKey((value) => value + 1)} type="button">Reintentar</button>
        </div>
      )}
      {!loading && !error && documents.length === 0 && (
        <div className="empty-state">
          <div className="empty-state__rule" aria-hidden="true" />
          <h2>Aún no hay cartas</h2>
          <p>Las cartas que crees o en las que colabores aparecerán aquí.</p>
        </div>
      )}
      {!loading && !error && documents.length > 0 && (
        <ul className="document-list" aria-label="Cartas disponibles">
          {documents.map((document) => (
            <li className="document-list__item" key={document.id}>
              <div className="document-list__main">
                <span className="document-list__type">{documentTypeNames[document.document_type] || 'Carta'}</span>
                <h2>{document.topic || document.recipient_name || 'Sin asunto'}</h2>
                <p>{document.recipient_name ? `Destinatario: ${document.recipient_name}` : 'Destinatario pendiente'}</p>
              </div>
              <div className="document-list__meta">
                <span>{document.identifier || 'Borrador sin número'}</span>
                <time dateTime={document.updated_at}>Actualizada {formatDate(document.updated_at)}</time>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
