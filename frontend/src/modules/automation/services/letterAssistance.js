import { request } from '../../../core/api.js';

export function createPrivacyPreview(documentId, sourceHash, kinds, manualRedactions, csrfToken) {
  return request(`/api/documents/${documentId}/analyze/preview`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({
      expected_source_hash: sourceHash,
      kinds,
      manual_redactions: manualRedactions,
    }),
  });
}

export function analyzeLetter(documentId, sourceHash, kinds, previewToken, manualRedactions, csrfToken) {
  return request(`/api/documents/${documentId}/analyze`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({
      expected_source_hash: sourceHash,
      kinds,
      preview_token: previewToken,
      manual_redactions: manualRedactions,
    }),
  });
}

export function listLetterSuggestions(documentId, sourceHash) {
  const query = new URLSearchParams({ source_hash: sourceHash });
  return request(`/api/documents/${documentId}/suggestions?${query}`);
}

export function acceptLetterSuggestion(documentId, suggestionId, sourceHash, csrfToken, contactId = null) {
  return request(`/api/documents/${documentId}/suggestions/${suggestionId}/accept`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ expected_source_hash: sourceHash, contact_id: contactId }),
  });
}

export function rejectLetterSuggestion(documentId, suggestionId, csrfToken) {
  return request(`/api/documents/${documentId}/suggestions/${suggestionId}/reject`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
  });
}

export function findContactsByRole(roleKey) {
  const query = new URLSearchParams({ role: roleKey, page_size: '20' });
  return request(`/api/contacts?${query}`);
}
