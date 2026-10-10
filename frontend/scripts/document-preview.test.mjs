import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { renderDocumentPreview } from '../src/core/api.js';

const originalFetch = globalThis.fetch;
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

afterEach(() => {
  globalThis.fetch = originalFetch;
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
});

test('sends CSRF token when requesting a PDF preview', async () => {
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return new Response(new Blob(['%PDF-test']), {
      status: 200,
      headers: { 'Content-Type': 'application/pdf' },
    });
  };
  URL.createObjectURL = () => 'blob:preview';
  URL.revokeObjectURL = () => {};

  const previewUrl = await renderDocumentPreview('---\n{}\n---\n', 'csrf-test-token');

  assert.equal(previewUrl, 'blob:preview');
  assert.equal(request.url, '/api/documents/preview');
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['X-CSRF-Token'], 'csrf-test-token');
});
