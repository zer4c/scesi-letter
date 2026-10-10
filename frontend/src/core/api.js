export class ApiError extends Error {
  constructor(status, code, message) {
    super(message || code || 'Request failed');
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

async function request(path, options = {}) {
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
      payload?.error?.code,
      payload?.error?.message,
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

export function listAutomations() {
  return request('/api/automations');
}

export function createAutomation(payload) {
  return request('/api/automations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function runAutomation(id) {
  return request(`/api/automations/${id}/run`, { method: 'POST' });
}
