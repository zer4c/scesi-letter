import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { ApiError, changePassword, getSignature, saveSignature } from '../../core/api.js';
import { useAuth } from '../auth/AuthProvider.jsx';
import { decryptInWorker, encryptInWorker, rewrapInWorker, terminateSignatureWorker } from './signatureCrypto.js';

const MAX_FILE_BYTES = 2 * 1024 * 1024;
const MAX_IMAGE_PIXELS = 4_000_000;

class SignatureActionError extends Error {}

async function normalizePng(file) {
  if (!file || file.type !== 'image/png' || file.size > MAX_FILE_BYTES) {
    throw new SignatureActionError('Selecciona una imagen PNG de hasta 2 MiB.');
  }
  const original = new Uint8Array(await file.arrayBuffer());
  let bitmap;
  try {
    const signature = [137, 80, 78, 71, 13, 10, 26, 10];
    if (!signature.every((value, index) => original[index] === value)) {
      throw new SignatureActionError('El archivo no contiene una imagen PNG válida.');
    }
    let chunkOffset = 8;
    while (chunkOffset + 12 <= original.length) {
      const chunkLength = new DataView(original.buffer, original.byteOffset, original.byteLength)
        .getUint32(chunkOffset);
      const chunkType = String.fromCharCode(...original.subarray(chunkOffset + 4, chunkOffset + 8));
      if (chunkType === 'acTL') throw new SignatureActionError('No se admiten imágenes PNG animadas.');
      if (chunkLength > original.length - chunkOffset - 12) break;
      chunkOffset += chunkLength + 12;
    }

    try {
      bitmap = await createImageBitmap(file);
    } catch {
      throw new SignatureActionError('No se pudo leer la imagen PNG. Selecciona un archivo válido.');
    }
    if (bitmap.width * bitmap.height > MAX_IMAGE_PIXELS) {
      throw new SignatureActionError('La imagen supera el límite de resolución permitido.');
    }
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext('2d', { alpha: true });
    if (!context) throw new SignatureActionError('No se pudo procesar la imagen.');
    context.drawImage(bitmap, 0, 0);
    const normalized = await new Promise((resolve, reject) => {
      canvas.toBlob((blob) => blob ? resolve(blob) : reject(new SignatureActionError('No se pudo normalizar la imagen.')), 'image/png');
    });
    if (normalized.size > MAX_FILE_BYTES) throw new SignatureActionError('La imagen normalizada supera 2 MiB.');
    return new Uint8Array(await normalized.arrayBuffer());
  } finally {
    original.fill(0);
    bitmap?.close();
  }
}

