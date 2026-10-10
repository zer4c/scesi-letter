import { useEffect, useId, useRef, useState } from 'react';
import { ApiError } from '../../../core/api.js';
import { createContact, getContact, searchContacts, updateContact } from '../services/contacts.js';
import './RecipientContactFields.css';

const blankContact = (value) => ({
  name: value.name || '',
  role_label: value.role || '',
  institution: value.institution || '',
  career: value.career || '',
  email: value.email || '',
});

const toLetterFields = (contact) => ({
  name: contact.name,
  role: contact.role_label,
  institution: contact.institution,
  career: contact.career || '',
  email: contact.emails?.[0] || '',
});

const roleKey = (label) => label.normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '_')
  .replace(/^_|_$/g, '')
  .slice(0, 80);

export default function RecipientContactFields({ value, onChange, csrfToken }) {
  const listId = useId();
  const inputRef = useRef(null);
  const requestSequence = useRef(0);
  const [matches, setMatches] = useState([]);
  const [selectedContact, setSelectedContact] = useState(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [editingContact, setEditingContact] = useState(false);
  const [contactDraft, setContactDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const [status, setStatus] = useState('');
  const actionButtonRef = useRef(null);

  useEffect(() => {
    const query = value.name?.trim() || '';
    if (query.length < 2 || selectedContact?.name === query) {
      setMatches([]);
      setSearching(false);
      return undefined;
    }
    let active = true;
    const sequence = ++requestSequence.current;
    setSearching(true);
    setSearchError('');
    const timer = window.setTimeout(() => {
      searchContacts(query)
        .then((page) => {
          if (active && requestSequence.current === sequence) {
            setMatches(page.items);
            setActiveIndex(-1);
            setSearching(false);
          }
        })
        .catch(() => {
          if (active && requestSequence.current === sequence) {
            setMatches([]);
            setSearching(false);
            setSearchError('No se pudo buscar en los contactos. Puedes continuar con los datos escritos.');
          }
        });
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [value.name, selectedContact]);

  const chooseContact = (contact) => {
    setSelectedContact(contact);
    setMatches([]);
    setActiveIndex(-1);
    setEditingContact(false);
    setError('');
    setConflict(false);
    setStatus('Se completaron los datos del destinatario. La carta aún no se ha guardado.');
    onChange(toLetterFields(contact));
  };

  const updateDraft = (key) => (event) => {
    setContactDraft((current) => ({ ...current, [key]: event.target.value }));
  };

  const saveContact = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setStatus('');
    const emails = contactDraft.email.trim() ? [contactDraft.email.trim()] : [];
    const role_key = roleKey(contactDraft.role_label);
    if (!role_key) {
      setError('Escribe un cargo válido antes de guardar el contacto.');
      setBusy(false);
      return;
    }
    const payload = {
      name: contactDraft.name,
      role_key,
      role_label: contactDraft.role_label,
      institution: contactDraft.institution,
      career: contactDraft.career || null,
      emails,
      active: true,
    };
    try {
      const saved = selectedContact
        ? await updateContact(selectedContact.id, { ...payload, expected_revision: selectedContact.revision }, csrfToken)
        : await createContact(payload, csrfToken);
      setSelectedContact(saved);
      setContactDraft(null);
      setEditingContact(false);
      setStatus(selectedContact ? 'Contacto actualizado. Los datos de esta carta no se modificaron.' : 'Contacto guardado en el directorio. Los datos de esta carta no se modificaron.');
      window.requestAnimationFrame(() => actionButtonRef.current?.focus());
    } catch (saveError) {
      const isConflict = saveError instanceof ApiError && saveError.status === 409;
      setConflict(isConflict);
      setError(isConflict
        ? 'El contacto cambió en otra sesión. Carga la versión actual y revisa tus cambios antes de guardar.'
        : 'No se pudo guardar el contacto. Revisa los campos e inténtalo de nuevo.');
    } finally {
      setBusy(false);
    }
  };

  const beginEditing = () => {
    setContactDraft(blankContact(value));
    setEditingContact(true);
    setError('');
    setStatus('');
  };

  const cancelEditing = () => {
    setEditingContact(false);
    setError('');
    window.requestAnimationFrame(() => actionButtonRef.current?.focus());
  };

  const reloadContact = async () => {
    if (!selectedContact) return;
    setBusy(true);
    setError('');
    try {
      setSelectedContact(await getContact(selectedContact.id));
      setConflict(false);
      setStatus('Versión actual cargada. Revisa el formulario; tus cambios siguen ahí.');
    } catch {
      setError('No se pudo cargar la versión actual del contacto. Inténtalo de nuevo.');
    } finally {
      setBusy(false);
    }
  };

  const handleNameKeyDown = (event) => {
    if (event.key === 'ArrowDown' && matches.length) {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % matches.length);
    } else if (event.key === 'ArrowUp' && matches.length) {
      event.preventDefault();
      setActiveIndex((current) => (current <= 0 ? matches.length - 1 : current - 1));
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault();
      chooseContact(matches[activeIndex]);
    } else if (event.key === 'Escape' && matches.length) {
      setMatches([]);
      setActiveIndex(-1);
    }
  };

  return (
    <fieldset className="editor-fields__group recipient-contact-fields">
      <legend>Destinatario</legend>
      <div className="recipient-contact-fields__name">
        <label className="editor-field" htmlFor={`${listId}-name`}>
          <span>Nombre</span>
          <input
            aria-autocomplete="list"
            aria-controls={listId}
            aria-expanded={matches.length > 0}
            aria-activedescendant={activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
            autoComplete="off"
            id={`${listId}-name`}
            maxLength="160"
            onChange={(event) => {
              setSelectedContact(null);
              setStatus('');
              onChange({ ...value, name: event.target.value });
            }}
            onKeyDown={handleNameKeyDown}
            ref={inputRef}
            role="combobox"
            value={value.name || ''}
          />
        </label>
        {matches.length > 0 && (
          <ul className="recipient-contact-fields__results" id={listId} role="listbox" aria-label="Contactos coincidentes">
            {matches.map((contact, index) => (
              <li key={contact.id} role="presentation">
                <button aria-selected={index === activeIndex} id={`${listId}-${index}`} onMouseDown={(event) => event.preventDefault()} onClick={() => chooseContact(contact)} role="option" type="button">
                  <strong>{contact.name}</strong>
                  <span>{contact.role_label} · {contact.institution}{contact.career ? ` · ${contact.career}` : ''}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <label className="editor-field"><span>Cargo</span><input maxLength="120" onChange={(event) => { setSelectedContact(null); onChange({ ...value, role: event.target.value }); }} value={value.role || ''} /></label>
      <label className="editor-field"><span>Institución</span><input maxLength="160" onChange={(event) => { setSelectedContact(null); onChange({ ...value, institution: event.target.value }); }} value={value.institution || ''} /></label>
      <label className="editor-field"><span>Carrera</span><input maxLength="120" onChange={(event) => { setSelectedContact(null); onChange({ ...value, career: event.target.value }); }} value={value.career || ''} /></label>
      <label className="editor-field"><span>Correo electrónico</span><input autoComplete="off" maxLength="254" onChange={(event) => { setSelectedContact(null); onChange({ ...value, email: event.target.value }); }} type="email" value={value.email || ''} /></label>
      {searching && <p className="recipient-contact-fields__status" role="status">Buscando contactos…</p>}
      {searchError && <p className="recipient-contact-fields__error" role="status">{searchError}</p>}
      <div className="recipient-contact-fields__actions">
        <button className="button-quiet" disabled={busy} onClick={beginEditing} ref={actionButtonRef} type="button">
          {selectedContact && <svg aria-hidden="true" className="recipient-contact-fields__pencil" viewBox="0 0 16 16" fill="currentColor"><path d="M12.854.146a.5.5 0 0 1 .707 0l2.293 2.293a.5.5 0 0 1 0 .707l-9.5 9.5a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168zM11.207 2.5 13.5 4.793l1.293-1.293L12.5 1.207zM12.793 5.5 10.5 3.207l-7.55 7.55-.1.1-.95 2.373 2.373-.95.1-.1z" /></svg>}
          {selectedContact ? 'Editar contacto' : 'Guardar como contacto'}
        </button>
      </div>
      {editingContact && (
        <form className="recipient-contact-fields__form" onSubmit={saveContact}>
          <p>{selectedContact ? 'Actualiza el directorio. La carta no se modifica con este guardado.' : 'Este contacto se añadirá al directorio; los datos de la carta se guardan aparte.'}</p>
          <label className="editor-field"><span>Nombre del contacto</span><input autoFocus maxLength="160" onChange={updateDraft('name')} required value={contactDraft.name} /></label>
          <label className="editor-field"><span>Cargo</span><input maxLength="120" onChange={updateDraft('role_label')} required value={contactDraft.role_label} /></label>
          <label className="editor-field"><span>Institución</span><input maxLength="160" onChange={updateDraft('institution')} required value={contactDraft.institution} /></label>
          <label className="editor-field"><span>Carrera, si corresponde</span><input maxLength="120" onChange={updateDraft('career')} value={contactDraft.career} /></label>
          <label className="editor-field"><span>Correo electrónico, si corresponde</span><input maxLength="254" onChange={updateDraft('email')} type="email" value={contactDraft.email} /></label>
          {error && <p className="recipient-contact-fields__error" role="alert">{error}</p>}
          {conflict && <button className="button-quiet" disabled={busy} onClick={reloadContact} type="button">{busy ? 'Cargando…' : 'Cargar versión actual'}</button>}
          <div className="recipient-contact-fields__actions">
            <button className="button-primary" disabled={busy} type="submit">{busy ? 'Guardando…' : 'Guardar contacto'}</button>
            <button className="button-quiet" disabled={busy} onClick={cancelEditing} type="button">Cancelar</button>
          </div>
        </form>
      )}
      {error && !editingContact && <p className="recipient-contact-fields__error" role="alert">{error}</p>}
      {status && <p className="recipient-contact-fields__status" role="status">{status}</p>}
    </fieldset>
  );
}
