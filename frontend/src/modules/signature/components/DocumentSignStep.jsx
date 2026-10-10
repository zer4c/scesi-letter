import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider.jsx';
import {
  ApiError,
  createSigningAuthorization,
  getSignature,
  signDocumentVersion,
} from '../../../core/api.js';
import { decryptInWorker, terminateSignatureWorker } from '../signatureCrypto.js';
import './DocumentSignStep.css';

const WRONG_PASSWORD = 'La contraseña no coincide. La carta no se firmó.';

function describeError(error) {
  if (!(error instanceof ApiError)) {
    return 'No se pudo firmar la carta. Comprueba la conexión e inténtalo de nuevo.';
  }
  if (error.status === 401) return WRONG_PASSWORD;
  if (error.status === 429) return 'Demasiados intentos. Espera unos minutos antes de volver a intentarlo.';
  if (error.code === 'SIGNATURE_DOES_NOT_FIT') {
    return 'La firma no cabe: el texto ocupa el espacio reservado para ella al final de la página. Acorta la carta y guarda de nuevo.';
  }
  if (error.code === 'CONFLICT') {
    return 'La carta cambió después de guardar esta versión. Guarda de nuevo y firma la versión más reciente.';
  }
  if (error.code === 'SIGNATURE_LOCKED') {
    return 'La autorización para firmar venció o ya se usó. Vuelve a intentarlo.';
  }
  if ([413, 415, 422].includes(error.status)) {
    return 'La imagen de tu firma no es válida. Vuelve a subirla en Firma.';
  }
  return 'No se pudo generar el PDF firmado. Inténtalo de nuevo en unos segundos.';
}

export default function DocumentSignStep({ documentId, version, disabled, onSigned }) {
  const { csrfToken, user } = useAuth();
  const envelope = useRef(null);
  const [envelopeState, setEnvelopeState] = useState('loading');
  const [expanded, setExpanded] = useState(false);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    getSignature()
      .then((stored) => {
        if (!active) return;
        envelope.current = stored;
        setEnvelopeState('ready');
      })
      .catch((requestError) => {
        if (active) setEnvelopeState(requestError?.status === 404 ? 'missing' : 'unavailable');
      });
    return () => {
      active = false;
      envelope.current = null;
      terminateSignatureWorker();
    };
  }, []);

  useEffect(() => {
    setExpanded(false);
    setPassword('');
    setError('');
  }, [version.id]);

  const cancel = () => {
    setExpanded(false);
    setPassword('');
    setError('');
  };

  const handleSign = async (event) => {
    event.preventDefault();
    if (busy || !password || !envelope.current) return;
    setBusy(true);
    setError('');
    let imageBytes;
    try {
      try {
        imageBytes = await decryptInWorker(envelope.current, password, user.id);
      } catch {
        setError(WRONG_PASSWORD);
        return;
      }
      const authorization = await createSigningAuthorization({
        password,
        document_id: documentId,
        source_hash: version.source_hash,
        version_id: version.id,
      }, csrfToken);
      const signed = await signDocumentVersion(
        documentId, version.id, authorization.authorization_token, imageBytes, csrfToken,
      );
      setExpanded(false);
      onSigned(signed);
    } catch (signError) {
      setError(describeError(signError));
    } finally {
      imageBytes?.fill(0);
      setPassword('');
      setBusy(false);
    }
  };

  return (
    <>
      <h3>Firmar y finalizar esta versión</h3>
      {envelopeState === 'loading' && <p role="status">Comprobando tu firma…</p>}
      {envelopeState === 'missing' && (
        <p>Todavía no guardaste una firma. <Link to="/settings/signature">Súbela en Firma</Link> para poder aplicarla.</p>
      )}
      {envelopeState === 'unavailable' && (
        <p role="alert">No se pudo comprobar tu firma. Cierra este panel y vuelve a abrirlo.</p>
      )}
      {envelopeState === 'ready' && !expanded && (
        <>
          <p>Tu firma se inserta en el espacio fijo de la plantilla y se crea una versión nueva, ya finalizada. Quien abra ese PDF podrá ver la firma.</p>
          <button className="button-secondary sign-step__start" disabled={disabled} onClick={() => setExpanded(true)} type="button">Firmar con mi firma</button>
        </>
      )}
      {envelopeState === 'ready' && expanded && (
        <form className="sign-step__form" onSubmit={handleSign}>
          <p>Vas a firmar la versión {version.version_number}, con PDF {version.pdf_hash.slice(0, 12)}. La firma se descifra en este navegador con tu contraseña.</p>
          <label className="editor-field" htmlFor="sign-step-password"><span>Contraseña de tu cuenta</span>
            <input autoComplete="current-password" autoFocus disabled={busy} id="sign-step-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
          </label>
          <div className="sign-step__actions">
            <button className="button-primary" disabled={busy || !password} type="submit">{busy ? 'Firmando…' : 'Firmar y finalizar'}</button>
            <button className="button-quiet" disabled={busy} onClick={cancel} type="button">Cancelar</button>
          </div>
        </form>
      )}
      {error && <p className="notice notice--error sign-step__error" role="alert">{error}</p>}
    </>
  );
}
