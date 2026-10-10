import { decryptSignatureImage, encryptSignatureImage, rewrapSignatureKey } from './signatureEnvelope.js';

self.onmessage = async ({ data }) => {
  try {
    const result = data.operation === 'encrypt'
      ? await encryptSignatureImage(new Uint8Array(data.imageBytes), data.password, data.userId)
      : data.operation === 'decrypt'
        ? await decryptSignatureImage(data.envelope, data.password, data.userId)
        : await rewrapSignatureKey(data.envelope, data.password, data.newPassword, data.userId);
    self.postMessage({ id: data.id, result }, result instanceof Uint8Array ? [result.buffer] : []);
  } catch (error) {
    self.postMessage({ id: data.id, error: error instanceof Error ? error.message : 'Signature operation failed' });
  }
};
