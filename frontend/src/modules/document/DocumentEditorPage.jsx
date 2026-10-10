import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider.jsx';

import {
  ApiError,
  checkpointDocument,
  createEvent,
  getEvent,
  getDocument,
  listEvents,
  renderDocumentPreview,
  saveDocument,
} from '../../core/api.js';
import { createCollaborativeDocument } from '../../core/collaboration/yjsTransport.js';
import LetterAssistancePanel from '../automation/components/LetterAssistancePanel.jsx';
import RecipientContactFields from '../contact/components/RecipientContactFields.jsx';
import DocumentMailPanel from '../mail/components/DocumentMailPanel.jsx';

const CodeMirror = lazy(() => import('@uiw/react-codemirror'));
const PdfPreview = lazy(() => import('./components/PdfPreview.jsx'));

const documentTypes = [
  ['INV', 'Invitación'], ['SOL', 'Solicitud'], ['MEM', 'Memorándum'], ['ACT', 'Acta'],
  ['PRES', 'Presentación'], ['CIRC', 'Circular'], ['NOT', 'Notificación'], ['GEN', 'Carta'],
];

const connectionLabels = {
  connecting: 'Conectando…',
  connected: 'En línea',
  reconnecting: 'Reconectando…',
  disconnected: 'Conexión interrumpida',
  unauthorized: 'Acceso perdido',
};

const emptyFields = () => ({
  document_type: 'SOL',
  date: new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10),
  reference: '',
  salutation: '',
  recipient: { name: '', role: '', institution: '', career: '', email: '' },
  sender: { name: '', role: '', institution: '', career: '', email: '' },
  topic: '',
  signoff: '',
  event_id: null,
});

function parseMetadataMap(map) {
  const value = Object.fromEntries(map.entries());
  for (const key of ['recipient', 'sender']) {
    if (typeof value[key] === 'string') {
      try { value[key] = JSON.parse(value[key]); } catch { value[key] = null; }
    }
    const partial = {};
    for (const field of ['name', 'role', 'institution', 'career', 'email']) {
      const mapKey = `${key}_${field}`;
      if (mapKey in value) {
        partial[field] = value[mapKey];
        delete value[mapKey];
      }
    }
    if (Object.keys(partial).length > 0) value[key] = partial;
  }
  const defaults = emptyFields();
  return {
    ...defaults,
    ...value,
    recipient: { ...defaults.recipient, ...(value.recipient || {}) },
    sender: { ...defaults.sender, ...(value.sender || {}) },
  };
}

function metadataForMap(fields) {
  const { recipient, sender, ...metadata } = fields;
  return {
    ...metadata,
    ...Object.fromEntries(['recipient', 'sender'].flatMap((party) => (
      Object.entries(fields[party]).map(([key, value]) => [`${party}_${key}`, value || ''])
    ))),
  };
}

function buildMarkdown(fields, identifier, body) {
  const metadata = { ...fields, ...(identifier ? { identifier } : {}) };
  return `---\n${JSON.stringify(metadata, null, 2)}\n---\n\n${body}\n`;
}

function saveMetadata(fields) {
  const party = (value) => value.name ? Object.fromEntries(
    ['name', 'role', 'institution', 'career', 'email'].map((key) => [key, value[key] || null]),
  ) : null;
  return {
    document_type: fields.document_type,
    date: fields.date,
    reference: fields.reference || null,
    salutation: fields.salutation || null,
    recipient: party(fields.recipient),
    sender: party(fields.sender),
    topic: fields.topic || null,
    signoff: fields.signoff || null,
    event_id: fields.event_id || null,
  };
}

function matchesCheckpoint(fields, checkpoint) {
  return JSON.stringify(saveMetadata(fields)) === JSON.stringify(saveMetadata({
    ...emptyFields(),
    ...checkpoint.metadata,
    recipient: { ...emptyFields().recipient, ...(checkpoint.metadata.recipient || {}) },
    sender: { ...emptyFields().sender, ...(checkpoint.metadata.sender || {}) },
  }));
}

