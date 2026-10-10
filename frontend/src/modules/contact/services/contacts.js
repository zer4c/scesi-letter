import { request } from '../../../core/api.js';

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
