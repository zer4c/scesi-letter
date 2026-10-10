import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { ApiError, createDocument, listDocuments } from '../../core/api.js';
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
  const { expireSession, csrfToken } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);

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

  const handleCreate = async () => {
    setCreating(true);
    setError('');
    const now = new Date();
    const date = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
      .toISOString().slice(0, 10);
    try {
      const document = await createDocument({
        metadata: { document_type: 'SOL', date },
        body: '',
      }, csrfToken);
      navigate(`/documents/${document.id}`);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        expireSession();
        navigate('/login', { replace: true, state: { expired: true, from: location } });
      } else {
        setError('No se pudo crear el borrador. Inténtalo de nuevo.');
      }
    } finally {
      setCreating(false);
    }
  };

  return (
    <section className="document-page" aria-labelledby="documents-title">
      <div className="page-heading">
        <div>
          <h1 id="documents-title">Cartas</h1>
          <p className="page-heading__intro">Correspondencia académica de tu comunidad.</p>
        </div>
        <button className="button-primary" disabled={creating} onClick={handleCreate} type="button">
          {creating ? 'Creando borrador…' : 'Nueva carta'}
        </button>
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
                <h2><Link className="document-list__link" to={`/documents/${document.id}`}>{document.topic || document.recipient_name || 'Sin asunto'}</Link></h2>
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
