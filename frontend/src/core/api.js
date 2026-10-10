async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
  return response.json();
}

export function listAutomations() {
  return request('/api/automations');
}

export function createAutomation(payload) {
  return request('/api/automations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function runAutomation(id) {
  return request(`/api/automations/${id}/run`, { method: 'POST' });
}
