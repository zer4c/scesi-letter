export class ApiError extends Error {
  constructor(status, code, message) {
    super(message || code || 'Request failed');
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });

  if (response.status === 204) return null;

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : null;

  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error?.code || payload?.detail,
      payload?.error?.message || payload?.message,
    );
  }

  return payload;
}

export const getSession = () => request('/api/auth/session');

export const logIn = (email, password) => request('/api/auth/login', {
  method: 'POST',
  body: JSON.stringify({ email, password }),
});

export const logOut = (csrfToken) => request('/api/auth/logout', {
  method: 'POST',
  headers: { 'X-CSRF-Token': csrfToken },
});

export const redeemInvitation = (token, displayName, password) => request(
  '/api/auth/invitations/redeem',
  {
    method: 'POST',
    body: JSON.stringify({ token, display_name: displayName, password }),
  },
);

export const listDocuments = () => request('/api/documents?page=1&page_size=25');
export const listEvents = (year) => request(`/api/events?year=${encodeURIComponent(year)}`);
export const getEvent = (id) => request(`/api/events/${id}`);

export const getSignature = () => request('/api/signature');

export const saveSignature = (password, envelope, csrfToken) => request('/api/signature', {
  method: 'PUT',
  headers: { 'X-CSRF-Token': csrfToken },
  body: JSON.stringify({ password, envelope }),
});

export const changePassword = (currentPassword, newPassword, expectedEnvelopeUpdatedAt, replacementEnvelope, csrfToken) => request(
  '/api/auth/password/change',
  {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
      expected_envelope_updated_at: expectedEnvelopeUpdatedAt,
      replacement_envelope: replacementEnvelope,
    }),
  },
);

export const createEvent = (payload, csrfToken) => request('/api/events', {
  method: 'POST',
  headers: { 'X-CSRF-Token': csrfToken },
  body: JSON.stringify(payload),
});

export const getDocument = (id) => request(`/api/documents/${id}`);

export const createDocument = (payload, csrfToken) => request('/api/documents', {
  method: 'POST',
  headers: { 'X-CSRF-Token': csrfToken },
  body: JSON.stringify(payload),
});

export const saveDocument = (id, payload, csrfToken) => request(`/api/documents/${id}/save`, {
  method: 'POST',
  headers: { 'X-CSRF-Token': csrfToken },
  body: JSON.stringify(payload),
});

export const checkpointDocument = (id, csrfToken) => request(`/api/documents/${id}/checkpoint`, {
  method: 'POST',
  headers: { 'X-CSRF-Token': csrfToken },
});

export async function renderDocumentPreview(markdown) {
  const response = await fetch('/api/documents/preview', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ markdown }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(response.status, payload?.error?.code || payload?.detail);
  }
  return URL.createObjectURL(await response.blob());
}
