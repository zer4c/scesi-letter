import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  createGoogleAuthorization,
  createOrganizationInvitation,
  disconnectGoogleIntegration,
  getOrganizationTemplate,
  listConnections,
  listOrganizationInvitations,
  listOrganizationUsers,
  revokeOrganizationInvitation,
  setInstitutionalDriveRoot,
  updateOrganizationTemplate,
  updateOrganizationUser,
} from '../../core/api.js';
import { useAuth } from './AuthProvider.jsx';
import './OrganizationAccessPage.css';

const invitationStates = {
  pending: 'Pendiente', redeemed: 'Aceptada', revoked: 'Revocada', expired: 'Vencida',
};

function messageFor(error) {
  if (error?.status === 403) return 'Tu sesión ya no tiene permisos de administración.';
  if (error?.status === 409) return 'La configuración cambió o la operación ya no está disponible. Actualiza la página e inténtalo de nuevo.';
  if (error?.status === 422 || error?.status === 400) return 'Revisa los datos ingresados.';
  if (error?.status === 503) return 'El servicio de configuración no está disponible. Inténtalo más tarde.';
  return 'No se pudo completar la operación. Comprueba la conexión e inténtalo de nuevo.';
}

function formatDate(value) {
  return new Intl.DateTimeFormat('es-BO', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

export default function OrganizationAccessPage() {
  const { csrfToken, user, restore } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [userPage, setUserPage] = useState(1);
  const [userTotal, setUserTotal] = useState(0);
  const [invitations, setInvitations] = useState([]);
  const [template, setTemplate] = useState(null);
  const [connections, setConnections] = useState([]);
  const [driveRoots, setDriveRoots] = useState({});
  const [inviteEmail, setInviteEmail] = useState('');
  const [createdInvitation, setCreatedInvitation] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [templateBusy, setTemplateBusy] = useState(false);

  const loadOrganization = useCallback(async (page = userPage) => {
    setLoading(true);
    setError('');
    const results = await Promise.allSettled([
      listOrganizationUsers(page),
      listOrganizationInvitations(),
      getOrganizationTemplate(),
      listConnections(),
    ]);
    const [userResult, invitationResult, templateResult, connectionResult] = results;
    if (userResult.status === 'fulfilled') {
      setUsers(userResult.value.items);
      setUserTotal(userResult.value.total);
    }
    if (invitationResult.status === 'fulfilled') setInvitations(invitationResult.value);
    if (templateResult.status === 'fulfilled') setTemplate(templateResult.value);
    if (connectionResult.status === 'fulfilled') setConnections(connectionResult.value.connections);
    if (results.some((result) => result.status === 'rejected')) {
      setError('Algunas secciones no pudieron cargarse. Puedes volver a intentar actualizar la página.');
    }
    setLoading(false);
  }, [userPage]);

  useEffect(() => { loadOrganization(); }, [loadOrganization]);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const connectionResult = query.get('connection');
    if (!connectionResult) return;
    setNotice(connectionResult === 'connected'
      ? 'Cuenta institucional conectada. Revisa su estado y configura la carpeta de Drive si corresponde.'
      : 'No se otorgó acceso a Google. Puedes volver a intentarlo cuando quieras.');
    window.history.replaceState({}, '', window.location.pathname);
  }, []);

  const runAction = async (action, successMessage, afterSuccess) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const value = await action();
      if (afterSuccess) await afterSuccess(value);
      if (successMessage) setNotice(successMessage);
    } catch (actionError) {
      setError(messageFor(actionError));
    } finally {
      setBusy(false);
    }
  };

  const handleInvite = async (event) => {
    event.preventDefault();
    setCreatedInvitation(null);
    await runAction(
      () => createOrganizationInvitation(inviteEmail, csrfToken),
      'Invitación creada. Comparte el enlace con la persona indicada; no se envió un correo.',
      async (invitation) => {
        setCreatedInvitation(invitation);
        setInviteEmail('');
        setInvitations(await listOrganizationInvitations());
      },
    );
  };

  const handleCopyInvitation = async () => {
    try {
      await navigator.clipboard.writeText(createdInvitation.invitation_url);
      setNotice('Enlace copiado. Compártelo únicamente con la persona invitada.');
    } catch {
      setError('No se pudo copiar automáticamente. Selecciona y copia el enlace mostrado.');
    }
  };

  const handleMemberUpdate = async (member, update) => {
    if (update.role === 'admin' && !window.confirm(`Transferir la administración a ${member.display_name}? Tu cuenta pasará a ser de usuario en la misma operación.`)) return;
    if (update.active === false && !window.confirm(`Suspender el acceso de ${member.display_name}? Sus sesiones activas se cerrarán.`)) return;
    await runAction(
      () => updateOrganizationUser(member.id, { expected_revision: member.revision, ...update }, csrfToken),
      'Acceso actualizado.',
      async () => {
        await loadOrganization();
        if (update.role === 'admin') {
          const authenticated = await restore();
          if (authenticated && user?.id === member.id) navigate('/documents', { replace: true });
        }
      },
    );
  };

  const handleTemplateSave = async (event) => {
    event.preventDefault();
    setTemplateBusy(true);
    setError('');
    setNotice('');
    const settings = {
      ...template.settings,
      footer_phones: template.settings.footer_phones_text
        .split(',').map((phone) => phone.trim()).filter(Boolean),
    };
    delete settings.footer_phones_text;
    try {
      const updated = await updateOrganizationTemplate({
        expected_revision: template.revision,
        settings,
      }, csrfToken);
      setTemplate(updated);
      setNotice(`Plantilla actualizada a la revisión ${updated.revision}. Los PDF existentes no cambian.`);
    } catch (saveError) {
      setError(messageFor(saveError));
    } finally {
      setTemplateBusy(false);
    }
  };

  const handleGoogleConnect = async (kind) => {
    setBusy(true);
    setError('');
    try {
      const authorization = await createGoogleAuthorization(kind, 'institutional', csrfToken);
      window.location.assign(authorization.authorization_url);
    } catch (connectError) {
      setError(messageFor(connectError));
      setBusy(false);
    }
  };

  const handleDriveRoot = async (connection) => {
    const folderId = driveRoots[connection.id] ?? connection.root_folder_id ?? '';
    if (!folderId.trim()) {
      setError('Ingresa el identificador de una carpeta de Drive.');
      return;
    }
    await runAction(
      () => setInstitutionalDriveRoot(connection.id, folderId.trim(), csrfToken),
      'Carpeta institucional verificada y guardada.',
      () => loadOrganization(),
    );
  };

  const handleDisconnect = async (connection) => {
    if (!window.confirm(`Desconectar ${connection.google_account}? Los documentos ya archivados permanecerán en Drive.`)) return;
    await runAction(
      () => disconnectGoogleIntegration(connection.id, csrfToken),
      'Cuenta desconectada. Los archivos existentes no se eliminaron.',
      () => loadOrganization(),
    );
  };

  const updateTemplateField = (key, value) => {
    setTemplate((current) => ({
      ...current,
      settings: { ...current.settings, [key]: value },
    }));
  };

  const institutionalConnections = connections.filter((connection) => connection.mode === 'institutional');
  const memberPages = Math.max(1, Math.ceil(userTotal / 25));

  return (
    <section className="document-page organization-page" aria-labelledby="organization-title">
      <header className="page-heading">
        <div>
          <h1 id="organization-title">Organización</h1>
          <p className="page-heading__intro">Administra el acceso, los datos de la plantilla y las cuentas institucionales.</p>
        </div>
        <button className="button-quiet" disabled={loading || busy} onClick={() => loadOrganization()} type="button">Actualizar</button>
      </header>

      {notice && <p className="organization-notice organization-notice--success" role="status">{notice}</p>}
      {error && <p className="organization-notice organization-notice--error" role="alert">{error}</p>}
      {loading ? <p className="inline-status" role="status">Cargando configuración de la organización…</p> : (
        <div className="organization-sections">
          <section className="organization-section" aria-labelledby="members-title">
            <div className="organization-section__heading"><div><h2 id="members-title">Miembros</h2><p>Invita a personas y administra su acceso. Solo puede haber un administrador activo.</p></div></div>
            <form className="organization-invite" onSubmit={handleInvite}>
              <label className="editor-field" htmlFor="invite-email"><span>Correo de la persona</span><input autoComplete="email" id="invite-email" maxLength="254" onChange={(event) => setInviteEmail(event.target.value)} required type="email" value={inviteEmail} /></label>
              <button className="button-primary" disabled={busy} type="submit">{busy ? 'Creando…' : 'Crear invitación'}</button>
            </form>
            {createdInvitation && <div className="organization-invitation-link"><p>Enlace para {createdInvitation.email}; vence {formatDate(createdInvitation.expires_at)}.</p><label className="editor-field" htmlFor="invitation-url"><span>Enlace de invitación</span><input id="invitation-url" onFocus={(event) => event.target.select()} readOnly value={createdInvitation.invitation_url} /></label><button className="button-quiet" onClick={handleCopyInvitation} type="button">Copiar enlace</button></div>}

            <h3 className="organization-subheading">Acceso activo</h3>
            {users.length === 0 ? <p className="inline-status">No hay miembros en esta página.</p> : <div className="organization-table-wrap"><table className="organization-table"><thead><tr><th scope="col">Persona</th><th scope="col">Rol</th><th scope="col">Estado</th><th scope="col">Acciones</th></tr></thead><tbody>
              {users.map((member) => <tr key={member.id}><th className="organization-table__identity" scope="row"><span>{member.display_name}</span><span>{member.email}</span></th><td>{member.role === 'admin' ? 'Administrador' : 'Usuario'}</td><td>{member.active ? 'Activo' : 'Suspendido'}</td><td className="organization-table__actions">
                {member.role !== 'admin' && member.active && <button className="button-quiet" disabled={busy} onClick={() => handleMemberUpdate(member, { role: 'admin' })} type="button">Transferir administración</button>}
                {member.id !== user?.id && <button className="button-quiet" disabled={busy} onClick={() => handleMemberUpdate(member, { active: !member.active })} type="button">{member.active ? 'Suspender' : 'Reactivar'}</button>}
              </td></tr>)}
            </tbody></table></div>}
            {memberPages > 1 && <div className="organization-pagination"><button className="button-quiet" disabled={userPage <= 1 || busy} onClick={() => setUserPage((page) => page - 1)} type="button">Anterior</button><span>Página {userPage} de {memberPages}</span><button className="button-quiet" disabled={userPage >= memberPages || busy} onClick={() => setUserPage((page) => page + 1)} type="button">Siguiente</button></div>}

            <h3 className="organization-subheading">Invitaciones</h3>
            {invitations.length === 0 ? <p className="inline-status">Todavía no hay invitaciones.</p> : <ul className="organization-invitations">{invitations.map((invitation) => <li key={invitation.id}><div><strong>{invitation.email}</strong><span>{invitationStates[invitation.status]} · vence {formatDate(invitation.expires_at)}</span></div>{invitation.status === 'pending' && <button className="button-quiet" disabled={busy} onClick={() => runAction(() => revokeOrganizationInvitation(invitation.id, csrfToken), 'Invitación revocada.', () => loadOrganization())} type="button">Revocar</button>}</li>)}</ul>}
          </section>

          <section className="organization-section" aria-labelledby="template-title">
            <div className="organization-section__heading"><div><h2 id="template-title">Plantilla predeterminada</h2><p>Estos datos se aplican a los documentos nuevos. Cada cambio crea una revisión y no altera PDF anteriores.</p></div>{template && <span className="organization-revision">Revisión {template.revision}</span>}</div>
            {template && <form className="organization-template" onSubmit={handleTemplateSave}>
              <label className="editor-field" htmlFor="template-organization"><span>Nombre de la organización</span><input id="template-organization" maxLength="160" onChange={(event) => updateTemplateField('organization_name', event.target.value)} required value={template.settings.organization_name} /></label>
              <label className="editor-field" htmlFor="template-university"><span>Universidad</span><input id="template-university" maxLength="160" onChange={(event) => updateTemplateField('university_name', event.target.value)} required value={template.settings.university_name} /></label>
              <label className="editor-field" htmlFor="template-faculty"><span>Facultad</span><input id="template-faculty" maxLength="160" onChange={(event) => updateTemplateField('faculty_name', event.target.value)} required value={template.settings.faculty_name} /></label>
              <label className="editor-field" htmlFor="template-phones"><span>Teléfonos del pie de página</span><input id="template-phones" maxLength="124" onChange={(event) => updateTemplateField('footer_phones_text', event.target.value)} placeholder="Separar números con comas" value={template.settings.footer_phones_text ?? template.settings.footer_phones.join(', ')} /><span className="organization-field-hint">Hasta cinco números. Se guardan en la siguiente revisión de plantilla.</span></label>
              <label className="editor-field" htmlFor="template-url"><span>URL institucional</span><input id="template-url" maxLength="2000" onChange={(event) => updateTemplateField('footer_url', event.target.value)} required type="url" value={template.settings.footer_url} /></label>
              <label className="editor-field" htmlFor="template-qr"><span>Destino del código QR</span><input id="template-qr" maxLength="2000" onChange={(event) => updateTemplateField('qr_destination', event.target.value)} required type="url" value={template.settings.qr_destination} /></label>
              <label className="editor-field" htmlFor="template-email"><span>Correo institucional del pie de página</span><input id="template-email" maxLength="254" onChange={(event) => updateTemplateField('footer_email', event.target.value)} required type="email" value={template.settings.footer_email} /></label>
              <label className="editor-field" htmlFor="template-address"><span>Dirección institucional</span><input id="template-address" maxLength="240" onChange={(event) => updateTemplateField('footer_address', event.target.value)} required value={template.settings.footer_address} /></label>
              <button className="button-primary" disabled={templateBusy} type="submit">{templateBusy ? 'Guardando…' : 'Guardar nueva revisión'}</button>
            </form>}
          </section>

          <section className="organization-section" aria-labelledby="connections-title">
            <div className="organization-section__heading"><div><h2 id="connections-title">Cuentas institucionales</h2><p>Conecta cuentas de Gmail y Drive. El acceso se concede en Google y puede revocarse aquí.</p></div></div>
            <div className="organization-connect-actions"><button className="button-quiet" disabled={busy} onClick={() => handleGoogleConnect('gmail')} type="button">Conectar Gmail institucional</button><button className="button-quiet" disabled={busy} onClick={() => handleGoogleConnect('drive')} type="button">Conectar Drive institucional</button></div>
            {institutionalConnections.length === 0 ? <p className="inline-status">No hay cuentas institucionales conectadas.</p> : <ul className="organization-connections">{institutionalConnections.map((connection) => <li key={connection.id}><div className="organization-connection__summary"><strong>{connection.kind === 'gmail' ? 'Gmail' : 'Google Drive'}</strong><span>{connection.google_account}</span><span className={connection.status === 'active' ? 'organization-state organization-state--active' : 'organization-state organization-state--warning'}>{connection.status === 'active' ? 'Conectada' : 'Requiere reconexión'}</span><span>Permisos: {connection.scopes.filter((scope) => scope.includes('gmail.send') || scope.includes('drive.file')).join(', ') || 'Sin permisos de servicio'}</span></div>
              {connection.kind === 'drive' && <div className="organization-drive-root"><label className="editor-field" htmlFor={`drive-root-${connection.id}`}><span>Identificador de carpeta raíz</span><input id={`drive-root-${connection.id}`} maxLength="256" onChange={(event) => setDriveRoots((current) => ({ ...current, [connection.id]: event.target.value }))} placeholder="ID de carpeta de Google Drive" value={driveRoots[connection.id] ?? connection.root_folder_id ?? ''} /></label><button className="button-quiet" disabled={busy || connection.status !== 'active'} onClick={() => handleDriveRoot(connection)} type="button">Verificar y guardar carpeta</button></div>}
              <button className="button-quiet organization-disconnect" disabled={busy} onClick={() => handleDisconnect(connection)} type="button">Desconectar</button>
            </li>)}</ul>}
            <p className="organization-field-hint">La cuenta personal de Gmail de cada usuario se administra desde su propio flujo de conexión. El administrador no puede ver ni modificar firmas personales.</p>
          </section>
        </div>
      )}
    </section>
  );
}