export default function SignatureSettingsPage() {
  const { user, csrfToken } = useAuth();
  const fileInput = useRef(null);
  const [envelope, setEnvelope] = useState(null);
  const [pageState, setPageState] = useState('loading');
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadPassword, setUploadPassword] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [unlockPassword, setUnlockPassword] = useState('');
  const [unlockFormOpen, setUnlockFormOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [previewUrl, setPreviewUrl] = useState('');

  useEffect(() => {
    let mounted = true;
    getSignature().then((value) => {
      if (!mounted) return;
      setEnvelope(value);
      setPageState('ready');
    }).catch((requestError) => {
      if (!mounted) return;
      if (requestError instanceof ApiError && requestError.status === 404) {
        setPageState('ready');
      } else {
        setError('No se pudo cargar el estado de tu firma. Inténtalo de nuevo.');
        setPageState('error');
      }
    });
    return () => {
      mounted = false;
      terminateSignatureWorker();
    };
  }, []);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const runBusy = async (operation) => {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await operation();
    } catch (operationError) {
      if (operationError instanceof ApiError && operationError.status === 401) {
        setError('La contraseña no coincide. La firma y la cuenta no se modificaron.');
      } else if (operationError instanceof ApiError && operationError.status === 409) {
        setError('La firma cambió en otra pestaña. Recarga la página e inténtalo de nuevo.');
      } else if (operationError instanceof SignatureActionError) {
        setError(operationError.message);
      } else {
        setError('No se pudo completar la operación. Comprueba tu conexión e inténtalo de nuevo.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSaveSignature = (event) => {
    event.preventDefault();
    runBusy(async () => {
      const normalized = await normalizePng(selectedFile);
      let encryptedEnvelope;
      try {
        try {
          encryptedEnvelope = await encryptInWorker(normalized, uploadPassword, user.id);
        } catch {
          throw new SignatureActionError('Este navegador no pudo cifrar la firma. Inténtalo de nuevo.');
        }
      } finally {
        normalized.fill(0);
      }
      const saved = await saveSignature(uploadPassword, encryptedEnvelope, csrfToken);
      setEnvelope(saved);
      setSelectedFile(null);
      setUploadPassword('');
      if (fileInput.current) fileInput.current.value = '';
      setMessage('La firma cifrada se guardó en tu cuenta.');
    });
  };

  const handlePasswordChange = (event) => {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setError('La confirmación no coincide con la nueva contraseña.');
      return;
    }
    if (newPassword.length < 12) {
      setError('La nueva contraseña debe tener al menos 12 caracteres.');
      return;
    }
    runBusy(async () => {
      let replacementEnvelope = null;
      if (envelope) {
        try {
          replacementEnvelope = await rewrapInWorker(envelope, currentPassword, newPassword, user.id);
        } catch {
          throw new SignatureActionError('No se pudo desbloquear la firma. Comprueba la contraseña; la cuenta no se modificó.');
        }
      }
      const changed = await changePassword(currentPassword, newPassword, envelope?.updated_at ?? null, replacementEnvelope, csrfToken);
      if (replacementEnvelope) {
        setEnvelope({ ...replacementEnvelope, user_id: user.id, updated_at: changed.envelope_updated_at });
      }
      setPreviewUrl('');
      setUnlockPassword('');
      setUnlockFormOpen(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setMessage('La contraseña se actualizó y las demás sesiones se cerraron.');
    });
  };

  const handlePreview = (event) => {
    event.preventDefault();
    runBusy(async () => {
      let imageBytes;
      try {
        imageBytes = await decryptInWorker(envelope, unlockPassword, user.id);
      } catch {
        setUnlockPassword('');
        throw new SignatureActionError('No se pudo desbloquear la firma. Comprueba la contraseña o reemplázala si se perdió su clave.');
      }
      let nextUrl;
      try {
        nextUrl = URL.createObjectURL(new Blob([imageBytes], { type: 'image/png' }));
      } finally {
        imageBytes.fill(0);
      }
      setPreviewUrl((previousUrl) => {
        if (previousUrl) URL.revokeObjectURL(previousUrl);
        return nextUrl;
      });
      setUnlockPassword('');
      setUnlockFormOpen(false);
    });
  };

  if (pageState === 'loading') return <p className="screen-status" role="status">Cargando la configuración de firma…</p>;

  return (
    <section className="signature-page" aria-labelledby="signature-title">
      <Link className="back-link" to="/documents">Cartas</Link>
      <h1 id="signature-title">Mi firma</h1>
      <p className="signature-page__intro">Tu firma se cifra en este navegador. El rol administrador no tiene acceso a tu firma cifrada.</p>
      {error && <p className="notice notice--error" role="alert">{error}</p>}
      {message && <p className="notice notice--success" role="status">{message}</p>}
      {pageState === 'error' && <button className="button-secondary" onClick={() => window.location.reload()} type="button">Volver a intentar</button>}

      {pageState === 'ready' && (
        <>
          <section className="signature-status" aria-labelledby="signature-status-title">
            <div>
              <h2 id="signature-status-title">Estado de la firma</h2>
              <p>{envelope ? 'Hay una firma cifrada guardada.' : 'Todavía no guardaste una firma.'}</p>
            </div>
            {envelope && (
              <div className="signature-card__actions">
                <button
                  className="button-secondary"
                  disabled={busy}
                  onClick={() => {
                    if (previewUrl) {
                      setPreviewUrl('');
                      setUnlockFormOpen(false);
                    } else {
                      setUnlockFormOpen((open) => !open);
                    }
                  }}
                  type="button"
                >
                  {previewUrl ? 'Bloquear vista previa' : unlockFormOpen ? 'Cancelar desbloqueo' : 'Desbloquear vista previa'}
                </button>
                {unlockFormOpen && !previewUrl && (
                  <form className="signature-unlock" onSubmit={handlePreview}>
                    <label htmlFor="signature-unlock-password">Contraseña de tu cuenta</label>
                    <input
                      autoComplete="current-password"
                      id="signature-unlock-password"
                      onChange={(event) => setUnlockPassword(event.target.value)}
                      required
                      type="password"
                      value={unlockPassword}
                    />
                    <button className="button-primary" disabled={busy} type="submit">{busy ? 'Desbloqueando…' : 'Mostrar firma'}</button>
                  </form>
                )}
                {previewUrl && (
                  <>
                    <img alt="Vista previa temporal de tu firma" className="signature-preview" src={previewUrl} />
                  </>
                )}
              </div>
            )}
          </section>

          <form className="signature-form" onSubmit={handleSaveSignature}>
            <h2>{envelope ? 'Reemplazar firma' : 'Guardar firma'}</h2>
            <p>Solo se aceptan PNG estáticos de hasta 2 MiB. La imagen se normaliza para quitar metadatos y luego se cifra localmente.</p>
            <p className="signature-form__field-label">Archivo PNG</p>
            <div className="signature-file-picker">
              <input
                accept="image/png"
                aria-label="Seleccionar archivo PNG"
                className="signature-file-picker__input"
                id="signature-file"
                onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                ref={fileInput}
                tabIndex={-1}
                type="file"
              />
              <button className="button-secondary" onClick={() => fileInput.current?.click()} type="button">
                Elegir archivo PNG
              </button>
              <span aria-live="polite">{selectedFile?.name || 'No se eligió ningún archivo.'}</span>
            </div>
            <label htmlFor="signature-upload-password">Contraseña de tu cuenta</label>
            <input autoComplete="current-password" id="signature-upload-password" onChange={(event) => setUploadPassword(event.target.value)} required type="password" value={uploadPassword} />
            <button className="button-primary" disabled={busy || !selectedFile} type="submit">{busy ? 'Procesando…' : 'Cifrar y guardar'}</button>
          </form>

          <form className="signature-form" onSubmit={handlePasswordChange}>
            <h2>Cambiar contraseña</h2>
            <p>Si hay una firma guardada, se desbloquea y se vuelve a cifrar en este navegador antes de cambiar la contraseña. Sin la contraseña actual no se puede conservar la firma.</p>
            <label htmlFor="current-password">Contraseña actual</label>
            <input autoComplete="current-password" id="current-password" onChange={(event) => setCurrentPassword(event.target.value)} required type="password" value={currentPassword} />
            <label htmlFor="new-password">Nueva contraseña</label>
            <input autoComplete="new-password" id="new-password" minLength={12} onChange={(event) => setNewPassword(event.target.value)} required type="password" value={newPassword} />
            <label htmlFor="confirm-password">Confirmar nueva contraseña</label>
            <input autoComplete="new-password" id="confirm-password" minLength={12} onChange={(event) => setConfirmPassword(event.target.value)} required type="password" value={confirmPassword} />
            <button className="button-primary" disabled={busy} type="submit">{busy ? 'Procesando…' : 'Cambiar contraseña'}</button>
          </form>

          <aside className="signature-warning" aria-label="Información importante sobre privacidad">
            <h2>Recuperación y privacidad</h2>
            <p>Si olvidas la contraseña, la firma cifrada no se puede recuperar; después de recuperar la cuenta tendrás que subir otra. Al insertar una firma en un PDF, cualquier persona con acceso a ese PDF puede verla o extraerla. Esto no equivale a una firma legal ni protege contra un servidor comprometido.</p>
          </aside>
        </>
      )}
    </section>
  );
}
