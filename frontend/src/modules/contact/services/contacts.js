import { createGoogleAuthorization, request } from '../../../core/api.js';

export function searchContacts(query) {
  const params = new URLSearchParams({ q: query, page: '1', page_size: '8' });
  return request(`/api/contacts?${params}`);
}

export function createContact(payload, csrfToken) {
  return request('/api/contacts', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(payload),
  });
}

export function getContact(contactId) {
  return request(`/api/contacts/${contactId}`);
}

export function updateContact(contactId, payload, csrfToken) {
  return request(`/api/contacts/${contactId}`, {
    method: 'PATCH',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(payload),
  });
}

export { createGoogleAuthorization };

export function previewGoogleOtherContacts(connectionId, pageToken) {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (pageToken) params.set('page_token', pageToken);
  return request(`/api/contacts/google/other-contacts?${params}`);
}

export function importGoogleOtherContacts(contacts, csrfToken) {
  return request('/api/contacts/google/other-contacts/import', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ confirmed: true, contacts }),
  });
}

export function listGoogleConnections() {
  return request('/api/integrations');
}
