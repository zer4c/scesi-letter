import { useEffect, useState } from 'react';
import { ApiError } from '../../../core/api.js';
import {
  createGoogleAuthorization,
  importGoogleOtherContacts,
  listGoogleConnections,
  previewGoogleOtherContacts,
} from '../services/contacts.js';

const makeRoleKey = (value) => value.normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '').toLowerCase()
  .replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 80);

export default function GoogleOtherContactsImport({ csrfToken }) {
  const [connections, setConnections] = useState([]);
  const [connectionId, setConnectionId] = useState('');
  const [items, setItems] = useState([]);
  const [nextToken, setNextToken] = useState(null);
  const [selected, setSelected] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  const loadConnections = async () => {
    const result = await listGoogleConnections();
    const available = result.connections.filter((item) => item.kind === 'contacts' && item.mode === 'personal');
    setConnections(available);
    if (!connectionId && available[0]) setConnectionId(available[0].id);
  };

  useEffect(() => {
    loadConnections().catch(() => setError('No se pudieron consultar las cuentas Google conectadas.'));
  }, []);

  const connect = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await createGoogleAuthorization('contacts', 'personal', csrfToken);
      window.location.assign(result.authorization_url);
    } catch {
      setError('No se pudo iniciar la autorización. Comprueba la configuración de Google.');
      setBusy(false);
    }
  };

  const loadPage = async (token = null, append = false) => {
    if (!connectionId) return;
    setBusy(true);
    setError('');
    try {
      const result = await previewGoogleOtherContacts(connectionId, token);
      setItems((current) => append ? [...current, ...result.items] : result.items);
      setNextToken(result.next_page_token);
    } catch (loadError) {
      setError(loadError instanceof ApiError && loadError.status === 403
        ? 'Google denegó o revocó el permiso de contactos. Vuelve a conectar la cuenta.'
        : 'No se pudieron cargar los Otros contactos de Google. Inténtalo de nuevo.');
    } finally {
      setBusy(false);
    }
  };

  const updateField = (email, field, value) => setSelected((current) => ({
    ...current,
    [email]: { ...current[email], [field]: value },
  }));

  const toggle = (item) => setSelected((current) => {
    if (current[item.email]) {
      const next = { ...current };
      delete next[item.email];
      return next;
    }
    if (Object.keys(current).length >= 25) {
      setError('Puedes importar hasta 25 contactos por confirmación.');
      return current;
    }
    setError('');
    return { ...current, [item.email]: { name: item.name, email: item.email, role_label: '', institution: '', career: '' } };
  });

  const confirmImport = async () => {
    const contacts = Object.values(selected).map((item) => ({
      name: item.name,
      role_key: makeRoleKey(item.role_label),
      role_label: item.role_label,
      institution: item.institution,
      career: item.career || null,
      emails: [item.email],
      active: true,
    }));
    if (!contacts.length || contacts.some((item) => !item.role_key || !item.institution.trim())) {
      setError('Completa el cargo y la institución de cada contacto seleccionado.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await importGoogleOtherContacts(contacts, csrfToken);
      setStatus(`Se añadieron ${result.imported.length} contactos. Se omitieron ${result.skipped_duplicates} duplicados; no se modificaron contactos existentes.`);
      setItems((current) => current.map((item) => selected[item.email] ? { ...item, already_imported: true } : item));
      setSelected({});
    } catch {
      setError('No se pudo completar la importación. Revisa los datos e inténtalo de nuevo.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="google-other-import">
      <summary>Importar contactos de Google</summary>
      <p>Se consultan solo los “Otros contactos” guardados por Google. No se leen mensajes ni se importan cuerpos, asuntos, firmas o historial. Los contactos elegidos se añadirán al directorio compartido.</p>
      {connections.length === 0 ? (
        <button className="button-quiet" disabled={busy} onClick={connect} type="button">{busy ? 'Conectando…' : 'Conectar cuenta personal'}</button>
      ) : (
        <div className="google-other-import__actions">
          <label className="editor-field"><span>Cuenta personal</span>
            <select onChange={(event) => { setConnectionId(event.target.value); setItems([]); setNextToken(null); setSelected({}); }} value={connectionId}>
              {connections.map((item) => <option key={item.id} value={item.id}>{item.google_account}</option>)}
            </select>
          </label>
          <button className="button-quiet" disabled={busy || !connectionId} onClick={() => loadPage()} type="button">{busy ? 'Cargando…' : 'Ver contactos disponibles'}</button>
          <button className="button-quiet" disabled={busy} onClick={connect} type="button">Conectar otra cuenta</button>
        </div>
      )}
      {status && <p role="status">{status}</p>}
      {error && <p className="recipient-contact-fields__error" role="alert">{error}</p>}
      {items.length > 0 && <ul className="google-other-import__list">
        {items.map((item) => <li key={item.email}>
          <label className="google-other-import__choice">
            <input checked={Boolean(selected[item.email])} disabled={busy || item.already_imported} onChange={() => toggle(item)} type="checkbox" />
            <span><strong>{item.name}</strong><small>{item.email}{item.already_imported ? ' · Ya está en el directorio' : ''}</small></span>
          </label>
          {selected[item.email] && <div className="google-other-import__fields">
            <label className="editor-field"><span>Cargo</span><input maxLength="120" onChange={(event) => updateField(item.email, 'role_label', event.target.value)} required value={selected[item.email].role_label} /></label>
            <label className="editor-field"><span>Institución</span><input maxLength="160" onChange={(event) => updateField(item.email, 'institution', event.target.value)} required value={selected[item.email].institution} /></label>
            <label className="editor-field"><span>Carrera, si corresponde</span><input maxLength="120" onChange={(event) => updateField(item.email, 'career', event.target.value)} value={selected[item.email].career} /></label>
          </div>}
        </li>)}
      </ul>}
      {nextToken && <button className="button-quiet" disabled={busy} onClick={() => loadPage(nextToken, true)} type="button">Cargar siguiente página</button>}
      {Object.keys(selected).length > 0 && <button className="button-primary" disabled={busy} onClick={confirmImport} type="button">Confirmar importación ({Object.keys(selected).length})</button>}
    </details>
  );
}
