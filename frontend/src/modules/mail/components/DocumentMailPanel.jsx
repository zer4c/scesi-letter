import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ApiError,
  finalizeDocumentVersion,
  getArchiveStatus,
  getDocumentVersion,
  getJobStatus,
  listConnections,
  listDocumentVersions,
  sendDocumentMail,
  syncArchivedVersion,
} from '../../../core/api.js';
import DocumentSignStep from '../../signature/components/DocumentSignStep.jsx';
import './DocumentMailPanel.css';

const archiveLabels = {
  queued: 'Pendiente de sincronización',
  running: 'Sincronizando con Drive',
  retry_wait: 'La sincronización se reintentará',
  waiting_connection: 'Conecta el Drive institucional para archivar',
  needs_classification: 'Selecciona una categoría para archivar',
  succeeded: 'Archivado en Drive',
  failed: 'No se pudo archivar',
};

const jobLabels = {
  queued: 'En cola para enviar',
  running: 'Enviando',
  succeeded: 'Correo enviado',
  failed: 'No se pudo enviar. Revisa la conexión y los datos.',
  unknown: 'Gmail no confirmó el resultado. Revisa la carpeta Enviados antes de iniciar otro envío.',
};

const versionLabels = {
  queued: 'En cola', rendering: 'Generando PDF', ready: 'Lista', archived: 'Archivada',
  render_failed: 'Falló la generación', sync_failed: 'Falló la sincronización',
};

const categories = [
  ['classrooms', 'Ambientes'], ['furniture', 'Mobiliario'], ['requests', 'Peticiones'],
  ['invitations', 'Invitaciones'], ['notifications', 'Notificaciones'],
  ['permissions', 'Permisos'], ['presentations', 'Presentaciones'],
  ['activities', 'Actividades'], ['miscellaneous', 'Misceláneo'],
];

function parseAddresses(value) {
  return value.split(/[;,]/).map((item) => item.trim()).filter(Boolean);
}

function showError(error) {
  if (error?.status === 409 && error?.code === 'VERSION_NOT_SENDABLE') {
    return 'La versión dejó de estar lista para enviar. Actualiza la selección y vuelve a revisarla.';
  }
  if (error?.status === 403) return 'La cuenta seleccionada no tiene permiso para enviar.';
  if (error?.status === 422) return 'Revisa los correos, el asunto y el cuerpo del mensaje.';
  if (error?.status === 503) return 'El servicio de correo no está disponible. Puedes descargar el PDF e intentarlo más tarde.';
  return 'No se pudo completar la operación. Comprueba la conexión e inténtalo de nuevo.';
}