function updateMap(map, fields) {
  const next = metadataForMap(fields);
  for (const key of map.keys()) {
    if (!(key in next)) map.delete(key);
  }
  for (const [key, value] of Object.entries(next)) {
    if (map.get(key) !== value) map.set(key, value);
  }
}

function RecipientFields({ label, value, onChange, prefix }) {
  const update = (key) => (event) => onChange({ ...value, [key]: event.target.value });
  return (
    <fieldset className="editor-fields__group">
      <legend>{label}</legend>
      <label className="editor-field">
        <span>Nombre</span>
        <input autoComplete="off" maxLength="160" onChange={update('name')} value={value.name || ''} />
      </label>
      <label className="editor-field">
        <span>Cargo</span>
        <input maxLength="120" onChange={update('role')} value={value.role || ''} />
      </label>
      <label className="editor-field">
        <span>Institución</span>
        <input maxLength="160" onChange={update('institution')} value={value.institution || ''} />
      </label>
      <label className="editor-field">
        <span>Carrera</span>
        <input maxLength="120" onChange={update('career')} value={value.career || ''} />
      </label>
      {prefix === 'recipient' && (
        <label className="editor-field">
          <span>Correo electrónico</span>
          <input autoComplete="off" maxLength="254" onChange={update('email')} type="email" value={value.email || ''} />
        </label>
      )}
    </fieldset>
  );
}

