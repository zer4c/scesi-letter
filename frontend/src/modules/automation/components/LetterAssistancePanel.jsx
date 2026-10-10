import { useEffect, useRef, useState } from 'react';
import { ApiError, checkpointDocument } from '../../../core/api.js';
import {
  acceptLetterSuggestion,
  analyzeLetter,
  createPrivacyPreview,
  findContactsByRole,
  rejectLetterSuggestion,
} from '../services/letterAssistance.js';
import { hasOverlappingRange, toCodePointOffset } from '../utils/offsets.js';
import './LetterAssistancePanel.css';

const suggestionLabels = {
  grammar: 'Ortografía y gramática',
  style: 'Redacción',
  reference: 'Contenido de la carta',
  document_type: 'Tipo de documento',
  topic: 'Asunto',
  recipient_role: 'Destinatario por cargo',
};

const roleLabels = {
  director_carrera: 'Dirección de carrera',
};

function suggestionReplacement(suggestion) {
  if (suggestion.kind === 'recipient_role') {
    return `Cargo sugerido: ${roleLabels[suggestion.replacement] || suggestion.replacement.replaceAll('_', ' ')}`;
  }
  return suggestion.replacement;
}

function publicError(error) {
  if (error instanceof ApiError && error.status === 409) {
    return 'La carta cambió durante la revisión. Actualiza las sugerencias antes de continuar.';
  }
  if (error instanceof ApiError && error.code === 'LLM_DISABLED') {
    return 'La asistencia está desactivada. Puedes continuar editando y guardar la carta.';
  }
  if (error instanceof ApiError && error.code === 'LLM_RATE_LIMITED') {
    return 'Se alcanzó el límite temporal de revisiones. Inténtalo más tarde.';
  }
  if (error instanceof ApiError && error.code === 'PRIVACY_PREVIEW_EXPIRED') {
    return 'La confirmación de privacidad venció. Revisa nuevamente el texto protegido.';
  }
  return 'No se pudo completar la revisión. La edición y el guardado siguen disponibles.';
}