export default function DocumentMailPanel({
  documentId,
  csrfToken,
  currentVersionId,
  finalizedVersionId,
  identifier,
  topic,
  recipientEmail,
  onFinalized,
  onSigned,
}) {
  const dialogRef = useRef(null);
  const pendingDispatch = useRef(null);
  const submissionLock = useRef(false);
  const [open, setOpen] = useState(false);
  const [versions, setVersions] = useState([]);
  const [selectedVersionId, setSelectedVersionId] = useState('');
  const [version, setVersion] = useState(null);
  const [archive, setArchive] = useState(null);
  const [connections, setConnections] = useState([]);
  const [connectionId, setConnectionId] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingSubmission, setPendingSubmission] = useState(false);
  const [error, setError] = useState('');
  const [archiveCategory, setArchiveCategory] = useState('');
  const [confirmFinalize, setConfirmFinalize] = useState(false);
  const [signedNotice, setSignedNotice] = useState('');
  const [to, setTo] = useState(recipientEmail || '');
  const [cc, setCc] = useState('');
  const [bcc, setBcc] = useState('');
  const [showCopyFields, setShowCopyFields] = useState(false);
  const [subject, setSubject] = useState(`Carta ${identifier || topic || ''}`.trim());
  const [toEdited, setToEdited] = useState(false);
  const [subjectEdited, setSubjectEdited] = useState(false);
  const [body, setBody] = useState('Adjunto encontrará la carta solicitada.');
  const [confirmed, setConfirmed] = useState(false);
  const [job, setJob] = useState(null);
  const [reviewedUnknown, setReviewedUnknown] = useState(false);

  const selectedVersionIsFinal = version?.finalized_at
    && finalizedVersionId === selectedVersionId;
  const canSend = selectedVersionIsFinal && version?.status === 'archived'
    && archive?.status === 'succeeded' && archive?.pdf_file_id;
  const activeConnections = useMemo(
    () => connections.filter((item) => item.kind === 'gmail' && item.status === 'active'),
    [connections],
  );
  const selectedConnection = activeConnections.find((item) => item.id === connectionId);

  useEffect(() => {
    if (!toEdited) setTo(recipientEmail || '');
  }, [recipientEmail, toEdited]);

  useEffect(() => {
    if (!subjectEdited) setSubject(`Carta ${identifier || topic || ''}`.trim());
  }, [identifier, topic, subjectEdited]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([listDocumentVersions(documentId), listConnections()])
      .then(([versionItems, integrationStatus]) => {
        if (!active) return;
        setVersions(versionItems);
        const defaultVersion = versionItems.find((item) => item.id === currentVersionId) || versionItems[0];
        setSelectedVersionId(defaultVersion?.id || '');
        const available = integrationStatus.connections || [];
        setConnections(available);
        const defaultConnection = available.find((item) => item.kind === 'gmail' && item.status === 'active' && item.mode === 'personal')
          || available.find((item) => item.kind === 'gmail' && item.status === 'active');
        setConnectionId(defaultConnection?.id || '');
      })
      .catch(() => { if (active) setError('No se pudieron cargar las versiones o las cuentas de envío.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, documentId, currentVersionId]);

  useEffect(() => {
    if (!open || !selectedVersionId) {
      setVersion(null);
      setArchive(null);
      return undefined;
    }
    let active = true;
    setVersion(null);
    setArchive(null);
    setArchiveCategory('');
    Promise.all([
      getDocumentVersion(documentId, selectedVersionId),
      getArchiveStatus(documentId, selectedVersionId).catch(() => null),
    ]).then(([detail, archiveStatus]) => {
      if (!active) return;
      setVersion(detail);
      setArchive(archiveStatus);
      setConfirmFinalize(false);
      setError('');
    }).catch(() => {
      if (active) setError('No se pudo cargar la versión seleccionada.');
    });
    return () => { active = false; };
  }, [open, selectedVersionId, documentId]);

  useEffect(() => {
    if (!open || !archive || !['queued', 'running', 'retry_wait'].includes(archive.status)) return undefined;
    let active = true;
    const timer = window.setTimeout(() => {
      getArchiveStatus(documentId, selectedVersionId)
        .then((status) => { if (active) setArchive(status); })
        .catch(() => {});
    }, 1800);
    return () => { active = false; window.clearTimeout(timer); };
  }, [open, archive, documentId, selectedVersionId]);

  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return undefined;
    let active = true;
    const timer = window.setTimeout(() => {
      getJobStatus(job.job_id)
        .then((status) => { if (active) setJob(status); })
        .catch(() => { if (active) setJob((current) => ({ ...current, status: 'unknown' })); });
    }, 1200);
    return () => { active = false; window.clearTimeout(timer); };
  }, [job]);

  const close = () => setOpen(false);

  const handleFinalize = async () => {
    if (!version?.pdf_hash) return;
    setBusy(true);
    setError('');
    try {
      const finalized = await finalizeDocumentVersion(
        documentId, selectedVersionId, version.pdf_hash, csrfToken,
      );
      setVersion(finalized);
      onFinalized(selectedVersionId);
      setConfirmFinalize(false);
      setArchive(await getArchiveStatus(documentId, selectedVersionId).catch(() => null));
    } catch (finalizeError) {
      setError(showError(finalizeError));
    } finally {
      setBusy(false);
    }
  };

  const handleSigned = (signed) => {
    setSignedNotice(`Carta firmada. Se creó la versión ${signed.version_number}, ya finalizada.`);
    onSigned(signed.version_id);
  };

  const handleArchiveRetry = async () => {
    setBusy(true);
    setError('');
    try {
      setArchive(await syncArchivedVersion(documentId, selectedVersionId, {
        topic_category: archiveCategory || undefined,
        confirm_miscellaneous: archiveCategory === 'miscellaneous',
      }, csrfToken));
    } catch (syncError) {
      setError(showError(syncError));
    } finally {
      setBusy(false);
    }
  };

  const handleSend = async (event) => {
    event.preventDefault();
    if (!canSend || !selectedConnection || !confirmed || job || busy || submissionLock.current || pendingSubmission) return;
    const toAddresses = parseAddresses(to);
    if (!toAddresses.length) {
      setError('Agrega al menos una dirección en Para.');
      return;
    }
    const requestPayload = {
        document_id: documentId,
        version_id: selectedVersionId,
        connection_id: connectionId,
        to: toAddresses,
        cc: parseAddresses(cc),
        bcc: parseAddresses(bcc),
        subject,
        body,
        confirmed: true,
      };
    pendingDispatch.current = { payload: requestPayload, key: crypto.randomUUID() };
    await submitPendingDispatch();
  };

  const submitPendingDispatch = async () => {
    if (!pendingDispatch.current || busy || submissionLock.current) return;
    submissionLock.current = true;
    setBusy(true);
    setError('');
    try {
      const response = await sendDocumentMail(
        pendingDispatch.current.payload,
        pendingDispatch.current.key,
        csrfToken,
      );
      pendingDispatch.current = null;
      setPendingSubmission(false);
      setJob(response);
      setConfirmed(false);
    } catch (sendError) {
      setError(showError(sendError));
      if (!(sendError instanceof ApiError) || sendError.status >= 500) {
        setPendingSubmission(true);
      } else {
        pendingDispatch.current = null;
        setPendingSubmission(false);
      }
    } finally {
      submissionLock.current = false;
      setBusy(false);
    }
  };

  const openDialog = () => {
    setConfirmed(false);
    setSignedNotice('');
    setOpen(true);
  };

  const prepareAnotherSend = () => {
    if (job?.status === 'unknown' && !reviewedUnknown) return;
    setJob(null);
    setConfirmed(false);
    setReviewedUnknown(false);
    setError('');
  };

  const selectedNumber = versions.find((item) => item.id === selectedVersionId)?.version_number;
  const pdfUrl = `/api/documents/${documentId}/versions/${selectedVersionId}/pdf`;
  const driveUrl = archive?.pdf_file_id
    ? `https://drive.google.com/file/d/${encodeURIComponent(archive.pdf_file_id)}/view`
    : null;

  return (
    <>
      <button className="button-quiet document-mail-trigger" onClick={openDialog} type="button">
        Versiones y envío
      </button>
      <dialog aria-labelledby="mail-panel-title" className="mail-panel" onCancel={(event) => { event.preventDefault(); close(); }} ref={dialogRef}>
        <header className="mail-panel__header">
          <div><h2 id="mail-panel-title">Finalizar y enviar PDF</h2><p>Selecciona la versión exacta que quieres conservar y enviar.</p></div>
          <button aria-label="Cerrar" className="button-quiet" onClick={close} type="button">Cerrar</button>
        </header>
        {loading ? <p className="mail-panel__status" role="status">Cargando versiones y cuentas…</p> : (
          <div className="mail-panel__content">
            {versions.length === 0 ? <p className="mail-panel__status">Guarda la carta para crear una versión inmutable antes de finalizarla.</p> : (
              <label className="editor-field" htmlFor="mail-version-select"><span>Versión de la carta</span>
                <select disabled={Boolean(job)} id="mail-version-select" onChange={(event) => setSelectedVersionId(event.target.value)} value={selectedVersionId}>
                  {versions.map((item) => <option key={item.id} value={item.id}>Versión {item.version_number} · {versionLabels[item.status] || 'Estado no disponible'} · {new Date(item.created_at).toLocaleDateString('es-BO')}</option>)}
                </select>
              </label>
            )}
            {version && (
              <section aria-label="PDF seleccionado" className="mail-panel__version">
                <h3>{version.metadata_snapshot.identifier || identifier || `Versión ${selectedNumber}`}</h3>
                <p>Versión {version.version_number} · {version.signature_owner_id ? 'Con firma' : 'Sin firma'}</p>
                {version.pdf_hash && <p className="mail-panel__hash">SHA-256: <code>{version.pdf_hash}</code></p>}
                {version.pdf_hash && <a className="button-quiet" href={pdfUrl}>Descargar este PDF</a>}
                {driveUrl && <a className="button-quiet" href={driveUrl} rel="noreferrer" target="_blank">Abrir PDF archivado en Drive</a>}
              </section>
            )}
            {version && !selectedVersionIsFinal && version.pdf_hash && ['ready', 'archived'].includes(version.status) && (
              <section className="mail-panel__step">
                <h3>{version.finalized_at ? 'Seleccionar esta versión para envío' : 'Finalizar esta versión'}</h3>
                <p>{version.finalized_at
                  ? 'La versión ya está congelada. Al seleccionarla, las futuras ediciones no cambiarán este PDF.'
                  : 'El PDF quedará congelado para el envío. Firmar es opcional; puedes imprimir y firmar en físico.'}</p>
                {!confirmFinalize ? (
                  <button className="button-primary" disabled={busy} onClick={() => setConfirmFinalize(true)} type="button">Continuar</button>
                ) : (
                  <div className="mail-panel__confirm-finalize">
                    <p>Confirmo que quiero finalizar la versión {version.version_number} con PDF {version.pdf_hash.slice(0, 12)}.</p>
                    <button className="button-primary" disabled={busy} onClick={handleFinalize} type="button">{busy ? 'Finalizando…' : 'Confirmar y congelar versión'}</button>
                    <button className="button-quiet" disabled={busy} onClick={() => setConfirmFinalize(false)} type="button">Cancelar</button>
                  </div>
                )}
              </section>
            )}
            {version && !version.finalized_at && !version.signature_owner_id && version.pdf_hash
              && version.status === 'ready' && selectedVersionId === currentVersionId && (
              <section className="mail-panel__step">
                <DocumentSignStep disabled={busy} documentId={documentId} onSigned={handleSigned} version={version} />
              </section>
            )}
            {signedNotice && <p className="mail-panel__status" role="status">{signedNotice}</p>}
            {selectedVersionIsFinal && version?.status !== 'archived' && (
              <section className="mail-panel__step">
                <h3>Archivo en Drive</h3>
                <p role="status">{archiveLabels[archive?.status] || 'La versión está finalizada; su archivo todavía no está confirmado.'}</p>
                {archive?.status === 'needs_classification' && <label className="editor-field" htmlFor="archive-category"><span>Clasificación</span><select id="archive-category" onChange={(event) => setArchiveCategory(event.target.value)} value={archiveCategory}><option value="">Selecciona una categoría</option>{categories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
                {['failed', 'waiting_connection', 'needs_classification'].includes(archive?.status) && <button className="button-quiet" disabled={busy || (archive.status === 'needs_classification' && !archiveCategory)} onClick={handleArchiveRetry} type="button">{busy ? 'Sincronizando…' : 'Reintentar sincronización'}</button>}
              </section>
            )}
            {canSend && !job && (
              <form className="mail-panel__form" onSubmit={handleSend}>
                <h3>Componer correo</h3>
                <label className="editor-field" htmlFor="mail-sender"><span>Enviar desde</span><select disabled={busy || pendingSubmission} id="mail-sender" onChange={(event) => setConnectionId(event.target.value)} value={connectionId}>{activeConnections.map((item) => <option key={item.id} value={item.id}>{item.mode === 'institutional' ? 'Institucional' : 'Personal'} · {item.google_account}</option>)}</select></label>
                <label className="editor-field" htmlFor="mail-to"><span>Para</span><input autoComplete="email" disabled={busy || pendingSubmission} id="mail-to" onChange={(event) => { setToEdited(true); setTo(event.target.value); }} placeholder="persona@institucion.edu" required value={to} /></label>
                <button aria-expanded={showCopyFields} className="button-quiet" disabled={busy || pendingSubmission} onClick={() => setShowCopyFields((shown) => !shown)} type="button">{showCopyFields ? 'Ocultar CC y CCO' : 'Agregar CC o CCO'}</button>
                {showCopyFields && <>
                  <label className="editor-field" htmlFor="mail-cc"><span>CC</span><input disabled={busy || pendingSubmission} id="mail-cc" onChange={(event) => setCc(event.target.value)} placeholder="Separar direcciones con coma" value={cc} /></label>
                  <label className="editor-field" htmlFor="mail-bcc"><span>CCO</span><input disabled={busy || pendingSubmission} id="mail-bcc" onChange={(event) => setBcc(event.target.value)} placeholder="Solo visible para quien envía" value={bcc} /></label>
                </>}
                <label className="editor-field" htmlFor="mail-subject"><span>Asunto</span><input disabled={busy || pendingSubmission} id="mail-subject" maxLength="200" onChange={(event) => { setSubjectEdited(true); setSubject(event.target.value); }} required value={subject} /></label>
                <label className="editor-field" htmlFor="mail-body"><span>Mensaje</span><textarea disabled={busy || pendingSubmission} id="mail-body" maxLength="1000" onChange={(event) => setBody(event.target.value)} required rows="4" value={body} /></label>
                <p className="mail-panel__attachment">Se adjuntará únicamente {version.metadata_snapshot.identifier || identifier}-v{String(version.version_number).padStart(4, '0')}.pdf. <span>El archivo Markdown no se adjunta.</span></p>
                <p className="mail-panel__confirm-summary"><strong>Desde:</strong> {selectedConnection?.google_account}<br /><strong>Para:</strong> {parseAddresses(to).join(', ')}<br />{parseAddresses(cc).length > 0 && <><strong>CC:</strong> {parseAddresses(cc).join(', ')}<br /></>}{parseAddresses(bcc).length > 0 && <><strong>CCO:</strong> {parseAddresses(bcc).join(', ')}<br /></>}<strong>PDF:</strong> {version.metadata_snapshot.identifier || identifier}-v{String(version.version_number).padStart(4, '0')}.pdf</p>
                <label className="mail-panel__confirm"><input checked={confirmed} disabled={busy || pendingSubmission} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" />Confirmo el remitente, las direcciones y el PDF seleccionado.</label>
                <button className="button-primary" disabled={!confirmed || busy || pendingSubmission || !selectedConnection || !parseAddresses(to).length} type="submit">{busy ? 'Enviando…' : 'Enviar correo'}</button>
              </form>
            )}
            {!selectedConnection && activeConnections.length === 0 && <p className="mail-panel__status">No hay una cuenta Gmail activa. Conecta una cuenta personal o institucional antes de enviar.</p>}
            {job && <section aria-live="polite" className={`mail-panel__result mail-panel__result--${job.status}`} role="status"><h3>{jobLabels[job.status] || 'Estado del envío desconocido'}</h3>{job.status === 'unknown' && <><p>No se reenviará automáticamente. Revisa Gmail antes de iniciar cualquier envío nuevo.</p><label className="mail-panel__confirm"><input checked={reviewedUnknown} onChange={(event) => setReviewedUnknown(event.target.checked)} type="checkbox" />Revisé Gmail y confirmo que no hay un correo duplicado.</label></>}{!['queued', 'running'].includes(job.status) && <button className="button-quiet" disabled={job.status === 'unknown' && !reviewedUnknown} onClick={prepareAnotherSend} type="button">Preparar otro envío</button>}</section>}
            {pendingSubmission && <section className="mail-panel__result mail-panel__result--unknown" aria-live="assertive" role="alert"><h3>No se pudo confirmar la solicitud</h3><p>Recuperar el estado volverá a usar la misma clave y el mismo contenido. No creará un segundo envío.</p><button className="button-quiet" disabled={busy} onClick={submitPendingDispatch} type="button">{busy ? 'Consultando…' : 'Recuperar solicitud'}</button></section>}
            {error && <p className="mail-panel__error" role="alert">{error}</p>}
          </div>
        )}
      </dialog>
    </>
  );
}