export default function DocumentEditorPage() {
  const { documentId } = useParams();
  const { csrfToken, expireSession, user } = useAuth();
  const navigate = useNavigate();
  const [fields, setFields] = useState(null);
  const [body, setBody] = useState('');
  const [identifier, setIdentifier] = useState(null);
  const [currentVersion, setCurrentVersion] = useState(null);
  const [finalizedVersionId, setFinalizedVersionId] = useState(null);
  const [collab, setCollab] = useState(null);
  const [collabStatus, setCollabStatus] = useState('connecting');
  const [synced, setSynced] = useState(false);
  const [pendingUpdates, setPendingUpdates] = useState(0);
  const [saveState, setSaveState] = useState('saved');
  const [saveError, setSaveError] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewError, setPreviewError] = useState('');
  const [previewState, setPreviewState] = useState('loading');
  const [mobileTab, setMobileTab] = useState('edit');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [awareness, setAwareness] = useState([]);
  const [events, setEvents] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [eventLoadError, setEventLoadError] = useState('');
  const [showEventForm, setShowEventForm] = useState(false);
  const [eventName, setEventName] = useState('');
  const [eventCreateError, setEventCreateError] = useState('');
  const [eventCreating, setEventCreating] = useState(false);
  const previewSequence = useRef(0);
  const previewTimer = useRef(null);
  const bodyRef = useRef('');
  const fieldsRef = useRef(null);
  const collabRef = useRef(null);

  useEffect(() => {
    let active = true;
    getDocument(documentId)
      .then((document) => {
        if (!active) return;
        setFields({
          ...emptyFields(),
          ...document.metadata,
          recipient: { ...emptyFields().recipient, ...(document.metadata.recipient || {}) },
          sender: { ...emptyFields().sender, ...(document.metadata.sender || {}) },
        });
        setBody(document.body);
        bodyRef.current = document.body;
        fieldsRef.current = document.metadata;
        setIdentifier(document.metadata.identifier);
        setCurrentVersion(document.current_version);
        setFinalizedVersionId(document.finalized_version_id || null);
        setSaveState(document.current_version ? 'saved' : 'draft');
      })
      .catch((error) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          expireSession();
          navigate('/login', { replace: true, state: { expired: true } });
          return;
        }
        setLoadError(error.status === 404
          ? 'Esta carta no existe o ya no tienes acceso.'
          : 'No se pudo abrir la carta. Comprueba tu conexión e inténtalo de nuevo.');
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [documentId, expireSession, navigate]);

  useEffect(() => {
    if (loading || loadError || !csrfToken || collabRef.current) return undefined;
    const room = createCollaborativeDocument({
      documentId,
      csrfToken,
      onStatusChange: setCollabStatus,
      onSynced: () => setSynced(true),
      onLocalUpdate: () => setPendingUpdates((count) => count + 1),
      onUpdatePersisted: () => setPendingUpdates((count) => Math.max(0, count - 1)),
      onAwarenessChange: (states) => setAwareness([...states.values()].map((state) => state.user).filter(Boolean)),
      onError: () => setSaveError('No se pudo sincronizar un cambio. Mantén esta pestaña abierta e inténtalo de nuevo.'),
    });
    collabRef.current = room;
    room.awareness.setLocalStateField('user', {
      name: user?.display_name || 'Miembro',
      color: '#a40000',
      colorLight: '#a4000033',
    });
    setCollab(room);
    return () => {
      collabRef.current = null;
      room.close();
    };
  }, [loading, loadError, csrfToken, documentId, user]);

  useEffect(() => {
    if (!collab || !synced) return undefined;
    const syncMetadata = () => {
      const next = parseMetadataMap(collab.metadata);
      fieldsRef.current = next;
      setFields(next);
    };
    const syncBody = () => {
      const next = collab.body.toString();
      bodyRef.current = next;
      setBody(next);
    };
    collab.metadata.observe(syncMetadata);
    collab.body.observe(syncBody);
    syncMetadata();
    syncBody();
    return () => {
      collab.metadata.unobserve(syncMetadata);
      collab.body.unobserve(syncBody);
    };
  }, [collab, synced]);

  useEffect(() => {
    if (!collab || !synced || !fields) return;
    updateMap(collab.metadata, fields);
  }, [collab, synced, fields]);

  useEffect(() => {
    if (!fields?.date) return undefined;
    let active = true;
    setEventLoadError('');
    listEvents(Number(fields.date.slice(0, 4)))
      .then((page) => { if (active) setEvents(page.items); })
      .catch(() => { if (active) setEventLoadError('No se pudieron cargar los eventos.'); });
    return () => { active = false; };
  }, [fields?.date]);

  useEffect(() => {
    if (!fields?.event_id) {
      setSelectedEvent(null);
      return undefined;
    }
    const available = events.find((event) => event.id === fields.event_id);
    if (available) {
      setSelectedEvent(available);
      return undefined;
    }
    let active = true;
    getEvent(fields.event_id)
      .then((event) => { if (active) setSelectedEvent(event); })
      .catch(() => { if (active) setSelectedEvent(null); });
    return () => { active = false; };
  }, [fields?.event_id, events]);

  useEffect(() => {
    if (pendingUpdates === 0 && saveState === 'pending') {
      setSaveState(currentVersion ? 'saved' : 'draft');
    }
  }, [pendingUpdates, saveState, currentVersion]);

  const markEdited = useCallback(() => {
    setSaveState('pending');
    setSaveError('');
  }, []);

  const handleFieldChange = (key, value) => {
    if (identifier && key === 'document_type') return;
    setFields((current) => ({ ...current, [key]: value }));
    markEdited();
  };

  const handlePartyChange = (key, value) => {
    setFields((current) => ({ ...current, [key]: value }));
    markEdited();
  };

  const handleCreateEvent = async (event) => {
    event.preventDefault();
    setEventCreating(true);
    setEventCreateError('');
    try {
      const created = await createEvent({ name: eventName, year: Number(fields.date.slice(0, 4)) }, csrfToken);
      setEvents((current) => [...current, created]);
      setSelectedEvent(created);
      handleFieldChange('event_id', created.id);
      setEventName('');
      setShowEventForm(false);
    } catch (error) {
      setEventCreateError(error instanceof ApiError && error.status === 409
        ? 'Ya existe un evento con ese nombre para este año.'
        : 'No se pudo crear el evento. Comprueba el nombre e inténtalo de nuevo.');
    } finally {
      setEventCreating(false);
    }
  };

  const [editorExtensions, setEditorExtensions] = useState(null);

  useEffect(() => {
    if (!collab || !synced) return undefined;
    let active = true;
    Promise.all([import('@codemirror/lang-markdown'), import('y-codemirror.next')]).then(([language, collaboration]) => {
      if (active) setEditorExtensions([language.markdown(), collaboration.yCollab(collab.body, collab.awareness)]);
    });
    return () => { active = false; };
  }, [collab, synced]);

  useEffect(() => {
    if (!synced || !fields) return undefined;
    const sequence = ++previewSequence.current;
    window.clearTimeout(previewTimer.current);
    setPreviewState('rendering');
    setPreviewError('');
    previewTimer.current = window.setTimeout(async () => {
      try {
        const url = await renderDocumentPreview(buildMarkdown(fields, identifier, body));
        if (sequence !== previewSequence.current) {
          URL.revokeObjectURL(url);
          return;
        }
        setPreviewUrl((previous) => {
          if (previous) URL.revokeObjectURL(previous);
          return url;
        });
        setPreviewState('ready');
      } catch {
        if (sequence !== previewSequence.current) return;
        setPreviewState('error');
        setPreviewError('No se pudo actualizar la vista previa. Puedes seguir editando y reintentar.');
      }
    }, 650);
    return () => window.clearTimeout(previewTimer.current);
  }, [synced, fields, body, identifier]);

  useEffect(() => () => {
    window.clearTimeout(previewTimer.current);
    previewSequence.current += 1;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const handleBodyChange = (value) => {
    bodyRef.current = value;
    setBody(value);
    markEdited();
  };

  const handleSave = async () => {
    if (!synced || !fields || collabStatus !== 'connected') {
      setSaveError('Conéctate de nuevo para sincronizar la carta antes de guardarla.');
      return;
    }
    if (!bodyRef.current.trim()) {
      setSaveError('Escribe el contenido de la carta antes de guardar.');
      return;
    }
    setSaveState('saving');
    setSaveError('');
    const submittedBody = bodyRef.current;
    const submittedFields = fieldsRef.current || fields;
    try {
      const checkpoint = await checkpointDocument(documentId, csrfToken);
      if (checkpoint.body !== submittedBody || !matchesCheckpoint(submittedFields, checkpoint)) {
        throw new ApiError(409, 'CONFLICT');
      }
      const saved = await saveDocument(documentId, {
        expected_revision: checkpoint.draft_revision,
        expected_source_hash: checkpoint.source_hash,
        metadata: saveMetadata(submittedFields),
        body: submittedBody,
      }, csrfToken);
      setIdentifier(saved.document.metadata.identifier);
      setCurrentVersion(saved.version.id);
      setPendingUpdates(0);
      setSaveState(bodyRef.current === submittedBody
        && JSON.stringify(saveMetadata(fieldsRef.current || fields)) === JSON.stringify(saveMetadata(submittedFields))
        ? 'saved'
        : 'pending');
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        expireSession();
        navigate('/login', { replace: true, state: { expired: true } });
        return;
      }
      if (error instanceof ApiError && error.status === 409) {
        setSaveError('Otra persona guardó cambios recientes. La sincronización está activa; vuelve a guardar en unos segundos.');
      } else {
        setSaveError('No se pudo guardar la carta. Comprueba la conexión e inténtalo de nuevo.');
      }
      setSaveState('error');
    }
  };

  const saveLabel = {
    draft: 'Borrador sin número',
    pending: 'Cambios pendientes',
    saving: 'Guardando…',
    saved: currentVersion ? 'Versión guardada' : 'Borrador sincronizado',
    error: 'Guardado pendiente',
  }[saveState];

  const handleTabKeyDown = (event) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const nextTab = mobileTab === 'edit' ? 'preview' : 'edit';
    setMobileTab(nextTab);
    document.getElementById(`${nextTab}-tab`).focus();
  };

  if (loading) return <p className="screen-status" role="status">Abriendo la carta…</p>;
  if (loadError) return <div className="editor-load-error"><p className="notice notice--error" role="alert">{loadError}</p><Link className="button-quiet" to="/documents">Volver a cartas</Link></div>;

  return (
    <section aria-labelledby="editor-title" className="workspace-page">
      <header className="workspace-heading">
        <div className="workspace-heading__title">
          <Link className="back-link" to="/documents">Cartas</Link>
          <h1 id="editor-title">{fields?.topic || 'Nueva carta'}</h1>
          <p className="workspace-heading__identifier">{identifier || 'Borrador sin número'}</p>
        </div>
        <div className="workspace-heading__actions">
          <div className="collaboration-status" aria-live="polite">
            <span aria-hidden="true" className={`status-indicator status-indicator--${collabStatus}`} />
            <span>{connectionLabels[collabStatus]}</span>
            {awareness.length > 0 && <span className="collaboration-status__people">{awareness.length} en la carta</span>}
          </div>
          <span className={`save-status save-status--${saveState}`} role="status">{pendingUpdates > 0 ? 'Sincronización pendiente' : saveLabel}</span>
          <LetterAssistancePanel
            documentId={documentId}
            csrfToken={csrfToken}
            body={body}
            isNumbered={Boolean(identifier)}
          />
          <DocumentMailPanel
            documentId={documentId}
            csrfToken={csrfToken}
            currentVersionId={currentVersion}
            finalizedVersionId={finalizedVersionId}
            identifier={identifier}
            topic={fields?.topic || ''}
            recipientEmail={fields?.recipient?.email || ''}
            onFinalized={setFinalizedVersionId}
          />
          <button className="button-primary workspace-save" disabled={!synced || saveState === 'saving'} onClick={handleSave} type="button">
            Guardar
          </button>
        </div>
      </header>

      {saveError && <p className="notice notice--error workspace-notice" role="alert">{saveError}</p>}
      {collabStatus === 'unauthorized' && <p className="notice notice--error workspace-notice" role="alert">Perdiste el acceso a esta carta. Los cambios que aún no se sincronizaron no se enviarán.</p>}

      <div aria-label="Vista del espacio de edición" className="workspace-tabs" onKeyDown={handleTabKeyDown} role="tablist">
        <button aria-controls="editor-panel" aria-selected={mobileTab === 'edit'} className={mobileTab === 'edit' ? 'is-selected' : ''} id="edit-tab" onClick={() => setMobileTab('edit')} role="tab" tabIndex={mobileTab === 'edit' ? 0 : -1} type="button">Editar</button>
        <button aria-controls="preview-panel" aria-selected={mobileTab === 'preview'} className={mobileTab === 'preview' ? 'is-selected' : ''} id="preview-tab" onClick={() => setMobileTab('preview')} role="tab" tabIndex={mobileTab === 'preview' ? 0 : -1} type="button">Vista previa</button>
      </div>

      <div className="workspace-columns">
        <section aria-labelledby="edit-tab" className={`workspace-editor${mobileTab === 'preview' ? ' is-mobile-hidden' : ''}`} id="editor-panel" role="tabpanel" tabIndex={0}>
          <div className="editor-fields">
            <div className="editor-fields__topline">
              <h2>Datos de la carta</h2>
              <span>Plantilla académica predeterminada</span>
            </div>
            <div className="editor-fields__row">
              <label className="editor-field">
                <span>Tipo de carta</span>
                <select disabled={Boolean(identifier)} onChange={(event) => handleFieldChange('document_type', event.target.value)} value={fields?.document_type || 'SOL'}>
                  {documentTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <label className="editor-field">
                <span>Fecha</span>
                <input onChange={(event) => handleFieldChange('date', event.target.value)} type="date" value={fields?.date || ''} />
              </label>
            </div>
            <label className="editor-field">
              <span>Asunto</span>
              <input maxLength="200" onChange={(event) => handleFieldChange('topic', event.target.value)} placeholder="Por ejemplo, solicitud de aula" value={fields?.topic || ''} />
            </label>
            <label className="editor-field">
              <span>Referencia</span>
              <input maxLength="300" onChange={(event) => handleFieldChange('reference', event.target.value)} value={fields?.reference || ''} />
            </label>
            <div className="editor-event-field">
              <label className="editor-field" htmlFor="event-select">
                <span>Evento (opcional)</span>
                <select id="event-select" onChange={(event) => handleFieldChange('event_id', event.target.value || null)} value={fields?.event_id || ''}>
                  <option value="">Sin evento</option>
                  {selectedEvent && !events.some((item) => item.id === selectedEvent.id) && <option value={selectedEvent.id}>{selectedEvent.name} ({selectedEvent.year})</option>}
                  {events.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.year})</option>)}
                </select>
              </label>
              {!showEventForm && <button className="button-quiet editor-event-create" onClick={() => setShowEventForm(true)} type="button">Crear evento</button>}
              {eventLoadError && <p className="field-error" role="status">{eventLoadError}</p>}
              {showEventForm && (
                <form className="editor-event-create__form" onSubmit={handleCreateEvent}>
                  <label className="editor-field" htmlFor="event-name"><span>Nombre del evento, {fields?.date?.slice(0, 4)}</span><input autoFocus id="event-name" maxLength="140" onChange={(event) => setEventName(event.target.value)} required value={eventName} /></label>
                  {eventCreateError && <p className="field-error" role="alert">{eventCreateError}</p>}
                  <div className="editor-event-create__actions"><button className="button-primary" disabled={eventCreating || !eventName.trim()} type="submit">{eventCreating ? 'Creando…' : 'Guardar evento'}</button><button className="button-quiet" onClick={() => { setShowEventForm(false); setEventCreateError(''); }} type="button">Cancelar</button></div>
                </form>
              )}
            </div>
            <RecipientContactFields csrfToken={csrfToken} onChange={(value) => handlePartyChange('recipient', value)} value={fields?.recipient || emptyFields().recipient} />
            <RecipientFields label="Remitente" onChange={(value) => handlePartyChange('sender', value)} prefix="sender" value={fields?.sender || emptyFields().sender} />
            <label className="editor-field">
              <span>Saludo</span>
              <input maxLength="300" onChange={(event) => handleFieldChange('salutation', event.target.value)} value={fields?.salutation || ''} />
            </label>
            <label className="editor-field">
              <span>Despedida</span>
              <input maxLength="300" onChange={(event) => handleFieldChange('signoff', event.target.value)} value={fields?.signoff || ''} />
            </label>
          </div>
          <div className="editor-body">
            <div className="editor-body__heading">
              <h2>Contenido en Markdown</h2>
              <span>{synced ? 'Los cambios se sincronizan al escribir' : 'Conectando al espacio compartido'}</span>
            </div>
            {!synced || !editorExtensions ? <p className="inline-status" role="status">Cargando contenido compartido…</p> : (
              <Suspense fallback={<p className="inline-status" role="status">Preparando el editor…</p>}>
                <CodeMirror
                  aria-label="Contenido de la carta en Markdown"
                  basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true }}
                  extensions={editorExtensions}
                  editable={collabStatus !== 'unauthorized'}
                  height="480px"
                  onChange={handleBodyChange}
                  value={body}
                  className="letter-code-editor"
                />
              </Suspense>
            )}
          </div>
        </section>

        <section aria-labelledby="preview-tab" className={`workspace-preview${mobileTab === 'edit' ? ' is-mobile-hidden' : ''}`} id="preview-panel" role="tabpanel" tabIndex={0}>
          <div className="preview-heading">
            <div>
              <h2>Vista previa</h2>
              <p>PDF actualizado desde tu borrador</p>
            </div>
            {previewUrl && <a className="button-quiet" download="vista-previa.pdf" href={previewUrl}>Descargar vista previa</a>}
          </div>
          {(previewState === 'loading' || previewState === 'rendering') && <p className="preview-message" role="status">{previewState === 'loading' ? 'Preparando el PDF…' : 'Actualizando la vista previa…'}</p>}
          {previewError && <p className="notice notice--error" role="alert">{previewError}</p>}
          {previewUrl && <Suspense fallback={<p className="preview-message" role="status">Preparando el visor PDF…</p>}><PdfPreview source={previewUrl} /></Suspense>}
          {previewState === 'error' && !previewUrl && <p className="preview-message">La edición sigue disponible. Corrige el contenido para generar una vista previa.</p>}
        </section>
      </div>
    </section>
  );
}