export default function LetterAssistancePanel({ documentId, csrfToken, body, isNumbered }) {
  const dialogRef = useRef(null);
  const sourceTextRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState('idle');
  const [sourceBody, setSourceBody] = useState('');
  const [sourceHash, setSourceHash] = useState('');
  const [privacyPreview, setPrivacyPreview] = useState(null);
  const [manualRedactions, setManualRedactions] = useState([]);
  const [selection, setSelection] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [selectedContacts, setSelectedContacts] = useState({});
  const [contactResults, setContactResults] = useState({});
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');
  const [stale, setStale] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (open && dialog && !dialog.open) dialog.showModal();
    if (!open && dialog?.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (!open || !sourceBody || body === sourceBody) return;
    if (phase === 'preview' || phase === 'analyzing') {
      setPrivacyPreview(null);
      setConfirmed(false);
      setStale(true);
      setPhase('stale');
    }
    if (phase === 'results') setStale(true);
  }, [body, open, phase, sourceBody]);

  async function buildPreview(ranges, expectedBody = null) {
    setPhase('preview_loading');
    setError('');
    setPrivacyPreview(null);
    setConfirmed(false);
    try {
      const checkpoint = await checkpointDocument(documentId, csrfToken);
      if (!checkpoint.body.trim()) {
        setError('Escribe el contenido de la carta antes de solicitar una revisión.');
        setPhase('error');
        return;
      }
      if (expectedBody !== null && checkpoint.body !== expectedBody) {
        setStale(true);
        setPhase('stale');
        setError('La carta cambió mientras preparabas las zonas privadas. Vuelve a iniciar la revisión.');
        return;
      }
      const preview = await createPrivacyPreview(
        documentId,
        checkpoint.source_hash,
        ['grammar', 'style', 'reference', 'document_type', 'topic', 'recipient_role'],
        ranges,
        csrfToken,
      );
      setSourceBody(checkpoint.body);
      setSourceHash(checkpoint.source_hash);
      setManualRedactions(ranges);
      setPrivacyPreview(preview);
      setStale(false);
      setPhase('preview');
    } catch (requestError) {
      setError(publicError(requestError));
      setPhase('error');
    }
  }

  async function openReview() {
    setOpen(true);
    setPhase('preview_loading');
    setSuggestions([]);
    setManualRedactions([]);
    setStale(false);
    await buildPreview([]);
  }

  function captureSelection() {
    const textarea = sourceTextRef.current;
    if (!textarea || textarea.selectionStart === textarea.selectionEnd) {
      setSelection(null);
      setError('Selecciona primero el fragmento que quieres ocultar al proveedor.');
      return;
    }
    const start = toCodePointOffset(sourceBody, textarea.selectionStart);
    const end = toCodePointOffset(sourceBody, textarea.selectionEnd);
    setSelection({ start, end });
    setError('');
  }

  async function maskSelection(event) {
    event.preventDefault();
    if (!selection) return;
    if (hasOverlappingRange(manualRedactions, selection.start, selection.end)) {
      setError('Ese fragmento ya está cubierto por una zona manual.');
      return;
    }
    const ranges = [...manualRedactions, selection].sort((a, b) => a.start - b.start);
    setSelection(null);
    await buildPreview(ranges, sourceBody);
  }

  async function runAnalysis() {
    if (!privacyPreview || !confirmed || !privacyPreview.analysis_available || stale) return;
    setPhase('analyzing');
    setError('');
    try {
      const result = await analyzeLetter(
        documentId,
        sourceHash,
        ['grammar', 'style', 'reference', 'document_type', 'topic', 'recipient_role'],
        privacyPreview.preview_token,
        manualRedactions,
        csrfToken,
      );
      setSuggestions(result.suggestions);
      setPhase('results');
    } catch (requestError) {
      setError(publicError(requestError));
      setPhase(requestError instanceof ApiError && requestError.status === 409 ? 'stale' : 'error');
      if (requestError instanceof ApiError && requestError.status === 409) setStale(true);
    }
  }

  async function loadRoleContacts(suggestion) {
    setBusyId(suggestion.id);
    setError('');
    try {
      const result = await findContactsByRole(suggestion.replacement);
      setContactResults((current) => ({ ...current, [suggestion.id]: result.items }));
    } catch (requestError) {
      setError(publicError(requestError));
    } finally {
      setBusyId('');
    }
  }

  async function accept(suggestion) {
    const contactId = selectedContacts[suggestion.id] || null;
    if (suggestion.kind === 'recipient_role' && !contactId) {
      setError('Elige una persona del directorio para confirmar el destinatario.');
      return;
    }
    setBusyId(suggestion.id);
    setError('');
    try {
      const checkpoint = await checkpointDocument(documentId, csrfToken);
      if (checkpoint.source_hash !== suggestion.source_hash) {
        setStale(true);
        setPhase('stale');
        setError('La carta cambió. Estas sugerencias ya no se pueden aplicar.');
        return;
      }
      const accepted = await acceptLetterSuggestion(
        documentId,
        suggestion.id,
        checkpoint.source_hash,
        csrfToken,
        contactId,
      );
      setSuggestions((current) => current.map((item) => (
        item.id === accepted.id
          ? accepted
          : item.status === 'proposed' ? { ...item, status: 'stale' } : item
      )));
      setStale(true);
    } catch (requestError) {
      setError(publicError(requestError));
      if (requestError instanceof ApiError && requestError.status === 409) {
        setStale(true);
        setPhase('stale');
      }
    } finally {
      setBusyId('');
    }
  }

  async function reject(suggestion) {
    setBusyId(suggestion.id);
    setError('');
    try {
      const rejected = await rejectLetterSuggestion(documentId, suggestion.id, csrfToken);
      setSuggestions((current) => current.map((item) => (
        item.id === rejected.id ? rejected : item
      )));
    } catch (requestError) {
      setError(publicError(requestError));
    } finally {
      setBusyId('');
    }
  }

  function closeReview() {
    setOpen(false);
    setPhase('idle');
    setError('');
  }

  return (
    <>
      <button className="button-quiet assistance-trigger" onClick={openReview} type="button">
        Revisar con IA
      </button>
      <dialog
        aria-labelledby="assistance-title"
        className="assistance-dialog"
        onCancel={closeReview}
        onClose={() => setOpen(false)}
        ref={dialogRef}
      >
        <div className="assistance-dialog__header">
          <div>
            <h2 id="assistance-title">Revisión de la carta</h2>
            <p>El texto protegido se revisa antes de cualquier envío.</p>
          </div>
          <button aria-label="Cerrar revisión" className="button-quiet" onClick={closeReview} type="button">Cerrar</button>
        </div>

        {phase === 'preview_loading' && <p className="assistance-status" role="status">Preparando una copia privada…</p>}
        {error && <p className="notice notice--error" role="alert">{error}</p>}

        {(phase === 'preview' || phase === 'analyzing' || phase === 'stale') && (
          <div className="assistance-privacy">
            <p className="assistance-privacy__notice">
              Se enviarán el cuerpo enmascarado, los tipos de revisión y conteos locales por cargo.
              No se envían nombres detectados, datos de contacto, plantilla, firma ni otros campos de la carta.
            </p>
            <div className="assistance-privacy__columns">
              <label className="assistance-source">
                <span>Texto local. Selecciona datos que también quieras ocultar.</span>
                <textarea
                  onSelect={captureSelection}
                  readOnly
                  ref={sourceTextRef}
                  value={sourceBody}
                />
              </label>
              <div className="assistance-redacted">
                <h3>Vista que recibirá el proveedor</h3>
                <pre>{privacyPreview?.redacted_body || 'La vista privada se está actualizando.'}</pre>
                <p>{privacyPreview?.redaction_count ?? 0} fragmentos ocultos automáticamente</p>
              </div>
            </div>
            <div className="assistance-privacy__actions">
              <button
                className="button-quiet"
                disabled={!selection || phase === 'analyzing' || stale}
                onClick={maskSelection}
                type="button"
              >
                Ocultar selección
              </button>
              <span>{manualRedactions.length} zonas añadidas manualmente</span>
              {manualRedactions.length > 0 && (
                <button className="button-quiet" disabled={phase === 'analyzing' || stale} onClick={() => buildPreview([], sourceBody)} type="button">
                  Quitar zonas añadidas
                </button>
              )}
            </div>
            {!stale && privacyPreview?.analysis_available ? (
              <label className="assistance-confirm">
                <input checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" />
                <span>Confirmo que la vista enmascarada no contiene datos que deban permanecer privados.</span>
              </label>
            ) : (
              <p className="assistance-disabled" role="status">
                {stale
                  ? 'La carta cambió. Prepara una nueva vista privada antes de revisar.'
                  : 'La asistencia externa está desactivada o no está configurada. Nada se enviará.'}
              </p>
            )}
            <div className="assistance-dialog__actions">
              <button
                className="button-primary"
                disabled={!confirmed || phase === 'analyzing' || stale || !privacyPreview?.analysis_available}
                onClick={runAnalysis}
                type="button"
              >
                {phase === 'analyzing' ? 'Revisando…' : 'Confirmar y revisar'}
              </button>
              {stale && <button className="button-quiet" onClick={() => buildPreview([])} type="button">Preparar otra vista</button>}
            </div>
          </div>
        )}

        {phase === 'results' && (
          <section aria-label="Sugerencias de revisión" className="assistance-results">
            <div className="assistance-results__heading">
              <h3>Sugerencias</h3>
              <p>Revisa cada cambio por separado. No se aplicará nada automáticamente.</p>
            </div>
            {suggestions.length === 0 ? (
              <p className="assistance-empty" role="status">No se encontraron sugerencias para esta revisión.</p>
            ) : (
              <ul className="assistance-list">
                {suggestions.map((suggestion) => {
                  const contacts = contactResults[suggestion.id];
                  const selectedContact = selectedContacts[suggestion.id];
                  const disabled = stale || suggestion.status !== 'proposed' || busyId === suggestion.id;
                  return (
                    <li className="assistance-suggestion" key={suggestion.id}>
                      <div className="assistance-suggestion__heading">
                        <h4>{suggestionLabels[suggestion.kind]}</h4>
                        <span className={`assistance-status-tag assistance-status-tag--${suggestion.status}`}>{suggestion.status === 'proposed' ? 'Pendiente' : suggestion.status === 'accepted' ? 'Aceptada' : suggestion.status === 'rejected' ? 'Descartada' : 'Desactualizada'}</span>
                      </div>
                      {suggestion.original && <p className="assistance-suggestion__original">{suggestion.original}</p>}
                      {suggestion.replacement && <p className="assistance-suggestion__replacement">{suggestionReplacement(suggestion)}</p>}
                      <p className="assistance-suggestion__reason">{suggestion.reason}</p>
                      {suggestion.kind === 'recipient_role' && suggestion.status === 'proposed' && (
                        <div className="assistance-candidates">
                          <button className="button-quiet" disabled={disabled} onClick={() => loadRoleContacts(suggestion)} type="button">
                            {busyId === suggestion.id ? 'Buscando…' : 'Buscar personas con este cargo'}
                          </button>
                          {contacts && contacts.length === 0 && <p role="status">No hay personas activas registradas con este cargo.</p>}
                          {contacts?.length > 0 && (
                            <fieldset>
                              <legend>Elige a quién dirigir la carta</legend>
                              {contacts.map((contact) => (
                                <label className="assistance-contact" key={contact.id}>
                                  <input
                                    checked={selectedContact === contact.id}
                                    disabled={disabled}
                                    name={`contact-${suggestion.id}`}
                                    onChange={() => setSelectedContacts((current) => ({ ...current, [suggestion.id]: contact.id }))}
                                    type="radio"
                                  />
                                  <span><strong>{contact.name}</strong><small>{contact.role_label} · {contact.institution}{contact.career ? ` · ${contact.career}` : ''}</small></span>
                                </label>
                              ))}
                            </fieldset>
                          )}
                        </div>
                      )}
                      {suggestion.kind === 'document_type' && isNumbered && suggestion.status === 'proposed' && (
                        <p className="assistance-suggestion__reason">El tipo de una carta numerada no se puede cambiar.</p>
                      )}
                      {suggestion.status === 'proposed' && (
                        <div className="assistance-suggestion__actions">
                          <button className="button-primary" disabled={disabled || (suggestion.kind === 'recipient_role' && !selectedContact) || (suggestion.kind === 'document_type' && isNumbered)} onClick={() => accept(suggestion)} type="button">
                            {suggestion.kind === 'recipient_role' ? 'Usar persona elegida' : 'Aceptar sugerencia'}
                          </button>
                          <button className="button-quiet" disabled={disabled} onClick={() => reject(suggestion)} type="button">Descartar</button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
            {stale && <p className="assistance-disabled" role="status">El texto cambió después de esta revisión. Las sugerencias pendientes ya no se pueden aplicar.</p>}
            <div className="assistance-dialog__actions">
              <button className="button-quiet" onClick={() => { setSuggestions([]); setStale(false); buildPreview([]); }} type="button">Revisar texto actualizado</button>
              <button className="button-primary" onClick={closeReview} type="button">Volver al editor</button>
            </div>
          </section>
        )}

        {phase === 'error' && (
          <div className="assistance-error-state">
            <p>La carta no cambió y sigue disponible en el editor.</p>
            <button className="button-quiet" onClick={() => buildPreview(manualRedactions)} type="button">Intentar de nuevo</button>
          </div>
        )}
      </dialog>
    </>
  );
}
